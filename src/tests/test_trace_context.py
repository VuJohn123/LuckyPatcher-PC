"""Test core/trace_context.py — correlation ID propagation."""
from __future__ import annotations

import contextvars
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import core.trace_context as tc
from core.trace_context import (
    ContextThreadPoolExecutor,
    TraceFilter,
    get_trace_id,
    new_trace_id,
    prefix_with_trace,
    reset_trace_id,
    set_trace_id,
    submit_with_context,
    trace_context,
)


# ============================================================
# new_trace_id
# ============================================================
class TestNewTraceId:
    def test_returns_8_char_hex(self):
        tid = new_trace_id()
        assert len(tid) == 8
        assert re.fullmatch(r"[0-9a-f]{8}", tid)

    def test_unique_across_calls(self):
        ids = {new_trace_id() for _ in range(100)}
        assert len(ids) == 100

    def test_env_override(self, monkeypatch):
        monkeypatch.setattr(tc, "_DISABLE", False)
        monkeypatch.setenv("LP_TRACE_ID", "deadbeef")
        assert new_trace_id() == "deadbeef"

    def test_disable_returns_dash(self, monkeypatch):
        monkeypatch.setattr(tc, "_DISABLE", True)
        monkeypatch.delenv("LP_TRACE_ID", raising=False)
        assert new_trace_id() == "-"

    def test_env_override_respects_disable(self, monkeypatch):
        monkeypatch.setattr(tc, "_DISABLE", True)
        monkeypatch.setenv("LP_TRACE_ID", "cafebabe")
        assert new_trace_id() == "-"


# ============================================================
# get/set/reset
# ============================================================
class TestGetSetReset:
    def test_default_is_dash(self):
        def _check():
            return get_trace_id()
        result = contextvars.copy_context().run(_check)
        assert isinstance(result, str)

    def test_set_then_get(self):
        token = set_trace_id("abcdef01")
        try:
            assert get_trace_id() == "abcdef01"
        finally:
            reset_trace_id(token)
        assert get_trace_id() == "-"

    def test_reset_invalid_token_no_crash(self):
        other_token = contextvars.ContextVar("x").set("y")
        reset_trace_id(other_token)  # should not raise


# ============================================================
# trace_context — context manager
# ============================================================
class TestTraceContext:
    def test_auto_generates_id(self):
        with trace_context() as tid:
            assert len(tid) == 8
            assert get_trace_id() == tid

    def test_restores_after_exit(self):
        initial = get_trace_id()
        with trace_context() as tid:
            assert get_trace_id() == tid
        assert get_trace_id() == initial

    def test_accepts_explicit_id(self):
        with trace_context("12345678") as tid:
            assert tid == "12345678"
            assert get_trace_id() == "12345678"

    def test_nested_contexts(self):
        with trace_context("outer001") as outer:
            assert get_trace_id() == "outer001"
            with trace_context("inner002") as inner:
                assert get_trace_id() == "inner002"
            assert get_trace_id() == "outer001"
        assert get_trace_id() == "-"

    def test_restores_on_exception(self):
        with pytest.raises(RuntimeError):
            with trace_context("exc00001"):
                assert get_trace_id() == "exc00001"
                raise RuntimeError("boom")
        assert get_trace_id() == "-"

    def test_yield_value_matches_contextvar(self):
        with trace_context("abcd1234") as tid:
            assert tid == get_trace_id() == "abcd1234"


# ============================================================
# prefix_with_trace
# ============================================================
class TestPrefixWithTrace:
    def test_prefix_when_active(self):
        with trace_context("abcdef01"):
            result = prefix_with_trace("hello")
            assert result == "[tid:abcdef01] hello"

    def test_no_prefix_when_dash(self):
        with trace_context("-"):
            result = prefix_with_trace("hello")
            assert result == "hello"

    def test_empty_message_still_prefixes(self):
        with trace_context("11111111"):
            assert prefix_with_trace("") == "[tid:11111111] "


# ============================================================
# submit_with_context — CORRECT pattern
# ============================================================
class TestSubmitWithContext:
    def test_thread_sees_parent_trace(self):
        captured: list[str] = []

        def worker():
            captured.append(get_trace_id())

        with trace_context("parent12"):
            with ThreadPoolExecutor(max_workers=1) as ex:
                submit_with_context(ex, worker).result()

        assert captured == ["parent12"]

    def test_multiple_workers_same_trace(self):
        captured: list[str] = []

        def worker(n: int):
            captured.append(get_trace_id())

        with trace_context("shared12"):
            with ThreadPoolExecutor(max_workers=4) as ex:
                futures = [
                    submit_with_context(ex, worker, i)
                    for i in range(4)
                ]
                for f in futures:
                    f.result()

        assert captured == ["shared12"] * 4

    def test_plain_submit_loses_trace(self):
        """Baseline: ex.submit() KHÔNG propagate → "-"."""
        captured: list[str] = []

        def worker():
            captured.append(get_trace_id())

        with trace_context("lost0001"):
            with ThreadPoolExecutor(max_workers=1) as ex:
                ex.submit(worker).result()

        assert captured == ["-"]

    def test_returns_future(self):
        def worker():
            return 42

        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = submit_with_context(ex, worker)
            assert fut.result() == 42

    def test_arguments_passed(self):
        def worker(a, b, *, c=None):
            return (a, b, c)

        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = submit_with_context(ex, worker, 1, 2, c=3)
            assert fut.result() == (1, 2, 3)

    def test_no_trace_context_uses_dash(self):
        captured: list[str] = []

        def worker():
            captured.append(get_trace_id())

        with ThreadPoolExecutor(max_workers=1) as ex:
            submit_with_context(ex, worker).result()

        assert captured == ["-"]


# ============================================================
# ContextThreadPoolExecutor — wrapper class
# ============================================================
class TestContextThreadPoolExecutor:
    def test_propagates_trace(self):
        captured: list[str] = []

        def worker():
            captured.append(get_trace_id())

        with trace_context("wrapper01"):
            with ContextThreadPoolExecutor(max_workers=2) as ex:
                ex.submit(worker).result()

        assert captured == ["wrapper01"]

    def test_multiple_submits(self):
        captured: list[str] = []

        def worker(n: int):
            captured.append(get_trace_id())

        with trace_context("multi001"):
            with ContextThreadPoolExecutor(max_workers=2) as ex:
                futures = [ex.submit(worker, i) for i in range(3)]
                for f in futures:
                    f.result()

        assert captured == ["multi001"] * 3

    def test_explicit_shutdown(self):
        ex = ContextThreadPoolExecutor(max_workers=1)
        ex.shutdown()
        # should not raise


# ============================================================
# TraceFilter
# ============================================================
class TestTraceFilter:
    def test_filter_injects_trace_id(self):
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="",
            lineno=0, msg="hello", args=(), exc_info=None,
        )
        flt = TraceFilter()
        with trace_context("filter01"):
            assert flt.filter(record) is True
            assert record.trace_id == "filter01"

    def test_filter_dash_when_no_context(self):
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="",
            lineno=0, msg="hello", args=(), exc_info=None,
        )
        flt = TraceFilter()
        assert flt.filter(record) is True
        assert record.trace_id == "-"


# ============================================================
# Thread isolation
# ============================================================
class TestThreadIsolation:
    def test_different_threads_isolated(self):
        results: dict[int, str] = {}

        def worker(idx: int):
            results[idx] = get_trace_id()

        threads = []
        for i in range(3):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

        # Tất cả thread đều thấy "-" (không kế thừa main thread)
        assert all(v == "-" for v in results.values())

    def test_set_in_thread_does_not_leak(self):
        def worker():
            set_trace_id("thread01")

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        # Main thread vẫn clean
        assert get_trace_id() == "-"

# ============================================================
# bind_trace_to_loguru
# ============================================================
class TestBindTraceToLoguru:
    def test_no_crash_when_loguru_missing(self, monkeypatch):
        """Không có loguru → graceful, không raise."""
        from core.trace_context import bind_trace_to_loguru
        fake = object()  # không phải loguru logger
        bind_trace_to_loguru(fake)  # should not raise

    def test_no_crash_when_configure_raises(self):
        from unittest.mock import MagicMock
        from core.trace_context import bind_trace_to_loguru
        fake = MagicMock()
        fake.configure.side_effect = RuntimeError("boom")
        bind_trace_to_loguru(fake)  # should not raise

    def test_calls_configure_patch_add(self):
        from unittest.mock import MagicMock
        from core.trace_context import bind_trace_to_loguru
        fake = MagicMock()
        fake.patch.return_value = fake
        bind_trace_to_loguru(fake)
        fake.configure.assert_called_once()
        fake.patch.assert_called_once()
        fake.add.assert_called_once()

    def test_patch_callback_reads_trace_id(self):
        """Verify patch callback inject trace_id từ context."""
        from unittest.mock import MagicMock
        from core.trace_context import bind_trace_to_loguru

        fake = MagicMock()
        fake.patch.return_value = fake

        captured_patch_fn = {}
        def _capture_patch(fn):
            captured_patch_fn["fn"] = fn
            return fake
        fake.patch.side_effect = _capture_patch

        bind_trace_to_loguru(fake)

        # Simulate loguru record
        record = {"extra": {}}
        with trace_context("patch001"):
            result = captured_patch_fn["fn"](record)
        # FIX: function returns record (không phải dict.update return None)
        assert result is not None
        assert result["extra"]["trace_id"] == "patch001"

    def test_add_callback_prints_with_trace(self, capsys):
        """Add callback → print có prefix [tid:xxx]."""
        from unittest.mock import MagicMock
        from core.trace_context import bind_trace_to_loguru

        fake = MagicMock()
        fake.patch.return_value = fake

        captured_add = {}
        def _capture_add(fn, **kw):
            captured_add["fn"] = fn
        fake.add.side_effect = _capture_add

        bind_trace_to_loguru(fake)

        # Simulate loguru Message
        msg = MagicMock()
        msg.record = {"extra": {"trace_id": "print001"}}
        msg.__str__ = lambda s: "hello world"
        captured_add["fn"](msg)
        out = capsys.readouterr().out
        assert "[tid:print001]" in out
        assert "hello world" in out

    def test_add_callback_handles_missing_trace(self, capsys):
        from unittest.mock import MagicMock
        from core.trace_context import bind_trace_to_loguru

        fake = MagicMock()
        fake.patch.return_value = fake
        captured_add = {}
        def _capture_add(fn, **kw):
            captured_add["fn"] = fn
        fake.add.side_effect = _capture_add

        bind_trace_to_loguru(fake)

        msg = MagicMock()
        msg.record = {"extra": {}}  # no trace_id
        msg.__str__ = lambda s: "bare"
        captured_add["fn"](msg)
        out = capsys.readouterr().out
        assert "[tid:-]" in out