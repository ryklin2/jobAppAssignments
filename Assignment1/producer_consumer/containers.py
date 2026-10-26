"""Thread-safe containers that supply items to producers and collect them."""

from collections.abc import Iterable
from threading import Lock

from producer_consumer.item import Item


class SourceContainer:
    """A fixed set of items that producers take from, one item at a time.

    The items are copied into a tuple at construction, so later changes to
    the caller's list cannot affect a running transfer.

    Thread safety:
        ``take()`` may be called concurrently by any number of producers;
        each item is handed out exactly once, in the original order. A plain
        shared iterator or generator would NOT be safe here: concurrent
        ``next()`` on a generator raises ``ValueError: generator already
        executing``. The only mutable state (the next index) is guarded by
        one lock.
    """

    def __init__(self, items: Iterable[Item]) -> None:
        """Create a source holding ``items``.

        Args:
            items: The items to transfer. Iterated once and copied.

        Raises:
            TypeError: If any element is not an ``Item``.
            ValueError: If two items share the same ``id``. Unique ids are
                what let the manager and the tests prove that nothing was
                lost or duplicated.
        """
        snapshot = tuple(items)
        for item in snapshot:
            if not isinstance(item, Item):
                raise TypeError(
                    f"every element must be an Item, got {type(item).__name__}"
                )
        ids = {item.id for item in snapshot}
        if len(ids) != len(snapshot):
            raise ValueError("item ids must be unique")

        self._items = snapshot
        self._next_index = 0
        self._lock = Lock()

    @property
    def total(self) -> int:
        """Number of items the source started with (immutable; no lock)."""
        return len(self._items)

    @property
    def remaining(self) -> int:
        """Number of items not yet taken.

        Read under the lock but stale as soon as it returns. Never use it to
        decide whether to call ``take()`` (check-then-act race); call
        ``take()`` and check for ``None`` instead.
        """
        with self._lock:
            return len(self._items) - self._next_index

    def take(self) -> Item | None:
        """Hand out the next item, or ``None`` once every item has been taken.

        Returns:
            The next item in original order, or ``None`` when exhausted.
            Every later call also returns ``None``.
        """
        with self._lock:
            # Read-and-advance must be one atomic step. Splitting it would
            # let two producers read the same index and hand out the same
            # item twice; `index += 1` is not atomic on its own either.
            if self._next_index >= len(self._items):
                return None
            item = self._items[self._next_index]
            self._next_index += 1
            return item


class DestinationContainer:
    """Collects the items delivered by consumers.

    Thread safety:
        ``add()`` may be called concurrently by any number of consumers.
        All readers take the same lock and return immutable snapshots, so a
        caller never observes the list mid-update. ``list.append`` happens to
        be atomic in CPython today; relying on that is an implementation
        detail, so the lock makes the guarantee explicit.
    """

    def __init__(self) -> None:
        """Create an empty destination."""
        self._items: list[Item] = []
        self._lock = Lock()

    def add(self, item: Item) -> None:
        """Store a delivered item.

        Raises:
            TypeError: If ``item`` is not an ``Item``.
        """
        if not isinstance(item, Item):
            raise TypeError(f"item must be an Item, got {type(item).__name__}")
        with self._lock:
            self._items.append(item)

    @property
    def count(self) -> int:
        """Number of items delivered so far (a snapshot)."""
        with self._lock:
            return len(self._items)

    def snapshot(self) -> tuple[Item, ...]:
        """Return an immutable copy of the delivered items, in delivery order."""
        with self._lock:
            return tuple(self._items)

    def ids(self) -> frozenset[int]:
        """Return the ids of all delivered items.

        ``len(snapshot()) != len(ids())`` means an item was delivered twice.
        """
        with self._lock:
            return frozenset(item.id for item in self._items)
