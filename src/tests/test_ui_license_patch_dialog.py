"""UI test cho LicensePatchDialog — 6 chế độ license."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QPushButton, QRadioButton

from ui.license_patch_dialog import LicensePatchDialog


@pytest.fixture
def dialog(qtbot):
    dlg = LicensePatchDialog(app_name="Test App")
    qtbot.addWidget(dlg)
    return dlg


def _find_button(widget, text_substr: str):
    for btn in widget.findChildren(QPushButton):
        if text_substr.lower() in btn.text().lower():
            return btn
    return None


class TestConstruction:
    def test_window_title(self, dialog):
        assert "Test App" in dialog.windowTitle()

    def test_has_6_options(self):
        assert len(LicensePatchDialog.OPTIONS) == 6

    def test_all_options_rendered(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        assert len(rbs) == 6

    def test_default_is_auto(self, dialog):
        assert dialog._selected == "auto"

    def test_default_radio_checked(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        checked = [r for r in rbs if r.isChecked()]
        assert len(checked) == 1


class TestSelection:
    def test_select_extreme(self, dialog):
        dialog._select("extreme")
        assert dialog._selected == "extreme"

    def test_select_all_modes(self, dialog):
        for key, _ in LicensePatchDialog.OPTIONS:
            dialog._select(key)
            assert dialog._selected == key

    def test_radio_click_updates(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        for rb in rbs:
            if "Reverse" in rb.text():
                rb.setChecked(True)
                break
        assert dialog._selected == "reverse"


class TestApplySignal:
    def test_apply_emits_license_prefix(self, dialog, qtbot):
        btn = _find_button(dialog, "Áp dụng")
        assert btn is not None
        with qtbot.waitSignal(
            dialog.patch_requested, timeout=500,
        ) as blocker:
            btn.click()
        assert blocker.args == ["license:auto"]

    def test_apply_with_extreme(self, dialog, qtbot):
        dialog._select("extreme")
        btn = _find_button(dialog, "Áp dụng")
        with qtbot.waitSignal(
            dialog.patch_requested, timeout=500,
        ) as blocker:
            btn.click()
        assert blocker.args == ["license:extreme"]

    def test_apply_accepts_dialog(self, dialog, qtbot):
        btn = _find_button(dialog, "Áp dụng")
        with qtbot.waitSignal(dialog.accepted, timeout=500):
            btn.click()

    def test_cancel_rejects(self, dialog, qtbot):
        btn = _find_button(dialog, "Hủy")
        with qtbot.waitSignal(dialog.rejected, timeout=500):
            btn.click()