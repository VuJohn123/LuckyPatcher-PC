"""
UI test cho RebuildTreeDialog — checkbox logic, preselect, summary.
"""
from __future__ import annotations

import pytest

from PyQt6.QtCore import Qt

from ui.rebuild_tree_dialog import RebuildTreeDialog


@pytest.fixture
def dialog(qtbot):
    dlg = RebuildTreeDialog(
        app_name="Test App",
        package="com.example.test",
        parent=None,
    )
    qtbot.addWidget(dlg)
    return dlg


# ============================================================
# Tree structure
# ============================================================
class TestTreeStructure:
    def test_item_map_populated(self, dialog):
        # Có license/ads/iap + change_perms/resign
        assert "license:auto" in dialog.item_map
        assert "license:extreme" in dialog.item_map
        assert "ads:remove" in dialog.item_map
        assert "iap:dex" in dialog.item_map
        assert "change_perms" in dialog.item_map
        assert "resign" in dialog.item_map

    def test_all_leaves_start_unchecked(self, dialog):
        for item in dialog.item_map.values():
            assert item.checkState(0) == Qt.CheckState.Unchecked

    def test_tree_has_root(self, dialog):
        assert dialog.tree.topLevelItemCount() >= 1

    def test_preselected_action_none(self, dialog):
        # Preselect None → không check gì
        assert dialog._collect_selection() == []


# ============================================================
# Preselect
# ============================================================
class TestPreselect:
    def test_preselect_single_no_colon(self, qtbot):
        dlg = RebuildTreeDialog(
            "App", "com.test", preselected_action="change_perms",
        )
        qtbot.addWidget(dlg)
        assert "change_perms" in dlg._collect_selection()

    def test_preselect_with_colon(self, qtbot):
        dlg = RebuildTreeDialog(
            "App", "com.test", preselected_action="license:extreme",
        )
        qtbot.addWidget(dlg)
        assert "license:extreme" in dlg._collect_selection()

    def test_preselect_prefix_matches_all_variants(self, qtbot):
        """preselect='license' → match license:auto, license:dex, ..."""
        dlg = RebuildTreeDialog(
            "App", "com.test", preselected_action="license",
        )
        qtbot.addWidget(dlg)
        selected = dlg._collect_selection()
        assert any(s.startswith("license:") for s in selected)

    def test_preselect_unknown_no_crash(self, qtbot):
        dlg = RebuildTreeDialog(
            "App", "com.test", preselected_action="bogus",
        )
        qtbot.addWidget(dlg)
        assert dlg._collect_selection() == []


# ============================================================
# Selection state
# ============================================================
class TestSelection:
    def test_select_all(self, dialog):
        dialog._select_all()
        n = len(dialog._collect_selection())
        assert n == len(dialog.item_map)

    def test_deselect_all(self, dialog):
        dialog._select_all()
        dialog._deselect_all()
        assert dialog._collect_selection() == []

    def test_manual_check(self, dialog):
        item = dialog.item_map["license:auto"]
        item.setCheckState(0, Qt.CheckState.Checked)
        assert "license:auto" in dialog._collect_selection()


# ============================================================
# Summary label
# ============================================================
class TestSummary:
    def test_summary_initial_zero(self, dialog):
        assert dialog.summary_lbl is not None
        assert "0 patch" in dialog.summary_lbl.text()

    def test_summary_updates_on_check(self, dialog):
        dialog.item_map["license:auto"].setCheckState(
            0, Qt.CheckState.Checked,
        )
        assert "1 patch" in dialog.summary_lbl.text()

    def test_summary_updates_on_uncheck(self, dialog):
        item = dialog.item_map["license:auto"]
        item.setCheckState(0, Qt.CheckState.Checked)
        item.setCheckState(0, Qt.CheckState.Unchecked)
        assert "0 patch" in dialog.summary_lbl.text()

    def test_summary_updates_via_select_all(self, dialog):
        dialog._select_all()
        n = len(dialog.item_map)
        assert f"{n} patch" in dialog.summary_lbl.text()


# ============================================================
# Advanced options
# ============================================================
class TestAdvanced:
    def test_key_type_default_testkey(self, dialog):
        assert dialog.get_key_type() == "testkey"

    def test_key_type_combo_has_4_options(self, dialog):
        assert dialog.key_combo.count() == 4

    def test_forced_package_id_default_none(self, dialog):
        # Spin value = 127 → get_forced_package_id() trả None
        assert dialog.get_forced_package_id() is None

    def test_forced_package_id_set(self, dialog):
        dialog.pkg_spin.setValue(42)
        assert dialog.get_forced_package_id() == 42

    def test_forced_package_id_127_is_none(self, dialog):
        dialog.pkg_spin.setValue(127)
        assert dialog.get_forced_package_id() is None


# ============================================================
# Build signal
# ============================================================
class TestBuildSignal:
    def test_build_emits_rebuild_requested(self, dialog, qtbot):
        dialog.item_map["license:auto"].setCheckState(
            0, Qt.CheckState.Checked,
        )
        with qtbot.waitSignal(
            dialog.rebuild_requested, timeout=1000
        ) as blocker:
            dialog._on_build()
        assert "license:auto" in blocker.args[0]

    def test_build_multi_mode_comma_separated(self, dialog, qtbot):
        dialog.item_map["license:auto"].setCheckState(
            0, Qt.CheckState.Checked,
        )
        dialog.item_map["ads:remove"].setCheckState(
            0, Qt.CheckState.Checked,
        )
        with qtbot.waitSignal(
            dialog.rebuild_requested, timeout=1000
        ) as blocker:
            dialog._on_build()
        mode_str = blocker.args[0]
        assert "license:auto" in mode_str
        assert "ads:remove" in mode_str
        assert "," in mode_str

    def test_build_without_selection_warns(self, dialog, qtbot, monkeypatch):
        called: list[bool] = []
        monkeypatch.setattr(
            "ui.rebuild_tree_dialog.QMessageBox.warning",
            lambda *a, **kw: called.append(True),
        )
        dialog._on_build()
        assert called, "Expected warning dialog"

    def test_build_without_selection_no_signal(
        self, dialog, qtbot, monkeypatch,
    ):
        monkeypatch.setattr(
            "ui.rebuild_tree_dialog.QMessageBox.warning",
            lambda *a, **kw: None,
        )
        with qtbot.assertNotEmitted(
            dialog.rebuild_requested, wait=200,
        ):
            dialog._on_build()