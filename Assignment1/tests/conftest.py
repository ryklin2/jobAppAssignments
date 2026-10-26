"""Shared pytest fixtures for the producer-consumer tests."""

import sys
from collections.abc import Callable, Iterator

import pytest

from producer_consumer.item import Item


@pytest.fixture
def fast_switching() -> Iterator[None]:
    """Force a thread switch roughly every microsecond to surface races."""
    original = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        yield
    finally:
        sys.setswitchinterval(original)


@pytest.fixture
def make_items() -> Callable[[int], list[Item]]:
    """Return a factory that builds ``count`` items with ids 0..count-1."""

    def _make(count: int) -> list[Item]:
        return [Item(id=i, data=f"item-{i}") for i in range(count)]

    return _make
