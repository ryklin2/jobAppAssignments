"""SharedQueue: a bounded FIFO queue built from one Lock and two Conditions.

This is deliberately not ``queue.Queue``: the assignment is about showing the
synchronization explicitly. The design is the classic bounded-buffer monitor.
"""

# Annotations are deferred, so `Lock | None` is never evaluated at runtime.
# On Python 3.10-3.12 `threading.Lock` is a factory function rather than a
# type, and evaluating that union raises TypeError at import time.
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Condition, Lock

from producer_consumer.exceptions import (
    QueueClosedError,
    QueueEmptyError,
    QueueFullError,
)
from producer_consumer.item import Item


@dataclass(frozen=True, slots=True)
class QueueSnapshot:
    """A mutually consistent view of a SharedQueue, from ``status()``.

    Every field is read inside one critical section, so
    ``size == enqueued - dequeued`` always holds.

    Attributes:
        size: Items currently held.
        capacity: Maximum items the queue can hold.
        enqueued: Total successful enqueues since construction.
        dequeued: Total successful dequeues since construction.
        closed: Whether the queue has been closed.
    """

    size: int
    capacity: int
    enqueued: int
    dequeued: int
    closed: bool

    @property
    def is_empty(self) -> bool:
        """Whether the queue held no items when the snapshot was taken."""
        return self.size == 0

    @property
    def is_full(self) -> bool:
        """Whether the queue was at capacity when the snapshot was taken."""
        return self.size >= self.capacity


class SharedQueue:
    """A bounded, thread-safe FIFO queue that can be closed.

    Synchronization:
        One ``Lock`` guards all mutable state (the deque, the counters and
        the closed flag). Two ``Condition`` objects share that same lock:

        * ``_not_full`` - waited on by producers, notified by a dequeue.
        * ``_not_empty`` - waited on by consumers, notified by an enqueue.

        Two conditions on one lock mean a dequeue wakes only a producer and
        an enqueue wakes only a consumer. A single condition would work but
        would need ``notify_all()`` and would wake threads that cannot
        proceed (the thundering-herd problem).

        Every wait goes through ``Condition.wait_for(predicate, timeout)``,
        which re-checks the predicate after each wake-up. That is required,
        not optional: a waiter can be woken spuriously, or another thread
        can win the race for the slot before the woken thread reacquires the
        lock. Waiting on a bare ``wait()`` and assuming the condition holds
        is the classic bug.

    Closing:
        ``close()`` is the end-of-data signal and is idempotent. After it:

        * ``enqueue()`` raises ``QueueClosedError`` immediately.
        * ``dequeue()`` keeps returning items until the queue is empty, then
          raises ``QueueClosedError``, so no item is ever stranded.

        ``close()`` uses ``notify_all()`` on both conditions, because every
        waiter's situation has changed and all of them must re-evaluate.

    Thread safety:
        Every public method is safe to call from any thread at any time.
    """

    def __init__(self, capacity: int = 10, lock: Lock | None = None) -> None:
        """Create an empty queue.

        Args:
            capacity: Maximum items held at once. The spec requires 10.
            lock: An externally supplied lock to synchronize on. The spec
                passes the lock in explicitly; omit it and the queue creates
                its own. Both conditions are built on this one lock.

        Raises:
            TypeError: If ``capacity`` is not an int (bools rejected).
            ValueError: If ``capacity`` < 1.
        """
        if isinstance(capacity, bool) or not isinstance(capacity, int):
            raise TypeError(
                f"capacity must be an int, got {type(capacity).__name__}"
            )
        if capacity < 1:
            raise ValueError(f"capacity must be at least 1, got {capacity}")

        self._capacity = capacity
        self._items: deque[Item] = deque()
        self._enqueued = 0
        self._dequeued = 0
        self._closed = False

        # One lock, two conditions built on it. Acquiring the lock directly
        # is what lets both conditions be used from the same critical
        # section; this is how the standard library's queue.Queue works too.
        self._lock = lock if lock is not None else Lock()
        self._not_full = Condition(self._lock)
        self._not_empty = Condition(self._lock)

    # ------------------------------------------------------------------- queries

    @property
    def capacity(self) -> int:
        """Maximum items the queue can hold (immutable; no lock needed)."""
        return self._capacity

    @property
    def closed(self) -> bool:
        """Whether the queue has been closed (a snapshot)."""
        with self._lock:
            return self._closed

    def size(self) -> int:
        """Items currently held.

        Stale the moment it returns. Never use it to decide whether to
        enqueue or dequeue (a check-then-act race); call the operation with
        a timeout and handle the exception instead.
        """
        with self._lock:
            return len(self._items)

    def __len__(self) -> int:
        """Same as ``size()``, so ``len(queue)`` works."""
        return self.size()

    def status(self) -> QueueSnapshot:
        """Return a mutually consistent snapshot of the queue."""
        with self._lock:
            return QueueSnapshot(
                size=len(self._items),
                capacity=self._capacity,
                enqueued=self._enqueued,
                dequeued=self._dequeued,
                closed=self._closed,
            )

    # ---------------------------------------------------------------- operations

    def enqueue(self, item: Item, timeout: float | None = None) -> None:
        """Add ``item``, waiting for space if the queue is full.

        Args:
            item: The item to add.
            timeout: Seconds to wait for space. ``None`` waits forever.

        Raises:
            TypeError: If ``item`` is not an ``Item``.
            ValueError: If ``timeout`` is negative.
            QueueFullError: If no space became free before ``timeout``.
            QueueClosedError: If the queue is closed, now or while waiting.
        """
        if not isinstance(item, Item):
            raise TypeError(f"item must be an Item, got {type(item).__name__}")
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be non-negative")

        with self._lock:
            if self._closed:
                raise QueueClosedError("cannot enqueue: the queue is closed")

            # wait_for re-checks the predicate on every wake-up and keeps
            # track of the remaining timeout across spurious wake-ups.
            # A close() while waiting also satisfies it, so a closing queue
            # never leaves a producer blocked.
            if not self._not_full.wait_for(self._has_space_or_closed, timeout):
                raise QueueFullError(
                    f"queue full ({self._capacity}) after {timeout}s"
                )
            if self._closed:
                raise QueueClosedError("cannot enqueue: the queue was closed")

            self._items.append(item)
            self._enqueued += 1
            # One slot was filled, so at most one consumer can proceed.
            self._not_empty.notify()

    def dequeue(self, timeout: float | None = None) -> Item:
        """Remove and return the oldest item, waiting for one if empty.

        Args:
            timeout: Seconds to wait for an item. ``None`` waits forever.

        Returns:
            The oldest item in the queue (strict FIFO).

        Raises:
            ValueError: If ``timeout`` is negative.
            QueueEmptyError: If no item arrived before ``timeout`` on a queue
                that is still open.
            QueueClosedError: If the queue is closed AND empty, which is the
                normal "all data has been processed" signal for consumers.
        """
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be non-negative")

        with self._lock:
            if not self._not_empty.wait_for(self._has_item_or_closed, timeout):
                raise QueueEmptyError(f"queue empty after {timeout}s")
            if not self._items:
                # Only reachable when the queue is closed: drained at last.
                raise QueueClosedError("cannot dequeue: the queue is closed and empty")

            item = self._items.popleft()
            self._dequeued += 1
            # One slot was freed, so at most one producer can proceed.
            self._not_full.notify()
            return item

    def close(self) -> None:
        """Signal end of data and wake every waiter. Idempotent.

        Producers blocked for space and consumers blocked for an item both
        wake immediately, so closing can never leave a thread stuck.
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True
            # Every waiter's predicate has changed, so wake all of them.
            self._not_full.notify_all()
            self._not_empty.notify_all()

    # -------------------------------------------------- predicates (lock is held)

    def _has_space_or_closed(self) -> bool:
        """Whether an enqueue can stop waiting. Called by ``wait_for``."""
        return self._closed or len(self._items) < self._capacity

    def _has_item_or_closed(self) -> bool:
        """Whether a dequeue can stop waiting. Called by ``wait_for``."""
        return bool(self._items) or self._closed

    def __repr__(self) -> str:
        """Debug form; takes the lock for a consistent reading."""
        snapshot = self.status()
        return (
            f"SharedQueue(size={snapshot.size}, capacity={snapshot.capacity}, "
            f"closed={snapshot.closed})"
        )
