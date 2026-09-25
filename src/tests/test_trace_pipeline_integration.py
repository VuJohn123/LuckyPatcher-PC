"""Integration tests — trace_id propagation qua pipeline + patcher.

Verify:
  - ThreadPool worker kế thừa trace_id qua submit_with_context.
  - BasePatcher.patch_files() log có prefix [tid:xxx].
  - setup_logging() gắn TraceFilter vào file handler.
"""
from __future__ import annotations

import logging

import pytest

from core.trace_context import (
    get_trace_id,
    trace_context,
)


# ============================================================
# ThreadPool propagation
# ============================================================
class TestThreadPoolPropagation:
    def test_execute_modes_worker_sees_trace_id(self, monkeypatch):
        """Worker trong execute_modes phải thấy trace_id từ caller."""
        from core import pipeline_executor as ex

        captured: list[str] = []

        class _CapPatcher:
            def __init__(self, *a, **kw):
                pass

            def patch(self):
                captured.append(get_trace_id())
                return 1

        # get_patcher_class trả _CapPatcher cho mọi mode
        monkeypatch.setattr(
            ex, "get_patcher_class", lambda name: _CapPatcher,
        )
        # Force parallel path
        monkeypatch.setattr(
            ex, "get_mode_group", lambda m: None,
        )
        # Clear stale file_cache
        ex.file_cache = None

        with trace_context("tr123456"):
            ex.execute_modes(
                ["fake_trace_mode"],
                "/tmp/decompiled",
                [],
                "/tmp/x.apk",
                log_callback=lambda m: None,
                strategy="balanced",
            )

        assert captured == ["tr123456"], captured

    def test_execute_modes_log_has_trace_prefix(self, monkeypatch):
        """Header log của execute_modes phải chứa [tid:xxx]."""
        from core import pipeline_executor as ex

        class _NoopPatcher:
            def __init__(self, *a, **kw):
                pass

            def patch(self):
                return 0

        monkeypatch.setattr(
            ex, "get_patcher_class", lambda name: _NoopPatcher,
        )
        monkeypatch.setattr(ex, "get_mode_group", lambda m: None)
        ex.file_cache = None

        messages: list[str] = []
        with trace_context("logtid01"):
            ex.execute_modes(
                ["fake_mode"],
                "/tmp",
                [],
                "/tmp/x.apk",
                log_callback=messages.append,
                strategy="balanced",
            )

        assert any("[tid:logtid01]" in m for m in messages), messages


# ============================================================
# BasePatcher prefix
# ============================================================
class TestBasePatcherTracePrefix:
    def test_patch_files_log_has_trace_prefix(
        self, monkeypatch, tmp_path,
    ):
        from patcher.base import BasePatcher

        # Không có file smali nào
        monkeypatch.setattr(
            "patcher.base.get_all_smali_files", lambda d: [],
        )

        messages: list[str] = []

        class _P(BasePatcher):
            def patch(self) -> int:
                return 0

        p = _P(str(tmp_path), log_callback=messages.append)

        with trace_context("patch123"):
            p.patch_files(
                transform=lambda c, fp: None,
                label="TestPatcher",
                show_progress=False,
            )

        assert messages, "patch_files không emit log nào"
        assert any("[tid:patch123]" in m for m in messages), messages
        assert any("TestPatcher" in m for m in messages), messages

    def test_patch_files_no_prefix_outside_trace(
        self, monkeypatch, tmp_path,
    ):
        """Ngoài trace_context, log không có [tid:...]."""
        from patcher.base import BasePatcher

        monkeypatch.setattr(
            "patcher.base.get_all_smali_files", lambda d: [],
        )

        messages: list[str] = []

        class _P(BasePatcher):
            def patch(self) -> int:
                return 0

        p = _P(str(tmp_path), log_callback=messages.append)
        p.patch_files(
            transform=lambda c, fp: None,
            label="TestPatcher",
            show_progress=False,
        )

        assert messages
        assert not any("[tid:" in m for m in messages), messages

    def test_patch_files_prefilter_log_has_trace(
        self, monkeypatch, tmp_path,
    ):
        """Path prefilter log cũng phải có prefix."""
        from patcher.base import BasePatcher

        monkeypatch.setattr(
            "patcher.base.get_all_smali_files",
            lambda d: [f"{d}/a.smali", f"{d}/b.smali"],
        )

        messages: list[str] = []

        class _P(BasePatcher):
            def patch(self) -> int:
                return 0

        p = _P(str(tmp_path), log_callback=messages.append)

        with trace_context("pf123456"):
            p.patch_files(
                transform=lambda c, fp: None,
                path_hints=("nonexistent_hint",),
                label="P",
                show_progress=False,
            )

        assert any("[tid:pf123456]" in m for m in messages), messages
        assert any("FULL scan" in m for m in messages), messages


# ============================================================
# setup_logging TraceFilter
# ============================================================
class TestSetupLoggingTraceFilter:
    def test_file_handler_has_trace_filter(self, tmp_path):
        """Verify handler được gắn TraceFilter."""
        from core import pipeline_helpers
        from core.trace_context import TraceFilter

        # Reset logger singleton
        lg = logging.getLogger("lp_pc_suite")
        original_handlers = list(lg.handlers)
        for h in list(lg.handlers):
            lg.removeHandler(h)

        try:
            log_file = tmp_path / "pipeline.log"
            config = {
                "logging": {
                    "level": "INFO",
                    "file": str(log_file),
                    "max_bytes": 1024 * 1024,
                    "backup_count": 2,
                }
            }
            logger = pipeline_helpers.setup_logging(config)
            assert logger.handlers, "no handler added"

            handler = logger.handlers[0]
            has_filter = any(
                isinstance(f, TraceFilter) for f in handler.filters
            )
            assert has_filter, (
                f"TraceFilter not attached: {handler.filters}"
            )

            fmt = handler.formatter._fmt
            assert "trace_id" in fmt, f"formatter missing trace_id: {fmt}"
        finally:
            for h in list(lg.handlers):
                lg.removeHandler(h)
            for h in original_handlers:
                lg.addHandler(h)