"""Smoke tests for the Assignment 1 demo."""

import threading

import pytest

from producer_consumer.containers import DestinationContainer
from producer_consumer.exceptions import TransferFailedError, TransferTimeoutError
from producer_consumer.item import Item
from producer_consumer.main import (
    EXIT_FAILED,
    EXIT_INTERRUPTED,
    EXIT_OK,
    _print_summary,
    build_sample_items,
    main,
    parse_args,
    run,
)
from producer_consumer.manager import DataTransferManager
from producer_consumer.status import TransferResult, TransferState


def _worker_threads() -> list[threading.Thread]:
    """Every live producer/consumer/monitor thread the demo may have leaked."""
    return [
        thread
        for thread in threading.enumerate()
        if thread.name.startswith(("producer-", "consumer-", "status-monitor"))
    ]


FAST_DEMO = [
    "--items",
    "20",
    "--producer-delay",
    "0",
    "--consumer-delay",
    "0",
    "--interval",
    "0.05",
]


def test_build_sample_items() -> None:
    """build_sample_items(3) returns ids 0, 1, 2; a negative count raises ValueError."""
    items = build_sample_items(3)
    assert [item.id for item in items] == [0, 1, 2]
    assert all(isinstance(item, Item) for item in items)
    assert build_sample_items(0) == []
    with pytest.raises(ValueError):
        build_sample_items(-1)


def test_sample_payloads_are_immutable() -> None:
    """Payloads are strings, matching Item's thread-safety contract."""
    assert all(isinstance(item.data, str) for item in build_sample_items(5))


def test_parse_args_defaults_match_the_specification() -> None:
    """The documented demo defaults: 50 items, 2 producers, 2 consumers, capacity 10."""
    args = parse_args([])
    assert (args.items, args.producers, args.consumers, args.capacity) == (
        50,
        2,
        2,
        10,
    )
    # Producers are faster than consumers, so the queue visibly fills up.
    assert args.producer_delay < args.consumer_delay


def test_parse_args_overrides() -> None:
    """Options override the defaults."""
    args = parse_args(["--items", "7", "--producers", "4", "--capacity", "3"])
    assert (args.items, args.producers, args.capacity) == (7, 4, 3)


def test_main_completes_with_exit_code_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """run(['--items', '20', ...]) returns 0 and reports a clean transfer."""
    assert run(FAST_DEMO) == EXIT_OK

    output = capsys.readouterr().out
    assert "COMPLETED" in output
    assert "Delivered:   20/20" in output
    assert "every source id delivered exactly once" in output


def test_main_leaves_no_threads_behind() -> None:
    """Every worker and the monitor are joined before run() returns."""
    before = set(threading.enumerate())
    assert run(FAST_DEMO) == EXIT_OK
    assert set(threading.enumerate()) <= before, "the demo leaked a thread"


def test_main_handles_an_empty_transfer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Zero items is a valid, successful run."""
    assert run(["--items", "0", "--interval", "0.05"]) == EXIT_OK
    assert "Delivered:   0/0" in capsys.readouterr().out


def test_main_runs_with_a_single_producer_and_consumer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The simplest configuration the spec allows still completes."""
    assert (
        run(
            [
                "--items",
                "10",
                "--producers",
                "1",
                "--consumers",
                "1",
                "--producer-delay",
                "0",
                "--consumer-delay",
                "0",
                "--interval",
                "0.05",
            ]
        )
        == EXIT_OK
    )
    assert "Delivered:   10/10" in capsys.readouterr().out


def test_main_reports_a_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ctrl-C stops the transfer, prints the partial result and returns 130."""
    def interrupt(self: DataTransferManager, timeout: float | None = None) -> object:
        raise KeyboardInterrupt

    monkeypatch.setattr(DataTransferManager, "wait_for_completion", interrupt)
    assert run(FAST_DEMO) == EXIT_INTERRUPTED

    output = capsys.readouterr().out
    assert "STOPPED" in output
    assert "Interrupted." in output
    assert not _worker_threads(), "the interrupt left a thread running"


def test_main_reports_a_worker_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failing worker prints the cause to stderr and returns a failure code."""
    cause = RuntimeError("worker exploded")

    def fail(self: DataTransferManager, timeout: float | None = None) -> object:
        raise TransferFailedError("worker consumer-1 failed") from cause

    monkeypatch.setattr(DataTransferManager, "wait_for_completion", fail)
    assert run(FAST_DEMO) == EXIT_FAILED

    captured = capsys.readouterr()
    assert "Transfer failed" in captured.err
    assert "worker exploded" in captured.err
    assert not _worker_threads(), "the failure left a thread running"


def test_main_reports_a_timeout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A transfer that overruns its timeout is aborted and reported."""

    def time_out(self: DataTransferManager, timeout: float | None = None) -> object:
        raise TransferTimeoutError("workers still running")

    monkeypatch.setattr(DataTransferManager, "wait_for_completion", time_out)
    assert run(FAST_DEMO) == EXIT_FAILED
    assert "Transfer failed" in capsys.readouterr().err


def test_main_flags_an_incomplete_transfer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A transfer that ends without delivering everything reports the shortfall."""
    stopped = TransferResult(
        state=TransferState.STOPPED,
        total_items=20,
        delivered=5,
        elapsed_seconds=0.1,
    )

    def stop_early(self: DataTransferManager, timeout: float | None = None) -> object:
        self.stop_transfer()
        return stopped

    monkeypatch.setattr(DataTransferManager, "wait_for_completion", stop_early)
    assert run(FAST_DEMO) == EXIT_FAILED

    output = capsys.readouterr().out
    assert "STOPPED" in output
    assert "Delivered:   5/20" in output
    assert "Undelivered: 15" in output


def test_summary_flags_missing_and_duplicated_items(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The integrity line names a loss or a double delivery instead of hiding it."""
    items = build_sample_items(4)
    destination = DestinationContainer()
    destination.add(items[0])
    destination.add(items[0])  # Delivered twice.
    destination.add(items[1])  # items[2] and items[3] never arrive.
    result = TransferResult(
        state=TransferState.STOPPED, total_items=4, delivered=3, elapsed_seconds=0.1
    )

    _print_summary(result, items, destination)

    output = capsys.readouterr().out
    assert "2 id(s) never delivered" in output
    assert "1 duplicate delivery(ies)" in output


def test_summary_reports_a_clean_run(capsys: pytest.CaptureFixture[str]) -> None:
    """Everything delivered exactly once produces the OK integrity line."""
    items = build_sample_items(3)
    destination = DestinationContainer()
    for item in items:
        destination.add(item)
    result = TransferResult(
        state=TransferState.COMPLETED, total_items=3, delivered=3, elapsed_seconds=0.1
    )

    _print_summary(result, items, destination)

    output = capsys.readouterr().out
    assert "every source id delivered exactly once" in output
    assert "Undelivered" not in output


def test_main_exits_with_the_run_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() hands run()'s exit code to sys.exit, which is what `python -m` uses."""
    monkeypatch.setattr("producer_consumer.main.run", lambda: EXIT_FAILED)
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code == EXIT_FAILED


def test_main_survives_a_stop_that_times_out(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stop that fails while handling an error must not escape run().

    Otherwise the summary is skipped and the process exits on a traceback
    instead of the documented EXIT_FAILED.
    """
    cause = RuntimeError("worker exploded")

    def fail(self: DataTransferManager, timeout: float | None = None) -> object:
        raise TransferFailedError("worker consumer-1 failed") from cause

    def refuse_to_stop(
        self: DataTransferManager, timeout: float | None = 5.0
    ) -> object:
        raise TransferTimeoutError("stop timed out too")

    monkeypatch.setattr(DataTransferManager, "wait_for_completion", fail)
    monkeypatch.setattr(DataTransferManager, "stop_transfer", refuse_to_stop)

    assert run(FAST_DEMO) == EXIT_FAILED
    captured = capsys.readouterr()
    # The summary still ran, and the original cause is still reported.
    assert "Delivered:" in captured.out
    assert "worker exploded" in captured.err


def test_main_reports_an_interrupt_during_start(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ctrl-C while the threads are starting is an interrupt, not a traceback."""
    real_start = DataTransferManager.start_transfer

    def interrupt_on_start(self: DataTransferManager) -> None:
        real_start(self)
        raise KeyboardInterrupt

    monkeypatch.setattr(DataTransferManager, "start_transfer", interrupt_on_start)
    assert run(FAST_DEMO) == EXIT_INTERRUPTED
    assert "Interrupted." in capsys.readouterr().out
    assert not _worker_threads(), "the interrupt left a thread running"


def test_main_reports_a_teardown_failure_after_a_clean_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stop that fails only during teardown is reported, not a traceback."""

    def refuse_to_stop(
        self: DataTransferManager, timeout: float | None = 5.0
    ) -> object:
        raise TransferTimeoutError("teardown stop timed out")

    # wait_for_completion still succeeds; only the context-manager exit fails.
    monkeypatch.setattr(DataTransferManager, "stop_transfer", refuse_to_stop)

    assert run(FAST_DEMO) == EXIT_FAILED
    captured = capsys.readouterr()
    assert "Delivered:   20/20" in captured.out
    assert "teardown stop timed out" in captured.err
