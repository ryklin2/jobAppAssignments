# Synchronization Strategy and Thread-Safety Guarantees

Assignment 1: producer-consumer transfer. Producers move items from a
`SourceContainer` into a bounded `SharedQueue` (capacity 10); consumers move
them into a `DestinationContainer`. Every thread terminates gracefully once
all data has been processed.

## 1. Why locks are needed despite the GIL

The GIL guarantees that only one thread executes Python bytecode at a time.
It does **not** make operations atomic. A thread can be suspended between
any two bytecodes, which is exactly where compound operations break:

- `count += 1` compiles to a load, an add and a store. Two threads can both
  load `5`, both store `6`, and one increment disappears.
- Check-then-act is worse, because the gap is wider. `if source.remaining:
  item = source.take()` can pass the check in two threads when only one
  item is left.

The GIL protects the interpreter's own state (reference counts, object
headers) from corruption. It says nothing about *program* invariants such as
"the queue never holds more than 10 items" or "each item is handed out
once". Those need explicit locks.

Relying on the GIL is also a bet on one implementation. CPython 3.13
introduced an officially supported free-threaded build (PEP 703) that runs
without a GIL, and the bytecode-level interleavings that are merely rare
there become common. Code written against the primitives in `threading` is
correct on both builds; code that leans on "the GIL makes this safe" is not.
Everything here therefore synchronizes explicitly, including
`DestinationContainer.add`, where `list.append` happens to be atomic in
CPython today.

## 2. Primitives used and why

| Primitive | Where | Why |
| --- | --- | --- |
| `threading.Lock` | SharedQueue, containers, manager | Mutual exclusion for compound state changes: the queue's deque plus counters, the source's next index, the destination's list, the manager's state and active-producer count. Non-reentrant on purpose, so an accidental re-entry deadlocks in a test instead of hiding a broken invariant. |
| `threading.Condition` | SharedQueue (`_not_full`, `_not_empty`) | Lets a thread *wait* for a state change instead of polling. A full queue must block a producer until a consumer frees a slot; a condition releases the lock while waiting and reacquires it on wake-up. Two conditions on one lock mean a dequeue wakes only a producer and an enqueue wakes only a consumer. |
| `threading.Event` | manager stop signal, monitor stop signal | A one-way, broadcast flag that many threads can poll or wait on. `Event.wait(timeout)` doubles as an interruptible sleep, which is why no worker ever calls `time.sleep`. |
| `queue.Queue` | manager worker-error channel | A ready-made thread-safe handoff for exceptions from many worker threads to the one controlling thread. Using the standard library here avoids inventing a second lock for a problem that is already solved; the assignment's point is the bounded buffer, which is hand-built. |
| `Thread.join()` | manager, monitor | The only way to know a thread has actually finished. `join(timeout)` returns silently whether the thread ended or the timeout expired, so every join is followed by an `is_alive()` check. |

`threading.RLock` is not used: no code path re-enters a lock it already
holds. Each lock guards a small critical section that calls no method which
takes the same lock, so a plain `Lock` is both sufficient and stricter — an
accidental re-entry shows up immediately rather than being silently allowed.

`threading.Barrier` is not used either: producers and consumers do not need a
synchronized start. Workers may begin as soon as they are created, and the
queue's conditions already handle a consumer that starts before any item
exists. (The tests do use a `Barrier`, where making threads contend
simultaneously is the point.)

`threading.Semaphore` would be an alternative way to express the free-slot
and used-slot counts, but it cannot guard the counters and the deque at the
same time; the lock-plus-conditions monitor keeps all queue state under one
lock and so keeps `size == enqueued - dequeued` true by construction.

## 3. SharedQueue design

`SharedQueue` is the classic bounded-buffer monitor:

- **One lock guards all mutable state** — the `deque`, the `enqueued` and
  `dequeued` counters, and the `closed` flag. Because the counters are
  updated in the same critical section as the deque, `status()` can never
  return a snapshot where `size != enqueued - dequeued`.
- **Two conditions share that lock.** `_not_full` is waited on by producers
  and notified by a dequeue; `_not_empty` is waited on by consumers and
  notified by an enqueue. A single condition would work, but it would have
  to use `notify_all()` on every operation and would wake threads that
  cannot proceed — the thundering-herd problem.
- **Every wait uses `Condition.wait_for(predicate, timeout)`.** This matters
  for two reasons. It re-checks the predicate after each wake-up, which is
  required because a waiter can be woken spuriously or lose the race for the
  freed slot to a third thread; and it tracks the *remaining* timeout across
  repeated wake-ups, so a 0.1s bounded wait cannot silently become longer.
  Waiting on a bare `wait()` and assuming the condition now holds is the
  classic bounded-buffer bug.
- **`notify()` per operation, `notify_all()` in `close()`.** One enqueue
  creates work for exactly one consumer, so waking one is correct and
  cheaper. `close()` changes the situation of *every* waiter, so all of them
  must re-evaluate their predicate.
- **Close semantics are asymmetric by design.** After `close()`, `enqueue()`
  raises `QueueClosedError` immediately — there is no point accepting work
  that will not be delivered. `dequeue()` keeps returning items until the
  queue is empty and only then raises `QueueClosedError`, so closing can
  never strand an item that a producer already handed over. Both waiting
  predicates include `self._closed`, so closing wakes blocked threads
  instead of leaving them to time out.

## 4. Termination protocol

Graceful termination is the heart of the assignment, because neither side
knows on its own when the work is finished:

1. Each producer thread body (`DataTransferManager._run_producer`) wraps
   `producer.run()` in `try/finally`. The `finally` decrements
   `_active_producers` under the manager lock.
2. The producer that brings the count to zero calls `shared_queue.close()`.
   This is the Python analog of Java's `CountDownLatch`: the last one out
   turns off the lights. It lives in `finally`, so a producer that crashed
   still counts down and consumers can never wait forever on a producer that
   will never return.
3. Consumers keep dequeuing. Because a closed queue drains before it
   reports closed, every produced item is delivered; each consumer then
   receives `QueueClosedError` and returns normally. The error is repeatable,
   so every consumer sees it, not just the first.
4. `wait_for_completion()` joins the producer threads and then the consumer
   threads against **one** shared deadline (`time.monotonic() + timeout`),
   not `timeout` per thread — otherwise *n* threads could take *n × timeout*
   seconds. Each join is followed by `is_alive()`, because `join(timeout)`
   does not report which of the two happened.

No worker ever decides the transfer is over by inspecting a count. The only
end-of-data signal is the closed queue.

## 5. Stopping and interruption

Python has no `Thread.interrupt()` and no safe way to kill a thread from
outside, so stopping is cooperative:

- `DataTransferManager.stop_transfer()` sets a `threading.Event` and closes
  the queue. Both are needed: the event releases a worker that is polling
  between bounded waits, and `close()` wakes a worker blocked *inside* a
  wait right now.
- Workers check the stop event before each item and between bounded
  attempts, so a stop is noticed within roughly one `poll_interval`
  (0.1s by default). This is why producers enqueue with
  `timeout=poll_interval` and retry on `QueueFullError` rather than blocking
  indefinitely: a `QueueFullError` means "that attempt timed out", not "this
  item cannot be delivered".
- Demo pacing uses `stop_event.wait(delay)`, never `time.sleep(delay)`, so a
  worker cannot sleep through a stop request. The same applies to
  `StatusMonitor`, whose loop is `while not stop_event.wait(interval)`.
- **Consumers always deliver an item they have already dequeued.** The stop
  check sits before the dequeue, never between the dequeue and the
  `destination.add()`, so no item is ever dropped from a consumer's hands.
  A producer's in-hand item is different: an item taken from the source but
  not yet enqueued when a stop arrives is simply not transferred, and
  `TransferResult.undelivered` accounts for it.

## 6. Failure handling

The system fails fast rather than hanging:

- A worker exception is caught in the thread body, wrapped in a
  `WorkerFailure(worker_name, error)` and put on a `queue.Queue` error
  channel. Exceptions never cross a thread boundary on their own — an
  unhandled one in a worker would print a traceback and vanish, leaving the
  manager to wait forever.
- `_record_failure` then sets the stop event and closes the queue. This is
  what prevents the obvious deadlock: if the only consumer dies, producers
  blocked on a full queue would otherwise wait for a consumer that no longer
  exists.
- `wait_for_completion()` empties the channel with `get_nowait()` until
  `queue.Empty` (never looping on `Queue.empty()`, which is only a hint and
  can race), sets the state to `FAILED`, and re-raises the first failure as
  `TransferFailedError` with the original exception as `__cause__`, so the
  real traceback survives.
- Draining is destructive, so collected failures are also **recorded** on the
  manager. Without that, a second `wait_for_completion()` would report
  success for a transfer that had failed. For the same reason
  `stop_transfer()` collects failures too and reports `FAILED` rather than
  `STOPPED` when a worker had already crashed — a stop must not bury the
  real cause.
- The queue's own `QueueClosedError` is *not* a failure. A producer that
  finds the queue closed returns normally; the manager reports the actual
  cause.

## 7. Lock order and deadlock freedom

Deadlock needs a cycle in the "holds A, wants B" graph. There is none here:

- The lock order is one-way: the manager lock may be held while acquiring a
  queue or container lock, never the reverse.
- The queue and the containers never call back into the manager, and never
  into each other. They are leaves in the call graph, so no cycle can form.
- Each critical section is short, straight-line code with no I/O. Nothing
  prints, logs or sleeps while holding a lock — only `StatusMonitor` prints,
  from its own thread, and it reads status through `get_queue_status()`
  without holding anything.
- `start_transfer()` builds the thread objects under the manager lock but
  calls `Thread.start()` outside it, so a worker's first action (which may
  take the queue lock) cannot contend with the starter.
- The locks are non-reentrant, so a path that re-entered one would fail
  loudly in the test suite rather than lurking.

The remaining hazard is not deadlock but livelock-by-waiting, and the
bounded waits plus `close()` address it: every unbounded wait in the system
is on a condition whose predicate includes `closed`.

## 8. Thread-safety guarantees by class

| Class | Guarantee |
| --- | --- |
| `Item` | Immutable (frozen dataclass), so it is safe to share with no lock. Freezing is shallow: a mutable payload is still mutable through `data`, so payloads must be immutable (`str`, `int`, `tuple`) for the guarantee to hold end to end. |
| `SharedQueue` | Fully thread-safe. Every public method may be called from any thread at any time. `size()` and `closed` are honest snapshots and are stale the moment they return; never use them for check-then-act. |
| `SourceContainer` | Fully thread-safe. `take()` hands out each item exactly once, in original order, to any number of concurrent producers. A shared generator could not do this — concurrent `next()` raises `ValueError: generator already executing`. |
| `DestinationContainer` | Fully thread-safe. `add()` is safe from any number of consumers; readers take the same lock and return immutable snapshots, so no caller sees the list mid-update. |
| `Producer` / `Consumer` | One instance must be run by one thread at a time; they hold no lock of their own. Any number of instances may share one source, queue and destination. They own no thread, which is what lets a test call `run()` directly. |
| `DataTransferManager` | Public methods are safe from any thread **except** its own workers, which must not call them (`wait_for_completion` and `stop_transfer` join the workers, and a thread cannot join itself; `_join_workers` skips the current thread defensively). Single use: Python threads cannot be restarted, so a finished manager refuses `start_transfer()`. |
| `StatusMonitor` | `start()` and `stop()` are meant for one controlling thread (normally main); `stop()` is idempotent and returns whether the thread actually exited, keeping it joinable if not. Single use, like the manager: `start()` raises once the monitor has been started, including after a stop, since its stop Event is set and a thread cannot be restarted. The monitor thread only reads through `manager.get_queue_status()`, so it adds no new sharing. It is the only thread that prints, which is why status lines never interleave. |

## 9. Known limitations

- **Stopping is cooperative, not immediate.** A stop is observed within
  roughly one `poll_interval`. A worker wedged in code that never checks the
  event (for example a destination whose `add()` blocks) cannot be killed;
  `stop_transfer()` reports `TransferTimeoutError` rather than hanging.
- **A producer's in-hand item is dropped on stop.** An item taken from the
  source but not yet enqueued is not transferred. It is counted in
  `TransferResult.undelivered`, not silently lost.
- **`QueueStatus` is only partly consistent.** `queue_size`, `capacity`,
  `enqueued` and `dequeued` come from one `SharedQueue.status()` call and
  cannot contradict each other. `delivered` and the live-thread counts are
  read separately, so they can lag by the items in flight between a dequeue
  and its delivery. Status is for monitoring, not for decisions.
- **Global delivery order is not guaranteed** with more than one producer or
  consumer. The queue itself is strictly FIFO, but which consumer wins a
  given item is up to the scheduler.
- **A manager is single use.** `TransferState` moves only forwards, because
  a Python `Thread` cannot be restarted. Run a second transfer with a new
  manager.
- **Threads do not help CPU-bound work.** Under the GIL this design wins on
  I/O-bound or latency-bound workloads; parallel computation would need
  `multiprocessing` or a free-threaded build.
- **Unbounded error channel.** The `queue.Queue` of failures has no maximum
  size. With one failure per worker thread that is bounded in practice by
  the worker count.
- **A wedged thread cannot be joined away.** `stop_transfer()` and
  `StatusMonitor.stop()` both report a thread they could not join (by
  exception and by return value respectively) and keep it joinable, rather
  than abandoning a live non-daemon thread that would stop the process from
  exiting. Neither can force it to end.
- **Thread startup is not transactional.** If the OS refuses a thread partway
  through `start_transfer()`, the manager corrects its active-producer count,
  closes the queue, marks the transfer `FAILED` and re-raises, rather than
  leaving consumers waiting on producers that will never run.
