"""Tests for Producer, calling run() directly where possible."""

import threading
import time
from collections.abc import Callable

import pytest

from producer_consumer.containers import SourceContainer
from producer_consumer.item import Item
from producer_consumer.producer import Producer
from producer_consumer.shared_queue import SharedQueue

TIMING_SLACK = 5.0
POLL = 0.05


def test_producer_enqueues_all_items_then_returns(
    make_items: Callable[[int], list[Item]],
) -> None:
    """With room in the queue, run() enqueues every item in order and returns."""
    items = make_items(5)
    queue = SharedQueue(capacity=10)
    producer = Producer(
        SourceContainer(items), queue, threading.Event(), poll_interval=POLL
    )
    producer.run()

    assert producer.name == "producer"
    assert queue.size() == len(items)
    assert [queue.dequeue() for _ in items] == items


def test_producer_exposes_its_name(make_items: Callable[[int], list[Item]]) -> None:
    """The name given at construction is what the manager reports on failure."""
    producer = Producer(
        SourceContainer(make_items(1)),
        SharedQueue(),
        threading.Event(),
        name="producer-7",
    )
    assert producer.name == "producer-7"


def test_producer_returns_promptly_when_stopped_while_queue_full(
    make_items: Callable[[int], list[Item]],
) -> None:
    """Blocked on a full queue, run() returns within ~poll_interval of a stop."""
    items = make_items(10)
    queue = SharedQueue(capacity=2)
    stop_event = threading.Event()
    producer = Producer(
        SourceContainer(items), queue, stop_event, poll_interval=POLL
    )
    thread = threading.Thread(target=producer.run)
    thread.start()
    try:
        # Let it fill the queue and start retrying against a full queue.
        time.sleep(POLL * 4)
        assert queue.size() == 2
        assert thread.is_alive(), "producer should be blocked on the full queue"

        stop_event.set()
        thread.join(TIMING_SLACK)
    finally:
        stop_event.set()
        thread.join(TIMING_SLACK)

    assert not thread.is_alive(), "a stop did not release the blocked producer"
    # Nothing was dropped from the queue, and not everything was enqueued.
    assert queue.size() == 2
    assert queue.status().enqueued < len(items)


def test_producer_returns_when_queue_closed(
    make_items: Callable[[int], list[Item]],
) -> None:
    """Closing the queue while run() is blocked makes it return without error."""
    items = make_items(10)
    queue = SharedQueue(capacity=1)
    errors: list[BaseException] = []

    def run() -> None:
        try:
            Producer(
                SourceContainer(items),
                queue,
                threading.Event(),
                poll_interval=POLL,
            ).run()
        except BaseException as error:  # noqa: BLE001 - recorded for the assertion
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    try:
        time.sleep(POLL * 2)
        assert thread.is_alive()
        queue.close()
        thread.join(TIMING_SLACK)
    finally:
        queue.close()
        thread.join(TIMING_SLACK)

    assert not thread.is_alive(), "close() did not release the blocked producer"
    assert not errors, f"QueueClosedError should be handled, not raised: {errors}"


def test_producer_shares_source_with_other_producers(
    make_items: Callable[[int], list[Item]],
) -> None:
    """Two producers on one source enqueue every item exactly once between them."""
    items = make_items(40)
    source = SourceContainer(items)
    queue = SharedQueue(capacity=len(items))
    stop_event = threading.Event()
    producers = [
        Producer(source, queue, stop_event, name=f"producer-{i}", poll_interval=POLL)
        for i in range(2)
    ]

    threads = [threading.Thread(target=p.run) for p in producers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(TIMING_SLACK)

    assert queue.size() == len(items)
    enqueued = [queue.dequeue() for _ in items]
    assert sorted(item.id for item in enqueued) == [item.id for item in items]


def test_producer_propagates_unexpected_errors(
    make_items: Callable[[int], list[Item]],
) -> None:
    """An unexpected exception from the queue propagates out of run()."""

    class BrokenQueue(SharedQueue):
        def enqueue(self, item: Item, timeout: float | None = None) -> None:
            raise RuntimeError("queue exploded")

    producer = Producer(
        SourceContainer(make_items(3)),
        BrokenQueue(capacity=5),
        threading.Event(),
        poll_interval=POLL,
    )
    with pytest.raises(RuntimeError, match="queue exploded"):
        producer.run()


def test_producer_delay_is_interrupted_by_a_stop(
    make_items: Callable[[int], list[Item]],
) -> None:
    """A long per-item delay does not delay a stop: Event.wait, not time.sleep."""
    queue = SharedQueue(capacity=50)
    stop_event = threading.Event()
    producer = Producer(
        SourceContainer(make_items(10)),
        queue,
        stop_event,
        poll_interval=POLL,
        delay=30.0,
    )
    thread = threading.Thread(target=producer.run)
    thread.start()
    try:
        time.sleep(POLL)
        stop_event.set()
        thread.join(TIMING_SLACK)
    finally:
        stop_event.set()
        thread.join(TIMING_SLACK)
    assert not thread.is_alive(), "the producer slept through the stop request"


def test_producer_honours_a_stop_set_before_it_runs(
    make_items: Callable[[int], list[Item]],
) -> None:
    """An already-set stop event means run() enqueues nothing."""
    queue = SharedQueue(capacity=5)
    stop_event = threading.Event()
    stop_event.set()
    Producer(
        SourceContainer(make_items(3)), queue, stop_event, poll_interval=POLL
    ).run()
    assert queue.size() == 0


@pytest.mark.parametrize(
    ("poll_interval", "delay"),
    [(0, 0.0), (-1, 0.0), (0.1, -0.5)],
)
def test_producer_rejects_invalid_poll_interval_and_delay(
    poll_interval: float, delay: float
) -> None:
    """poll_interval <= 0 or delay < 0 raise ValueError."""
    with pytest.raises(ValueError):
        Producer(
            SourceContainer([]),
            SharedQueue(),
            threading.Event(),
            poll_interval=poll_interval,
            delay=delay,
        )
