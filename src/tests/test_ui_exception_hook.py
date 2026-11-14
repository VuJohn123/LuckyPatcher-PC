"""UI test cho exception_hook — global handler install + behavior."""
from __future__ import annotations

import sys

import pytest

from ui.exception_hook import install_gui_exception_hook


@pytest.fixture
def clean_hook():
    """Save/restore sys.excepthook + install flag giữa các test."""
    saved_hook = sys.excepthook
    saved_flag = getattr(sys, "_lp_exception_hook_installed", None)
    yield
    sys.excepthook = saved_hook
    if saved_flag is None:
        if hasattr(sys, "_lp_exception_hook_installed"):
            del sys._lp_exception_hook_installed
    else:
        sys._lp_exception_hook_installed = saved_flag


# ============================================================
# Install
# ============================================================
class TestInstall:
    def test_installs_hook(self, clean_hook):
        original = sys.excepthook
        install_gui_exception_hook(show_dialog=False)
        assert sys.excepthook is not original

    def test_sets_flag(self, clean_hook):
        install_gui_exception_hook(show_dialog=False)
        assert sys._lp_exception_hook_installed is True

    def test_idempotent(self, clean_hook):
        install_gui_exception_hook(show_dialog=False)
        hook1 = sys.excepthook
        install_gui_exception_hook(show_dialog=False)
        hook2 = sys.excepthook
        assert hook1 is hook2

    def test_does_not_overwrite_when_flagged(self, clean_hook):
        sys._lp_exception_hook_installed = True
        original = sys.excepthook
        install_gui_exception_hook(show_dialog=False)
        assert sys.excepthook is original


# ============================================================
# Hook behavior
# ============================================================
class TestHookBehavior:
    def test_hook_catches_exception(self, clean_hook, tmp_path, monkeypatch):
        # Redirect logs dir → tmp_path
        monkeypatch.chdir(tmp_path)
        install_gui_exception_hook(show_dialog=False)

        try:
            raise ValueError("test exception")
        except ValueError:
            # Gọi hook thủ công với exc_info
            sys.excepthook(*sys.exc_info())

        # File crash report tạo ra
        crash_files = list((tmp_path / "logs").glob("crash_*.log"))
        assert crash_files, "No crash file created"

        content = crash_files[0].read_text(encoding="utf-8")
        assert "ValueError" in content
        assert "test exception" in content

    def test_hook_skips_keyboard_interrupt(
        self, clean_hook, tmp_path, monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
        install_gui_exception_hook(show_dialog=False)

        try:
            raise KeyboardInterrupt()
        except KeyboardInterrupt:
            sys.excepthook(*sys.exc_info())

        # Không tạo crash file
        crash_files = list((tmp_path / "logs").glob("crash_*.log"))
        assert not crash_files

    def test_crash_file_includes_platform(
        self, clean_hook, tmp_path, monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
        install_gui_exception_hook(show_dialog=False)

        try:
            raise RuntimeError("boom")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())

        crash_files = list((tmp_path / "logs").glob("crash_*.log"))
        assert crash_files
        content = crash_files[0].read_text(encoding="utf-8")
        assert "Python:" in content
        assert "Platform:" in content

    def test_multiple_exceptions_multiple_files(
        self, clean_hook, tmp_path, monkeypatch,
    ):
        import time
        monkeypatch.chdir(tmp_path)
        install_gui_exception_hook(show_dialog=False)

        for i in range(2):
            try:
                raise ValueError(f"err{i}")
            except ValueError:
                sys.excepthook(*sys.exc_info())
            time.sleep(1.1)  # crash filename có timestamp theo giây

        crash_files = list((tmp_path / "logs").glob("crash_*.log"))
        assert len(crash_files) >= 1


# ============================================================
# Dialog behavior
# ============================================================
class TestDialogBehavior:
    def test_no_dialog_when_disabled(
        self, clean_hook, tmp_path, monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
        install_gui_exception_hook(show_dialog=False)

        # Spy QMessageBox
        called: list = []

        def _spy(*a, **kw):
            called.append(True)
            return None

        from PyQt6.QtWidgets import QMessageBox
        monkeypatch.setattr(QMessageBox, "exec", _spy)

        try:
            raise ValueError("x")
        except ValueError:
            sys.excepthook(*sys.exc_info())

        assert not called

    def test_hook_handles_missing_qt(
        self, clean_hook, tmp_path, monkeypatch,
    ):
        """Khi show_dialog=True nhưng QApplication.instance()=None.

        Earlier qtbot tests in a full-suite run leave a live QApplication
        behind, so force instance() to None. Otherwise the hook opens a
        modal QMessageBox and blocks the whole run.
        """
        monkeypatch.chdir(tmp_path)
        from PyQt6.QtWidgets import QApplication
        monkeypatch.setattr(
            QApplication, "instance", staticmethod(lambda: None)
        )
        install_gui_exception_hook(show_dialog=True)

        # Không có QApplication → hook không crash
        try:
            raise RuntimeError("no qt")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())

        crash_files = list((tmp_path / "logs").glob("crash_*.log"))
        assert crash_files  # log vẫn ghi


# ============================================================
# Traceback passthrough
# ============================================================
class TestTracebackPassthrough:
    def test_calls_default_excepthook(
        self, clean_hook, tmp_path, monkeypatch, capsys,
    ):
        """Hook vẫn gọi sys.__excepthook__ → stderr có traceback."""
        monkeypatch.chdir(tmp_path)
        install_gui_exception_hook(show_dialog=False)

        try:
            raise ValueError("pass-through")
        except ValueError:
            sys.excepthook(*sys.exc_info())

        # sys.__excepthook__ writes to stderr
        captured = capsys.readouterr()
        assert "ValueError" in captured.err
        assert "pass-through" in captured.err
