"""Item: the immutable unit of data moved from source to destination."""

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Item:
    """One unit of data in transit.

    Attributes:
        id: Unique identifier. Producers and consumers never change it, and
            the tests use it to prove that nothing was lost or duplicated.
        data: The payload. Must be immutable (see the thread-safety note).
        timestamp: Unix time at creation, filled in automatically.

    Thread safety:
        Frozen, so no thread can mutate an Item after construction, and an
        Item needs no lock to be shared. Freezing is shallow: a mutable
        payload (list, dict, set) is still mutable through ``data``, so
        payloads must be immutable (str, int, tuple, frozenset) for the
        guarantee to hold end to end.
    """

    id: int
    data: Any
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        """Validate the identifier and timestamp.

        Raises:
            TypeError: If ``id`` is not an int (bools rejected), or
                ``timestamp`` is not a real number.
            ValueError: If ``timestamp`` is negative.
        """
        if isinstance(self.id, bool) or not isinstance(self.id, int):
            raise TypeError(f"id must be an int, got {type(self.id).__name__}")
        if isinstance(self.timestamp, bool) or not isinstance(
            self.timestamp, (int, float)
        ):
            raise TypeError(
                f"timestamp must be a number, got {type(self.timestamp).__name__}"
            )
        if self.timestamp < 0:
            raise ValueError("timestamp must be non-negative")

    def __str__(self) -> str:
        """Short form used in status and error messages."""
        return f"Item({self.id}, {self.data!r})"
