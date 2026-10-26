"""Lifecycle state and status types reported by DataTransferManager.

Thread safety:
    Every type here is an immutable value object and can be shared between
    threads freely.
"""

from dataclasses import dataclass
from enum import Enum


class TransferState(Enum):
    """Lifecycle state of a DataTransferManager.

    Transitions: CREATED -> RUNNING -> COMPLETED | STOPPED | FAILED, plus
    CREATED -> STOPPED (stopped before it started). Terminal states never
    change again.
    """

    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        """Whether no further transition is possible from this state."""
        return self in _TERMINAL_STATES


_TERMINAL_STATES = frozenset(
    {TransferState.COMPLETED, TransferState.STOPPED, TransferState.FAILED}
)


@dataclass(frozen=True, slots=True)
class QueueStatus:
    """A point-in-time view of a transfer, returned by ``get_queue_status()``.

    Attributes:
        state: Current lifecycle state.
        queue_size: Items currently in the shared queue.
        capacity: Maximum number of items the queue can hold.
        enqueued: Total items producers have put on the queue.
        dequeued: Total items consumers have taken off the queue.
        delivered: Items stored in the destination container.
        active_producers: Producer threads still alive.
        active_consumers: Consumer threads still alive.
        elapsed_seconds: Seconds since ``start_transfer()`` (0.0 before).

    Consistency:
        ``queue_size``, ``capacity``, ``enqueued`` and ``dequeued`` come from
        a single ``SharedQueue.status()`` call, so
        ``queue_size == enqueued - dequeued`` always holds. ``delivered`` and
        the thread counts are read separately and may lag by items in flight
        between dequeue and delivery.
    """

    state: TransferState
    queue_size: int
    capacity: int
    enqueued: int
    dequeued: int
    delivered: int
    active_producers: int
    active_consumers: int
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class TransferResult:
    """The outcome of a transfer.

    Returned by ``wait_for_completion()`` and ``stop_transfer()``.

    Attributes:
        state: Final lifecycle state.
        total_items: Items the source started with.
        delivered: Items stored in the destination.
        elapsed_seconds: Seconds from start to the end of the transfer.
    """

    state: TransferState
    total_items: int
    delivered: int
    elapsed_seconds: float

    @property
    def undelivered(self) -> int:
        """Items that never reached the destination (after a stop/failure)."""
        return self.total_items - self.delivered

    @property
    def succeeded(self) -> bool:
        """True only if the transfer completed and every item was delivered."""
        return self.state is TransferState.COMPLETED and self.undelivered == 0
