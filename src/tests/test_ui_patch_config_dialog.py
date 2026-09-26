"""UI test cho PatchConfigDialog — radio options single-select."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QRadioButton

from ui.patch_config_dialog import PatchConfigDialog


_OPTS = {
    "auto": "Tự động",
    "dex": "Dex mode",
    "reverse": "Đảo ngược",
    "extreme": "Cực đoan",
}


@pytest.fixture
def dialog(qtbot):
    dlg = PatchConfigDialog(
        patch_name="License",
        options=_OPTS,
    )
    qtbot.addWidget(dlg)
    return dlg


# ============================================================
# Construction
# ============================================================
class TestConstruction:
    def test_window_title_has_patch_name(self, dialog):
        assert "License" in dialog.windowTitle()

    def test_all_options_rendered(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        assert len(rbs) == 4
        texts = [rb.text() for rb in rbs]
        for key in _OPTS:
            assert any(key in t for t in texts)

    def test_default_selects_first(self, dialog):
        # current_mode=None → first option
        assert dialog.get_mode() == "auto"

    def test_default_radio_checked(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        checked = [r for r in rbs if r.isChecked()]
        assert len(checked) == 1
        assert "auto" in checked[0].text()


# ============================================================
# With current_mode
# ============================================================
class TestCurrentMode:
    def test_current_mode_selected(self, qtbot):
        dlg = PatchConfigDialog(
            patch_name="License",
            options=_OPTS,
            current_mode="extreme",
        )
        qtbot.addWidget(dlg)
        assert dlg.get_mode() == "extreme"

    def test_current_mode_radio_checked(self, qtbot):
        dlg = PatchConfigDialog(
            patch_name="License",
            options=_OPTS,
            current_mode="reverse",
        )
        qtbot.addWidget(dlg)
        rbs = dlg.findChildren(QRadioButton)
        checked = [r for r in rbs if r.isChecked()]
        assert len(checked) == 1
        assert "reverse" in checked[0].text()


# ============================================================
# Selection change
# ============================================================
class TestSelectionChange:
    def test_set_key_via_api(self, dialog):
        dialog._select("dex")
        assert dialog.get_mode() == "dex"

    def test_radio_click_updates_selection(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        for rb in rbs:
            if "extreme" in rb.text():
                rb.setChecked(True)
                break
        assert dialog.get_mode() == "extreme"

    def test_switch_through_all(self, dialog):
        rbs = dialog.findChildren(QRadioButton)
        for key in _OPTS:
            for rb in rbs:
                if rb.text().startswith(f"{key}:"):
                    rb.setChecked(True)
                    break
            assert dialog.get_mode() == key


# ============================================================
# Edge cases
# ============================================================
class TestEdgeCases:
    def test_empty_options_no_crash(self, qtbot):
        dlg = PatchConfigDialog(
            patch_name="Empty", options={},
        )
        qtbot.addWidget(dlg)
        # _selected = current_mode or next(iter({}), "") == ""
        assert dlg.get_mode() == ""

    def test_single_option(self, qtbot):
        dlg = PatchConfigDialog(
            patch_name="One", options={"only": "Only option"},
        )
        qtbot.addWidget(dlg)
        assert dlg.get_mode() == "only"