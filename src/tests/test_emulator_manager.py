"""Test core/emulator_manager.py — emulator lifecycle."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import core.emulator_manager as em
from core.emulator_manager import EmulatorManager


# ============================================================
# _find_emulator
# ============================================================
class TestFindEmulator:
    def test_from_path(self):
        with patch("shutil.which") as wh:
            wh.side_effect = lambda x: "/usr/bin/emulator" if x == "emulator" else None
            mgr = EmulatorManager(log_callback=lambda *a: None)
            assert mgr.emulator == "emulator"

    def test_from_android_home(self, tmp_path, monkeypatch):
        fake_sdk = tmp_path / "sdk"
        (fake_sdk / "emulator").mkdir(parents=True)
        exe_name = "emulator.exe" if os.name == "nt" else "emulator"
        (fake_sdk / "emulator" / exe_name).write_bytes(b"x")

        monkeypatch.setenv("ANDROID_HOME", str(fake_sdk))
        with patch("shutil.which", return_value=None):
            mgr = EmulatorManager(log_callback=lambda *a: None)
            assert mgr.emulator is not None
            assert "emulator" in mgr.emulator

    def test_from_android_sdk_root(self, tmp_path, monkeypatch):
        fake_sdk = tmp_path / "sdk2"
        (fake_sdk / "emulator").mkdir(parents=True)
        exe_name = "emulator.exe" if os.name == "nt" else "emulator"
        (fake_sdk / "emulator" / exe_name).write_bytes(b"x")

        monkeypatch.delenv("ANDROID_HOME", raising=False)
        monkeypatch.setenv("ANDROID_SDK_ROOT", str(fake_sdk))
        with patch("shutil.which", return_value=None):
            mgr = EmulatorManager(log_callback=lambda *a: None)
            assert mgr.emulator is not None

    def test_not_found(self, monkeypatch):
        monkeypatch.delenv("ANDROID_HOME", raising=False)
        monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
        with patch("shutil.which", return_value=None):
            mgr = EmulatorManager(log_callback=lambda *a: None)
            assert mgr.emulator is None

    def test_android_home_path_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANDROID_HOME", str(tmp_path / "nope"))
        with patch("shutil.which", return_value=None):
            mgr = EmulatorManager(log_callback=lambda *a: None)
            assert mgr.emulator is None


# ============================================================
# is_running
# ============================================================
class TestIsRunning:
    def test_emulator_in_output(self):
        mgr = EmulatorManager(log_callback=lambda *a: None)
        fake = MagicMock(stdout="List of devices\nemulator-5554\tdevice\n")
        with patch.object(subprocess, "run", return_value=fake):
            assert mgr.is_running() is True

    def test_no_emulator(self):
        mgr = EmulatorManager(log_callback=lambda *a: None)
        fake = MagicMock(stdout="List of devices\n192.168.1.1:5555\tdevice\n")
        with patch.object(subprocess, "run", return_value=fake):
            assert mgr.is_running() is False

    def test_subprocess_error(self):
        mgr = EmulatorManager(log_callback=lambda *a: None)
        with patch.object(
            subprocess, "run",
            side_effect=subprocess.SubprocessError("fail"),
        ):
            assert mgr.is_running() is False


# ============================================================
# start
# ============================================================
class TestStart:
    def test_already_running(self):
        mgr = EmulatorManager(log_callback=lambda *a: None)
        mgr.is_running = lambda: True
        msgs: list[str] = []
        mgr.log = msgs.append
        assert mgr.start() is True
        assert any("đã chạy" in m for m in msgs)

    def test_no_emulator_binary(self):
        mgr = EmulatorManager(log_callback=lambda *a: None)
        mgr.emulator = None
        mgr.is_running = lambda: False
        assert mgr.start() is False

    def test_popen_oserror(self):
        mgr = EmulatorManager(log_callback=lambda *a: None)
        mgr.emulator = "emulator"
        mgr.is_running = lambda: False
        with patch.object(subprocess, "Popen",
                          side_effect=OSError("no exec")):
            assert mgr.start() is False

    def test_timeout(self, tmp_path):
        mgr = EmulatorManager(log_callback=lambda *a: None)
        mgr.emulator = "emulator"
        mgr.is_running = lambda: False
        with patch.object(subprocess, "Popen", return_value=MagicMock()), \
             patch("time.sleep"):
            assert mgr.start(timeout=0) is False

    def test_success(self):
        mgr = EmulatorManager(log_callback=lambda *a: None)
        mgr.emulator = "emulator"
        # First call (pre-check) False, then True on poll
        calls = {"n": 0}
        def fake_running():
            calls["n"] += 1
            return calls["n"] >= 2
        mgr.is_running = fake_running
        with patch.object(subprocess, "Popen", return_value=MagicMock()), \
             patch("time.sleep"):
            assert mgr.start(timeout=5) is True


# ============================================================
# install_apk
# ============================================================
class TestInstallApk:
    def test_not_running(self, tmp_path):
        mgr = EmulatorManager(log_callback=lambda *a: None)
        mgr.is_running = lambda: False
        assert mgr.install_apk(str(tmp_path / "x.apk")) is False

    def test_success(self, tmp_path):
        mgr = EmulatorManager(log_callback=lambda *a: None)
        mgr.is_running = lambda: True
        fake = MagicMock(stdout="Success\n")
        with patch.object(subprocess, "run", return_value=fake):
            assert mgr.install_apk(str(tmp_path / "x.apk")) is True

    def test_failure_output(self, tmp_path):
        mgr = EmulatorManager(log_callback=lambda *a: None)
        mgr.is_running = lambda: True
        fake = MagicMock(stdout="Failure [INSTALL_FAILED]\n")
        with patch.object(subprocess, "run", return_value=fake):
            assert mgr.install_apk(str(tmp_path / "x.apk")) is False

    def test_subprocess_error(self, tmp_path):
        mgr = EmulatorManager(log_callback=lambda *a: None)
        mgr.is_running = lambda: True
        with patch.object(subprocess, "run",
                          side_effect=subprocess.SubprocessError()):
            assert mgr.install_apk(str(tmp_path / "x.apk")) is False


# ============================================================
# launch
# ============================================================
class TestLaunch:
    def test_success(self):
        mgr = EmulatorManager(log_callback=lambda *a: None)
        with patch.object(subprocess, "run", return_value=MagicMock()):
            assert mgr.launch("com.test") is True

    def test_subprocess_error(self):
        mgr = EmulatorManager(log_callback=lambda *a: None)
        with patch.object(subprocess, "run",
                          side_effect=subprocess.SubprocessError()):
            assert mgr.launch("com.test") is False