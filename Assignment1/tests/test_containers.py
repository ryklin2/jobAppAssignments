"""Tests for SourceContainer and DestinationContainer."""

import threading
from collections.abc import Callable

import pytest

from producer_consumer.containers import DestinationContainer, SourceContainer
from producer_consumer.item import Item

TIMING_SLACK = 5.0


def test_source_hands_out_each_item_once_in_order(
    make_items: Callable[[int], list[Item]],
) -> None:
    """take() returns every item exactly once, in original order."""
    items = make_items(5)
    source = SourceContainer(items)
    assert [source.take() for _ in items] == items


def test_source_returns_none_when_exhausted(
    make_items: Callable[[int], list[Item]],
) -> None:
    """After the last item, take() returns None on every call."""
    source = SourceContainer(make_items(1))
    assert source.take() is not None
    assert source.take() is None
    assert source.take() is None


def test_source_total_and_remaining(make_items: Callable[[int], list[Item]]) -> None:
    """total is fixed; remaining counts down as items are taken."""
    source = SourceContainer(make_items(3))
    assert (source.total, source.remaining) == (3, 3)
    source.take()
    assert (source.total, source.remaining) == (3, 2)
    source.take()
    source.take()
    assert (source.total, source.remaining) == (3, 0)
    source.take()  # Exhausted: remaining must not go negative.
    assert source.remaining == 0


def test_empty_source_is_immediately_exhausted() -> None:
    """A source with no items reports zero and hands out nothing."""
    source = SourceContainer([])
    assert (source.total, source.remaining) == (0, 0)
    assert source.take() is None


def test_source_accepts_any_iterable(make_items: Callable[[int], list[Item]]) -> None:
    """A generator is consumed once at construction, not held as an iterator."""
    source = SourceContainer(item for item in make_items(3))
    assert source.total == 3
    assert [source.take() for _ in range(3)] != [None, None, None]


def test_source_rejects_non_items() -> None:
    """Constructing with a non-Item raises TypeError."""
    with pytest.raises(TypeError):
        SourceContainer(["not an item"])  # type: ignore[list-item]
    with pytest.raises(TypeError):
        SourceContainer([Item(id=0, data="a"), None])  # type: ignore[list-item]


def test_source_rejects_duplicate_ids() -> None:
    """Two items with the same id raise ValueError."""
    with pytest.raises(ValueError):
        SourceContainer([Item(id=1, data="a"), Item(id=1, data="b")])


def test_source_is_isolated_from_caller_list(
    make_items: Callable[[int], list[Item]],
) -> None:
    """Mutating the caller's list after construction changes nothing."""
    items = make_items(2)
    source = SourceContainer(items)
    items.append(Item(id=99, data="late"))
    items.clear()
    assert source.total == 2
    assert {item.id for item in (source.take(), source.take())} == {0, 1}  # type: ignore[union-attr]


def test_source_take_is_exactly_once_under_concurrency(
    make_items: Callable[[int], list[Item]], fast_switching: None
) -> None:
    """Concurrent take() calls get disjoint sets that together cover every item."""
    items = make_items(500)
    source = SourceContainer(items)
    taken: list[list[Item]] = [[] for _ in range(8)]
    barrier = threading.Barrier(len(taken))

    def drain(slot: int) -> None:
        # Start together, so the threads actually contend for the lock.
        barrier.wait()
        while True:
            item = source.take()
            if item is None:
                return
            taken[slot].append(item)

    threads = [
        threading.Thread(target=drain, args=(slot,)) for slot in range(len(taken))
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(TIMING_SLACK)

    collected = [item for slot in taken for item in slot]
    assert len(collected) == len(items), "an item was handed out twice or lost"
    assert {item.id for item in collected} == {item.id for item in items}
    assert source.remaining == 0
    # Each thread's own slice stays in ascending id order: the lock hands
    # out indices monotonically, it does not shuffle them.
    for slot in taken:
        assert [item.id for item in slot] == sorted(item.id for item in slot)


def test_destination_add_and_snapshot(
    make_items: Callable[[int], list[Item]],
) -> None:
    """add() stores items; snapshot() returns them in delivery order as a tuple."""
    destination = DestinationContainer()
    assert destination.count == 0
    assert destination.snapshot() == ()
    assert destination.ids() == frozenset()

    items = make_items(3)
    for item in reversed(items):
        destination.add(item)
    assert destination.count == 3
    assert destination.snapshot() == tuple(reversed(items))
    assert destination.ids() == {item.id for item in items}


def test_destination_snapshot_is_detached(
    make_items: Callable[[int], list[Item]],
) -> None:
    """A snapshot taken earlier does not change when more items arrive."""
    destination = DestinationContainer()
    items = make_items(2)
    destination.add(items[0])
    snapshot = destination.snapshot()
    destination.add(items[1])
    assert snapshot == (items[0],)


def test_destination_rejects_non_items() -> None:
    """add() with a non-Item raises TypeError."""
    destination = DestinationContainer()
    with pytest.raises(TypeError):
        destination.add("not an item")  # type: ignore[arg-type]
    assert destination.count == 0


def test_destination_concurrent_adds_lose_nothing(
    make_items: Callable[[int], list[Item]], fast_switching: None
) -> None:
    """Many threads adding at once: count and ids() match everything added."""
    items = make_items(800)
    destination = DestinationContainer()
    workers = 8
    chunk = len(items) // workers
    barrier = threading.Barrier(workers)

    def add_chunk(slot: int) -> None:
        barrier.wait()
        for item in items[slot * chunk : (slot + 1) * chunk]:
            destination.add(item)

    threads = [threading.Thread(target=add_chunk, args=(s,)) for s in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(TIMING_SLACK)

    assert destination.count == len(items), "a concurrent add was lost"
    assert len(destination.snapshot()) == len(items)
    # Equal lengths prove no item was delivered twice.
    assert destination.ids() == {item.id for item in items}
    assert len(destination.snapshot()) == len(destination.ids())
