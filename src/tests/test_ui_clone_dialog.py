"""UI test cho CloneDialog — validation package + name."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QMessageBox

from ui.clone_dialog import CloneDialog


@pytest.fixture
def dialog(qtbot):
    dlg = CloneDialog(
        app_name="Test App", package="com.example.app",
    )
    qtbot.addWidget(dlg)
    return dlg


@pytest.fixture
def no_warning(monkeypatch):
    """Silence QMessageBox.warning — return captured list."""
    calls: list[tuple] = []

    def _w(parent, title, text, *a, **kw):
        calls.append((title, text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(
        "ui.clone_dialog.QMessageBox.warning", _w,
    )
    return calls


# ============================================================
# Construction
# ============================================================
class TestConstruction:
    def test_window_title(self, dialog):
        assert dialog.windowTitle() == "Clone App"

    def test_stores_original(self, dialog):
        assert dialog.original_package == "com.example.app"
        assert dialog.original_name == "Test App"

    def test_pkg_input_prefilled(self, dialog):
        assert dialog.pkg_input.text() == "com.example.app.clone"

    def test_name_input_prefilled(self, dialog):
        assert dialog.name_input.text() == "Test App (Clone)"

    def test_getters_return_text(self, dialog):
        assert dialog.get_new_package() == "com.example.app.clone"
        assert dialog.get_new_name() == "Test App (Clone)"


# ============================================================
# Validation
# ============================================================
class TestValidation:
    def test_valid_accepts(self, dialog, no_warning, qtbot):
        dialog.pkg_input.setText("com.example.app.clone2")
        with qtbot.waitSignal(
            dialog.accepted, timeout=500,
        ):
            dialog._on_ok()
        assert dialog.result() == CloneDialog.DialogCode.Accepted
        assert no_warning == []

    def test_empty_pkg_warns(
        self, dialog, no_warning, qtbot,
    ):
        dialog.pkg_input.setText("")
        with qtbot.assertNotEmitted(dialog.accepted, wait=100):
            dialog._on_ok()
        assert len(no_warning) == 1
        assert "Package không hợp lệ" in no_warning[0][1]

    def test_invalid_regex_warns(
        self, dialog, no_warning, qtbot,
    ):
        dialog.pkg_input.setText("123invalid")
        with qtbot.assertNotEmitted(dialog.accepted, wait=100):
            dialog._on_ok()
        assert len(no_warning) == 1
        assert "bắt đầu bằng chữ cái" in no_warning[0][1]

    def test_same_package_warns(
        self, dialog, no_warning, qtbot,
    ):
        dialog.pkg_input.setText("com.example.app")
        with qtbot.assertNotEmitted(dialog.accepted, wait=100):
            dialog._on_ok()
        assert len(no_warning) == 1
        assert "khác package gốc" in no_warning[0][1]

    def test_special_chars_warn(
        self, dialog, no_warning, qtbot,
    ):
        dialog.pkg_input.setText("com.example.app-bad!")
        with qtbot.assertNotEmitted(dialog.accepted, wait=100):
            dialog._on_ok()
        assert len(no_warning) == 1

    def test_underscore_accepted(
        self, dialog, no_warning, qtbot,
    ):
        """
        Fix: regex `[a-zA-Z0-9._]` cho phép `_` (literal trong class).
        Nên `com.example_app.clone` là package HỢP LỆ.
        """
        dialog.pkg_input.setText("com.example_app.clone")
        with qtbot.waitSignal(dialog.accepted, timeout=500):
            dialog._on_ok()
        assert no_warning == []
        assert dialog.result() == CloneDialog.DialogCode.Accepted

    def test_dots_valid(self, dialog, no_warning, qtbot):
        dialog.pkg_input.setText("com.foo.bar.baz.qux")
        with qtbot.waitSignal(dialog.accepted, timeout=500):
            dialog._on_ok()
        assert no_warning == []

    def test_whitespace_stripped(
        self, dialog, no_warning, qtbot,
    ):
        dialog.pkg_input.setText("   com.new.app   ")
        with qtbot.waitSignal(dialog.accepted, timeout=500):
            dialog._on_ok()
        assert dialog.get_new_package() == "com.new.app"


# ============================================================
# Getters after accept
# ============================================================
class TestGetters:
    def test_get_new_name_returns_current(self, dialog):
        dialog.name_input.setText("My Clone")
        assert dialog.get_new_name() == "My Clone"

    def test_empty_name_allowed(self, dialog):
        dialog.name_input.setText("")
        assert dialog.get_new_name() == ""