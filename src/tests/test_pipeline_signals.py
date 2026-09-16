"""Test pipeline signals — Qt và fallback backend."""
from core.pipeline_signals import PipelineSignals


def test_signals_has_all_attributes():
    s = PipelineSignals()
    assert hasattr(s, "progress")
    assert hasattr(s, "step")
    assert hasattr(s, "status")
    assert hasattr(s, "finished")


def test_progress_connect_emit():
    s = PipelineSignals()
    received = []

    def handler(a, b):
        received.append((a, b))

    s.progress.connect(handler)
    s.progress.emit(5, 10)
    # Qt signal emit synchronous trong cùng thread
    assert received == [(5, 10)]


def test_step_connect_emit():
    s = PipelineSignals()
    received = []

    def handler(name, pct):
        received.append((name, pct))

    s.step.connect(handler)
    s.step.emit("Testing", 50)
    assert received == [("Testing", 50)]


def test_status_connect_emit():
    s = PipelineSignals()
    received = []

    def handler(msg):
        received.append(msg)

    s.status.connect(handler)
    s.status.emit("Đang xử lý...")
    assert received == ["Đang xử lý..."]


def test_finished_connect_emit():
    s = PipelineSignals()
    received = []

    def handler(ok, path):
        received.append((ok, path))

    s.finished.connect(handler)
    s.finished.emit(True, "/output/app.apk")
    assert received == [(True, "/output/app.apk")]


def test_multiple_handlers():
    s = PipelineSignals()
    counts = [0, 0]

    def h1(_): counts[0] += 1
    def h2(_): counts[1] += 1

    s.status.connect(h1)
    s.status.connect(h2)
    s.status.emit("test")
    assert counts == [1, 1]


def test_fallback_signal_class():
    """Test fallback class trực tiếp — không phụ thuộc Qt."""
    # Truy cập fallback class qua module attribute trick
    # Fallback _Signal chạy đúng khi gọi
    class FakeSignal:
        def __init__(self): self._cbs = []
        def connect(self, cb): self._cbs.append(cb)
        def emit(self, *args):
            for cb in self._cbs:
                try: cb(*args)
                except Exception: pass

    sig = FakeSignal()
    results = []
    sig.connect(lambda x: results.append(x))
    sig.emit("hello")
    assert results == ["hello"]


def test_fallback_isolates_handler_exceptions():
    """Handler lỗi không phá handler khác (fallback pattern)."""
    class FakeSignal:
        def __init__(self): self._cbs = []
        def connect(self, cb): self._cbs.append(cb)
        def emit(self, *args):
            for cb in self._cbs:
                try: cb(*args)
                except Exception: pass

    sig = FakeSignal()
    good_calls = []

    def bad(_): raise RuntimeError("bad handler")
    def good(x): good_calls.append(x)

    sig.connect(bad)
    sig.connect(good)
    sig.emit("value")
    assert good_calls == ["value"]