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
    __init__.py        public API re-exports
    __main__.py        enables `python -m producer_consumer`
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
tests/                   pytest suite (159 tests)
```

## Sample output

A real run of `python -m producer_consumer` (the defaults make producers
faster than consumers, so the queue fills and the status lines show producers
waiting at 10/10):

```text
Transferring 50 items with 2 producer(s) and 2 consumer(s), queue capacity 10.
[  0.25s] RUNNING    queue 10/10 [##########] enq  20 deq  10 done  10 | P 2 C 2
[  0.50s] RUNNING    queue 10/10 [##########] enq  30 deq  20 done  20 | P 2 C 2
[  0.75s] RUNNING    queue 10/10 [##########] enq  40 deq  30 done  30 | P 2 C 2
[  1.00s] RUNNING    queue 10/10 [##########] enq  50 deq  40 done  40 | P 0 C 2
[  1.25s] RUNNING    queue  0/10 [..........] enq  50 deq  50 done  50 | P 0 C 2
[  1.26s] COMPLETED  queue  0/10 [..........] enq  50 deq  50 done  50 | P 0 C 0

State:       COMPLETED
Delivered:   50/50
Elapsed:     1.26s
Integrity:   OK - every source id delivered exactly once
```

Reading a status line: elapsed time, lifecycle state, queue fill (one bar
character per slot), cumulative enqueued / dequeued / delivered counts, and
the number of live producer (`P`) and consumer (`C`) threads.

## Design summary

`SharedQueue` is a hand-built bounded-buffer monitor: one `threading.Lock`
guards the deque and the counters, and two `Condition` objects on that same
lock (`_not_full`, `_not_empty`) let a dequeue wake only a producer and an
enqueue wake only a consumer. `DataTransferManager` owns every thread —
`Producer` and `Consumer` just expose a `run()` method, which is what lets
the tests drive them directly on the test thread. Termination needs no item
counting: each producer thread decrements an active-producer count in a
`finally`, and whoever brings it to zero closes the queue (the Python analog
of a `CountDownLatch`), after which consumers drain the closed queue, receive
`QueueClosedError` and return. A worker exception is wrapped and put on a
`queue.Queue` error channel, which then sets the stop event and closes the
queue so nothing can block forever; `wait_for_completion()` re-raises it as
`TransferFailedError` with the original exception as `__cause__`. Because
Python has no `Thread.interrupt()`, stopping is cooperative: a
`threading.Event` plus bounded waits plus `close()` to wake anything already
blocked, and `Event.wait(delay)` instead of `time.sleep` so no worker can
sleep through a stop.

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

| Specification item | How it is met | File | Proving test |
| --- | --- | --- | --- |
| `Item` holds id, data, timestamp | Frozen dataclass; timestamp defaults to `time.time()` | [item.py](producer_consumer/item.py) | `test_item.py::test_item_holds_id_data_and_timestamp` |
| Shared queue is bounded at capacity 10 | `SharedQueue(capacity=10)` is the default and the manager's `DEFAULT_CAPACITY` | [shared_queue.py](producer_consumer/shared_queue.py) | `test_shared_queue.py::test_default_capacity_is_ten`, `test_manager.py::test_default_capacity_matches_the_specification` |
| Capacity is never exceeded | `enqueue` waits on `_not_full` until a slot is free, inside the lock | [shared_queue.py](producer_consumer/shared_queue.py) | `test_shared_queue.py::test_queue_never_exceeds_capacity_under_load`, `test_manager.py::test_queue_never_exceeds_capacity_during_transfer` |
| Queue is synchronized with an explicit lock | One `Lock` guards all state; the spec's `SharedQueue(capacity, lock)` form accepts an external lock | [shared_queue.py](producer_consumer/shared_queue.py) | `test_shared_queue.py::test_accepts_an_externally_supplied_lock` |
| Producers block when the queue is full | Bounded `enqueue` retried while the stop event is clear | [producer.py](producer_consumer/producer.py) | `test_shared_queue.py::test_blocked_enqueue_resumes_when_space_appears`, `test_producer.py::test_producer_returns_promptly_when_stopped_while_queue_full` |
| Consumers block when the queue is empty | `dequeue` waits on `_not_empty` | [shared_queue.py](producer_consumer/shared_queue.py) | `test_shared_queue.py::test_blocked_dequeue_resumes_when_an_item_arrives` |
| `enqueue()` / `dequeue()` | `SharedQueue.enqueue()` / `SharedQueue.dequeue()`, strict FIFO | [shared_queue.py](producer_consumer/shared_queue.py) | `test_shared_queue.py::test_fifo_order_is_strict` |
| Multiple producers and consumers | Manager creates `num_producers` / `num_consumers` threads over shared containers | [manager.py](producer_consumer/manager.py) | `test_manager.py::test_complete_transfer_delivers_every_item_exactly_once` (1x1, 3x2, 2x5) |
| Every item transferred exactly once | Unique ids; `take()` hands out each index once; destination ids compared to source ids | [containers.py](producer_consumer/containers.py) | `test_containers.py::test_source_take_is_exactly_once_under_concurrency`, `test_manager.py::test_complete_transfer_delivers_every_item_exactly_once` |
| `startTransfer()` | `DataTransferManager.start_transfer()`, non-daemon named threads | [manager.py](producer_consumer/manager.py) | `test_manager.py::test_status_reports_state_transitions` |
| `stopTransfer()` | `stop_transfer()`: stop event + `close()` + joins; idempotent | [manager.py](producer_consumer/manager.py) | `test_manager.py::test_stop_mid_transfer_terminates_all_threads`, `test_stop_is_idempotent` |
| `waitForCompletion()` | `wait_for_completion()`, one deadline for all joins plus `is_alive()` checks | [manager.py](producer_consumer/manager.py) | `test_manager.py::test_wait_timeout_raises_transfer_timeout_error`, `test_wait_without_a_timeout_joins_until_done` |
| `getQueueStatus()` | `get_queue_status()` returns an immutable `QueueStatus` from one queue snapshot | [manager.py](producer_consumer/manager.py), [status.py](producer_consumer/status.py) | `test_manager.py::test_status_reports_state_transitions`, `test_status.py::test_queue_status_is_immutable` |
| All threads terminate gracefully | Last producer closes the queue; consumers drain and exit | [manager.py](producer_consumer/manager.py) | `test_manager.py::test_complete_transfer_delivers_every_item_exactly_once` (asserts no thread survives), `test_empty_source_completes_immediately` |
| Deadlock freedom | One-way lock order; every unbounded wait has `closed` in its predicate | [docs/SYNCHRONIZATION.md](docs/SYNCHRONIZATION.md) §7 | `test_manager.py::test_consumer_failure_aborts_without_deadlock`, `test_shared_queue.py::test_close_wakes_every_waiter` |
| Error handling across threads | Exceptions wrapped in `WorkerFailure` on a `queue.Queue`; re-raised with `__cause__` | [manager.py](producer_consumer/manager.py) | `test_manager.py::test_producer_failure_aborts_and_raises_transfer_failed`, `test_consumer_failure_aborts_without_deadlock` |
| Real-time status reporting | `StatusMonitor` prints from one background thread at a fixed interval | [monitor.py](producer_consumer/monitor.py) | `test_monitor.py::test_monitor_emits_lines_and_final_line_on_stop` |
| Demo entry point | `python -m producer_consumer` with CLI options | [main.py](producer_consumer/main.py) | `test_main.py::test_main_completes_with_exit_code_zero` |

## Assumptions

- Item payloads are immutable (str, int, tuple). `Item` is a frozen
  dataclass, but freezing is shallow, so a mutable payload is not protected.
- A stop aborts the transfer: items still queued are not delivered, and
  `TransferResult.undelivered` reports them.
- With several producers and consumers, global delivery order is not
  guaranteed; the queue itself is strictly FIFO.
- A `DataTransferManager` is single use, because Python threads cannot be
  restarted.
- Item ids must be unique within a source. `SourceContainer` rejects
  duplicates at construction, because unique ids are what make
  "transferred exactly once" checkable.
- A `QueueFullError` or `QueueEmptyError` from a bounded call means only
  that *this attempt* timed out, not that the item cannot be transferred;
  workers retry after re-checking the stop event.
- `QueueClosedError` is a normal control signal, not a failure. A worker
  that sees it returns quietly and the manager reports the real cause, if
  any.
- `QueueStatus` is for monitoring, not for decisions: only the four queue
  fields are mutually consistent, and `delivered` plus the thread counts may
  lag by the items in flight between a dequeue and its delivery.
- `stop_transfer()` cannot kill a worker wedged in code that never checks
  the stop event; it raises `TransferTimeoutError` instead of hanging.
- Worker counts must be `int`. `bool` is rejected, because
  `num_producers=True` almost certainly means a flag was passed by mistake.
- The demo's `--producer-delay` / `--consumer-delay` exist only to make the
  queue dynamics visible; they are not part of the specification.
