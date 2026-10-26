"""Producer: moves items from a SourceContainer into a SharedQueue."""

from threading import Event

from producer_consumer.containers import SourceContainer
from producer_consumer.item import Item
from producer_consumer.shared_queue import SharedQueue

# Suggested imports for the implementation:
#   from producer_consumer.exceptions import QueueClosedError, QueueFullError


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
        raise NotImplementedError

    @property
    def name(self) -> str:
        """The producer's name."""
        raise NotImplementedError

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
        raise NotImplementedError

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
        raise NotImplementedError
