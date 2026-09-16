"""Test core.event_logger — runtime event logger."""
from core.event_logger import EventLogger


def test_log_and_counters():
    el = EventLogger()
    el.log("test", "msg1")
    el.log("test", "msg2")
    el.log("other", "msg3")
    counters = el.get_counters()
    assert counters["test"] == 2
    assert counters["other"] == 1


def test_get_events_all():
    el = EventLogger()
    el.log("a", "1")
    el.log("b", "2")
    events = el.get_events()
    assert len(events) == 2


def test_get_events_filtered():
    el = EventLogger()
    el.log("a", "1")
    el.log("b", "2")
    el.log("a", "3")
    events = el.get_events("a")
    assert len(events) == 2
    assert all(e["type"] == "a" for e in events)


def test_ring_buffer_limit():
    el = EventLogger()
    el.MAX_BUFFER = 5
    for i in range(20):
        el.log("evt", f"msg{i}")
    assert len(el.get_events()) <= 5


def test_clear():
    el = EventLogger()
    el.log("a", "1")
    el.clear()
    assert el.get_events() == []
    assert el.get_counters() == {}


def test_extra_kwargs():
    el = EventLogger()
    el.log("evt", "msg", key1="value1", key2=42)
    events = el.get_events("evt")
    assert events[0]["extra"] == {"key1": "value1", "key2": 42}