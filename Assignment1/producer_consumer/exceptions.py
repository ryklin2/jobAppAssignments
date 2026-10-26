"""Exceptions raised by the producer-consumer transfer system."""


class TransferError(Exception):
    """Base exception for all failures in the transfer system."""


class QueueFullError(TransferError):
    """Raised when an item cannot be enqueued before the timeout expires.

    A blocking enqueue with no timeout waits for space instead of raising.
    """


class QueueEmptyError(TransferError):
    """Raised when no item can be dequeued before the timeout expires.

    A blocking dequeue with no timeout waits for an item instead of raising.
    """


class QueueClosedError(TransferError):
    """Raised when the queue has been closed.

    On enqueue, raised as soon as the queue is closed. On dequeue, raised
    only once the queue is closed AND empty, so consumers drain every
    remaining item first. Consumers treat this as the normal signal that
    all data has been processed.
    """


class TransferTimeoutError(TransferError, TimeoutError):
    """Raised when a transfer does not complete within the allotted time."""


class TransferStateError(TransferError):
    """Raised when a manager method is called in an invalid lifecycle state.

    Examples: starting a transfer twice, or waiting for a transfer that was
    never started.
    """


class TransferFailedError(TransferError):
    """Raised when a worker thread fails during a transfer.

    The worker's original exception is attached as ``__cause__`` (raise it
    with ``raise TransferFailedError(...) from original``).
    """
