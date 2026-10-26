"""Real-time status output for a running transfer."""

from __future__ import annotations

import threading
from collections.abc import Callable
from types import TracebackType
from typing import TYPE_CHECKING

from producer_consumer.status import QueueStatus

if TYPE_CHECKING:
    from producer_consumer.manager import DataTransferManager

MAX_BAR_WIDTH = 20


def format_status(status: QueueStatus) -> str:
    """Render one status line for ``status``.

    Example::

        [  1.25s] RUNNING    queue  7/10 [#######...] enq  31 deq  24 done  24 | P 2 C 2

    The bar uses one character per queue slot ('#' used, '.' free), capped
    at ``MAX_BAR_WIDTH`` characters (scale it for larger capacities).
    """
    width = min(status.capacity, MAX_BAR_WIDTH)
    # Integer maths, so the bar is never one character too long through
    # floating-point rounding.
    filled = (width * status.queue_size) // status.capacity if status.capacity else 0
    filled = max(0, min(width, filled))
    if filled == 0 and status.queue_size > 0:
        # A scaled bar floors small fills to zero (4 of 100 slots -> 0), which
        # would draw a non-empty queue as empty. Show at least one mark.
        filled = 1
    bar = "#" * filled + "." * (width - filled)
    return (
        f"[{status.elapsed_seconds:6.2f}s] "
        f"{status.state.name:<10} "
        f"queue {status.queue_size:>2}/{status.capacity} [{bar}] "
        f"enq {status.enqueued:>3} deq {status.dequeued:>3} "
        f"done {status.delivered:>3} "
        f"| P {status.active_producers} C {status.active_consumers}"
    )


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
        if interval <= 0:
            raise ValueError(f"interval must be > 0, got {interval}")
        self._manager = manager
        self._interval = interval
        self._sink = sink
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # Separate from `_thread`, which stop() may clear: a monitor is
        # single use, because its stop Event has already been set and a
        # Python thread cannot be restarted.
        self._started = False

    def start(self) -> None:
        """Start the monitor thread (non-daemon, named ``status-monitor``).

        Single use: a monitor that has been stopped cannot be restarted.

        Raises:
            RuntimeError: If the monitor was already started, whether or not
                it has since been stopped. Restarting silently would hand
                back a monitor whose stop Event is already set, which would
                emit one line and exit.
        """
        if self._started:
            raise RuntimeError("the monitor has already been started")
        self._started = True
        self._thread = threading.Thread(
            target=self._run, name="status-monitor", daemon=False
        )
        self._thread.start()

    def stop(self, timeout: float | None = 2.0) -> None:
        """Signal the thread to stop and join it. Idempotent.

        The thread emits one final status line on its way out, so the last
        line printed always shows the finished state.

        If the join times out, the thread reference is kept so a later
        ``stop()`` can join it again. Dropping it would abandon a live
        non-daemon thread, which would keep the process from exiting while
        this method reported success. Use ``is_running()`` to check.
        """
        self._stop_event.set()
        if self._thread is None:
            return
        self._thread.join(timeout)
        if not self._thread.is_alive():
            self._thread = None

    def is_running(self) -> bool:
        """Whether the monitor thread is still alive.

        False before ``start()`` and after a ``stop()`` that joined
        successfully; True if a ``stop()`` timed out and the thread is still
        finishing.
        """
        return self._thread is not None and self._thread.is_alive()

    def __enter__(self) -> StatusMonitor:
        """Start the monitor and return it."""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Stop the monitor. Never suppresses errors."""
        self.stop()

    def _run(self) -> None:
        """Thread body: ``while not stop_event.wait(interval)``, emit a line.

        ``Event.wait`` returns True as soon as a stop is requested, so the
        monitor exits promptly instead of finishing a sleep. Emit one final
        line after the loop.
        """
        # wait() both paces the loop and listens for the stop, so there is
        # no time.sleep to sit through before noticing one.
        while not self._stop_event.wait(self._interval):
            self._emit()
        self._emit()

    def _emit(self) -> None:
        """Render and hand one status line to the sink."""
        self._sink(format_status(self._manager.get_queue_status()))
