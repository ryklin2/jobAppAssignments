"""Tests for TransferState, QueueStatus and TransferResult."""

import dataclasses

import pytest

from producer_consumer.status import QueueStatus, TransferResult, TransferState


def make_status(**overrides: object) -> QueueStatus:
    """Build a QueueStatus, overriding only the fields a test cares about."""
    fields: dict[str, object] = {
        "state": TransferState.RUNNING,
        "queue_size": 3,
        "capacity": 10,
        "enqueued": 8,
        "dequeued": 5,
        "delivered": 5,
        "active_producers": 1,
        "active_consumers": 1,
        "elapsed_seconds": 1.0,
    }
    fields.update(overrides)
    return QueueStatus(**fields)  # type: ignore[arg-type]


def make_result(**overrides: object) -> TransferResult:
    """Build a TransferResult, overriding only the relevant fields."""
    fields: dict[str, object] = {
        "state": TransferState.COMPLETED,
        "total_items": 10,
        "delivered": 10,
        "elapsed_seconds": 1.0,
    }
    fields.update(overrides)
    return TransferResult(**fields)  # type: ignore[arg-type]


def test_terminal_states() -> None:
    """COMPLETED, STOPPED and FAILED are terminal; CREATED and RUNNING are not."""
    assert TransferState.COMPLETED.is_terminal
    assert TransferState.STOPPED.is_terminal
    assert TransferState.FAILED.is_terminal
    assert not TransferState.CREATED.is_terminal
    assert not TransferState.RUNNING.is_terminal


def test_queue_status_is_immutable() -> None:
    """Assigning to a QueueStatus field raises FrozenInstanceError."""
    status = make_status()
    with pytest.raises(dataclasses.FrozenInstanceError):
        status.queue_size = 99  # type: ignore[misc]


def test_transfer_result_is_immutable() -> None:
    """Assigning to a TransferResult field raises FrozenInstanceError."""
    result = make_result()
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.delivered = 0  # type: ignore[misc]


def test_transfer_result_undelivered() -> None:
    """undelivered == total_items - delivered."""
    assert make_result(total_items=10, delivered=10).undelivered == 0
    assert make_result(total_items=10, delivered=4).undelivered == 6
    assert make_result(total_items=0, delivered=0).undelivered == 0


def test_transfer_result_succeeded_requires_completed_and_all_delivered() -> None:
    """succeeded is False for STOPPED/FAILED or when any item is undelivered."""
    assert make_result(state=TransferState.COMPLETED, delivered=10).succeeded
    # Completed but short of the full set: not a success.
    assert not make_result(state=TransferState.COMPLETED, delivered=9).succeeded
    for state in (TransferState.STOPPED, TransferState.FAILED):
        assert not make_result(state=state, delivered=10).succeeded


def test_empty_transfer_succeeds() -> None:
    """A completed transfer of zero items counts as a success."""
    assert make_result(total_items=0, delivered=0).succeeded
