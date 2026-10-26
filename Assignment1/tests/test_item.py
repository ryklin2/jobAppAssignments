"""Tests for Item, the immutable unit of data."""

import dataclasses

import pytest

from producer_consumer.item import Item


def test_item_holds_id_data_and_timestamp() -> None:
    """The three spec fields are stored, and the timestamp defaults to now."""
    item = Item(id=7, data="payload")
    assert (item.id, item.data) == (7, "payload")
    assert item.timestamp > 0


def test_item_is_frozen() -> None:
    """Assigning to any field raises FrozenInstanceError."""
    item = Item(id=1, data="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.id = 2  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.data = "y"  # type: ignore[misc]


def test_item_accepts_an_explicit_timestamp() -> None:
    """A supplied timestamp is kept as given."""
    assert Item(id=1, data="x", timestamp=123.5).timestamp == 123.5


@pytest.mark.parametrize("bad_id", ["1", 1.5, None, True])
def test_item_rejects_non_int_ids(bad_id: object) -> None:
    """A non-int id raises TypeError; bool is rejected on purpose."""
    with pytest.raises(TypeError):
        Item(id=bad_id, data="x")  # type: ignore[arg-type]


def test_item_rejects_invalid_timestamps() -> None:
    """A non-numeric timestamp raises TypeError; a negative one ValueError."""
    with pytest.raises(TypeError):
        Item(id=1, data="x", timestamp="now")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Item(id=1, data="x", timestamp=-1.0)


def test_items_with_equal_fields_are_equal() -> None:
    """Dataclass equality compares all three fields, so ids alone are not enough."""
    assert Item(id=1, data="x", timestamp=5.0) == Item(id=1, data="x", timestamp=5.0)
    assert Item(id=1, data="x", timestamp=5.0) != Item(id=1, data="y", timestamp=5.0)


def test_item_is_hashable_with_an_immutable_payload() -> None:
    """Frozen plus immutable payload means an Item can go in a set or dict key."""
    assert len({Item(id=1, data="x", timestamp=5.0)}) == 1


def test_freezing_is_shallow() -> None:
    """A mutable payload is still mutable: why payloads must be immutable.

    Documents the limitation stated in Item's docstring rather than a
    behaviour to rely on.
    """
    payload: list[int] = []
    item = Item(id=1, data=payload)
    item.data.append(1)
    assert item.data == [1]


def test_item_str_is_short_and_shows_id_and_payload() -> None:
    """__str__ is what appears in status lines and error messages."""
    assert str(Item(id=3, data="payload")) == "Item(3, 'payload')"
