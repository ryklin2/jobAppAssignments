"""Tests for format_status and StatusMonitor.

Skeleton: every test calls pytest.skip("TODO") until implemented.
"""

import pytest

from producer_consumer.monitor import StatusMonitor, format_status  # noqa: F401


def test_format_status_line() -> None:
    """A known QueueStatus renders the expected line, including the fill bar."""
    pytest.skip("TODO")


def test_format_status_caps_bar_width() -> None:
    """A capacity above MAX_BAR_WIDTH still renders a bar of at most MAX_BAR_WIDTH
    characters.
    """
    pytest.skip("TODO")


def test_monitor_emits_lines_and_final_line_on_stop(make_items: object) -> None:
    """With sink=lines.append, lines appear while running and the last line shows the
    final state.
    """
    pytest.skip("TODO")


def test_monitor_rejects_invalid_interval() -> None:
    """interval <= 0 raises ValueError."""
    pytest.skip("TODO")
