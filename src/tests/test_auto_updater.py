"""Test core/auto_updater.py — watch folder + auto re-patch."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.auto_updater import AutoUpdater


# ============================================================
# Init
# ============================================================
class TestInit:
    def test_custom_watch_dir(self, tmp_path):
        au = AutoUpdater(watch_dir=str(tmp_path),
                         log_callback=lambda *a: None)
        assert au.watch_dir == tmp_path

    def test_default_watch_dir(self):
        au = AutoUpdater(log_callback=lambda *a: None)
        assert "Downloads" in str(au.watch_dir)

    def test_init_no_thread(self, tmp_path):
        au = AutoUpdater(watch_dir=str(tmp_path),
                         log_callback=lambda *a: None)
        assert au._thread is None
        assert au._known == set()


# ============================================================
# _scan
# ============================================================
class TestScan:
    def test_finds_apk_files(self, tmp_path):
        (tmp_path / "a.apk").write_bytes(b"x")
        (tmp_path / "b.xapk").write_bytes(b"x")
        (tmp_path / "c.txt").write_bytes(b"x")

        au = AutoUpdater(watch_dir=str(tmp_path),
                         log_callback=lambda *a: None)
        result = au._scan()
        assert len(result) == 2
        assert any("a.apk" in s for s in result)
        assert any("b.xapk" in s for s in result)

    def test_empty_dir(self, tmp_path):
        au = AutoUpdater(watch_dir=str(tmp_path),
                         log_callback=lambda *a: None)
        assert au._scan() == set()


# ============================================================
# start / stop
# ============================================================
class TestStartStop:
    def test_start_creates_watch_dir(self, tmp_path):
        target = tmp_path / "missing_subdir"
        au = AutoUpdater(watch_dir=str(target),
                         log_callback=lambda *a: None,
                         poll_interval=0.05)
        au.start()
        try:
            assert target.exists()
            assert au._thread is not None
        finally:
            au.stop()

    def test_start_idempotent(self, tmp_path):
        au = AutoUpdater(watch_dir=str(tmp_path),
                         log_callback=lambda *a: None,
                         poll_interval=0.05)
        au.start()
        try:
            first = au._thread
            au.start()  # no-op
            assert au._thread is first
        finally:
            au.stop()

    def test_stop_sets_event(self, tmp_path):
        au = AutoUpdater(watch_dir=str(tmp_path),
                         log_callback=lambda *a: None,
                         poll_interval=0.05)
        au.start()
        au.stop()
        assert au._stop.is_set()

    def test_stop_idempotent(self, tmp_path):
        au = AutoUpdater(watch_dir=str(tmp_path),
                         log_callback=lambda *a: None)
        au.stop()  # no thread yet — should not raise
        au.stop()


# ============================================================
# _process
# ============================================================
class TestProcess:
    def test_no_callback_only_logs(self, tmp_path):
        apk = tmp_path / "a.apk"
        apk.write_bytes(b"x")
        msgs: list[str] = []
        au = AutoUpdater(watch_dir=str(tmp_path),
                         log_callback=msgs.append)
        au._process(str(apk))
        assert any("New" in m for m in msgs)

    def test_apk_read_error_returns(self, tmp_path):
        apk = tmp_path / "a.apk"
        apk.write_bytes(b"x")
        au = AutoUpdater(watch_dir=str(tmp_path),
                         log_callback=lambda *a: None,
                         pipeline_callback=MagicMock())

        with patch("androguard.core.apk.APK",
                   side_effect=Exception("bad apk")):
            au._process(str(apk))  # should not raise

    def test_no_history_match_skips_callback(self, tmp_path):
        apk = tmp_path / "a.apk"
        apk.write_bytes(b"x")
        cb = MagicMock()
        au = AutoUpdater(watch_dir=str(tmp_path),
                         log_callback=lambda *a: None,
                         pipeline_callback=cb)

        mock_apk = MagicMock()
        mock_apk.get_package.return_value = "com.test.app"

        with patch("androguard.core.apk.APK", return_value=mock_apk), \
             patch("core.auto_updater.PatchHistory") as ph:
            ph.return_value.get_history.return_value = []
            au._process(str(apk))

        cb.assert_not_called()

    def test_history_match_calls_pipeline(self, tmp_path):
        apk = tmp_path / "a.apk"
        apk.write_bytes(b"x")
        cb = MagicMock()
        au = AutoUpdater(watch_dir=str(tmp_path),
                         log_callback=lambda *a: None,
                         pipeline_callback=cb)

        mock_apk = MagicMock()
        mock_apk.get_package.return_value = "com.test.app"

        history = [
            {"success": True, "apk": "/path/com.test.app-v1.apk",
             "mode": "license:auto"},
        ]

        with patch("androguard.core.apk.APK", return_value=mock_apk), \
             patch("core.auto_updater.PatchHistory") as ph:
            ph.return_value.get_history.return_value = history
            au._process(str(apk))

        cb.assert_called_once_with(str(apk), "license:auto")

    def test_history_failed_record_skipped(self, tmp_path):
        apk = tmp_path / "a.apk"
        apk.write_bytes(b"x")
        cb = MagicMock()
        au = AutoUpdater(watch_dir=str(tmp_path),
                         log_callback=lambda *a: None,
                         pipeline_callback=cb)

        mock_apk = MagicMock()
        mock_apk.get_package.return_value = "com.test.app"

        history = [
            {"success": False, "apk": "com.test.app", "mode": "license"},
        ]

        with patch("androguard.core.apk.APK", return_value=mock_apk), \
             patch("core.auto_updater.PatchHistory") as ph:
            ph.return_value.get_history.return_value = history
            au._process(str(apk))

        cb.assert_not_called()

    def test_pipeline_callback_exception_isolated(self, tmp_path):
        apk = tmp_path / "a.apk"
        apk.write_bytes(b"x")
        cb = MagicMock(side_effect=Exception("boom"))
        au = AutoUpdater(watch_dir=str(tmp_path),
                         log_callback=lambda *a: None,
                         pipeline_callback=cb)

        mock_apk = MagicMock()
        mock_apk.get_package.return_value = "com.test.app"

        history = [
            {"success": True, "apk": "com.test.app",
             "mode": "license"},
        ]

        with patch("androguard.core.apk.APK", return_value=mock_apk), \
             patch("core.auto_updater.PatchHistory") as ph:
            ph.return_value.get_history.return_value = history
            au._process(str(apk))  # should not raise


# ============================================================
# _run loop
# ============================================================
class TestRunLoop:
    def test_run_detects_new_file(self, tmp_path):
        """
        Regression fix: file phải được tạo SAU `start()`.

        Lý do: `start()` gọi `_known = self._scan()` — nếu file đã tồn tại
        trước start, nó nằm trong baseline → không detect là "new".
        Race condition trong test cũ (đã fix bằng cách tạo file sau start).
        """
        au = AutoUpdater(watch_dir=str(tmp_path),
                         log_callback=lambda *a: None,
                         poll_interval=0.02)

        calls: list[str] = []
        au._process = lambda p: calls.append(p)

        # start() TRƯỚC — scan lần đầu: empty dir → _known = set()
        au.start()
        try:
            # Tạo file SAU khi start → loop tiếp theo sẽ thấy là "new"
            apk = tmp_path / "new.apk"
            apk.write_bytes(b"x")
            # Đợi ~10 polls @ 20ms
            time.sleep(0.2)
        finally:
            au.stop()

        assert str(apk) in calls

    def test_run_loop_skips_known_files(self, tmp_path):
        """File đã có trước start() → không trigger _process."""
        apk = tmp_path / "old.apk"
        apk.write_bytes(b"x")

        au = AutoUpdater(watch_dir=str(tmp_path),
                         log_callback=lambda *a: None,
                         poll_interval=0.02)

        calls: list[str] = []
        au._process = lambda p: calls.append(p)

        au.start()
        try:
            time.sleep(0.1)
        finally:
            au.stop()

        assert calls == []

    def test_run_loop_stop_interrupts(self, tmp_path):
        """stop() phải break loop nhanh, không cần đợi hết interval."""
        au = AutoUpdater(watch_dir=str(tmp_path),
                         log_callback=lambda *a: None,
                         poll_interval=10.0)  # interval dài

        au.start()
        t0 = time.monotonic()
        au.stop()  # .join(timeout=2)
        elapsed = time.monotonic() - t0

        # stop() join timeout = 2s → không được block quá 2.5s
        assert elapsed < 2.5