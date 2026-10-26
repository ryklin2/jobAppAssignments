"""Tests for TransferState, QueueStatus and TransferResult.

Skeleton: every test calls pytest.skip("TODO") until implemented.
"""

import pytest

from producer_consumer.status import QueueStatus, TransferResult, TransferState  # noqa: F401


def test_terminal_states() -> None:
    """COMPLETED, STOPPED and FAILED are terminal; CREATED and RUNNING are not."""
    pytest.skip("TODO")


def test_queue_status_is_immutable() -> None:
    """Assigning to a QueueStatus field raises FrozenInstanceError."""
    pytest.skip("TODO")


def test_transfer_result_undelivered() -> None:
    """undelivered == total_items - delivered."""
    pytest.skip("TODO")


def test_transfer_result_succeeded_requires_completed_and_all_delivered() -> None:
    """succeeded is False for STOPPED/FAILED or when any item is undelivered."""
    pytest.skip("TODO")
