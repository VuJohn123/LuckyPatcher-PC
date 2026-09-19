"""Test core/safety_guard.py — counters, own-tree CPU, CLI fallback."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from core.safety_guard import (
    _JAVA_NAMES,
    _TOOL_KEYWORDS,
    GuardLimits,
    SafetyGuard,
)


# ============================================================
# GuardLimits
# ============================================================
class TestGuardLimits:
    def test_defaults(self):
        lim = GuardLimits()
        assert lim.max_cpu_pct == 98.0
        assert lim.max_ram_pct == 85.0
        assert lim.enabled is True
        assert lim.reset_after_ok_checks == 3
        assert lim.cli_mode_action == "mute"

    def test_overrides(self):
        lim = GuardLimits(
            max_cpu_pct=50.0, enabled=False, cli_mode_action="abort",
        )
        assert lim.max_cpu_pct == 50.0
        assert lim.enabled is False
        assert lim.cli_mode_action == "abort"


# ============================================================
# Constructor
# ============================================================
class TestConstructor:
    def test_defaults(self):
        g = SafetyGuard()
        assert g.limits.max_cpu_pct == 98.0
        assert g.prompt_after_n == 5
        assert g.abort_flag is False

    def test_prompt_after_n_minimum_1(self):
        g = SafetyGuard(prompt_after_n_violations=0)
        assert g.prompt_after_n == 1
        g2 = SafetyGuard(prompt_after_n_violations=-5)
        assert g2.prompt_after_n == 1


# ============================================================
# _record_ok — counter reset semantics
# ============================================================
class TestRecordOk:
    def test_reset_after_n_ok(self):
        g = SafetyGuard(limits=GuardLimits(reset_after_ok_checks=3))
        g._consecutive["cpu"] = 5
        # 2 OK → không reset
        g._record_ok("cpu")
        g._record_ok("cpu")
        assert g._consecutive["cpu"] == 5
        # OK thứ 3 → reset
        g._record_ok("cpu")
        assert g._consecutive["cpu"] == 0

    def test_ok_streak_resets_on_violation(self):
        g = SafetyGuard(limits=GuardLimits(reset_after_ok_checks=3))
        g._record_ok("cpu")
        g._record_ok("cpu")
        assert g._ok_streak["cpu"] == 2
        # Violation reset streak
        g._handle_violation("cpu", {"used_pct": 99, "threshold": 98})
        assert g._ok_streak["cpu"] == 0


# ============================================================
# _get_own_tree_cpu_time — mock psutil
# ============================================================
class TestGetOwnTreeCpuTime:
    def _make_proc(self, pid, user=1.0, system=0.5, children=None,
                   name="", cmdline=None):
        p = MagicMock()
        p.pid = pid
        ct = MagicMock()
        ct.user = user
        ct.system = system
        p.cpu_times.return_value = ct
        p.children.return_value = children or []
        p.info = {"pid": pid, "name": name, "cmdline": cmdline or []}
        return p

    def test_none_own_process_returns_0(self):
        g = SafetyGuard()
        ps = MagicMock()
        assert g._get_own_tree_cpu_time(ps) == 0.0

    def test_own_process_only(self):
        g = SafetyGuard()
        own = self._make_proc(100, user=2.0, system=1.0)
        g._own_process = own
        ps = MagicMock()
        ps.process_iter.return_value = iter([])
        total = g._get_own_tree_cpu_time(ps)
        assert total == pytest.approx(3.0)

    def test_own_process_with_children(self):
        g = SafetyGuard()
        child1 = self._make_proc(101, user=1.0, system=0.5)
        child2 = self._make_proc(102, user=0.5, system=0.5)
        own = self._make_proc(100, user=2.0, system=1.0,
                              children=[child1, child2])
        g._own_process = own
        ps = MagicMock()
        ps.process_iter.return_value = iter([])
        total = g._get_own_tree_cpu_time(ps)
        assert total == pytest.approx(3.0 + 1.5 + 1.0)

    def test_nailgun_daemon_detected(self):
        g = SafetyGuard()
        g._own_process = self._make_proc(100, user=0.5, system=0.5)
        daemon = self._make_proc(
            200, user=10.0, system=5.0,
            name="java.exe",
            cmdline=["java", "-cp", "ng-server.jar",
                     "com.facebook.nailgun.NGServer"],
        )
        ps = MagicMock()
        ps.process_iter.return_value = iter([daemon])
        total = g._get_own_tree_cpu_time(ps)
        assert total == pytest.approx(1.0 + 15.0)

    def test_tool_keyword_matched(self):
        g = SafetyGuard()
        g._own_process = self._make_proc(100, user=0.5, system=0.5)
        apktool = self._make_proc(
            300, user=20.0, system=3.0,
            name="java.exe",
            cmdline=["java", "-jar", "C:/tools/apktool.jar", "d", "a.apk"],
        )
        ps = MagicMock()
        ps.process_iter.return_value = iter([apktool])
        total = g._get_own_tree_cpu_time(ps)
        assert total >= 20.0

    def test_new_java_process_detected(self):
        """Java process spawn sau guard.start() (không trong baseline)."""
        g = SafetyGuard()
        g._own_process = self._make_proc(100, user=0.1, system=0.1)
        g._baseline_pids = {50, 51, 52}
        g._baseline_ready = True

        new_java = self._make_proc(
            999, user=15.0, system=2.0, name="java.exe",
            cmdline=["java", "-Xmx4096m", "SomeTool"],
        )
        ps = MagicMock()
        ps.process_iter.return_value = iter([new_java])
        total = g._get_own_tree_cpu_time(ps)
        assert total >= 17.0

    def test_baseline_java_NOT_double_counted(self):
        """Java process CÓ trong baseline → không đếm."""
        g = SafetyGuard()
        g._own_process = self._make_proc(100, user=0.1, system=0.1)
        g._baseline_pids = {500}
        g._baseline_ready = True

        baseline_java = self._make_proc(
            500, user=100.0, system=50.0, name="java.exe",
            cmdline=["java", "-jar", "unrelated-tool.jar"],
        )
        ps = MagicMock()
        ps.process_iter.return_value = iter([baseline_java])
        total = g._get_own_tree_cpu_time(ps)
        # Chỉ đếm own process (0.2), KHÔNG đếm baseline java
        assert total == pytest.approx(0.2)

    def test_no_duplicate_pid(self):
        """Process xuất hiện 2 lần → không double-count."""
        g = SafetyGuard()
        own = self._make_proc(100, user=1.0, system=1.0)
        g._own_process = own
        # Same PID 100 xuất hiện trong process_iter
        dup = self._make_proc(
            100, user=999.0, system=999.0,
            cmdline=["java", "apktool.jar"],
        )
        ps = MagicMock()
        ps.process_iter.return_value = iter([dup])
        total = g._get_own_tree_cpu_time(ps)
        assert total == pytest.approx(2.0)  # chỉ đếm own

    def test_access_denied_graceful(self):
        g = SafetyGuard()
        own = self._make_proc(100, user=1.0, system=0.5)
        g._own_process = own
        ps = MagicMock()
        ps.process_iter.side_effect = Exception("permission denied")
        # Không crash
        total = g._get_own_tree_cpu_time(ps)
        assert total == pytest.approx(1.5)

    def test_missing_psutil_exception_types(self):
        """psutil.NoSuchProcess khi access proc.pid → skip."""
        g = SafetyGuard()
        own = self._make_proc(100, user=1.0, system=0.5)
        g._own_process = own
        ps = MagicMock()

        class NoSuchProcess(Exception):
            pass

        ps.NoSuchProcess = NoSuchProcess
        ps.AccessDenied = Exception
        ps.process_iter.return_value = iter([])
        total = g._get_own_tree_cpu_time(ps)
        assert total == pytest.approx(1.5)


# ============================================================
# _measure_own_tree_cpu
# ============================================================
class TestMeasureOwnTreeCpu:
    def test_first_call_returns_0(self):
        g = SafetyGuard()
        g._own_process = MagicMock()
        ps = MagicMock()
        with patch.object(g, "_get_own_tree_cpu_time", return_value=10.0):
            result = g._measure_own_tree_cpu(ps)
        assert result == 0.0
        assert g._last_cpu_time == 10.0

    def test_delta_computation(self):
        g = SafetyGuard()
        g._own_process = MagicMock()
        g._cpu_count = 4
        g._last_cpu_time = 100.0
        g._last_cpu_ts = time.monotonic() - 1.0  # 1s ago

        ps = MagicMock()
        with patch.object(g, "_get_own_tree_cpu_time",
                          return_value=102.0):  # +2s cpu over 1s wall
            result = g._measure_own_tree_cpu(ps)
        # 2/1/4 * 100 = 50%
        assert result == pytest.approx(50.0, rel=0.5)

    def test_zero_delta_wall_returns_0(self):
        """delta_wall = 0 → return 0 (không chia cho 0)."""
        g = SafetyGuard()
        g._own_process = MagicMock()
        g._last_cpu_time = 100.0
        g._last_cpu_ts = 1000.0  # fixed

        ps = MagicMock()
        # Patch time.monotonic để cả 2 lần gọi trả cùng giá trị
        with patch("core.safety_guard.time.monotonic",
                   return_value=1000.0), \
             patch.object(g, "_get_own_tree_cpu_time",
                          return_value=200.0):
            result = g._measure_own_tree_cpu(ps)
        # delta_wall = 1000 - 1000 = 0 ≤ 0.001 → return 0.0
        assert result == 0.0

    def test_caps_at_100(self):
        g = SafetyGuard()
        g._own_process = MagicMock()
        g._cpu_count = 1
        g._last_cpu_time = 0.0
        g._last_cpu_ts = time.monotonic() - 1.0
        ps = MagicMock()
        with patch.object(g, "_get_own_tree_cpu_time",
                          return_value=9999.0):
            result = g._measure_own_tree_cpu(ps)
        assert result == 100.0


# ============================================================
# _handle_violation
# ============================================================
class TestHandleViolation:
    def test_muted_skipped(self):
        logs = []
        g = SafetyGuard(log_callback=logs.append)
        g._muted.add("cpu")
        g._handle_violation("cpu", {"x": 1})
        assert logs == []

    def test_prompting_skipped(self):
        logs = []
        g = SafetyGuard(log_callback=logs.append)
        g._prompting.add("cpu")
        g._handle_violation("cpu", {"x": 1})
        assert logs == []

    def test_first_violation_logs_details(self):
        logs = []
        g = SafetyGuard(log_callback=logs.append)
        g._handle_violation("cpu", {"used_pct": 99, "threshold": 98})
        assert any("CPU #1" in l and "used_pct" in l for l in logs)
        assert g._consecutive["cpu"] == 1

    def test_grace_no_throttle_first(self):
        """Violation #1 không gọi on_violation."""
        on_viol = MagicMock()
        g = SafetyGuard(on_violation=on_viol, log_callback=lambda *_: None)
        g._handle_violation("cpu", {})
        on_viol.assert_not_called()

    def test_grace_throttle_at_n2(self):
        """Violation #2 mới throttle."""
        on_viol = MagicMock()
        g = SafetyGuard(on_violation=on_viol, log_callback=lambda *_: None)
        g._handle_violation("cpu", {})
        g._handle_violation("cpu", {})
        on_viol.assert_called_once()

    def test_on_violation_exception_isolated(self):
        def bad(*a, **k):
            raise RuntimeError("callback boom")
        g = SafetyGuard(on_violation=bad, log_callback=lambda *_: None)
        g._handle_violation("cpu", {})
        # No crash
        g._handle_violation("cpu", {})


# ============================================================
# _cli_fallback — 3 modes
# ============================================================
class TestCliFallback:
    def test_mute_mode(self):
        logs = []
        on_mute = MagicMock()
        g = SafetyGuard(
            limits=GuardLimits(cli_mode_action="mute"),
            on_mute=on_mute,
            log_callback=logs.append,
        )
        g._consecutive["cpu"] = 3
        g._cli_fallback("cpu", {}, 5)

        assert "cpu" in g._muted
        assert g._consecutive["cpu"] == 0
        on_mute.assert_called_once_with("cpu")
        assert any("auto-MUTE" in l for l in logs)

    def test_abort_mode(self):
        logs = []
        g = SafetyGuard(
            limits=GuardLimits(cli_mode_action="abort"),
            log_callback=logs.append,
        )
        g._cli_fallback("cpu", {}, 5)
        assert g.abort_flag is True
        assert any("ABORT" in l for l in logs)

    def test_continue_mode(self):
        logs = []
        g = SafetyGuard(
            limits=GuardLimits(cli_mode_action="continue"),
            log_callback=logs.append,
        )
        initial = g.limits.max_cpu_pct
        g._consecutive["cpu"] = 4
        g._cli_fallback("cpu", {}, 5)

        assert g.limits.max_cpu_pct > initial
        assert g._consecutive["cpu"] == 0
        assert any("nâng ngưỡng" in l for l in logs)

    def test_invalid_action_falls_back_to_mute(self):
        logs = []
        g = SafetyGuard(
            limits=GuardLimits(cli_mode_action="bogus"),
            log_callback=logs.append,
        )
        g._cli_fallback("cpu", {}, 5)
        assert "cpu" in g._muted
        assert any("không hợp lệ" in l for l in logs)


# ============================================================
# _prompt_gui
# ============================================================
class TestPromptGui:
    def test_continue_mutes_and_raises(self):
        """
        Continue: mute + raise threshold.
        Threshold 90 → 95 (không bị cap 99).
        """
        on_mute = MagicMock()
        on_prompt = MagicMock(return_value=True)
        logs = []
        g = SafetyGuard(
            on_prompt=on_prompt,
            on_mute=on_mute,
            threshold_raise_pct=5.0,
            log_callback=logs.append,
        )
        # Set 90 để test raise không cap
        g.limits.max_cpu_pct = 90.0
        g._prompt_gui("cpu", {}, 5)

        assert "cpu" in g._muted
        assert g.limits.max_cpu_pct == 95.0  # 90 + 5
        on_mute.assert_called_once_with("cpu")
        assert g.abort_flag is False

    def test_continue_caps_threshold_at_99(self):
        """Continue khi threshold gần max → cap 99."""
        g = SafetyGuard(
            on_prompt=lambda *a: True,
            threshold_raise_pct=5.0,
            log_callback=lambda *_: None,
        )
        g.limits.max_cpu_pct = 98.0
        g._prompt_gui("cpu", {}, 5)
        assert g.limits.max_cpu_pct == 99.0

    def test_stop_aborts(self):
        on_prompt = MagicMock(return_value=False)
        logs = []
        g = SafetyGuard(
            on_prompt=on_prompt,
            log_callback=logs.append,
        )
        g._prompt_gui("cpu", {}, 5)
        assert g.abort_flag is True
        assert "cpu" not in g._muted
        assert any("DỪNG" in l for l in logs)

    def test_prompt_exception_isolated(self):
        def bad(*a, **k):
            raise RuntimeError("prompt crash")
        g = SafetyGuard(
            on_prompt=bad,
            log_callback=lambda *_: None,
        )
        # Exception → default continue
        g._prompt_gui("cpu", {}, 5)
        assert "cpu" in g._muted
        assert g.abort_flag is False

    def test_prompting_set_cleared_after(self):
        """_prompting phải được clear dù exception hay không."""
        g = SafetyGuard(
            on_prompt=lambda *a: True,
            log_callback=lambda *_: None,
        )
        g._prompt_gui("cpu", {}, 5)
        assert "cpu" not in g._prompting


# ============================================================
# Threshold
# ============================================================
class TestThreshold:
    def test_raise_cpu(self):
        g = SafetyGuard(threshold_raise_pct=5.0)
        g.limits.max_cpu_pct = 90.0
        g._raise_threshold("cpu")
        assert g.limits.max_cpu_pct == 95.0

    def test_raise_cpu_capped_at_99(self):
        g = SafetyGuard(threshold_raise_pct=10.0)
        g.limits.max_cpu_pct = 95.0
        g._raise_threshold("cpu")
        assert g.limits.max_cpu_pct == 99.0

    def test_raise_ram(self):
        g = SafetyGuard(threshold_raise_pct=3.0)
        g.limits.max_ram_pct = 80.0
        g._raise_threshold("ram")
        assert g.limits.max_ram_pct == 83.0

    def test_raise_temp(self):
        g = SafetyGuard(threshold_raise_pct=2.0)
        g.limits.max_temp_celsius = 80.0
        g._raise_threshold("temp")
        assert g.limits.max_temp_celsius == 82.0

    def test_disk_not_raised(self):
        g = SafetyGuard(threshold_raise_pct=5.0)
        initial = g.limits.min_disk_free_pct
        g._raise_threshold("disk")
        assert g.limits.min_disk_free_pct == initial

    def test_get_threshold(self):
        g = SafetyGuard(limits=GuardLimits(
            max_cpu_pct=90.0, max_ram_pct=80.0,
            max_temp_celsius=70.0, min_disk_free_pct=15.0,
        ))
        assert g._get_threshold("cpu") == 90.0
        assert g._get_threshold("ram") == 80.0
        assert g._get_threshold("temp") == 70.0
        assert g._get_threshold("disk") == 15.0
        assert g._get_threshold("unknown") == 0.0


# ============================================================
# Lifecycle
# ============================================================
class TestLifecycle:
    def test_start_disabled_skips(self):
        logs = []
        g = SafetyGuard(
            limits=GuardLimits(enabled=False),
            log_callback=logs.append,
        )
        g.start()
        assert g._thread is None
        assert any("Disabled" in l for l in logs)

    def test_stop_idempotent(self):
        logs = []
        g = SafetyGuard(log_callback=logs.append)
        g.stop()  # No thread started
        g.stop()  # Should not crash


# ============================================================
# Constants
# ============================================================
def test_tool_keywords_contains_apktool():
    assert any("apktool" in k for k in _TOOL_KEYWORDS)


def test_java_names_contains_java():
    assert "java" in _JAVA_NAMES
    assert "java.exe" in _JAVA_NAMES