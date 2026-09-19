"""Test core/subprocess_runner.py — java subprocess wrapper."""
import subprocess
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from core.subprocess_runner import (
    _get_tree_cpu_seconds,
    run_java_with_heartbeat,
)


# ============================================================
# _get_tree_cpu_seconds
# ============================================================
class TestGetTreeCpuSeconds:
    def test_returns_float(self):
        result = _get_tree_cpu_seconds(999999)  # nonexistent pid
        assert isinstance(result, float)
        assert result >= 0.0

    def test_own_pid_returns_value(self):
        import os
        result = _get_tree_cpu_seconds(os.getpid())
        # May be 0 if cpu_times not accessible, but should be float
        assert isinstance(result, float)


# ============================================================
# run_java_with_heartbeat
# ============================================================
def _make_fake_proc(rc=0, stdout_lines=None, delay=0.0):
    """Tạo fake Popen object."""
    proc = MagicMock()
    proc.pid = 12345
    proc.returncode = rc

    if stdout_lines is not None:
        # Use iter for stdout
        proc.stdout = iter([f"{l}\n" for l in stdout_lines])
    else:
        proc.stdout = iter([])

    def _wait(timeout=None):
        if delay:
            time.sleep(delay)
        return rc

    proc.wait = _wait
    proc.kill = MagicMock()
    return proc


class TestRunJavaWithHeartbeat:
    def test_success_rc_0(self):
        logs = []
        proc = _make_fake_proc(rc=0, stdout_lines=["line1", "line2"])

        with patch(
            "core.subprocess_runner.subprocess.Popen",
            return_value=proc,
        ):
            rc, output = run_java_with_heartbeat(
                ["fake", "cmd"], logs.append, "Test",
                timeout_sec=5, heartbeat_sec=1,
            )
        assert rc == 0
        assert "line1" in output
        assert "line2" in output
        assert any("Xong" in l for l in logs)

    def test_failure_rc_nonzero(self):
        logs = []
        proc = _make_fake_proc(rc=42)

        with patch(
            "core.subprocess_runner.subprocess.Popen",
            return_value=proc,
        ):
            rc, _ = run_java_with_heartbeat(
                ["fake"], logs.append, "Test",
                timeout_sec=5, heartbeat_sec=1,
            )
        assert rc == 42

    def test_popen_oserror_returns_minus1(self):
        logs = []
        with patch(
            "core.subprocess_runner.subprocess.Popen",
            side_effect=OSError("no java"),
        ):
            rc, out = run_java_with_heartbeat(
                ["fake"], logs.append, "Test",
                timeout_sec=5,
            )
        assert rc == -1
        assert out == ""
        assert any("Không chạy" in l for l in logs)

    def test_timeout_kills_proc(self):
        logs = []
        proc = MagicMock()
        proc.pid = 12345
        proc.stdout = iter([])
        proc.kill = MagicMock()

        # wait raises TimeoutExpired
        def _wait(timeout=None):
            raise subprocess.TimeoutExpired("cmd", timeout)

        proc.wait = _wait

        with patch(
            "core.subprocess_runner.subprocess.Popen",
            return_value=proc,
        ):
            rc, _ = run_java_with_heartbeat(
                ["fake"], logs.append, "Test",
                timeout_sec=0.5, heartbeat_sec=0.2,
            )
        assert rc == -1
        proc.kill.assert_called()

    def test_stream_callback_invoked(self):
        logs = []
        proc = _make_fake_proc(rc=0, stdout_lines=["a", "b", "c"])

        with patch(
            "core.subprocess_runner.subprocess.Popen",
            return_value=proc,
        ):
            run_java_with_heartbeat(
                ["x"], logs.append, "Label",
                timeout_sec=5, heartbeat_sec=1,
            )

        # Each line prefixed with spaces from _stream
        assert any("    a" in l for l in logs)
        assert any("    b" in l for l in logs)

    def test_empty_output_lines_ignored(self):
        logs = []
        proc = _make_fake_proc(rc=0, stdout_lines=["", "  ", "real"])

        with patch(
            "core.subprocess_runner.subprocess.Popen",
            return_value=proc,
        ):
            rc, output = run_java_with_heartbeat(
                ["x"], logs.append, "Label",
                timeout_sec=5, heartbeat_sec=1,
            )
        assert rc == 0
        assert "real" in output