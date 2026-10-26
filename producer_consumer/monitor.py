"""Real-time status output for a running transfer."""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import TYPE_CHECKING

from producer_consumer.status import QueueStatus

if TYPE_CHECKING:
    from producer_consumer.manager import DataTransferManager

# Suggested import for the implementation: import threading

MAX_BAR_WIDTH = 20


def format_status(status: QueueStatus) -> str:
    """Render one status line for ``status``.

    Example::

        [  1.25s] RUNNING    queue  7/10 [#######...] enq  31 deq  24 done  24 | P 2 C 2

    The bar uses one character per queue slot ('#' used, '.' free), capped
    at ``MAX_BAR_WIDTH`` characters (scale it for larger capacities).
    """
    raise NotImplementedError


class StatusMonitor:
    """Prints transfer status at a fixed interval from one background thread.

    Only this thread writes status lines, so output never interleaves;
    workers themselves never print.

    Thread safety:
        ``start()`` and ``stop()`` are meant to be called by one controlling
        thread (normally main). The monitor only reads status through
        ``manager.get_queue_status()``, which is thread-safe.
    """

    def __init__(
        self,
        manager: DataTransferManager,
        *,
        interval: float = 0.25,
        sink: Callable[[str], None] = print,
    ) -> None:
        """Create a monitor (not started).

        Args:
            manager: The transfer to report on.
            interval: Seconds between status lines.
            sink: Receives each formatted line. Tests pass ``lines.append``.

        Raises:
            ValueError: If ``interval`` <= 0.
        """
        raise NotImplementedError

    def start(self) -> None:
        """Start the monitor thread (non-daemon, named ``status-monitor``).

        Raises:
            RuntimeError: If the monitor was already started.
        """
        raise NotImplementedError

    def stop(self, timeout: float | None = 2.0) -> None:
        """Signal the thread to stop and join it. Idempotent.

        The thread emits one final status line on its way out, so the last
        line printed always shows the finished state.
        """
        raise NotImplementedError

    def __enter__(self) -> StatusMonitor:
        """Start the monitor and return it."""
        raise NotImplementedError

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Stop the monitor. Never suppresses errors."""
        raise NotImplementedError

    def _run(self) -> None:
        """Thread body: ``while not stop_event.wait(interval)``, emit a line.

        ``Event.wait`` returns True as soon as a stop is requested, so the
        monitor exits promptly instead of finishing a sleep. Emit one final
        line after the loop.
        """
        raise NotImplementedError
