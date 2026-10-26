"""Demo: transfer sample items with real-time status output.

Run with ``python -m producer_consumer`` (``--help`` lists the options).
"""

import argparse
import sys
from collections.abc import Sequence

from producer_consumer.containers import DestinationContainer, SourceContainer
from producer_consumer.exceptions import (
    TransferError,
    TransferFailedError,
    TransferTimeoutError,
)
from producer_consumer.item import Item
from producer_consumer.manager import DataTransferManager
from producer_consumer.monitor import StatusMonitor
from producer_consumer.status import TransferResult

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
    args = parse_args(argv)
    items = build_sample_items(args.items)
    source = SourceContainer(items)
    destination = DestinationContainer()

    print(
        f"Transferring {len(items)} items with {args.producers} producer(s) "
        f"and {args.consumers} consumer(s), queue capacity {args.capacity}."
    )

    manager = DataTransferManager(
        source,
        destination,
        capacity=args.capacity,
        num_producers=args.producers,
        num_consumers=args.consumers,
        producer_delay=args.producer_delay,
        consumer_delay=args.consumer_delay,
    )

    error: TransferError | None = None
    exit_code = EXIT_OK

    # Both context managers guarantee the worker threads and the monitor
    # thread are joined on every exit path, including Ctrl-C.
    with manager, StatusMonitor(manager, interval=args.interval):
        manager.start_transfer()
        try:
            result = manager.wait_for_completion(timeout=args.timeout)
        except KeyboardInterrupt:
            result = manager.stop_transfer()
            exit_code = EXIT_INTERRUPTED
        except (TransferFailedError, TransferTimeoutError) as failure:
            error = failure
            # The transfer is already terminal after a failure, so this just
            # collects the final numbers; after a timeout it aborts the run.
            result = manager.stop_transfer()
            exit_code = EXIT_FAILED

    # Printed after the `with` block so the monitor's final status line does
    # not land in the middle of the summary.
    _print_summary(result, items, destination)
    if error is not None:
        print(f"\nTransfer failed: {error}", file=sys.stderr)
        if error.__cause__ is not None:
            print(f"  caused by: {error.__cause__!r}", file=sys.stderr)
    elif exit_code == EXIT_INTERRUPTED:
        print("\nInterrupted.")

    if exit_code == EXIT_OK and not result.succeeded:
        return EXIT_FAILED
    return exit_code


def _print_summary(
    result: TransferResult,
    items: Sequence[Item],
    destination: DestinationContainer,
) -> None:
    """Print the end-of-run summary, including the no-loss/no-duplicate check."""
    delivered = destination.snapshot()
    delivered_ids = destination.ids()
    expected_ids = frozenset(item.id for item in items)

    print()
    print(f"State:       {result.state.name}")
    print(f"Delivered:   {result.delivered}/{result.total_items}")
    if result.undelivered:
        print(f"Undelivered: {result.undelivered}")
    print(f"Elapsed:     {result.elapsed_seconds:.2f}s")

    # len(snapshot) counts deliveries; len(ids) counts distinct items. They
    # differ only if an item was delivered twice.
    duplicates = len(delivered) - len(delivered_ids)
    missing = sorted(expected_ids - delivered_ids)
    if not missing and not duplicates:
        print("Integrity:   OK - every source id delivered exactly once")
    else:
        print(
            f"Integrity:   {len(missing)} id(s) never delivered, "
            f"{duplicates} duplicate delivery(ies)"
        )


def main() -> None:
    """Console entry point."""
    sys.exit(run())
