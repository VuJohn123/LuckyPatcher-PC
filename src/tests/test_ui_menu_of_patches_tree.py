"""UI test cho MenuOfPatchesTreeDialog — tree structure + action signals."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt

from ui.menu_of_patches_tree import MenuOfPatchesTreeDialog


@pytest.fixture
def dialog(qtbot):
    dlg = MenuOfPatchesTreeDialog(
        app_name="Test App",
        package="com.example.test",
        colors=["green", "blue"],
        findings=[
            {"type": "license", "color": "green", "title": "x"},
            {"type": "iap", "color": "green", "title": "y"},
        ],
    )
    qtbot.addWidget(dlg)
    return dlg


# ============================================================
# Structure
# ============================================================
class TestStructure:
    def test_root_exists(self, dialog):
        assert dialog.tree.topLevelItemCount() >= 1

    def test_root_text(self, dialog):
        root = dialog.tree.topLevelItem(0)
        assert "Menu of Patches" in root.text(0)

    def test_has_create_modified_apk_section(self, dialog):
        assert _find_item(dialog.tree, "Create Modified APK")

    def test_has_direct_actions_section(self, dialog):
        assert _find_item(dialog.tree, "Hành động trực tiếp")

    def test_has_misc_section(self, dialog):
        assert _find_item(dialog.tree, "Khác")


# ============================================================
# Leaves + actions
# ============================================================
class TestLeaves:
    def test_license_leaf_present(self, dialog):
        item = _find_item(dialog.tree, "Chế độ tự động")
        assert item is not None
        assert item.data(0, Qt.ItemDataRole.UserRole) == "license:auto"

    def test_iap_dex_action(self, dialog):
        item = _find_item(dialog.tree, "Reassembly Dex")
        assert item is not None
        assert item.data(0, Qt.ItemDataRole.UserRole) == "iap:dex"

    def test_change_perms_action(self, dialog):
        item = _find_item(dialog.tree, "Đổi quyền")
        assert item is not None
        assert item.data(0, Qt.ItemDataRole.UserRole) == "change_perms"

    def test_direct_remove_license_action(self, dialog):
        item = _find_item(
            dialog.tree, "Remove License Verification",
        )
        assert item is not None
        assert item.data(0, Qt.ItemDataRole.UserRole) == "remove_license"

    def test_all_leaves_have_action(self, dialog):
        for item in _iter_all_items(dialog.tree):
            if item.childCount() == 0:  # leaf
                action = item.data(0, Qt.ItemDataRole.UserRole)
                assert action, f"Leaf without action: {item.text(0)}"


# ============================================================
# Auto-expand based on findings
# ============================================================
class TestAutoExpand:
    def test_license_submenu_expanded_when_finding(self, qtbot):
        dlg = MenuOfPatchesTreeDialog(
            "App", "com.test", [],
            findings=[{"type": "license"}],
        )
        qtbot.addWidget(dlg)
        lic = _find_item(dlg.tree, "Giấy phép Xác minh")
        assert lic.isExpanded()

    def test_license_collapsed_without_finding(self, qtbot):
        dlg = MenuOfPatchesTreeDialog(
            "App", "com.test", [], findings=[],
        )
        qtbot.addWidget(dlg)
        lic = _find_item(dlg.tree, "Giấy phép Xác minh")
        assert not lic.isExpanded()

    def test_iap_submenu_expanded_when_finding(self, qtbot):
        dlg = MenuOfPatchesTreeDialog(
            "App", "com.test", [],
            findings=[{"type": "iap"}],
        )
        qtbot.addWidget(dlg)
        iap = _find_item(dlg.tree, "Giả lập InApp")
        assert iap.isExpanded()


# ============================================================
# Double click → signal
# ============================================================
class TestDoubleClick:
    def test_double_click_leaf_emits_signal(self, dialog, qtbot):
        item = _find_item(dialog.tree, "Chế độ tự động")
        assert item is not None
        with qtbot.waitSignal(
            dialog.action_requested, timeout=1000
        ) as blocker:
            dialog._on_double_click(item, 0)
        assert blocker.args == ["license:auto"]

    def test_double_click_group_no_signal(self, dialog, qtbot):
        # Group items có child → không có UserRole
        root = dialog.tree.topLevelItem(0)
        with qtbot.assertNotEmitted(
            dialog.action_requested, wait=100,
        ):
            dialog._on_double_click(root, 0)

    def test_double_click_emits_accept(self, dialog, qtbot):
        item = _find_item(dialog.tree, "Remove Google Ads")
        assert item is not None
        with qtbot.waitSignal(
            dialog.action_requested, timeout=1000
        ) as blocker:
            dialog._on_double_click(item, 0)
        assert blocker.args == ["remove_ads"]


# ============================================================
# Color badges
# ============================================================
class TestColorBadges:
    def test_badges_rendered(self, dialog):
        from PyQt6.QtWidgets import QLabel
        labels = [
            lbl.text() for lbl in dialog.findChildren(QLabel)
            if "License" in lbl.text() or "Ads" in lbl.text()
        ]
        assert labels, "Color badges not rendered"

    def test_no_colors_no_badges(self, qtbot):
        dlg = MenuOfPatchesTreeDialog("App", "com.test", [], [])
        qtbot.addWidget(dlg)
        # Không crash — badges optional


# ============================================================
# Helpers
# ============================================================
def _find_item(tree, text_substring: str):
    """Tìm QTreeWidgetItem theo substring trong text(0)."""
    def _walk(item):
        if text_substring.lower() in item.text(0).lower():
            return item
        for i in range(item.childCount()):
            res = _walk(item.child(i))
            if res:
                return res
        return None

    for i in range(tree.topLevelItemCount()):
        res = _walk(tree.topLevelItem(i))
        if res:
            return res
    return None


def _iter_all_items(tree):
    """Iterator qua mọi QTreeWidgetItem."""
    def _walk(item):
        yield item
        for i in range(item.childCount()):
            yield from _walk(item.child(i))

    for i in range(tree.topLevelItemCount()):
        yield from _walk(tree.topLevelItem(i))