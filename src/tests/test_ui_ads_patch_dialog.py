"""UI test cho AdsPatchDialog — 4 chế độ ads."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QPushButton, QRadioButton

from ui.ads_patch_dialog import AdsPatchDialog


@pytest.fixture
def dialog(qtbot):
    dlg = AdsPatchDialog(app_name="Test App")
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

    def test_has_4_options(self):
        assert len(AdsPatchDialog.OPTIONS) == 4

    def test_all_rendered(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        assert len(rbs) == 4

    def test_default_remove(self, dialog):
        assert dialog._selected == "remove"

    def test_default_radio_checked(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        checked = [r for r in rbs if r.isChecked()]
        assert len(checked) == 1


class TestSelection:
    def test_select_offline(self, dialog):
        dialog._select("offline")
        assert dialog._selected == "offline"

    def test_select_full_offline(self, dialog):
        dialog._select("full_offline")
        assert dialog._selected == "full_offline"

    def test_all_modes(self, dialog):
        for key, _ in AdsPatchDialog.OPTIONS:
            dialog._select(key)
            assert dialog._selected == key


class TestApplySignal:
    def test_apply_emits_ads_prefix(self, dialog, qtbot):
        btn = _find_button(dialog, "Áp dụng")
        assert btn is not None
        with qtbot.waitSignal(
            dialog.patch_requested, timeout=500,
        ) as blocker:
            btn.click()
        assert blocker.args == ["ads:remove"]

    def test_apply_with_full_offline(self, dialog, qtbot):
        dialog._select("full_offline")
        btn = _find_button(dialog, "Áp dụng")
        with qtbot.waitSignal(
            dialog.patch_requested, timeout=500,
        ) as blocker:
            btn.click()
        assert blocker.args == ["ads:full_offline"]

    def test_apply_accepts(self, dialog, qtbot):
        btn = _find_button(dialog, "Áp dụng")
        with qtbot.waitSignal(dialog.accepted, timeout=500):
            btn.click()

    def test_cancel_rejects(self, dialog, qtbot):
        btn = _find_button(dialog, "Hủy")
        with qtbot.waitSignal(dialog.rejected, timeout=500):
            btn.click()