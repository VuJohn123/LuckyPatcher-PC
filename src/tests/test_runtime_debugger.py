"""Test core/runtime_debugger.py — logcat pattern detection."""
from __future__ import annotations

import subprocess
import threading
from unittest.mock import MagicMock, patch

import pytest

from core.runtime_debugger import RuntimeDebugger, _PATTERNS


# ============================================================
# Init
# ============================================================
class TestInit:
    def test_basic(self):
        dbg = RuntimeDebugger("com.test", log_callback=lambda *a: None)
        assert dbg.package == "com.test"
        assert dbg.suggest is None
        assert dbg._proc is None
        assert dbg._thread is None

    def test_with_suggestion_callback(self):
        cb = MagicMock()
        dbg = RuntimeDebugger("com.test", log_callback=lambda *a: None,
                              suggestion_callback=cb)
        assert dbg.suggest is cb

    def test_patterns_defined(self):
        assert "gms_error" in _PATTERNS
        assert "license_error" in _PATTERNS
        assert "billing_error" in _PATTERNS
        assert "signature_error" in _PATTERNS


# ============================================================
# _analyze
# ============================================================
class TestAnalyze:
    def test_gms_pattern_match(self):
        msgs: list[str] = []
        dbg = RuntimeDebugger("com.test", log_callback=msgs.append)
        dbg._analyze("Google Play services is not available\n")
        assert any("gms_spoof" in m for m in msgs)

    def test_license_pattern_match(self):
        msgs: list[str] = []
        dbg = RuntimeDebugger("com.test", log_callback=msgs.append)
        dbg._analyze("License check failed: dontAllow\n")
        assert any("license:extreme" in m for m in msgs)

    def test_billing_pattern_match(self):
        msgs: list[str] = []
        dbg = RuntimeDebugger("com.test", log_callback=msgs.append)
        dbg._analyze("Billing error: RESPONSE_CODE 5\n")
        assert any("iap:dex" in m for m in msgs)

    def test_signature_pattern_match(self):
        msgs: list[str] = []
        dbg = RuntimeDebugger("com.test", log_callback=msgs.append)
        dbg._analyze("Signature mismatch on verify\n")
        assert any("sig_disable" in m for m in msgs)

    def test_no_match_silent(self):
        msgs: list[str] = []
        dbg = RuntimeDebugger("com.test", log_callback=msgs.append)
        dbg._analyze("Some random log line\n")
        assert msgs == []

    def test_suggestion_callback_invoked(self):
        cb = MagicMock()
        dbg = RuntimeDebugger("com.test", log_callback=lambda *a: None,
                              suggestion_callback=cb)
        dbg._analyze("License check failed\n")
        cb.assert_called_once()

    def test_suggestion_callback_exception_isolated(self):
        cb = MagicMock(side_effect=Exception("boom"))
        dbg = RuntimeDebugger("com.test", log_callback=lambda *a: None,
                              suggestion_callback=cb)
        dbg._analyze("License check failed\n")  # should not raise

    def test_first_match_wins(self):
        """Multiple patterns matching → only first logged."""
        cb = MagicMock()
        dbg = RuntimeDebugger("com.test", log_callback=lambda *a: None,
                              suggestion_callback=cb)
        # Line matching both gms AND license
        dbg._analyze("Google Play services not available License check fail\n")
        cb.assert_called_once()


# ============================================================
# start
# ============================================================
class TestStart:
    def test_start_popen_success(self):
        dbg = RuntimeDebugger("com.test", log_callback=lambda *a: None)
        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        with patch.object(subprocess, "Popen", return_value=mock_proc), \
             patch("threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            dbg.start()
            mock_thread.assert_called_once()

    def test_start_popen_oserror(self):
        msgs: list[str] = []
        dbg = RuntimeDebugger("com.test", log_callback=msgs.append)
        with patch.object(subprocess, "Popen",
                          side_effect=OSError("no adb")):
            dbg.start()
        assert any("logcat start failed" in m for m in msgs)

    def test_start_already_running(self):
        dbg = RuntimeDebugger("com.test", log_callback=lambda *a: None)
        fake_thread = MagicMock()
        fake_thread.is_alive.return_value = True
        dbg._thread = fake_thread
        dbg.start()  # should return early
        # _proc vẫn None
        assert dbg._proc is None


# ============================================================
# _read_loop
# ============================================================
class TestReadLoop:
    def test_analyze_called_per_line(self):
        dbg = RuntimeDebugger("com.test", log_callback=lambda *a: None)
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["line1\n", "line2\n", "line3\n"])
        dbg._proc = mock_proc
        dbg._analyze = MagicMock()
        dbg._read_loop()
        assert dbg._analyze.call_count == 3

    def test_stop_breaks_loop(self):
        dbg = RuntimeDebugger("com.test", log_callback=lambda *a: None)
        dbg._stop.set()
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["line1\n", "line2\n"])
        dbg._proc = mock_proc
        dbg._analyze = MagicMock()
        dbg._read_loop()
        # Stop was set → first iteration breaks
        dbg._analyze.assert_not_called()

    def test_no_proc_returns_silent(self):
        dbg = RuntimeDebugger("com.test", log_callback=lambda *a: None)
        dbg._proc = None
        dbg._read_loop()  # should not raise

    def test_proc_no_stdout(self):
        dbg = RuntimeDebugger("com.test", log_callback=lambda *a: None)
        mock_proc = MagicMock()
        mock_proc.stdout = None
        dbg._proc = mock_proc
        dbg._read_loop()  # should not raise


# ============================================================
# stop
# ============================================================
class TestStop:
    def test_stop_sets_event(self):
        dbg = RuntimeDebugger("com.test", log_callback=lambda *a: None)
        dbg.stop()
        assert dbg._stop.is_set()

    def test_stop_terminates_proc(self):
        dbg = RuntimeDebugger("com.test", log_callback=lambda *a: None)
        mock_proc = MagicMock()
        dbg._proc = mock_proc
        dbg.stop()
        mock_proc.terminate.assert_called_once()

    def test_stop_proc_terminate_oserror_isolated(self):
        dbg = RuntimeDebugger("com.test", log_callback=lambda *a: None)
        mock_proc = MagicMock()
        mock_proc.terminate.side_effect = OSError("already dead")
        dbg._proc = mock_proc
        dbg.stop()  # should not raise

    def test_stop_no_proc(self):
        dbg = RuntimeDebugger("com.test", log_callback=lambda *a: None)
        dbg.stop()  # should not raise