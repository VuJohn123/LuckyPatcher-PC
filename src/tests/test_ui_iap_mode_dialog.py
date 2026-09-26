"""UI test cho IAPModeDialog — 3 phương pháp IAP."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QPushButton, QRadioButton

from ui.iap_mode_dialog import IAPModeDialog


@pytest.fixture
def dialog(qtbot):
    dlg = IAPModeDialog()
    qtbot.addWidget(dlg)
    return dlg


def _find_button(widget, text_substr: str):
    for btn in widget.findChildren(QPushButton):
        if text_substr.lower() in btn.text().lower():
            return btn
    return None


class TestConstruction:
    def test_window_title(self, dialog):
        assert "IAP" in dialog.windowTitle()

    def test_has_3_options(self):
        assert len(IAPModeDialog.OPTIONS) == 3

    def test_all_rendered(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        assert len(rbs) == 3

    def test_default_iap_dex(self, dialog):
        assert dialog.get_mode() == "iap_dex"

    def test_default_radio_checked(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        checked = [r for r in rbs if r.isChecked()]
        assert len(checked) == 1


class TestSelection:
    def test_select_proxy(self, dialog):
        dialog._select("iap_proxy")
        assert dialog.get_mode() == "iap_proxy"

    def test_select_aidl(self, dialog):
        dialog._select("aidl_proxy")
        assert dialog.get_mode() == "aidl_proxy"

    def test_all_modes_switchable(self, dialog):
        for key, _ in IAPModeDialog.OPTIONS:
            dialog._select(key)
            assert dialog.get_mode() == key


class TestButtons:
    def test_continue_accepts(self, dialog, qtbot):
        btn = _find_button(dialog, "Tiếp tục")
        assert btn is not None
        with qtbot.waitSignal(dialog.accepted, timeout=500):
            btn.click()

    def test_cancel_rejects(self, dialog, qtbot):
        btn = _find_button(dialog, "Hủy")
        with qtbot.waitSignal(dialog.rejected, timeout=500):
            btn.click()