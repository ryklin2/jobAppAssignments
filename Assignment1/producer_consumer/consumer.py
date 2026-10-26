"""Consumer: moves items from a SharedQueue into a DestinationContainer."""

from threading import Event

from producer_consumer.containers import DestinationContainer
from producer_consumer.exceptions import QueueClosedError, QueueEmptyError
from producer_consumer.shared_queue import SharedQueue


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
        if poll_interval <= 0:
            raise ValueError(f"poll_interval must be > 0, got {poll_interval}")
        if delay < 0:
            raise ValueError(f"delay must be >= 0, got {delay}")

        self._queue = shared_queue
        self._destination = destination_container
        self._stop_event = stop_event
        self._name = name
        self._poll_interval = poll_interval
        self._delay = delay

    @property
    def name(self) -> str:
        """The consumer's name."""
        return self._name

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
        while not self._stop_event.is_set():
            try:
                item = self._queue.dequeue(timeout=self._poll_interval)
            except QueueEmptyError:
                # Nothing available yet. Re-check the stop event and retry;
                # this bounds how long a blocked consumer ignores a stop.
                continue
            except QueueClosedError:
                # Closed AND drained: every produced item has been handled.
                return

            # Deliver unconditionally. The item is already out of the queue,
            # so bailing out here would silently lose it.
            self._destination.add(item)

            if self._delay > 0:
                self._stop_event.wait(self._delay)
