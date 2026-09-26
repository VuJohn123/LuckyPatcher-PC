"""UI test cho RebuildDialog — checkbox row + config + selection."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox

from ui.rebuild_dialog import RebuildDialog


@pytest.fixture
def dialog(qtbot):
    dlg = RebuildDialog(app_name="Test App", package="com.test")
    qtbot.addWidget(dlg)
    return dlg


class TestConstruction:
    def test_window_title(self, dialog):
        assert "Test App" in dialog.windowTitle()

    def test_stores_inputs(self, dialog):
        assert dialog.app_name == "Test App"
        assert dialog.package == "com.test"

    def test_patch_widgets_populated(self, dialog):
        expected = {"license", "ads", "iap",
                    "change_perms", "custom", "resign"}
        assert expected.issubset(set(dialog.patch_widgets.keys()))

    def test_extra_widgets_populated(self, dialog):
        expected = {
            "save_purchase", "auto_repeat",
            "sig_disable", "sig_integrity", "sig_fake_archive",
        }
        assert expected == set(dialog.extra_widgets.keys())

    def test_all_start_unchecked(self, dialog):
        for w in dialog.patch_widgets.values():
            assert not w["checkbox"].isChecked()
        for chk in dialog.extra_widgets.values():
            assert not chk.isChecked()


class TestCollectSelection:
    def test_empty_by_default(self, dialog):
        assert dialog._collect_selection() == []

    def test_license_with_default_mode(self, dialog):
        dialog.patch_widgets["license"]["checkbox"].setChecked(True)
        # default_mode = "auto"
        sel = dialog._collect_selection()
        assert "license:auto" in sel

    def test_multiple_selected(self, dialog):
        dialog.patch_widgets["license"]["checkbox"].setChecked(True)
        dialog.patch_widgets["ads"]["checkbox"].setChecked(True)
        sel = dialog._collect_selection()
        assert "license:auto" in sel
        assert "ads:remove" in sel

    def test_no_mode_appends_name_only(self, dialog):
        dialog.patch_widgets["resign"]["checkbox"].setChecked(True)
        sel = dialog._collect_selection()
        assert "resign" in sel
        assert not any("resign:" in s for s in sel)

    def test_extra_option_appended(self, dialog):
        dialog.extra_widgets["save_purchase"].setChecked(True)
        sel = dialog._collect_selection()
        assert "save_purchase" in sel

    def test_extra_plus_patch(self, dialog):
        dialog.patch_widgets["license"]["checkbox"].setChecked(True)
        dialog.extra_widgets["sig_disable"].setChecked(True)
        sel = dialog._collect_selection()
        assert "license:auto" in sel
        assert "sig_disable" in sel


class TestAdvancedOptions:
    def test_key_type_default(self, dialog):
        assert dialog.get_key_type() == "testkey"

    def test_key_type_change(self, dialog):
        dialog.key_combo.setCurrentText("platform")
        assert dialog.get_key_type() == "platform"

    def test_forced_package_id_default_none(self, dialog):
        assert dialog.get_forced_package_id() is None

    def test_forced_package_id_set(self, dialog):
        dialog.pkg_spin.setValue(50)
        assert dialog.get_forced_package_id() == 50


class TestBuildSignal:
    def test_build_emits_mode_string(self, dialog, qtbot):
        dialog.patch_widgets["license"]["checkbox"].setChecked(True)
        with qtbot.waitSignal(
            dialog.rebuild_requested, timeout=500,
        ) as blocker:
            dialog._on_build()
        assert "license:auto" in blocker.args[0]

    def test_build_without_selection_warns(
        self, dialog, monkeypatch,
    ):
        called: list = []
        monkeypatch.setattr(
            "ui.rebuild_dialog.QMessageBox.warning",
            lambda *a, **kw: called.append(True),
        )
        dialog._on_build()
        assert called

    def test_build_multiple_comma_separated(self, dialog, qtbot):
        dialog.patch_widgets["license"]["checkbox"].setChecked(True)
        dialog.patch_widgets["ads"]["checkbox"].setChecked(True)
        dialog.extra_widgets["save_purchase"].setChecked(True)
        with qtbot.waitSignal(
            dialog.rebuild_requested, timeout=500,
        ) as blocker:
            dialog._on_build()
        mode_str = blocker.args[0]
        assert "," in mode_str
        assert "license:auto" in mode_str
        assert "save_purchase" in mode_str


class TestConfigModeChange:
    def test_direct_mode_change(self, dialog):
        dialog.patch_widgets["license"]["mode"] = "extreme"
        dialog.patch_widgets["license"]["checkbox"].setChecked(True)
        sel = dialog._collect_selection()
        assert "license:extreme" in sel

    def test_switch_mode(self, dialog):
        dialog.patch_widgets["ads"]["mode"] = "full_offline"
        dialog.patch_widgets["ads"]["checkbox"].setChecked(True)
        assert "ads:full_offline" in dialog._collect_selection()