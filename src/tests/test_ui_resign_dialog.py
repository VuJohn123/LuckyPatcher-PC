"""UI test cho ResignDialog — key_type radio + forced package ID."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QRadioButton

from ui.resign_dialog import ResignDialog


@pytest.fixture
def dialog(qtbot):
    dlg = ResignDialog(app_name="Test App")
    qtbot.addWidget(dlg)
    return dlg


# ============================================================
# Construction
# ============================================================
class TestConstruction:
    def test_window_title_has_app_name(self, dialog):
        assert "Test App" in dialog.windowTitle()

    def test_key_info_has_4_entries(self):
        assert len(ResignDialog.KEY_INFO) == 4
        for k in ("testkey", "platform", "media", "shared"):
            assert k in ResignDialog.KEY_INFO

    def test_4_radio_buttons(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        assert len(rbs) == 4

    def test_default_key_is_testkey(self, dialog):
        assert dialog.get_key_type() == "testkey"

    def test_default_radio_checked(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        checked = [r for r in rbs if r.isChecked()]
        assert len(checked) == 1
        assert "testkey" in checked[0].text()


# ============================================================
# Key type selection
# ============================================================
class TestKeySelection:
    def test_switch_to_platform(self, dialog):
        dialog._set_key("platform")
        assert dialog.get_key_type() == "platform"

    def test_switch_via_radio_click(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        for rb in rbs:
            if "platform" in rb.text():
                rb.setChecked(True)
                break
        assert dialog.get_key_type() == "platform"

    def test_switch_all_keys(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        for key in ("testkey", "platform", "media", "shared"):
            for rb in rbs:
                if f"<b>{key}</b>" in rb.text():
                    rb.setChecked(True)
                    break
            assert dialog.get_key_type() == key

    def test_radio_group_exclusive(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        for rb in rbs:
            rb.setChecked(True)
        # Chỉ 1 checked tại 1 thời điểm
        checked_count = sum(1 for rb in rbs if rb.isChecked())
        assert checked_count == 1


# ============================================================
# Forced package ID
# ============================================================
class TestForcedPackageId:
    def test_default_127_returns_none(self, dialog):
        assert dialog.pkg_spin.value() == 127
        assert dialog.get_forced_package_id() is None

    def test_set_valid_id(self, dialog):
        dialog.pkg_spin.setValue(42)
        assert dialog.get_forced_package_id() == 42

    def test_set_1_is_valid(self, dialog):
        dialog.pkg_spin.setValue(1)
        assert dialog.get_forced_package_id() == 1

    def test_set_126(self, dialog):
        dialog.pkg_spin.setValue(126)
        assert dialog.get_forced_package_id() == 126

    def test_spin_range_is_1_to_127(self, dialog):
        assert dialog.pkg_spin.minimum() == 1
        assert dialog.pkg_spin.maximum() == 127

    def test_set_127_back_to_none(self, dialog):
        dialog.pkg_spin.setValue(50)
        assert dialog.get_forced_package_id() == 50
        dialog.pkg_spin.setValue(127)
        assert dialog.get_forced_package_id() is None