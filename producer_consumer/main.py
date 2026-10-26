"""Demo: transfer sample items with real-time status output.

Run with ``python -m producer_consumer`` (``--help`` lists the options).
"""

import argparse
import sys
from collections.abc import Sequence

from producer_consumer.item import Item

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_INTERRUPTED = 130


def build_sample_items(count: int) -> list[Item]:
    """Create ``count`` items with ids ``0 .. count - 1``.

    Payloads are immutable strings, matching Item's thread-safety contract.

    Raises:
        ValueError: If ``count`` is negative.
    """
    if count < 0:
        raise ValueError("count must be non-negative")
    return [Item(id=i, data=f"payload-{i:03d}") for i in range(count)]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the demo's command-line options."""
    parser = argparse.ArgumentParser(description="Producer-consumer transfer demo.")
    parser.add_argument("--items", type=int, default=50, help="items to transfer")
    parser.add_argument("--producers", type=int, default=2)
    parser.add_argument("--consumers", type=int, default=2)
    parser.add_argument("--capacity", type=int, default=10)
    parser.add_argument(
        "--producer-delay", type=float, default=0.02, help="seconds per item"
    )
    parser.add_argument(
        "--consumer-delay", type=float, default=0.05, help="seconds per item"
    )
    parser.add_argument(
        "--interval", type=float, default=0.25, help="seconds between status lines"
    )
    parser.add_argument(
        "--timeout", type=float, default=60.0, help="completion timeout in seconds"
    )
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    """Run the demo and return a process exit code.

    Outline:
        1. Parse args; build items; create the Source/Destination containers.
        2. Create the manager and a StatusMonitor (both as context managers).
        3. ``start_transfer()``, then ``wait_for_completion(timeout)``.
        4. Print a summary: delivered/total, elapsed time, and a check that
           destination ids == source ids (no loss, no duplicates).
        5. Return ``EXIT_OK`` on success.

    Error handling:
        ``KeyboardInterrupt`` -> ``stop_transfer()``, print the partial
        result, return ``EXIT_INTERRUPTED``. ``TransferFailedError`` or
        ``TransferTimeoutError`` -> ``stop_transfer()``, print the error to
        stderr, return ``EXIT_FAILED``.

    Defaults make producers faster than consumers, so the queue fills and the
    status lines visibly show producers waiting at 10/10.
    """
    raise NotImplementedError


def main() -> None:
    """Console entry point."""
    sys.exit(run())
