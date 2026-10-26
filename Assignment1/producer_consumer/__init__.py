"""Producer-consumer data transfer with explicit thread synchronization.

Submodules import from each other by full module path (never
``from producer_consumer import X``) to avoid circular imports.
"""

from producer_consumer.consumer import Consumer
from producer_consumer.containers import DestinationContainer, SourceContainer
from producer_consumer.exceptions import (
    QueueClosedError,
    QueueEmptyError,
    QueueFullError,
    TransferError,
    TransferFailedError,
    TransferStateError,
    TransferTimeoutError,
)
from producer_consumer.item import Item
from producer_consumer.manager import DataTransferManager
from producer_consumer.monitor import StatusMonitor
from producer_consumer.producer import Producer
from producer_consumer.shared_queue import QueueSnapshot, SharedQueue
from producer_consumer.status import QueueStatus, TransferResult, TransferState

__all__ = [
    "Consumer",
    "DataTransferManager",
    "DestinationContainer",
    "Item",
    "Producer",
    "QueueClosedError",
    "QueueEmptyError",
    "QueueFullError",
    "QueueSnapshot",
    "QueueStatus",
    "SharedQueue",
    "SourceContainer",
    "StatusMonitor",
    "TransferError",
    "TransferFailedError",
    "TransferResult",
    "TransferState",
    "TransferStateError",
    "TransferTimeoutError",
]
