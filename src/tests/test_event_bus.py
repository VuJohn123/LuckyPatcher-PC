"""Test event bus — pub/sub, thread-safe, isolate errors."""
import threading
import time

from core.event_bus import EventBus


def test_subscribe_and_emit():
    bus = EventBus()
    received = []
    bus.subscribe("test", lambda d: received.append(d))
    bus.emit("test", {"x": 1})
    assert received == [{"x": 1}]


def test_unsubscribe():
    bus = EventBus()
    received = []

    def cb(d):
        received.append(d)

    bus.subscribe("evt", cb)
    bus.emit("evt", 1)
    bus.unsubscribe("evt", cb)
    bus.emit("evt", 2)
    assert received == [1]


def test_multiple_subscribers():
    bus = EventBus()
    a, b = [], []
    bus.subscribe("e", a.append)
    bus.subscribe("e", b.append)
    bus.emit("e", "x")
    assert a == ["x"] and b == ["x"]


def test_failing_handler_does_not_break_others():
    bus = EventBus()
    received = []

    def bad(d):
        raise ValueError("boom")

    bus.subscribe("e", bad)
    bus.subscribe("e", received.append)
    bus.emit("e", 1)
    assert received == [1]


def test_emit_no_subscribers_is_noop():
    bus = EventBus()
    bus.emit("nothing", 1)  # Không raise


def test_thread_safety():
    bus = EventBus()
    counter = {"n": 0}
    lock = threading.Lock()

    def cb(_):
        with lock:
            counter["n"] += 1

    bus.subscribe("t", cb)
    threads = [threading.Thread(target=bus.emit, args=("t", i))
               for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert counter["n"] == 50