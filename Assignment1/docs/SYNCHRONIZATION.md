# Synchronization Strategy and Thread-Safety Guarantees

Assignment 1: producer-consumer transfer. Replace every TODO with prose.

## 1. Why locks are needed despite the GIL

TODO: The GIL lets only one thread run Python bytecode at a time, but threads
can switch between any two bytecodes, so compound operations (`count += 1`,
check-then-act) still race. The GIL protects the interpreter, not program
invariants. Mention free-threaded Python 3.13+ builds.

## 2. Primitives used and why

| Primitive | Where | Why |
| --- | --- | --- |
| `threading.Lock` | SharedQueue, containers, manager | TODO |
| `threading.Condition` | SharedQueue (`_not_full`, `_not_empty`) | TODO |
| `threading.Event` | manager stop signal, monitor stop signal | TODO |
| `queue.Queue` | manager worker-error channel | TODO |
| `Thread.join()` | manager, monitor | TODO |

TODO: Why `RLock` and `Barrier` are not used (no lock re-entry; no need for a
synchronized start).

## 3. SharedQueue design

TODO: one lock guarding all mutable state; two Conditions on that same lock;
`wait_for` (re-checks the predicate, tracks remaining timeout); `notify()`
after each enqueue/dequeue vs `notify_all()` in `close()`; close semantics
(enqueue fails immediately, dequeue drains first); counters updated in the
same critical section, so `size == enqueued - dequeued` always holds.

## 4. Termination protocol

TODO: last producer closes the queue in `finally` (CountDownLatch analog);
consumers drain and exit on `QueueClosedError`; `wait_for_completion` joins
against one deadline and checks `is_alive()`.

## 5. Stopping and interruption

TODO: Python has no `Thread.interrupt()`. Stop Event + bounded waits +
`close()` waking every waiter; `Event.wait(delay)` instead of `time.sleep`.
Consumers always deliver an item they have dequeued.

## 6. Failure handling

TODO: worker exceptions go on the `queue.Queue` error channel; fail fast (stop
event + close); re-raised as `TransferFailedError` with `__cause__`.

## 7. Lock order and deadlock freedom

TODO: manager lock -> queue/container locks only; the queue and containers
never call back into the manager; nothing prints or logs while holding a lock.

## 8. Thread-safety guarantees by class

| Class | Guarantee |
| --- | --- |
| `Item` | TODO (immutable; payload must be immutable too) |
| `SharedQueue` | TODO |
| `SourceContainer` | TODO |
| `DestinationContainer` | TODO |
| `Producer` / `Consumer` | TODO (one thread per instance) |
| `DataTransferManager` | TODO (any thread except its own workers) |
| `StatusMonitor` | TODO |

## 9. Known limitations

TODO: e.g. stop is cooperative (bounded by `poll_interval`); a producer's
in-hand item is dropped on stop; status fields outside the queue may lag;
CPU-bound work would not run in parallel under the GIL.
