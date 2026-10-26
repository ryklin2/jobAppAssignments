"""DataTransferManager: owns the worker threads and the transfer lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType

from producer_consumer.consumer import Consumer
from producer_consumer.containers import DestinationContainer, SourceContainer
from producer_consumer.producer import Producer
from producer_consumer.shared_queue import SharedQueue
from producer_consumer.status import QueueStatus, TransferResult, TransferState

# Suggested imports for the implementation:
#   import queue, threading, time
#   from producer_consumer.exceptions import (
#       TransferFailedError, TransferStateError, TransferTimeoutError)

DEFAULT_CAPACITY = 10


@dataclass(frozen=True, slots=True)
class WorkerFailure:
    """An exception raised inside a worker thread, sent over the error channel.

    Attributes:
        worker_name: Name of the thread that failed.
        error: The exception it raised.
    """

    worker_name: str
    error: Exception


class DataTransferManager:
    """Coordinates producers and consumers moving items source -> destination.

    Lifecycle (single use; Python threads cannot be restarted)::

        CREATED --start_transfer()--> RUNNING --> COMPLETED | STOPPED | FAILED
        CREATED --stop_transfer()---> STOPPED

    Termination protocol (normal run):
        1. Each producer thread runs inside ``try/finally``; the ``finally``
           decrements the active-producer count under ``self._lock``.
        2. The producer that brings the count to zero closes the queue. This
           is the Python analog of Java's CountDownLatch, and it runs even if
           a producer crashed.
        3. Consumers drain the closed queue, receive ``QueueClosedError`` and
           return.
        4. ``wait_for_completion`` joins every thread against one deadline.

    Failure handling (fail fast):
        A worker exception is wrapped in a ``WorkerFailure`` and put on a
        ``queue.Queue`` error channel. The manager then sets the stop event
        and closes the queue so no thread can block forever.
        ``wait_for_completion`` re-raises the first failure as
        ``TransferFailedError`` with the original exception as ``__cause__``.

    Thread safety:
        Public methods may be called from any thread except this manager's
        own worker threads (they join workers, and a thread cannot join
        itself). Lifecycle state is guarded by ``self._lock``.

        Lock order: the manager lock may be held while acquiring queue or
        container locks, never the reverse. The queue and containers never
        call back into the manager, so no lock cycle (deadlock) is possible.
        Nothing prints or logs while holding a lock.
    """

    def __init__(
        self,
        source_container: SourceContainer,
        destination_container: DestinationContainer,
        *,
        capacity: int = DEFAULT_CAPACITY,
        num_producers: int = 1,
        num_consumers: int = 1,
        poll_interval: float = 0.1,
        producer_delay: float = 0.0,
        consumer_delay: float = 0.0,
    ) -> None:
        """Create a manager in the CREATED state. No threads start yet.

        Creates the SharedQueue, the stop ``threading.Event``, the
        ``queue.Queue`` error channel, the manager ``threading.Lock``, and
        one Producer/Consumer object per requested worker.

        Args:
            source_container: Items to transfer (shared by all producers).
            destination_container: Receives delivered items.
            capacity: SharedQueue capacity; the spec requires 10.
            num_producers: Producer threads to run (at least 1).
            num_consumers: Consumer threads to run (at least 1).
            poll_interval: Bounded-wait length workers use between stop
                checks, in seconds.
            producer_delay: Per-item pause for producers (demo pacing).
            consumer_delay: Per-item pause for consumers (demo pacing).

        Raises:
            TypeError: If a container has the wrong type, or a worker count
                is not an int (bools rejected).
            ValueError: If a worker count < 1, ``poll_interval`` <= 0, or a
                delay < 0. Invalid ``capacity`` is rejected by SharedQueue.
        """
        raise NotImplementedError

    # ----------------------------------------------------------- context manager

    def __enter__(self) -> DataTransferManager:
        """Return the manager; use ``with`` to guarantee threads are stopped."""
        raise NotImplementedError

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Stop the transfer if it is still running. Never suppresses errors."""
        raise NotImplementedError

    # ------------------------------------------------------------------- queries

    @property
    def state(self) -> TransferState:
        """Current lifecycle state (read under the manager lock)."""
        raise NotImplementedError

    @property
    def shared_queue(self) -> SharedQueue:
        """The queue between producers and consumers (for tests and status)."""
        raise NotImplementedError

    def get_queue_status(self) -> QueueStatus:
        """Return a point-in-time status snapshot. Safe from any thread.

        Queue fields come from one ``SharedQueue.status()`` call (mutually
        consistent). Delivered count and live-thread counts are read
        separately; see ``QueueStatus`` for the consistency note.
        """
        raise NotImplementedError

    # ----------------------------------------------------------------- lifecycle

    def start_transfer(self) -> None:
        """Start every worker thread and move to RUNNING.

        Threads are non-daemon and named after their worker (``producer-1``,
        ``consumer-2``) so status output and errors are readable.

        Raises:
            TransferStateError: If the manager is not in CREATED (already
                started, finished, or stopped).
        """
        raise NotImplementedError

    def wait_for_completion(self, timeout: float | None = None) -> TransferResult:
        """Block until every worker has finished, then return the result.

        ``Thread.join(timeout)`` returns silently on timeout, so this method
        checks ``is_alive()`` afterwards. All joins share ONE deadline
        (``time.monotonic() + timeout``), not ``timeout`` each.

        On timeout the transfer keeps running; call ``stop_transfer()`` to
        abort it.

        Args:
            timeout: Seconds to wait in total, or ``None`` to wait forever.

        Returns:
            A ``TransferResult`` with state COMPLETED (or STOPPED if
            ``stop_transfer()`` ran meanwhile).

        Raises:
            TransferStateError: If the transfer was never started.
            TransferTimeoutError: If workers are still alive at the deadline.
            TransferFailedError: If any worker raised; the original exception
                is the ``__cause__``. State becomes FAILED.
        """
        raise NotImplementedError

    def stop_transfer(self, timeout: float | None = 5.0) -> TransferResult:
        """Abort the transfer: set the stop event, close the queue, join workers.

        Idempotent: after the first call, or once the transfer has finished,
        it returns the current result without changing the state. From
        CREATED it moves straight to STOPPED without starting threads.

        Items still queued when the stop happens are not delivered;
        ``TransferResult.undelivered`` reports them.

        Raises:
            TransferTimeoutError: If workers are still alive after
                ``timeout`` seconds.
        """
        raise NotImplementedError

    # ------------------------------------------------------- worker thread bodies

    def _run_producer(self, producer: Producer) -> None:
        """Thread target for a producer.

        ``try: producer.run()`` / ``except Exception as e:
        self._record_failure(producer.name, e)`` / ``finally:`` decrement the
        active-producer count under the lock; if it reached zero, close the
        queue (closing is idempotent).
        """
        raise NotImplementedError

    def _run_consumer(self, consumer: Consumer) -> None:
        """Thread target for a consumer: run it; report any exception."""
        raise NotImplementedError

    def _record_failure(self, worker_name: str, error: Exception) -> None:
        """Put a ``WorkerFailure`` on the error channel, then abort.

        Sets the stop event and closes the queue so every other worker wakes
        and exits. Holding the manager lock while closing the queue is allowed
        (manager -> queue is the permitted lock order), but not required.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------- helpers

    def _join_workers(self, deadline: float | None) -> bool:
        """Join producers, then consumers, against one shared deadline.

        Skips ``threading.current_thread()`` (joining yourself raises
        ``RuntimeError``).

        Returns:
            True if every worker thread has exited.
        """
        raise NotImplementedError

    def _drain_failures(self) -> list[WorkerFailure]:
        """Empty the error channel with ``get_nowait()`` until ``queue.Empty``.

        Do not loop on ``Queue.empty()``: it is only a hint and can race.
        """
        raise NotImplementedError

    def _build_result(self) -> TransferResult:
        """Assemble a ``TransferResult`` from the current state and counts."""
        raise NotImplementedError
