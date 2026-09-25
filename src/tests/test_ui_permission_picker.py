"""
UI test cho PermissionPickerDialog.

Mock `APK` để không cần file APK thật.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from ui.permission_picker_dialog import (
    PermissionPickerDialog,
    _classify,
    _PERMISSION_DB,
    _CATEGORY_ORDER,
)


# ============================================================
# Mock APK
# ============================================================
def _mock_apk_with_perms(perms: list[str]):
    def _factory(_path):
        m = MagicMock()
        m.get_permissions.return_value = perms
        return m
    return _factory


@pytest.fixture
def sample_perms():
    return [
        "android.permission.INTERNET",
        "android.permission.CAMERA",
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.READ_CONTACTS",
        "com.android.vending.BILLING",
        "android.permission.VIBRATE",
        "com.unknown.vendor.CUSTOM_THING",
    ]


@pytest.fixture
def dialog(qtbot, monkeypatch, sample_perms):
    monkeypatch.setattr(
        "ui.permission_picker_dialog.APK",
        _mock_apk_with_perms(sample_perms),
    )
    dlg = PermissionPickerDialog(
        apk_path="/fake/path.apk",
        package="com.example.app",
        app_name="Test App",
    )
    qtbot.addWidget(dlg)
    return dlg


# ============================================================
# _classify() — pure logic
# ============================================================
class TestClassify:
    def test_full_name_match(self):
        emoji, cat, desc = _classify(
            "android.permission.CAMERA"
        )
        assert cat == "dangerous"
        assert emoji == "📷"

    def test_short_name_only(self):
        emoji, cat, _ = _classify("CAMERA")
        assert cat == "dangerous"

    def test_progressive_suffix(self):
        emoji, cat, _ = _classify(
            "com.vendor.custom.CAMERA"
        )
        assert cat == "dangerous"

    def test_unknown_vendor_fallback(self):
        emoji, cat, desc = _classify(
            "com.unknown.vendor.MY_THING"
        )
        assert cat == "normal"
        assert emoji == "❔"

    def test_plain_unknown(self):
        _, cat, _ = _classify("SOMETHING_ELSE")
        assert cat == "other"

    def test_permission_dot_in_path(self):
        _, cat, _ = _classify(
            "com.x.permission.BOGUS_PERM_XYZ"
        )
        assert cat == "normal"

    def test_billing_is_signature(self):
        _, cat, _ = _classify(
            "com.android.vending.BILLING"
        )
        assert cat == "signature"

    def test_internet_is_normal(self):
        _, cat, _ = _classify(
            "android.permission.INTERNET"
        )
        assert cat == "normal"


# ============================================================
# Load permissions
# ============================================================
class TestLoadPermissions:
    def test_permissions_loaded(self, dialog, sample_perms):
        assert len(dialog.permissions) == len(sample_perms)

    def test_permissions_sorted(self, dialog):
        assert dialog.permissions == sorted(dialog.permissions)

    def test_permissions_deduplicated(self, qtbot, monkeypatch):
        monkeypatch.setattr(
            "ui.permission_picker_dialog.APK",
            _mock_apk_with_perms([
                "android.permission.CAMERA",
                "android.permission.CAMERA",
            ]),
        )
        dlg = PermissionPickerDialog("/x.apk")
        qtbot.addWidget(dlg)
        assert dlg.permissions == ["android.permission.CAMERA"]

    def test_apk_load_failure_returns_empty(self, qtbot, monkeypatch):
        def _raise(_p):
            raise RuntimeError("bad apk")
        monkeypatch.setattr(
            "ui.permission_picker_dialog.APK", _raise,
        )
        dlg = PermissionPickerDialog("/bad.apk")
        qtbot.addWidget(dlg)
        assert dlg.permissions == []


# ============================================================
# Tree building
# ============================================================
class TestTreeBuild:
    def test_item_map_populated(self, dialog):
        assert len(dialog.item_map) == len(dialog.permissions)

    def test_all_start_unchecked(self, dialog):
        for item in dialog.item_map.values():
            assert item.checkState(0) == Qt.CheckState.Unchecked

    def test_categories_rendered(self, dialog):
        cats = [
            dialog.tree.topLevelItem(i).text(0)
            for i in range(dialog.tree.topLevelItemCount())
        ]
        assert any("DANGEROUS" in c for c in cats)
        assert any("NORMAL" in c for c in cats)


# ============================================================
# Selection
# ============================================================
class TestSelection:
    def test_preset_all(self, dialog):
        dialog._preset_all()
        assert len(dialog.get_selected_permissions()) == len(
            dialog.permissions
        )

    def test_preset_none(self, dialog):
        dialog._preset_all()
        dialog._preset_none()
        assert dialog.get_selected_permissions() == []

    def test_preset_dangerous(self, dialog):
        dialog._preset_dangerous()
        selected = dialog.get_selected_permissions()
        for p in selected:
            _, cat, _ = _classify(p)
            assert cat == "dangerous"

    def test_preset_safe(self, dialog):
        dialog._preset_safe()
        selected = dialog.get_selected_permissions()
        for p in selected:
            _, cat, _ = _classify(p)
            assert cat in ("normal", "signature")


# ============================================================
# Summary + warnings
# ============================================================
class TestSummary:
    def test_summary_zero_initially(self, dialog):
        assert dialog.summary is not None
        assert "0" in dialog.summary.text()

    def test_summary_updates_on_check(self, dialog):
        dialog._preset_all()
        n = len(dialog.permissions)
        assert str(n) in dialog.summary.text()

    def test_selected_panel_text(self, dialog):
        dialog._preset_all()
        text = dialog.selected_text.text()
        assert "(Chưa chọn" not in text
        assert "INTERNET" in text or "CAMERA" in text

    def test_warning_on_internet(self, dialog):
        """
        Fix: isVisible() = False khi parent chưa show().
        Dùng `not isHidden()` để check setVisible(True) đã gọi.
        """
        dialog.item_map[
            "android.permission.INTERNET"
        ].setCheckState(0, Qt.CheckState.Checked)
        dialog._check_warnings()
        # After setVisible(True), isHidden() == False
        assert not dialog.warn_label.isHidden()
        assert "INTERNET" in dialog.warn_label.text()

    def test_no_warning_on_safe_perm(self, dialog):
        dialog.item_map[
            "android.permission.CAMERA"
        ].setCheckState(0, Qt.CheckState.Checked)
        dialog._check_warnings()
        # After setVisible(False), isHidden() == True
        assert dialog.warn_label.isHidden()


# ============================================================
# Apply
# ============================================================
class TestApply:
    def test_apply_without_selection_no_close(
        self, dialog, monkeypatch,
    ):
        called: list[bool] = []
        monkeypatch.setattr(
            "ui.permission_picker_dialog.QMessageBox.information",
            lambda *a, **kw: called.append(True),
        )
        dialog._on_apply()
        assert called, "Expected info dialog"
        assert dialog.result() != QMessageBox.DialogCode.Accepted

    def test_apply_with_selection_confirms(
        self, dialog, monkeypatch,
    ):
        """
        Fix: mock phải trả StandardButton.Yes (16384), không phải 1.
        """
        dialog._preset_dangerous()
        monkeypatch.setattr(
            "ui.permission_picker_dialog.QMessageBox.question",
            lambda *a, **kw: QMessageBox.StandardButton.Yes,
        )
        dialog._on_apply()
        assert dialog.result() == QMessageBox.DialogCode.Accepted

    def test_apply_cancel_does_not_accept(
        self, dialog, monkeypatch,
    ):
        dialog._preset_dangerous()
        monkeypatch.setattr(
            "ui.permission_picker_dialog.QMessageBox.question",
            lambda *a, **kw: QMessageBox.StandardButton.No,
        )
        dialog._on_apply()
        assert dialog.result() != QMessageBox.DialogCode.Accepted

    def test_apply_internet_warning_in_message(
        self, dialog, monkeypatch,
    ):
        dialog.item_map[
            "android.permission.INTERNET"
        ].setCheckState(0, Qt.CheckState.Checked)
        captured: dict = {}

        def _q(parent, title, text, *a, **kw):
            captured["text"] = text
            return QMessageBox.StandardButton.No

        monkeypatch.setattr(
            "ui.permission_picker_dialog.QMessageBox.question", _q,
        )
        dialog._on_apply()
        assert "INTERNET" in captured["text"]
        assert "CẢNH BÁO" in captured["text"] or "⚠️" in captured["text"]


# ============================================================
# Constants sanity
# ============================================================
class TestConstants:
    def test_permission_db_has_entries(self):
        assert len(_PERMISSION_DB) >= 50

    def test_all_categories_used(self):
        cats = {cat for _, cat, _ in _PERMISSION_DB.values()}
        assert "dangerous" in cats
        assert "normal" in cats
        assert "signature" in cats

    def test_category_order_covers_all(self):
        cats = {cat for _, cat, _ in _PERMISSION_DB.values()}
        assert cats.issubset(set(_CATEGORY_ORDER))