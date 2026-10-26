"""Producer: moves items from a SourceContainer into a SharedQueue."""

from threading import Event

from producer_consumer.containers import SourceContainer
from producer_consumer.exceptions import QueueClosedError, QueueFullError
from producer_consumer.item import Item
from producer_consumer.shared_queue import SharedQueue


class Producer:
    """Takes items from a source and enqueues them until the source is empty.

    A Producer does not own a thread. DataTransferManager runs ``run()`` on a
    thread it creates, names and joins. That keeps this class easy to unit
    test: tests call ``run()`` directly on the test thread.

    Stopping (cooperative interruption):
        Python cannot interrupt a thread from outside. ``run()`` checks
        ``stop_event`` before taking each item and between bounded enqueue
        attempts, so a stop is noticed within about ``poll_interval``
        seconds. Closing the queue wakes a blocked enqueue immediately.

    Thread safety:
        One Producer instance must be run by one thread at a time. Any number
        of Producers may share one SourceContainer and one SharedQueue.
    """

    def __init__(
        self,
        source_container: SourceContainer,
        shared_queue: SharedQueue,
        stop_event: Event,
        *,
        name: str = "producer",
        poll_interval: float = 0.1,
        delay: float = 0.0,
    ) -> None:
        """Create a producer.

        Args:
            source_container: Where items come from (shared, thread-safe).
            shared_queue: Where items go.
            stop_event: Set by the manager to request an early stop.
            name: Used as the thread name and in error reports.
            poll_interval: Seconds per bounded enqueue attempt before
                re-checking ``stop_event``.
            delay: Seconds to pause after each item so the demo is visible.
                Implemented as ``stop_event.wait(delay)``, never
                ``time.sleep()``, so a stop interrupts the pause.

        Raises:
            ValueError: If ``poll_interval`` <= 0 or ``delay`` < 0.
        """
        if poll_interval <= 0:
            raise ValueError(f"poll_interval must be > 0, got {poll_interval}")
        if delay < 0:
            raise ValueError(f"delay must be >= 0, got {delay}")

        self._source = source_container
        self._queue = shared_queue
        self._stop_event = stop_event
        self._name = name
        self._poll_interval = poll_interval
        self._delay = delay

    @property
    def name(self) -> str:
        """The producer's name."""
        return self._name

    def run(self) -> None:
        """Enqueue items until the source empties, a stop arrives, or the queue closes.

        Returns normally in all three cases. Any other exception propagates
        to the caller; the manager records it and aborts the transfer.

        Outline:
            1. While ``stop_event`` is not set: ``item = source.take()``;
               if it is ``None``, return.
            2. If ``_enqueue_with_retry(item)`` returns False, return.
            3. If ``delay`` > 0: ``stop_event.wait(delay)``.
            4. Catch ``QueueClosedError`` around the loop and return.

        An item taken but not enqueued because of a stop is not transferred;
        ``TransferResult.undelivered`` accounts for it.
        """
        try:
            while not self._stop_event.is_set():
                item = self._source.take()
                if item is None:
                    return  # Source exhausted: this producer's work is done.
                if not self._enqueue_with_retry(item):
                    return  # Stopped while waiting for space.
                if self._delay > 0:
                    # Event.wait, never time.sleep: a stop cuts the pause short.
                    self._stop_event.wait(self._delay)
        except QueueClosedError:
            # Another worker failed or the transfer was aborted. Not an error
            # for this producer; the manager reports the real cause.
            return

    def _enqueue_with_retry(self, item: Item) -> bool:
        """Enqueue ``item``, retrying each timed-out attempt until stopped.

        Each attempt is ``enqueue(item, timeout=poll_interval)``. A
        ``QueueFullError`` only means that attempt timed out: re-check
        ``stop_event`` and try again.

        Returns:
            True once enqueued; False if ``stop_event`` was set first.

        Raises:
            QueueClosedError: If the queue is closed (handled in ``run()``).
        """
        while not self._stop_event.is_set():
            try:
                self._queue.enqueue(item, timeout=self._poll_interval)
            except QueueFullError:
                # Only this attempt timed out. Re-check the stop event and
                # try again; this is what bounds how long a blocked producer
                # can ignore a stop request.
                continue
            return True
        return False
