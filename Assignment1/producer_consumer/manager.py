"""DataTransferManager: owns the worker threads and the transfer lifecycle."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from types import TracebackType

from producer_consumer.consumer import Consumer
from producer_consumer.containers import DestinationContainer, SourceContainer
from producer_consumer.exceptions import (
    TransferFailedError,
    TransferStateError,
    TransferTimeoutError,
)
from producer_consumer.producer import Producer
from producer_consumer.shared_queue import SharedQueue
from producer_consumer.status import QueueStatus, TransferResult, TransferState

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
        if not isinstance(source_container, SourceContainer):
            raise TypeError("source_container must be a SourceContainer")
        if not isinstance(destination_container, DestinationContainer):
            raise TypeError("destination_container must be a DestinationContainer")
        _check_count("num_producers", num_producers)
        _check_count("num_consumers", num_consumers)
        if poll_interval <= 0:
            raise ValueError(f"poll_interval must be > 0, got {poll_interval}")
        if producer_delay < 0:
            raise ValueError(f"producer_delay must be >= 0, got {producer_delay}")
        if consumer_delay < 0:
            raise ValueError(f"consumer_delay must be >= 0, got {consumer_delay}")

        self._source = source_container
        self._destination = destination_container
        # Capacity validation lives in SharedQueue, the one place that owns it.
        self._queue = SharedQueue(capacity=capacity)

        # Guards the lifecycle state, the timestamps and the active-producer
        # count. Never held while printing or while joining a thread.
        self._lock = threading.Lock()
        self._state = TransferState.CREATED
        self._start_time: float | None = None
        self._end_time: float | None = None

        # Cooperative interruption: Python has no Thread.interrupt(), so a
        # stop is a flag every worker polls between bounded waits.
        self._stop_event = threading.Event()

        # Error channel. A thread-safe queue.Queue is the right tool here:
        # workers only ever put, the controlling thread only ever gets, and
        # no extra lock of ours is involved.
        self._failures: queue.Queue[WorkerFailure] = queue.Queue()

        self._producers = [
            Producer(
                source_container,
                self._queue,
                self._stop_event,
                name=f"producer-{i + 1}",
                poll_interval=poll_interval,
                delay=producer_delay,
            )
            for i in range(num_producers)
        ]
        self._consumers = [
            Consumer(
                self._queue,
                destination_container,
                self._stop_event,
                name=f"consumer-{i + 1}",
                poll_interval=poll_interval,
                delay=consumer_delay,
            )
            for i in range(num_consumers)
        ]
        self._producer_threads: list[threading.Thread] = []
        self._consumer_threads: list[threading.Thread] = []
        self._active_producers = num_producers

    # ----------------------------------------------------------- context manager

    def __enter__(self) -> DataTransferManager:
        """Return the manager; use ``with`` to guarantee threads are stopped."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Stop the transfer if it is still running. Never suppresses errors."""
        self.stop_transfer()

    # ------------------------------------------------------------------- queries

    @property
    def state(self) -> TransferState:
        """Current lifecycle state (read under the manager lock)."""
        with self._lock:
            return self._state

    @property
    def shared_queue(self) -> SharedQueue:
        """The queue between producers and consumers (for tests and status)."""
        return self._queue

    def get_queue_status(self) -> QueueStatus:
        """Return a point-in-time status snapshot. Safe from any thread.

        Queue fields come from one ``SharedQueue.status()`` call (mutually
        consistent). Delivered count and live-thread counts are read
        separately; see ``QueueStatus`` for the consistency note.
        """
        # One call, so these four fields cannot contradict each other.
        snapshot = self._queue.status()
        with self._lock:
            state = self._state
            elapsed = self._elapsed_locked()
        return QueueStatus(
            state=state,
            queue_size=snapshot.size,
            capacity=snapshot.capacity,
            enqueued=snapshot.enqueued,
            dequeued=snapshot.dequeued,
            delivered=self._destination.count,
            active_producers=sum(t.is_alive() for t in self._producer_threads),
            active_consumers=sum(t.is_alive() for t in self._consumer_threads),
            elapsed_seconds=elapsed,
        )

    # ----------------------------------------------------------------- lifecycle

    def start_transfer(self) -> None:
        """Start every worker thread and move to RUNNING.

        Threads are non-daemon and named after their worker (``producer-1``,
        ``consumer-2``) so status output and errors are readable.

        Raises:
            TransferStateError: If the manager is not in CREATED (already
                started, finished, or stopped).
        """
        with self._lock:
            if self._state is not TransferState.CREATED:
                raise TransferStateError(
                    f"cannot start a transfer in state {self._state.value}"
                )
            self._state = TransferState.RUNNING
            self._start_time = time.monotonic()
            self._producer_threads = [
                threading.Thread(
                    target=self._run_producer,
                    args=(producer,),
                    name=producer.name,
                    daemon=False,
                )
                for producer in self._producers
            ]
            self._consumer_threads = [
                threading.Thread(
                    target=self._run_consumer,
                    args=(consumer,),
                    name=consumer.name,
                    daemon=False,
                )
                for consumer in self._consumers
            ]
            threads = [*self._producer_threads, *self._consumer_threads]

        # Started outside the lock: a worker's first action may take the
        # queue lock, and we keep the manager lock hold time short.
        for thread in threads:
            thread.start()

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
        with self._lock:
            if self._state is TransferState.CREATED:
                raise TransferStateError("the transfer was never started")

        # ONE deadline for all joins. Giving each thread its own `timeout`
        # would let n threads take n * timeout seconds in total.
        deadline = None if timeout is None else time.monotonic() + timeout
        if not self._join_workers(deadline):
            raise TransferTimeoutError(
                f"workers still running after {timeout}s; call stop_transfer()"
            )

        failures = self._drain_failures()
        with self._lock:
            if self._end_time is None:
                self._end_time = time.monotonic()
            if failures:
                self._state = TransferState.FAILED
            elif self._state is TransferState.RUNNING:
                self._state = TransferState.COMPLETED

        result = self._build_result()
        if failures:
            first = failures[0]
            raise TransferFailedError(
                f"worker {first.worker_name} failed: {first.error}"
            ) from first.error
        return result

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
        with self._lock:
            if self._state is TransferState.CREATED:
                # Nothing was ever started, so there is nothing to join.
                self._state = TransferState.STOPPED
                self._end_time = self._start_time = time.monotonic()
                return self._build_result_locked()
            if self._state.is_terminal:
                return self._build_result_locked()

        # Both signals are needed: the event releases workers that are
        # polling between bounded waits, and closing the queue wakes the
        # ones blocked inside a wait right now.
        self._stop_event.set()
        self._queue.close()

        deadline = None if timeout is None else time.monotonic() + timeout
        joined = self._join_workers(deadline)

        with self._lock:
            if self._end_time is None:
                self._end_time = time.monotonic()
            if self._state is TransferState.RUNNING:
                self._state = TransferState.STOPPED
            result = self._build_result_locked()

        if not joined:
            raise TransferTimeoutError(
                f"workers still running {timeout}s after the stop request"
            )
        return result

    # ------------------------------------------------------- worker thread bodies

    def _run_producer(self, producer: Producer) -> None:
        """Thread target for a producer.

        ``try: producer.run()`` / ``except Exception as e:
        self._record_failure(producer.name, e)`` / ``finally:`` decrement the
        active-producer count under the lock; if it reached zero, close the
        queue (closing is idempotent).
        """
        try:
            producer.run()
        except Exception as error:  # noqa: BLE001 - reported, never swallowed
            self._record_failure(producer.name, error)
        finally:
            # The CountDownLatch analog: whoever turns the count to zero
            # closes the queue. In `finally`, so a crashed producer still
            # counts down and consumers can never hang waiting for it.
            with self._lock:
                self._active_producers -= 1
                is_last = self._active_producers == 0
            if is_last:
                self._queue.close()

    def _run_consumer(self, consumer: Consumer) -> None:
        """Thread target for a consumer: run it; report any exception."""
        try:
            consumer.run()
        except Exception as error:  # noqa: BLE001 - reported, never swallowed
            self._record_failure(consumer.name, error)

    def _record_failure(self, worker_name: str, error: Exception) -> None:
        """Put a ``WorkerFailure`` on the error channel, then abort.

        Sets the stop event and closes the queue so every other worker wakes
        and exits. Holding the manager lock while closing the queue is allowed
        (manager -> queue is the permitted lock order), but not required.
        """
        self._failures.put(WorkerFailure(worker_name=worker_name, error=error))
        # Fail fast: without these two lines a producer blocked on a full
        # queue would wait forever for a consumer that has already died.
        self._stop_event.set()
        self._queue.close()

    # ------------------------------------------------------------------- helpers

    def _join_workers(self, deadline: float | None) -> bool:
        """Join producers, then consumers, against one shared deadline.

        Skips ``threading.current_thread()`` (joining yourself raises
        ``RuntimeError``).

        Returns:
            True if every worker thread has exited.
        """
        current = threading.current_thread()
        all_done = True
        # Producers first: they are what close the queue and so let the
        # consumers finish.
        for thread in (*self._producer_threads, *self._consumer_threads):
            if thread is current:
                continue
            if deadline is None:
                thread.join()
            else:
                thread.join(max(0.0, deadline - time.monotonic()))
            # join() returns silently on timeout, so ask explicitly.
            if thread.is_alive():
                all_done = False
        return all_done

    def _drain_failures(self) -> list[WorkerFailure]:
        """Empty the error channel with ``get_nowait()`` until ``queue.Empty``.

        Do not loop on ``Queue.empty()``: it is only a hint and can race.
        """
        failures: list[WorkerFailure] = []
        while True:
            try:
                failures.append(self._failures.get_nowait())
            except queue.Empty:
                return failures

    def _build_result(self) -> TransferResult:
        """Assemble a ``TransferResult`` from the current state and counts."""
        with self._lock:
            return self._build_result_locked()

    def _build_result_locked(self) -> TransferResult:
        """Same as ``_build_result``, for callers already holding the lock."""
        return TransferResult(
            state=self._state,
            total_items=self._source.total,
            delivered=self._destination.count,
            elapsed_seconds=self._elapsed_locked(),
        )

    def _elapsed_locked(self) -> float:
        """Seconds the transfer has been running. The lock must be held."""
        if self._start_time is None:
            return 0.0
        end = self._end_time if self._end_time is not None else time.monotonic()
        return end - self._start_time


def _check_count(name: str, value: int) -> None:
    """Validate a worker count.

    Raises:
        TypeError: If ``value`` is not an int. ``bool`` is rejected on
            purpose: ``num_producers=True`` almost certainly means the caller
            confused a flag for a count.
        ValueError: If ``value`` < 1.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, got {type(value).__name__}")
    if value < 1:
        raise ValueError(f"{name} must be at least 1, got {value}")
