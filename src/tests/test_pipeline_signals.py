"""Test core/pipeline_signals.py — Qt + fallback."""
import threading

import pytest

from core.pipeline_signals import (
    _FallbackSignal,
    _HAS_QT,
    PipelineSignals,
)


# ============================================================
# _FallbackSignal
# ============================================================
class TestFallbackSignal:
    def test_connect_emit(self):
        """Multi-arg emit → callback cần match signature."""
        sig = _FallbackSignal("test")
        received = []
        # list.append chỉ nhận 1 arg → wrap trong lambda *args
        sig.connect(lambda *args: received.append(args))
        sig.emit("hello", 42)
        assert received == [("hello", 42)]

    def test_connect_emit_single_arg(self):
        """Single-arg emit → list.append hoạt động trực tiếp."""
        sig = _FallbackSignal("single")
        received = []
        sig.connect(received.append)
        sig.emit("hello")
        assert received == ["hello"]

    def test_multiple_subscribers(self):
        sig = _FallbackSignal("multi")
        a, b = [], []
        sig.connect(a.append)
        sig.connect(b.append)
        sig.emit("x")
        assert a == ["x"]
        assert b == ["x"]

    def test_disconnect_specific(self):
        sig = _FallbackSignal("disc")
        a, b = [], []
        ca, cb = a.append, b.append
        sig.connect(ca)
        sig.connect(cb)
        sig.disconnect(ca)
        sig.emit("y")
        assert a == []
        assert b == ["y"]

    def test_disconnect_all(self):
        sig = _FallbackSignal("disc_all")
        a, b = [], []
        sig.connect(a.append)
        sig.connect(b.append)
        sig.disconnect()
        sig.emit("z")
        assert a == [] and b == []

    def test_disconnect_nonexistent_no_error(self):
        sig = _FallbackSignal("noop")
        sig.disconnect(lambda x: None)  # Never connected → no error

    def test_connect_none_ignored(self):
        sig = _FallbackSignal("none")
        sig.connect(None)
        assert len(sig) == 0

    def test_exception_in_callback_isolated(self):
        """Callback lỗi không ảnh hưởng callback khác."""
        sig = _FallbackSignal("boom")
        received = []

        def bad(*a, **k):
            raise RuntimeError("callback error")

        sig.connect(bad)
        sig.connect(received.append)
        sig.emit("data")
        # Callback 2 vẫn chạy dù callback 1 lỗi
        assert received == ["data"]

    def test_len(self):
        sig = _FallbackSignal("count")
        assert len(sig) == 0
        sig.connect(lambda *a: None)
        assert len(sig) == 1
        sig.connect(lambda *a: None)
        assert len(sig) == 2

    def test_thread_safety_concurrent_emit(self):
        """Concurrent emit không crash."""
        sig = _FallbackSignal("thread")
        counter = {"n": 0}
        lock = threading.Lock()

        def cb(*a, **k):
            with lock:
                counter["n"] += 1

        sig.connect(cb)

        def worker():
            for _ in range(50):
                sig.emit()

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert counter["n"] == 200

    def test_emit_no_subscribers_noop(self):
        sig = _FallbackSignal("empty")
        sig.emit("x", "y")  # No error


# ============================================================
# PipelineSignals
# ============================================================
class TestPipelineSignals:
    def test_has_all_signals(self):
        s = PipelineSignals()
        for attr in ("progress", "step", "status", "patch_complete",
                     "finished", "safety_prompt"):
            assert hasattr(s, attr), f"Missing signal: {attr}"

    def test_progress_emit_when_fallback(self):
        """Chỉ test emit khi KHÔNG có Qt."""
        if _HAS_QT:
            pytest.skip("PyQt6 available — dùng Qt signals")
        s = PipelineSignals()
        received = []
        s.progress.connect(lambda cur, tot: received.append((cur, tot)))
        s.progress.emit(3, 10)
        assert received == [(3, 10)]

    def test_step_emit_when_fallback(self):
        if _HAS_QT:
            pytest.skip("PyQt6 available")
        s = PipelineSignals()
        received = []
        s.step.connect(lambda name, pct: received.append((name, pct)))
        s.step.emit("Decompiling", 15)
        assert received == [("Decompiling", 15)]

    def test_status_emit_when_fallback(self):
        if _HAS_QT:
            pytest.skip("PyQt6 available")
        s = PipelineSignals()
        received = []
        s.status.connect(received.append)
        s.status.emit("Working")
        assert received == ["Working"]

    def test_finished_emit_when_fallback(self):
        if _HAS_QT:
            pytest.skip("PyQt6 available")
        s = PipelineSignals()
        received = []
        s.finished.connect(
            lambda ok, path: received.append((ok, path))
        )
        s.finished.emit(True, "/path/out.apk")
        assert received == [(True, "/path/out.apk")]

    def test_safety_prompt_emit_when_fallback(self):
        if _HAS_QT:
            pytest.skip("PyQt6 available")
        s = PipelineSignals()
        received = []

        def _cb(reason, details, count, callback):
            received.append((reason, count))
            callback(True)

        s.safety_prompt.connect(_cb)
        s.safety_prompt.emit("cpu", {"x": 1}, 5, lambda v: None)
        assert received == [("cpu", 5)]


# ============================================================
# HAS_QT flag
# ============================================================
def test_has_qt_is_bool():
    assert isinstance(_HAS_QT, bool)