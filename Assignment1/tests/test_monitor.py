"""Tests for format_status and StatusMonitor."""

import threading
from collections.abc import Callable

import pytest

from producer_consumer.containers import DestinationContainer, SourceContainer
from producer_consumer.item import Item
from producer_consumer.manager import DataTransferManager
from producer_consumer.monitor import MAX_BAR_WIDTH, StatusMonitor, format_status
from producer_consumer.status import QueueStatus, TransferState

TIMING_SLACK = 5.0
POLL = 0.05


def make_status(**overrides: object) -> QueueStatus:
    """Build a QueueStatus, overriding only the fields a test cares about."""
    fields: dict[str, object] = {
        "state": TransferState.RUNNING,
        "queue_size": 7,
        "capacity": 10,
        "enqueued": 31,
        "dequeued": 24,
        "delivered": 24,
        "active_producers": 2,
        "active_consumers": 2,
        "elapsed_seconds": 1.25,
    }
    fields.update(overrides)
    return QueueStatus(**fields)  # type: ignore[arg-type]


def bar_of(line: str) -> str:
    """Extract the fill bar from a formatted status line.

    Anchored on "queue", so the "[" of the leading timestamp is skipped.
    """
    start = line.index("[", line.index("queue"))
    return line[start + 1 : line.index("]", start)]


def test_format_status_line() -> None:
    """A known QueueStatus renders the expected line, including the fill bar."""
    assert format_status(make_status()) == (
        "[  1.25s] RUNNING    queue  7/10 [#######...] "
        "enq  31 deq  24 done  24 | P 2 C 2"
    )


def test_format_status_shows_an_empty_and_a_full_queue() -> None:
    """The bar's two extremes render as all free and all used slots."""
    assert bar_of(format_status(make_status(queue_size=0))) == "." * 10
    assert bar_of(format_status(make_status(queue_size=10))) == "#" * 10


def test_format_status_caps_bar_width() -> None:
    """A capacity above MAX_BAR_WIDTH still renders a bar of at most MAX_BAR_WIDTH
    characters.
    """
    for size in (0, 37, 500, 1000):
        bar = bar_of(format_status(make_status(queue_size=size, capacity=1000)))
        assert len(bar) == MAX_BAR_WIDTH
    # It still scales rather than rounding everything to empty or full.
    assert bar_of(format_status(make_status(queue_size=500, capacity=1000))) == (
        "#" * (MAX_BAR_WIDTH // 2) + "." * (MAX_BAR_WIDTH // 2)
    )


def test_format_status_includes_the_state_name() -> None:
    """Each lifecycle state appears by name, so the line is self-describing."""
    for state in TransferState:
        assert state.name in format_status(make_status(state=state))


def test_monitor_emits_lines_and_final_line_on_stop(
    make_items: Callable[[int], list[Item]],
) -> None:
    """With sink=lines.append, lines appear while running and the last line shows the
    final state.
    """
    lines: list[str] = []
    manager = DataTransferManager(
        SourceContainer(make_items(60)),
        DestinationContainer(),
        num_consumers=2,
        poll_interval=POLL,
        consumer_delay=0.01,
    )
    monitor = StatusMonitor(manager, interval=0.02, sink=lines.append)

    with monitor:
        manager.start_transfer()
        result = manager.wait_for_completion(timeout=TIMING_SLACK * 2)

    assert result.succeeded
    assert len(lines) >= 2, "the monitor emitted no periodic lines"
    # The final line is emitted on the way out, so it shows the end state.
    assert "COMPLETED" in lines[-1]
    assert "done  60" in lines[-1]
    assert all(line.startswith("[") for line in lines)


def test_monitor_stop_is_idempotent(
    make_items: Callable[[int], list[Item]],
) -> None:
    """stop() twice is safe, and the thread is gone afterwards."""
    lines: list[str] = []
    manager = DataTransferManager(
        SourceContainer(make_items(5)), DestinationContainer(), poll_interval=POLL
    )
    monitor = StatusMonitor(manager, interval=0.02, sink=lines.append)
    monitor.start()
    monitor.stop(timeout=TIMING_SLACK)
    monitor.stop(timeout=TIMING_SLACK)

    assert lines, "stop() should still emit the final line"
    assert not any(
        thread.name == "status-monitor" for thread in threading.enumerate()
    ), "the monitor thread outlived stop()"


def test_monitor_cannot_be_started_twice(
    make_items: Callable[[int], list[Item]],
) -> None:
    """A second start() raises RuntimeError rather than leaking a second thread."""
    manager = DataTransferManager(
        SourceContainer(make_items(5)), DestinationContainer(), poll_interval=POLL
    )
    monitor = StatusMonitor(manager, interval=0.05, sink=lambda _: None)
    monitor.start()
    try:
        with pytest.raises(RuntimeError):
            monitor.start()
    finally:
        monitor.stop(timeout=TIMING_SLACK)


def test_monitor_stop_without_start_is_harmless(
    make_items: Callable[[int], list[Item]],
) -> None:
    """stop() on a monitor that was never started does nothing and does not raise."""
    manager = DataTransferManager(
        SourceContainer(make_items(5)), DestinationContainer(), poll_interval=POLL
    )
    StatusMonitor(manager, sink=lambda _: None).stop(timeout=TIMING_SLACK)


def test_monitor_exits_promptly_despite_a_long_interval(
    make_items: Callable[[int], list[Item]],
) -> None:
    """A stop does not wait out the interval: Event.wait, not time.sleep."""
    manager = DataTransferManager(
        SourceContainer(make_items(5)), DestinationContainer(), poll_interval=POLL
    )
    monitor = StatusMonitor(manager, interval=30.0, sink=lambda _: None)
    monitor.start()
    # pytest-timeout fails this test if stop() sits out the 30s interval.
    monitor.stop(timeout=TIMING_SLACK)
    assert not any(
        thread.name == "status-monitor" for thread in threading.enumerate()
    )


@pytest.mark.parametrize("interval", [0, -1, -0.5])
def test_monitor_rejects_invalid_interval(interval: float) -> None:
    """interval <= 0 raises ValueError."""
    manager = DataTransferManager(SourceContainer([]), DestinationContainer())
    with pytest.raises(ValueError):
        StatusMonitor(manager, interval=interval)
