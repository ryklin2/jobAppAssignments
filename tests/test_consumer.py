"""Tests for Consumer, calling run() directly where possible.

Skeleton: every test calls pytest.skip("TODO") until implemented.
"""

import pytest

from producer_consumer.consumer import Consumer  # noqa: F401


def test_consumer_drains_closed_queue_then_returns(make_items: object) -> None:
    """Pre-filled closed queue: run() delivers all items in FIFO order, then returns."""
    pytest.skip("TODO")


def test_consumer_returns_promptly_when_stopped_while_queue_empty() -> None:
    """Blocked on an empty queue, run() returns within ~poll_interval of
    stop_event.set().
    """
    pytest.skip("TODO")


def test_consumer_propagates_destination_errors(make_items: object) -> None:
    """A destination whose add() raises makes run() raise the same exception."""
    pytest.skip("TODO")


def test_consumer_rejects_invalid_poll_interval_and_delay() -> None:
    """poll_interval <= 0 or delay < 0 raise ValueError."""
    pytest.skip("TODO")
