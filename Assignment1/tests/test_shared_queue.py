"""Tests for SharedQueue: bounds, FIFO order, blocking, timeouts and closing."""

import contextlib
import threading
import time
from collections.abc import Callable

import pytest

from producer_consumer.exceptions import (
    QueueClosedError,
    QueueEmptyError,
    QueueFullError,
)
from producer_consumer.item import Item
from producer_consumer.shared_queue import SharedQueue

# Generous enough not to fail on a loaded CI box, tight enough to catch a
# call that blocks when it should not.
TIMING_SLACK = 2.0


def test_default_capacity_is_ten() -> None:
    """The specification requires a bounded queue of capacity 10."""
    assert SharedQueue().capacity == 10


@pytest.mark.parametrize("bad", [0, -1])
def test_rejects_capacity_below_one(bad: int) -> None:
    """A capacity under 1 raises ValueError."""
    with pytest.raises(ValueError):
        SharedQueue(capacity=bad)


@pytest.mark.parametrize("bad", ["10", 1.5, None, True])
def test_rejects_non_int_capacity(bad: object) -> None:
    """A non-int capacity raises TypeError; bool is rejected on purpose."""
    with pytest.raises(TypeError):
        SharedQueue(capacity=bad)  # type: ignore[arg-type]


def test_accepts_an_externally_supplied_lock() -> None:
    """The spec's SharedQueue(capacity, lock) form works and really uses the lock.

    While the caller holds the lock, no queue operation can make progress:
    ``timeout`` bounds the wait for space or an item, not the wait for the
    lock itself (``queue.Queue`` behaves the same way).
    """
    lock = threading.Lock()
    queue = SharedQueue(capacity=2, lock=lock)
    queue.enqueue(Item(id=1, data="a"))
    finished = threading.Event()

    def enqueue_second() -> None:
        queue.enqueue(Item(id=2, data="b"))
        finished.set()

    thread = threading.Thread(target=enqueue_second)
    with lock:
        thread.start()
        assert not finished.wait(0.1), "the queue ignored the supplied lock"
    thread.join(TIMING_SLACK)
    assert finished.is_set()
    assert queue.size() == 2


def test_enqueue_rejects_non_items() -> None:
    """enqueue() with a non-Item raises TypeError."""
    with pytest.raises(TypeError):
        SharedQueue().enqueue("not an item")  # type: ignore[arg-type]


def test_negative_timeout_is_rejected() -> None:
    """A negative timeout raises ValueError on both operations."""
    queue = SharedQueue()
    with pytest.raises(ValueError):
        queue.enqueue(Item(id=1, data="a"), timeout=-1)
    with pytest.raises(ValueError):
        queue.dequeue(timeout=-1)


def test_fifo_order_is_strict(make_items: Callable[[int], list[Item]]) -> None:
    """Items come out in the order they went in."""
    queue = SharedQueue(capacity=5)
    items = make_items(5)
    for item in items:
        queue.enqueue(item)
    assert [queue.dequeue() for _ in items] == items


def test_size_and_len_track_contents(make_items: Callable[[int], list[Item]]) -> None:
    """size() and len() both report the current number of items."""
    queue = SharedQueue(capacity=3)
    assert queue.size() == 0 and len(queue) == 0
    queue.enqueue(make_items(1)[0])
    assert queue.size() == 1 and len(queue) == 1
    queue.dequeue()
    assert queue.size() == 0


def test_status_counters_stay_consistent(
    make_items: Callable[[int], list[Item]],
) -> None:
    """status() always satisfies size == enqueued - dequeued."""
    queue = SharedQueue(capacity=4)
    for item in make_items(3):
        queue.enqueue(item)
    queue.dequeue()

    snapshot = queue.status()
    assert (snapshot.enqueued, snapshot.dequeued, snapshot.size) == (3, 1, 2)
    assert snapshot.size == snapshot.enqueued - snapshot.dequeued
    assert snapshot.capacity == 4
    assert not snapshot.closed
    assert not snapshot.is_empty
    assert not snapshot.is_full


def test_enqueue_times_out_when_full(make_items: Callable[[int], list[Item]]) -> None:
    """A full queue raises QueueFullError once the timeout expires."""
    queue = SharedQueue(capacity=2)
    items = make_items(3)
    queue.enqueue(items[0])
    queue.enqueue(items[1])

    started = time.monotonic()
    with pytest.raises(QueueFullError):
        queue.enqueue(items[2], timeout=0.1)
    # It really waited rather than failing immediately.
    assert time.monotonic() - started >= 0.1
    assert queue.size() == 2


def test_dequeue_times_out_when_empty() -> None:
    """An empty open queue raises QueueEmptyError once the timeout expires."""
    queue = SharedQueue()
    started = time.monotonic()
    with pytest.raises(QueueEmptyError):
        queue.dequeue(timeout=0.1)
    assert time.monotonic() - started >= 0.1


def test_queue_never_exceeds_capacity_under_load(
    make_items: Callable[[int], list[Item]], fast_switching: None
) -> None:
    """With many producers hammering a small queue, size never passes capacity."""
    capacity = 4
    queue = SharedQueue(capacity=capacity)
    items = make_items(200)
    source = iter(items)
    source_lock = threading.Lock()
    breaches: list[int] = []
    received: list[Item] = []
    done = threading.Event()

    def produce() -> None:
        while True:
            with source_lock:
                item = next(source, None)
            if item is None:
                return
            queue.enqueue(item)

    def consume() -> None:
        while not done.is_set() or queue.size():
            try:
                received.append(queue.dequeue(timeout=0.05))
            except QueueEmptyError:
                continue

    def sample() -> None:
        while not done.is_set():
            snapshot = queue.status()
            if snapshot.size > capacity or snapshot.size != (
                snapshot.enqueued - snapshot.dequeued
            ):
                breaches.append(snapshot.size)

    producers = [threading.Thread(target=produce) for _ in range(4)]
    consumers = [threading.Thread(target=consume) for _ in range(2)]
    sampler = threading.Thread(target=sample)
    for thread in (*producers, *consumers, sampler):
        thread.start()
    for thread in producers:
        thread.join(TIMING_SLACK * 5)
    done.set()
    for thread in (*consumers, sampler):
        thread.join(TIMING_SLACK * 5)

    assert not breaches, f"capacity or counter invariant broken: {breaches}"
    assert sorted(item.id for item in received) == [item.id for item in items]


def test_blocked_enqueue_resumes_when_space_appears(
    make_items: Callable[[int], list[Item]],
) -> None:
    """A producer blocked on a full queue proceeds as soon as one slot frees up."""
    queue = SharedQueue(capacity=1)
    items = make_items(2)
    queue.enqueue(items[0])
    enqueued = threading.Event()

    def produce() -> None:
        queue.enqueue(items[1])  # Blocks: no timeout, so it waits for room.
        enqueued.set()

    thread = threading.Thread(target=produce)
    thread.start()
    try:
        assert not enqueued.wait(0.1), "enqueue should still be blocked"
        assert queue.dequeue() == items[0]
        assert enqueued.wait(TIMING_SLACK), "enqueue did not resume after a dequeue"
    finally:
        thread.join(TIMING_SLACK)
    assert queue.dequeue() == items[1]


def test_blocked_dequeue_resumes_when_an_item_arrives(
    make_items: Callable[[int], list[Item]],
) -> None:
    """A consumer blocked on an empty queue proceeds as soon as an item arrives."""
    queue = SharedQueue(capacity=2)
    item = make_items(1)[0]
    got: list[Item] = []

    def consume() -> None:
        got.append(queue.dequeue())  # Blocks until something is enqueued.

    thread = threading.Thread(target=consume)
    thread.start()
    try:
        time.sleep(0.05)
        assert not got
        queue.enqueue(item)
        thread.join(TIMING_SLACK)
    finally:
        thread.join(TIMING_SLACK)
    assert got == [item]


def test_close_is_idempotent() -> None:
    """close() twice is harmless and the closed flag stays set."""
    queue = SharedQueue()
    queue.close()
    queue.close()
    assert queue.closed
    assert queue.status().closed


def test_enqueue_on_closed_queue_raises_immediately(
    make_items: Callable[[int], list[Item]],
) -> None:
    """A closed queue refuses new items at once, even with room to spare."""
    queue = SharedQueue(capacity=5)
    queue.close()
    started = time.monotonic()
    with pytest.raises(QueueClosedError):
        queue.enqueue(make_items(1)[0], timeout=5)
    # It did not sit out the timeout.
    assert time.monotonic() - started < TIMING_SLACK


def test_dequeue_drains_a_closed_queue_before_raising(
    make_items: Callable[[int], list[Item]],
) -> None:
    """Closing never strands items: consumers get them all, then QueueClosedError."""
    queue = SharedQueue(capacity=5)
    items = make_items(3)
    for item in items:
        queue.enqueue(item)
    queue.close()

    assert [queue.dequeue() for _ in items] == items
    with pytest.raises(QueueClosedError):
        queue.dequeue()
    # The signal is repeatable, so every consumer sees it.
    with pytest.raises(QueueClosedError):
        queue.dequeue(timeout=5)


def test_close_wakes_a_blocked_producer(
    make_items: Callable[[int], list[Item]],
) -> None:
    """A producer waiting for space gets QueueClosedError the moment close() runs."""
    queue = SharedQueue(capacity=1)
    items = make_items(2)
    queue.enqueue(items[0])
    outcome: list[str] = []

    def produce() -> None:
        try:
            queue.enqueue(items[1])  # Unbounded wait: only close() frees it.
        except QueueClosedError:
            outcome.append("closed")

    thread = threading.Thread(target=produce)
    thread.start()
    try:
        time.sleep(0.05)
        assert not outcome, "producer should still be blocked"
        queue.close()
        thread.join(TIMING_SLACK)
    finally:
        thread.join(TIMING_SLACK)
    assert not thread.is_alive(), "close() left a producer blocked"
    assert outcome == ["closed"]


def test_close_wakes_a_blocked_consumer() -> None:
    """A consumer waiting for an item gets QueueClosedError the moment close() runs."""
    queue = SharedQueue()
    outcome: list[str] = []

    def consume() -> None:
        try:
            queue.dequeue()  # Unbounded wait: only close() frees it.
        except QueueClosedError:
            outcome.append("closed")

    thread = threading.Thread(target=consume)
    thread.start()
    try:
        time.sleep(0.05)
        assert not outcome, "consumer should still be blocked"
        queue.close()
        thread.join(TIMING_SLACK)
    finally:
        thread.join(TIMING_SLACK)
    assert not thread.is_alive(), "close() left a consumer blocked"
    assert outcome == ["closed"]


def test_close_wakes_every_waiter(make_items: Callable[[int], list[Item]]) -> None:
    """close() uses notify_all: many blocked threads all wake, none is left behind."""
    queue = SharedQueue(capacity=1)
    queue.enqueue(make_items(1)[0])
    woken = threading.Semaphore(0)

    def produce(item: Item) -> None:
        # Either outcome is fine; the point is that the thread wakes at all.
        with contextlib.suppress(QueueClosedError):
            queue.enqueue(item)
        woken.release()

    extra = [Item(id=100 + i, data=i) for i in range(5)]
    threads = [threading.Thread(target=produce, args=(item,)) for item in extra]
    for thread in threads:
        thread.start()
    time.sleep(0.05)
    queue.close()
    for thread in threads:
        thread.join(TIMING_SLACK)
    assert all(not thread.is_alive() for thread in threads)
    assert all(woken.acquire(blocking=False) for _ in threads)


def test_drain_returns_held_items_and_keeps_counters_consistent(
    make_items: Callable[[int], list[Item]],
) -> None:
    """drain() empties the queue, counting the items as dequeued."""
    queue = SharedQueue(capacity=5)
    items = make_items(3)
    for item in items:
        queue.enqueue(item)

    assert queue.drain() == tuple(items)
    snapshot = queue.status()
    assert snapshot.size == 0
    assert snapshot.size == snapshot.enqueued - snapshot.dequeued
    assert queue.drain() == ()


def test_repr_mentions_size_and_capacity() -> None:
    """repr() is useful in a failing assertion."""
    assert "capacity=10" in repr(SharedQueue())
