"""Consumer: moves items from a SharedQueue into a DestinationContainer."""

from threading import Event

from producer_consumer.containers import DestinationContainer
from producer_consumer.shared_queue import SharedQueue

# Suggested imports for the implementation:
#   from producer_consumer.exceptions import QueueClosedError, QueueEmptyError


class Consumer:
    """Dequeues items and stores them until the closed queue is drained.

    Termination:
        The manager closes the queue after the last producer finishes.
        ``dequeue`` keeps returning items until the closed queue is empty,
        then raises ``QueueClosedError`` and ``run()`` returns. Every item
        produced is therefore delivered before consumers exit.

    Stopping (cooperative interruption):
        ``run()`` checks ``stop_event`` BEFORE each dequeue. Once an item has
        been dequeued it is always delivered, even if a stop arrives, so no
        item is ever dropped from a consumer's hands.

    Thread safety:
        One Consumer instance must be run by one thread at a time. Any number
        of Consumers may share one SharedQueue and one DestinationContainer.
    """

    def __init__(
        self,
        shared_queue: SharedQueue,
        destination_container: DestinationContainer,
        stop_event: Event,
        *,
        name: str = "consumer",
        poll_interval: float = 0.1,
        delay: float = 0.0,
    ) -> None:
        """Create a consumer.

        Args:
            shared_queue: Where items come from.
            destination_container: Where items go (shared, thread-safe).
            stop_event: Set by the manager to request an early stop.
            name: Used as the thread name and in error reports.
            poll_interval: Seconds per bounded dequeue attempt before
                re-checking ``stop_event``.
            delay: Seconds to pause after each item so the demo is visible.
                Implemented as ``stop_event.wait(delay)``.

        Raises:
            ValueError: If ``poll_interval`` <= 0 or ``delay`` < 0.
        """
        raise NotImplementedError

    @property
    def name(self) -> str:
        """The consumer's name."""
        raise NotImplementedError

    def run(self) -> None:
        """Deliver items until the closed queue is drained or a stop arrives.

        Returns normally in both cases. Any other exception propagates to the
        caller; the manager records it and aborts the transfer.

        Outline:
            1. While ``stop_event`` is not set:
               ``item = queue.dequeue(timeout=poll_interval)``;
               on ``QueueEmptyError`` continue (re-check the stop event);
               on ``QueueClosedError`` return (all data processed).
            2. ``destination.add(item)``, always, even if a stop is now set.
            3. If ``delay`` > 0: ``stop_event.wait(delay)``.
        """
        raise NotImplementedError
