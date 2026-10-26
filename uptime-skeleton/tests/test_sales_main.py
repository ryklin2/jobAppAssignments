"""Smoke tests for the Assignment 2 demo.

Skeleton: every test calls pytest.skip("TODO") until implemented.
"""

import pytest

from sales_analytics.main import run  # noqa: F401


def test_main_runs_on_sample_data(capsys: object) -> None:
    """run([]) returns 0 and prints every section heading."""
    pytest.skip("TODO")


def test_main_missing_file_returns_data_error(tmp_path: object, capsys: object) -> None:
    """A missing path returns 2 and prints the error to stderr."""
    pytest.skip("TODO")


def test_main_strict_mode_on_malformed_file_returns_data_error(capsys: object) -> None:
    """run(['data/sales_malformed.csv', '--strict']) returns 2."""
    pytest.skip("TODO")
