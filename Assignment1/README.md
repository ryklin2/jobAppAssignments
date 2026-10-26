# Assignment 1: Producer-Consumer with Thread Synchronization

Producers move items from a source container into a shared bounded queue
(capacity 10); consumers move them into a destination container. All
coordination uses Python's `threading` primitives, and every thread
terminates gracefully once all data has been processed.

## Requirements

- Python 3.10 or newer
- No runtime dependencies (standard library only)
- Development tools are pinned in `requirements.txt`

## Setup

Run every command from this `Assignment1` folder.

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks `Activate.ps1`, run
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first (affects
the current window only).

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Running the demo

```bash
python -m producer_consumer            # 50 items, 2 producers, 2 consumers
python -m producer_consumer --help     # all options
```

## Running the tests

`python -m pytest` works even when the `pytest` command is not on PATH.

```bash
python -m pytest                                    # full suite, 10 s per-test timeout
python -m pytest --cov --cov-report=term-missing    # with coverage
python -m pytest tests/test_shared_queue.py tests/test_manager.py --count=50
python -m ruff check .                              # lint
```

## Project layout

```text
producer_consumer/
    item.py            Item: immutable unit of data
    shared_queue.py    SharedQueue: bounded queue (Lock + two Conditions)
    containers.py      SourceContainer / DestinationContainer
    producer.py        Producer: source -> queue
    consumer.py        Consumer: queue -> destination
    manager.py         DataTransferManager: threads, lifecycle, status
    status.py          TransferState, QueueStatus, TransferResult
    monitor.py         StatusMonitor: real-time status output
    exceptions.py      exception hierarchy
    main.py            demo entry point
docs/SYNCHRONIZATION.md  synchronization strategy and thread-safety guarantees
tests/                   pytest suite
```

## Sample output

<!-- TODO: paste the output of a real run of `python -m producer_consumer`. -->

## Design summary

<!-- TODO: 4-6 sentences. SharedQueue built on one Lock and two Conditions;
manager owns all threads; last producer closes the queue; consumers drain
and exit; fail-fast error channel; cooperative stop via Event. -->

Full details: [docs/SYNCHRONIZATION.md](docs/SYNCHRONIZATION.md).

## Spec-to-code name mapping

The specification uses Java-style names; the code follows PEP 8.

| Specification | Implementation |
| --- | --- |
| `Item(id, data, timestamp)` | `producer_consumer.item.Item` |
| `SharedQueue(capacity, lock)` | `producer_consumer.shared_queue.SharedQueue` |
| `Producer(sourceContainer, sharedQueue)` | `Producer(source_container, shared_queue, stop_event)` |
| `Consumer(sharedQueue, destinationContainer)` | `Consumer(shared_queue, destination_container, stop_event)` |
| `DataTransferManager` | `producer_consumer.manager.DataTransferManager` |
| `enqueue()` / `dequeue()` | `SharedQueue.enqueue()` / `SharedQueue.dequeue()` |
| `startTransfer()` | `DataTransferManager.start_transfer()` |
| `stopTransfer()` | `DataTransferManager.stop_transfer()` |
| `getQueueStatus()` | `DataTransferManager.get_queue_status()` |
| `waitForCompletion()` | `DataTransferManager.wait_for_completion()` |

## Requirements traceability

<!-- TODO: paste the Assignment 1 traceability table from the plan
(spec item -> how it is met -> file -> proving test). -->

## Assumptions

- Item payloads are immutable (str, int, tuple). `Item` is a frozen
  dataclass, but freezing is shallow, so a mutable payload is not protected.
- A stop aborts the transfer: items still queued are not delivered, and
  `TransferResult.undelivered` reports them.
- With several producers and consumers, global delivery order is not
  guaranteed; the queue itself is strictly FIFO.
- A `DataTransferManager` is single use, because Python threads cannot be
  restarted.
- <!-- TODO: add any further assumptions made while implementing. -->
