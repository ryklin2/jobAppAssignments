"""Tests for Consumer, calling run() directly where possible."""

import threading
import time
from collections.abc import Callable

import pytest

from producer_consumer.consumer import Consumer
from producer_consumer.containers import DestinationContainer
from producer_consumer.item import Item
from producer_consumer.shared_queue import SharedQueue

TIMING_SLACK = 5.0
POLL = 0.05


def test_consumer_drains_closed_queue_then_returns(
    make_items: Callable[[int], list[Item]],
) -> None:
    """Pre-filled closed queue: run() delivers all items in FIFO order, then returns."""
    items = make_items(5)
    queue = SharedQueue(capacity=10)
    for item in items:
        queue.enqueue(item)
    queue.close()

    destination = DestinationContainer()
    consumer = Consumer(queue, destination, threading.Event(), poll_interval=POLL)
    consumer.run()

    assert consumer.name == "consumer"
    assert destination.snapshot() == tuple(items)
    assert queue.size() == 0


def test_consumer_exposes_its_name() -> None:
    """The name given at construction is what the manager reports on failure."""
    consumer = Consumer(
        SharedQueue(), DestinationContainer(), threading.Event(), name="consumer-3"
    )
    assert consumer.name == "consumer-3"


def test_consumer_returns_promptly_when_stopped_while_queue_empty() -> None:
    """Blocked on an empty queue, run() returns within ~poll_interval of
    stop_event.set().
    """
    queue = SharedQueue()
    stop_event = threading.Event()
    consumer = Consumer(
        queue, DestinationContainer(), stop_event, poll_interval=POLL
    )
    thread = threading.Thread(target=consumer.run)
    thread.start()
    try:
        time.sleep(POLL * 3)
        assert thread.is_alive(), "consumer should be waiting on the empty queue"
        stop_event.set()
        thread.join(TIMING_SLACK)
    finally:
        stop_event.set()
        thread.join(TIMING_SLACK)
    assert not thread.is_alive(), "a stop did not release the blocked consumer"


def test_consumer_returns_when_queue_closed_while_waiting() -> None:
    """Closing an empty queue ends run() without an error."""
    queue = SharedQueue()
    thread = threading.Thread(
        target=Consumer(
            queue, DestinationContainer(), threading.Event(), poll_interval=POLL
        ).run
    )
    thread.start()
    try:
        time.sleep(POLL * 2)
        assert thread.is_alive()
        queue.close()
        thread.join(TIMING_SLACK)
    finally:
        queue.close()
        thread.join(TIMING_SLACK)
    assert not thread.is_alive(), "close() did not release the blocked consumer"


def test_consumer_delivers_an_item_it_already_holds_despite_a_stop(
    make_items: Callable[[int], list[Item]],
) -> None:
    """A stop set while an item is in hand still results in that item arriving.

    This is the "no item is ever dropped from a consumer's hands" guarantee:
    the stop is checked before a dequeue, never between dequeue and add.
    """
    items = make_items(1)
    queue = SharedQueue(capacity=2)
    queue.enqueue(items[0])
    stop_event = threading.Event()
    destination = DestinationContainer()

    class StopOnAdd(DestinationContainer):
        def add(self, item: Item) -> None:
            # The worst case: a stop lands at the instant of delivery.
            stop_event.set()
            destination.add(item)

    Consumer(queue, StopOnAdd(), stop_event, poll_interval=POLL).run()
    assert destination.snapshot() == tuple(items)


def test_consumer_shares_queue_with_other_consumers(
    make_items: Callable[[int], list[Item]],
) -> None:
    """Two consumers on one queue deliver every item exactly once between them."""
    items = make_items(40)
    queue = SharedQueue(capacity=len(items))
    for item in items:
        queue.enqueue(item)
    queue.close()

    destination = DestinationContainer()
    stop_event = threading.Event()
    threads = [
        threading.Thread(
            target=Consumer(
                queue, destination, stop_event, name=f"consumer-{i}", poll_interval=POLL
            ).run
        )
        for i in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(TIMING_SLACK)

    assert destination.count == len(items)
    assert destination.ids() == {item.id for item in items}


def test_consumer_propagates_destination_errors(
    make_items: Callable[[int], list[Item]],
) -> None:
    """A destination whose add() raises makes run() raise the same exception."""

    class BrokenDestination(DestinationContainer):
        def add(self, item: Item) -> None:
            raise RuntimeError("destination exploded")

    queue = SharedQueue(capacity=5)
    queue.enqueue(make_items(1)[0])
    consumer = Consumer(
        queue, BrokenDestination(), threading.Event(), poll_interval=POLL
    )
    with pytest.raises(RuntimeError, match="destination exploded"):
        consumer.run()


def test_consumer_delay_is_interrupted_by_a_stop(
    make_items: Callable[[int], list[Item]],
) -> None:
    """A long per-item delay does not delay a stop: Event.wait, not time.sleep."""
    items = make_items(5)
    queue = SharedQueue(capacity=10)
    for item in items:
        queue.enqueue(item)
    stop_event = threading.Event()
    consumer = Consumer(
        queue, DestinationContainer(), stop_event, poll_interval=POLL, delay=30.0
    )
    thread = threading.Thread(target=consumer.run)
    thread.start()
    try:
        time.sleep(POLL)
        stop_event.set()
        thread.join(TIMING_SLACK)
    finally:
        stop_event.set()
        thread.join(TIMING_SLACK)
    assert not thread.is_alive(), "the consumer slept through the stop request"


def test_consumer_honours_a_stop_set_before_it_runs(
    make_items: Callable[[int], list[Item]],
) -> None:
    """An already-set stop event means run() delivers nothing."""
    queue = SharedQueue(capacity=5)
    queue.enqueue(make_items(1)[0])
    stop_event = threading.Event()
    stop_event.set()
    destination = DestinationContainer()
    Consumer(queue, destination, stop_event, poll_interval=POLL).run()
    assert destination.count == 0


@pytest.mark.parametrize(
    ("poll_interval", "delay"),
    [(0, 0.0), (-1, 0.0), (0.1, -0.5)],
)
def test_consumer_rejects_invalid_poll_interval_and_delay(
    poll_interval: float, delay: float
) -> None:
    """poll_interval <= 0 or delay < 0 raise ValueError."""
    with pytest.raises(ValueError):
        Consumer(
            SharedQueue(),
            DestinationContainer(),
            threading.Event(),
            poll_interval=poll_interval,
            delay=delay,
        )
