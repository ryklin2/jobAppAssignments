"""Tests for DataTransferManager: lifecycle, termination, failures."""

import threading
import time
from collections.abc import Callable

import pytest

from producer_consumer.containers import DestinationContainer, SourceContainer
from producer_consumer.exceptions import (
    TransferFailedError,
    TransferStateError,
    TransferTimeoutError,
)
from producer_consumer.item import Item
from producer_consumer.manager import DataTransferManager
from producer_consumer.status import TransferState

TIMING_SLACK = 5.0
POLL = 0.05


def worker_threads() -> list[threading.Thread]:
    """Every live producer/consumer thread, whichever manager created it."""
    return [
        thread
        for thread in threading.enumerate()
        if thread.name.startswith(("producer-", "consumer-"))
    ]


class FailingDestination(DestinationContainer):
    """A destination that raises on the Nth delivery."""

    def __init__(self, fail_after: int = 0) -> None:
        super().__init__()
        self._fail_after = fail_after
        self._seen = 0
        self._guard = threading.Lock()

    def add(self, item: Item) -> None:
        with self._guard:
            self._seen += 1
            should_fail = self._seen > self._fail_after
        if should_fail:
            raise RuntimeError("destination exploded")
        super().add(item)


@pytest.mark.parametrize(
    ("num_producers", "num_consumers"), [(1, 1), (3, 2), (2, 5)]
)
def test_complete_transfer_delivers_every_item_exactly_once(
    make_items: Callable[[int], list[Item]],
    num_producers: int,
    num_consumers: int,
) -> None:
    """Destination ids == source ids, no duplicates, state COMPLETED."""
    items = make_items(60)
    source = SourceContainer(items)
    destination = DestinationContainer()
    manager = DataTransferManager(
        source,
        destination,
        num_producers=num_producers,
        num_consumers=num_consumers,
        poll_interval=POLL,
    )

    manager.start_transfer()
    result = manager.wait_for_completion(timeout=TIMING_SLACK * 4)

    assert result.state is TransferState.COMPLETED
    assert result.succeeded
    assert result.delivered == len(items) == result.total_items
    assert result.undelivered == 0
    assert destination.ids() == {item.id for item in items}
    # Equal lengths prove nothing was delivered twice.
    assert len(destination.snapshot()) == len(destination.ids()) == len(items)
    assert source.remaining == 0
    assert not worker_threads(), "a worker thread outlived the transfer"


def test_empty_source_completes_immediately() -> None:
    """Zero items: wait_for_completion returns COMPLETED with nothing delivered."""
    destination = DestinationContainer()
    manager = DataTransferManager(
        SourceContainer([]), destination, num_producers=2, num_consumers=2,
        poll_interval=POLL,
    )
    manager.start_transfer()
    result = manager.wait_for_completion(timeout=TIMING_SLACK)

    assert result.state is TransferState.COMPLETED
    assert (result.total_items, result.delivered) == (0, 0)
    assert result.succeeded
    assert destination.count == 0


def test_queue_never_exceeds_capacity_during_transfer(
    make_items: Callable[[int], list[Item]], fast_switching: None
) -> None:
    """A sampler thread polling get_queue_status() never sees queue_size > capacity or
    queue_size != enqueued - dequeued.
    """
    capacity = 10
    manager = DataTransferManager(
        SourceContainer(make_items(300)),
        DestinationContainer(),
        capacity=capacity,
        num_producers=4,
        num_consumers=3,
        poll_interval=POLL,
    )
    breaches: list[str] = []
    done = threading.Event()

    def sample() -> None:
        while not done.is_set():
            status = manager.get_queue_status()
            if status.queue_size > status.capacity:
                breaches.append(f"size {status.queue_size} > capacity")
            if status.queue_size != status.enqueued - status.dequeued:
                breaches.append(
                    f"size {status.queue_size} != "
                    f"{status.enqueued} - {status.dequeued}"
                )

    sampler = threading.Thread(target=sample, name="sampler")
    sampler.start()
    manager.start_transfer()
    result = manager.wait_for_completion(timeout=TIMING_SLACK * 6)
    done.set()
    sampler.join(TIMING_SLACK)

    assert not breaches, f"queue invariant broken: {breaches[:5]}"
    assert result.succeeded


def test_start_twice_raises(make_items: Callable[[int], list[Item]]) -> None:
    """A second start_transfer() raises TransferStateError."""
    manager = DataTransferManager(
        SourceContainer(make_items(5)), DestinationContainer(), poll_interval=POLL
    )
    manager.start_transfer()
    try:
        with pytest.raises(TransferStateError):
            manager.start_transfer()
    finally:
        manager.wait_for_completion(timeout=TIMING_SLACK)

    # Also refused once the transfer is over: a manager is single use.
    with pytest.raises(TransferStateError):
        manager.start_transfer()


def test_wait_before_start_raises(make_items: Callable[[int], list[Item]]) -> None:
    """wait_for_completion() before start raises TransferStateError."""
    manager = DataTransferManager(
        SourceContainer(make_items(5)), DestinationContainer(), poll_interval=POLL
    )
    with pytest.raises(TransferStateError):
        manager.wait_for_completion(timeout=TIMING_SLACK)


def test_stop_before_start_marks_stopped(
    make_items: Callable[[int], list[Item]],
) -> None:
    """stop_transfer() from CREATED moves to STOPPED and starts no threads."""
    manager = DataTransferManager(
        SourceContainer(make_items(5)), DestinationContainer(), poll_interval=POLL
    )
    result = manager.stop_transfer(timeout=TIMING_SLACK)

    assert result.state is TransferState.STOPPED
    assert manager.state is TransferState.STOPPED
    assert result.delivered == 0
    assert result.undelivered == 5
    assert not result.succeeded
    assert not worker_threads(), "stop_transfer() started threads"
    # And it stays single use.
    with pytest.raises(TransferStateError):
        manager.start_transfer()


def test_stop_mid_transfer_terminates_all_threads(
    make_items: Callable[[int], list[Item]],
) -> None:
    """With slow consumers, stop_transfer() ends every worker thread within its timeout;
    state STOPPED; undelivered > 0.
    """
    items = make_items(200)
    destination = DestinationContainer()
    manager = DataTransferManager(
        SourceContainer(items),
        destination,
        num_producers=2,
        num_consumers=2,
        poll_interval=POLL,
        consumer_delay=0.05,
    )
    manager.start_transfer()
    time.sleep(0.2)
    result = manager.stop_transfer(timeout=TIMING_SLACK)

    assert result.state is TransferState.STOPPED
    assert not result.succeeded
    assert result.undelivered > 0, "the transfer finished before the stop landed"
    assert result.delivered == destination.count
    assert not worker_threads(), "a worker thread survived the stop"
    # Nothing was delivered twice, even on the abort path.
    assert len(destination.snapshot()) == len(destination.ids())


def test_stop_is_idempotent(make_items: Callable[[int], list[Item]]) -> None:
    """Calling stop_transfer() twice is safe and returns the same state."""
    manager = DataTransferManager(
        SourceContainer(make_items(100)),
        DestinationContainer(),
        poll_interval=POLL,
        consumer_delay=0.02,
    )
    manager.start_transfer()
    time.sleep(0.1)
    first = manager.stop_transfer(timeout=TIMING_SLACK)
    second = manager.stop_transfer(timeout=TIMING_SLACK)

    assert first.state is second.state is TransferState.STOPPED
    assert first.delivered == second.delivered
    assert first.elapsed_seconds == second.elapsed_seconds


def test_stop_after_completion_keeps_the_completed_state(
    make_items: Callable[[int], list[Item]],
) -> None:
    """A stop that arrives after the work is done does not rewrite the outcome."""
    manager = DataTransferManager(
        SourceContainer(make_items(20)), DestinationContainer(), poll_interval=POLL
    )
    manager.start_transfer()
    completed = manager.wait_for_completion(timeout=TIMING_SLACK)
    stopped = manager.stop_transfer(timeout=TIMING_SLACK)

    assert completed.state is TransferState.COMPLETED
    assert stopped.state is TransferState.COMPLETED
    assert manager.state is TransferState.COMPLETED


def test_wait_timeout_raises_transfer_timeout_error(
    make_items: Callable[[int], list[Item]],
) -> None:
    """With very slow consumers, wait_for_completion(timeout=0.1) raises
    TransferTimeoutError (also a TimeoutError).
    """
    manager = DataTransferManager(
        SourceContainer(make_items(100)),
        DestinationContainer(),
        num_consumers=1,
        poll_interval=POLL,
        consumer_delay=0.5,
    )
    manager.start_transfer()
    try:
        with pytest.raises(TransferTimeoutError) as caught:
            manager.wait_for_completion(timeout=0.1)
        # TransferTimeoutError also subclasses the builtin, so `except
        # TimeoutError` catches it.
        assert isinstance(caught.value, TimeoutError)
        # A timeout does not end the transfer; it is still running.
        assert manager.state is TransferState.RUNNING
    finally:
        manager.stop_transfer(timeout=TIMING_SLACK)
    assert not worker_threads()


def test_producer_failure_aborts_and_raises_transfer_failed(
    make_items: Callable[[int], list[Item]],
) -> None:
    """A failing producer: wait_for_completion raises TransferFailedError whose
    __cause__ is the original; state FAILED; no thread left alive.
    """
    boom = RuntimeError("source exploded")

    class FailingSource(SourceContainer):
        def take(self) -> Item | None:
            raise boom

    manager = DataTransferManager(
        FailingSource(make_items(50)),
        DestinationContainer(),
        num_producers=2,
        num_consumers=2,
        poll_interval=POLL,
    )
    manager.start_transfer()
    with pytest.raises(TransferFailedError) as caught:
        manager.wait_for_completion(timeout=TIMING_SLACK * 2)

    assert caught.value.__cause__ is boom
    assert manager.state is TransferState.FAILED
    assert not worker_threads(), "a worker thread survived the failure"


def test_consumer_failure_aborts_without_deadlock(
    make_items: Callable[[int], list[Item]],
) -> None:
    """A destination whose add() raises: producers blocked on a full queue still exit;
    TransferFailedError raised.
    """
    manager = DataTransferManager(
        SourceContainer(make_items(500)),
        FailingDestination(fail_after=5),
        capacity=10,
        num_producers=3,
        num_consumers=1,
        poll_interval=POLL,
    )
    manager.start_transfer()
    with pytest.raises(TransferFailedError) as caught:
        manager.wait_for_completion(timeout=TIMING_SLACK * 2)

    assert isinstance(caught.value.__cause__, RuntimeError)
    assert manager.state is TransferState.FAILED
    # The real point: the producers were waiting on a full queue, and the
    # failure path closed it so they could not wait forever.
    assert not worker_threads(), "the failure deadlocked a producer"


def test_context_manager_stops_on_exception(
    make_items: Callable[[int], list[Item]],
) -> None:
    """An exception inside `with manager:` stops all threads and still propagates."""
    manager = DataTransferManager(
        SourceContainer(make_items(300)),
        DestinationContainer(),
        num_producers=2,
        num_consumers=2,
        poll_interval=POLL,
        consumer_delay=0.02,
    )
    with pytest.raises(ZeroDivisionError), manager:
        manager.start_transfer()
        time.sleep(0.05)
        raise ZeroDivisionError("boom")

    assert manager.state is TransferState.STOPPED
    assert not worker_threads(), "__exit__ left a worker thread running"


def test_context_manager_leaves_a_finished_transfer_alone(
    make_items: Callable[[int], list[Item]],
) -> None:
    """A clean `with` block that finished its work still reports COMPLETED."""
    with DataTransferManager(
        SourceContainer(make_items(20)), DestinationContainer(), poll_interval=POLL
    ) as manager:
        manager.start_transfer()
        result = manager.wait_for_completion(timeout=TIMING_SLACK)
    assert result.succeeded
    assert manager.state is TransferState.COMPLETED


def test_status_reports_state_transitions(
    make_items: Callable[[int], list[Item]],
) -> None:
    """get_queue_status().state goes CREATED -> RUNNING -> COMPLETED."""
    manager = DataTransferManager(
        SourceContainer(make_items(40)),
        DestinationContainer(),
        num_consumers=1,
        poll_interval=POLL,
        consumer_delay=0.01,
    )
    created = manager.get_queue_status()
    assert created.state is TransferState.CREATED
    assert created.elapsed_seconds == 0.0
    assert (created.queue_size, created.enqueued, created.delivered) == (0, 0, 0)
    assert created.capacity == 10
    assert (created.active_producers, created.active_consumers) == (0, 0)

    manager.start_transfer()
    assert manager.get_queue_status().state is TransferState.RUNNING

    manager.wait_for_completion(timeout=TIMING_SLACK * 2)
    final = manager.get_queue_status()
    assert final.state is TransferState.COMPLETED
    assert final.elapsed_seconds > 0
    assert final.delivered == 40
    assert final.enqueued == final.dequeued == 40
    assert (final.active_producers, final.active_consumers) == (0, 0)


def test_shared_queue_is_exposed_with_the_requested_capacity(
    make_items: Callable[[int], list[Item]],
) -> None:
    """The queue is reachable for inspection and honours the capacity argument."""
    manager = DataTransferManager(
        SourceContainer(make_items(5)), DestinationContainer(), capacity=3
    )
    assert manager.shared_queue.capacity == 3


def test_default_capacity_matches_the_specification(
    make_items: Callable[[int], list[Item]],
) -> None:
    """The spec requires a bounded buffer of 10."""
    manager = DataTransferManager(
        SourceContainer(make_items(1)), DestinationContainer()
    )
    assert manager.shared_queue.capacity == 10


@pytest.mark.parametrize(
    "kwargs",
    [
        {"num_producers": 0},
        {"num_consumers": 0},
        {"num_producers": -1},
        {"poll_interval": 0},
        {"poll_interval": -0.5},
        {"producer_delay": -1},
        {"consumer_delay": -1},
        {"capacity": 0},
    ],
)
def test_rejects_invalid_configuration_values(kwargs: dict[str, object]) -> None:
    """Out-of-range worker counts, intervals, delays and capacity raise ValueError."""
    with pytest.raises(ValueError):
        DataTransferManager(
            SourceContainer([]), DestinationContainer(), **kwargs  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"num_producers": True},
        {"num_consumers": True},
        {"num_producers": 1.5},
        {"num_consumers": "2"},
    ],
)
def test_rejects_non_int_worker_counts(kwargs: dict[str, object]) -> None:
    """A worker count that is not an int raises TypeError; bool is rejected."""
    with pytest.raises(TypeError):
        DataTransferManager(
            SourceContainer([]), DestinationContainer(), **kwargs  # type: ignore[arg-type]
        )


def test_rejects_wrong_container_types() -> None:
    """Swapped or foreign containers raise TypeError."""
    with pytest.raises(TypeError):
        DataTransferManager(DestinationContainer(), DestinationContainer())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        DataTransferManager(SourceContainer([]), SourceContainer([]))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        DataTransferManager([], DestinationContainer())  # type: ignore[arg-type]


def test_wait_without_a_timeout_joins_until_done(
    make_items: Callable[[int], list[Item]],
) -> None:
    """timeout=None waits as long as it takes rather than polling."""
    manager = DataTransferManager(
        SourceContainer(make_items(40)),
        DestinationContainer(),
        num_producers=2,
        num_consumers=2,
        poll_interval=POLL,
    )
    manager.start_transfer()
    result = manager.wait_for_completion()  # No deadline at all.
    assert result.succeeded
    assert not worker_threads()


def test_stop_timeout_raises_when_a_worker_will_not_exit(
    make_items: Callable[[int], list[Item]],
) -> None:
    """A worker wedged inside add() makes stop_transfer() report a timeout.

    The stop is cooperative, so a worker stuck in code that never checks the
    stop event cannot be killed; the manager says so instead of hanging.
    """
    release = threading.Event()

    class WedgedDestination(DestinationContainer):
        def add(self, item: Item) -> None:
            # Ignores the stop event entirely, which is the point.
            release.wait(TIMING_SLACK * 2)
            super().add(item)

    manager = DataTransferManager(
        SourceContainer(make_items(20)),
        WedgedDestination(),
        num_producers=1,
        num_consumers=1,
        poll_interval=POLL,
    )
    manager.start_transfer()
    try:
        time.sleep(POLL * 2)
        with pytest.raises(TransferTimeoutError):
            manager.stop_transfer(timeout=0.1)
        # The state is still recorded, even though the join did not finish.
        assert manager.state is TransferState.STOPPED
    finally:
        # Let the wedged consumer go. A second stop_transfer() is idempotent
        # and returns at once without re-joining, so wait for the thread
        # here rather than leaking it into the next test.
        release.set()
        deadline = time.monotonic() + TIMING_SLACK * 2
        while worker_threads() and time.monotonic() < deadline:
            time.sleep(0.01)
    assert not worker_threads(), "the released worker never exited"
