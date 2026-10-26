"""Smoke tests for the Assignment 1 demo.

Skeleton: every test calls pytest.skip("TODO") until implemented.
"""

import pytest

from producer_consumer.main import build_sample_items, run  # noqa: F401


def test_build_sample_items() -> None:
    """build_sample_items(3) returns ids 0, 1, 2; a negative count raises ValueError."""
    pytest.skip("TODO")


def test_main_completes_with_exit_code_zero() -> None:
    """run(['--items', '20', '--producer-delay', '0', '--consumer-delay', '0', '--
    interval', '0.05']) returns 0.
    """
    pytest.skip("TODO")
