"""UI test cho WizardDialog — quick-pick mode selection."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QRadioButton

from ui.wizard_dialog import WizardDialog


@pytest.fixture
def dialog(qtbot):
    dlg = WizardDialog()
    qtbot.addWidget(dlg)
    return dlg


# ============================================================
# Constants
# ============================================================
class TestConstants:
    def test_has_4_options(self):
        assert len(WizardDialog.OPTIONS) == 4

    def test_iap_dex_present(self):
        keys = [k for k, _ in WizardDialog.OPTIONS]
        assert "iap_dex" in keys

    def test_full_patch_present(self):
        keys = [k for k, _ in WizardDialog.OPTIONS]
        assert any(k.startswith("multi:") for k in keys)


# ============================================================
# Construction
# ============================================================
class TestConstruction:
    def test_window_title(self, dialog):
        assert "Wizard" in dialog.windowTitle()

    def test_4_radio_buttons(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        assert len(rbs) == 4

    def test_default_is_iap_dex(self, dialog):
        assert dialog.get_mode() == "iap_dex"

    def test_default_radio_checked(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        checked = [r for r in rbs if r.isChecked()]
        assert len(checked) == 1


# ============================================================
# Selection
# ============================================================
class TestSelection:
    def test_select_ads(self, dialog):
        dialog._select("ads_full_offline")
        assert dialog.get_mode() == "ads_full_offline"

    def test_select_license(self, dialog):
        dialog._select("license:extreme")
        assert dialog.get_mode() == "license:extreme"

    def test_select_full_patch(self, dialog):
        dialog._select("multi:license,ads,iap_dex")
        assert dialog.get_mode() == "multi:license,ads,iap_dex"

    def test_radio_click_updates(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        for rb in rbs:
            if "Xóa quảng cáo" in rb.text():
                rb.setChecked(True)
                break
        assert dialog.get_mode() == "ads_full_offline"

    def test_switch_all_modes(self, dialog):
        for key, _ in WizardDialog.OPTIONS:
            dialog._select(key)
            assert dialog.get_mode() == key