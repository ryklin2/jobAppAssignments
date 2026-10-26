"""Tests for Producer, calling run() directly where possible.

Skeleton: every test calls pytest.skip("TODO") until implemented.
"""

import pytest

from producer_consumer.producer import Producer  # noqa: F401


def test_producer_enqueues_all_items_then_returns(make_items: object) -> None:
    """With room in the queue, run() enqueues every item in order and returns."""
    pytest.skip("TODO")


def test_producer_returns_promptly_when_stopped_while_queue_full(
    make_items: object,
) -> None:
    """Blocked on a full queue, run() returns within ~poll_interval of a stop."""
    pytest.skip("TODO")


def test_producer_returns_when_queue_closed(make_items: object) -> None:
    """Closing the queue while run() is blocked makes it return without error."""
    pytest.skip("TODO")


def test_producer_shares_source_with_other_producers(make_items: object) -> None:
    """Two producers on one source enqueue every item exactly once between them."""
    pytest.skip("TODO")


def test_producer_propagates_unexpected_errors(make_items: object) -> None:
    """An unexpected exception from the queue propagates out of run()."""
    pytest.skip("TODO")


def test_producer_rejects_invalid_poll_interval_and_delay() -> None:
    """poll_interval <= 0 or delay < 0 raise ValueError."""
    pytest.skip("TODO")
