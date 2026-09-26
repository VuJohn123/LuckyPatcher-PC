"""UI test cho MenuOfPatchesDialog — feature detection, signals."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QPushButton

from ui.menu_of_patches import MenuOfPatchesDialog


@pytest.fixture
def dialog(qtbot):
    dlg = MenuOfPatchesDialog(
        app_name="Test App",
        package="com.example.test",
        colors=["green"],
        findings=[
            {"type": "license", "color": "green", "description": "License found"},
            {"type": "ads", "color": "blue", "description": "Ads detected"},
        ],
    )
    qtbot.addWidget(dlg)
    return dlg


def _find_button(widget, text_substr: str):
    for btn in widget.findChildren(QPushButton):
        if text_substr.lower() in btn.text().lower():
            return btn
    return None


class TestConstruction:
    def test_window_title_has_app_name(self, dialog):
        assert "Test App" in dialog.windowTitle()

    def test_stores_inputs(self, dialog):
        assert dialog.app_name == "Test App"
        assert dialog.package == "com.example.test"
        assert dialog.colors == ["green"]
        assert len(dialog.findings) == 2

    def test_has_finding_helper(self, dialog):
        assert dialog._has_finding("license")
        assert dialog._has_finding("ads")
        assert not dialog._has_finding("iap")

    def test_buttons_rendered(self, dialog):
        btns = dialog.findChildren(QPushButton)
        # Ít nhất 10 nút (rebuild, license, ads, iap, custom, perms, resign,
        # backup, launch, info, close)
        assert len(btns) >= 10


class TestFeatureEnableDisable:
    def test_license_button_enabled_when_finding(self, dialog):
        btn = _find_button(dialog, "Remove License")
        assert btn is not None
        assert btn.isEnabled()

    def test_ads_button_enabled(self, dialog):
        btn = _find_button(dialog, "Remove Google Ads")
        assert btn is not None
        assert btn.isEnabled()

    def test_iap_button_disabled_without_finding(self, dialog):
        btn = _find_button(dialog, "IAP Emulation")
        assert btn is not None
        assert not btn.isEnabled()

    def test_custom_button_disabled(self, dialog):
        btn = _find_button(dialog, "Custom Patch")
        assert btn is not None
        assert not btn.isEnabled()

    def test_rebuild_always_enabled(self, dialog):
        btn = _find_button(dialog, "Create Modified")
        assert btn is not None
        assert btn.isEnabled()

    def test_change_perms_always_enabled(self, dialog):
        btn = _find_button(dialog, "Change Permissions")
        assert btn is not None
        assert btn.isEnabled()

    def test_resign_always_enabled(self, dialog):
        btn = _find_button(dialog, "Resign")
        assert btn is not None
        assert btn.isEnabled()


class TestSignals:
    def test_open_rebuild_emits_signal(self, dialog, qtbot):
        btn = _find_button(dialog, "Create Modified")
        with qtbot.waitSignal(
            dialog.action_requested, timeout=500,
        ) as blocker:
            btn.click()
        assert blocker.args == ["open_rebuild"]

    def test_remove_license_emits(self, dialog, qtbot):
        btn = _find_button(dialog, "Remove License")
        with qtbot.waitSignal(
            dialog.action_requested, timeout=500,
        ) as blocker:
            btn.click()
        assert blocker.args == ["remove_license"]

    def test_remove_ads_emits(self, dialog, qtbot):
        btn = _find_button(dialog, "Remove Google Ads")
        with qtbot.waitSignal(
            dialog.action_requested, timeout=500,
        ) as blocker:
            btn.click()
        assert blocker.args == ["remove_ads"]

    def test_change_perms_uses_correct_key(self, dialog, qtbot):
        """Regression: key là 'change_perms' không phải 'manage_permissions'."""
        btn = _find_button(dialog, "Change Permissions")
        with qtbot.waitSignal(
            dialog.action_requested, timeout=500,
        ) as blocker:
            btn.click()
        assert blocker.args == ["change_perms"]

    def test_resign_emits(self, dialog, qtbot):
        btn = _find_button(dialog, "Resign")
        with qtbot.waitSignal(
            dialog.action_requested, timeout=500,
        ) as blocker:
            btn.click()
        assert blocker.args == ["resign"]

    def test_backup_emits(self, dialog, qtbot):
        btn = _find_button(dialog, "Backup App")
        with qtbot.waitSignal(
            dialog.action_requested, timeout=500,
        ) as blocker:
            btn.click()
        assert blocker.args == ["backup"]


class TestFindingRendering:
    def test_findings_shown(self, qtbot):
        dlg = MenuOfPatchesDialog(
            "App", "com.x",
            findings=[
                {"type": "license", "color": "green",
                 "description": "License XYZ"},
            ],
        )
        qtbot.addWidget(dlg)
        from PyQt6.QtWidgets import QLabel
        labels = [l.text() for l in dlg.findChildren(QLabel)]
        assert any("License XYZ" in t for t in labels)

    def test_no_findings_no_crash(self, qtbot):
        dlg = MenuOfPatchesDialog("App", "com.x", findings=[])
        qtbot.addWidget(dlg)
        assert dlg.findings == []


class TestClose:
    def test_close_button_accepts(self, dialog, qtbot):
        btn = _find_button(dialog, "Đóng")
        assert btn is not None
        with qtbot.waitSignal(dialog.accepted, timeout=500):
            btn.click()