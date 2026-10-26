"""Tests for SourceContainer and DestinationContainer.

Skeleton: every test calls pytest.skip("TODO") until implemented.
"""

import pytest

from producer_consumer.containers import DestinationContainer, SourceContainer  # noqa: F401


def test_source_hands_out_each_item_once_in_order(make_items: object) -> None:
    """take() returns every item exactly once, in original order."""
    pytest.skip("TODO")


def test_source_returns_none_when_exhausted(make_items: object) -> None:
    """After the last item, take() returns None on every call."""
    pytest.skip("TODO")


def test_source_total_and_remaining(make_items: object) -> None:
    """total is fixed; remaining counts down as items are taken."""
    pytest.skip("TODO")


def test_source_rejects_non_items() -> None:
    """Constructing with a non-Item raises TypeError."""
    pytest.skip("TODO")


def test_source_rejects_duplicate_ids() -> None:
    """Two items with the same id raise ValueError."""
    pytest.skip("TODO")


def test_source_is_isolated_from_caller_list(make_items: object) -> None:
    """Mutating the caller's list after construction changes nothing."""
    pytest.skip("TODO")


def test_source_take_is_exactly_once_under_concurrency(
    make_items: object, fast_switching: object
) -> None:
    """Concurrent take() calls get disjoint sets that together cover every item."""
    pytest.skip("TODO")


def test_destination_add_and_snapshot(make_items: object) -> None:
    """add() stores items; snapshot() returns them in delivery order as a tuple."""
    pytest.skip("TODO")


def test_destination_rejects_non_items() -> None:
    """add() with a non-Item raises TypeError."""
    pytest.skip("TODO")


def test_destination_concurrent_adds_lose_nothing(
    make_items: object, fast_switching: object
) -> None:
    """Many threads adding at once: count and ids() match everything added."""
    pytest.skip("TODO")
