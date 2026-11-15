"""Tests for the UI mode (Beginner / Mitigative / Advanced) system."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QPushButton

from core.ui_mode import (
    ACTION_META,
    RiskLevel,
    UIMode,
    action_meta,
    action_risk,
    action_tooltip,
    action_visible,
    get_ui_mode,
    reset_ui_mode,
    set_ui_mode,
)


@pytest.fixture(autouse=True)
def _reset_mode():
    reset_ui_mode()
    yield
    reset_ui_mode()


class TestUIModeEnum:
    def test_three_modes(self):
        assert [m.value for m in UIMode] == [
            "beginner", "mitigative", "advanced",
        ]

    def test_from_str_valid(self):
        assert UIMode.from_str("beginner") is UIMode.BEGINNER
        assert UIMode.from_str("ADVANCED") is UIMode.ADVANCED
        assert UIMode.from_str(" Mitigative ") is UIMode.MITIGATIVE

    def test_from_str_invalid_falls_back(self):
        assert UIMode.from_str("nonsense") is UIMode.MITIGATIVE
        assert UIMode.from_str(None) is UIMode.MITIGATIVE

    def test_label_is_localized(self):
        for mode in UIMode:
            assert mode.label
            assert mode.label != f"ui_mode.{mode.value}"


class TestGlobalModeState:
    def test_default_is_mitigative(self):
        assert get_ui_mode() is UIMode.MITIGATIVE

    def test_set_and_get(self):
        set_ui_mode(UIMode.ADVANCED)
        assert get_ui_mode() is UIMode.ADVANCED

    def test_set_from_string(self):
        set_ui_mode("beginner")
        assert get_ui_mode() is UIMode.BEGINNER

    def test_reset(self):
        set_ui_mode(UIMode.ADVANCED)
        reset_ui_mode()
        assert get_ui_mode() is UIMode.MITIGATIVE


class TestActionRegistry:
    def test_all_meta_have_tooltips(self):
        for key in ACTION_META:
            assert action_tooltip(key)
            assert action_tooltip(key) != f"actions.{key}"

    def test_unknown_action_defaults_visible(self):
        for mode in UIMode:
            assert action_visible("totally_unknown_action", mode)

    def test_unknown_action_meta_safe(self):
        meta = action_meta("totally_unknown_action")
        assert meta.risk is RiskLevel.SAFE

    def test_beginner_hides_dangerous_actions(self):
        assert not action_visible("apply_custom_patch", UIMode.BEGINNER)
        assert not action_visible("change_perms", UIMode.BEGINNER)
        assert not action_visible("resign", UIMode.BEGINNER)
        assert not action_visible("sig_disable", UIMode.BEGINNER)

    def test_beginner_shows_safe_actions(self):
        assert action_visible("open_rebuild", UIMode.BEGINNER)
        assert action_visible("remove_license", UIMode.BEGINNER)
        assert action_visible("remove_ads", UIMode.BEGINNER)
        assert action_visible("iap_emulation", UIMode.BEGINNER)
        assert action_visible("backup", UIMode.BEGINNER)

    def test_mitigative_shows_custom_patch(self):
        assert action_visible("apply_custom_patch", UIMode.MITIGATIVE)
        assert action_visible("change_perms", UIMode.MITIGATIVE)
        assert action_visible("resign", UIMode.MITIGATIVE)

    def test_mitigative_hides_signature_patches(self):
        assert not action_visible("sig_disable", UIMode.MITIGATIVE)
        assert not action_visible("custom", UIMode.MITIGATIVE)

    def test_advanced_shows_everything(self):
        for key in ACTION_META:
            assert action_visible(key, UIMode.ADVANCED)

    def test_risk_levels(self):
        assert action_risk("remove_ads") is RiskLevel.SAFE
        assert action_risk("remove_license") is RiskLevel.CAUTION
        assert action_risk("resign") is RiskLevel.DANGEROUS


class TestMenuOfPatchesIntegration:
    def _make_dialog(self, qtbot, mode: UIMode):
        from ui.menu_of_patches import MenuOfPatchesDialog

        set_ui_mode(mode)
        dlg = MenuOfPatchesDialog(
            app_name="Test App",
            package="com.example.test",
            colors=["green", "yellow"],
            findings=[
                {"type": "license", "color": "green", "description": "L"},
                {"type": "custom_patch", "color": "yellow", "description": "C"},
            ],
        )
        qtbot.addWidget(dlg)
        return dlg

    @staticmethod
    def _find(dialog, substr: str):
        for btn in dialog.findChildren(QPushButton):
            if substr.lower() in btn.text().lower():
                return btn
        return None

    def test_beginner_hides_custom_patch(self, qtbot):
        dlg = self._make_dialog(qtbot, UIMode.BEGINNER)
        assert self._find(dlg, "Custom Patch") is None
        assert self._find(dlg, "Change Permissions") is None

    def test_beginner_keeps_safe_actions(self, qtbot):
        dlg = self._make_dialog(qtbot, UIMode.BEGINNER)
        assert self._find(dlg, "Create Modified") is not None
        assert self._find(dlg, "Remove Google Ads") is not None
        assert self._find(dlg, "Backup App") is not None

    def test_mitigative_shows_custom_patch(self, qtbot):
        dlg = self._make_dialog(qtbot, UIMode.MITIGATIVE)
        assert self._find(dlg, "Custom Patch") is not None

    def test_advanced_shows_all(self, qtbot):
        dlg = self._make_dialog(qtbot, UIMode.ADVANCED)
        assert self._find(dlg, "Custom Patch") is not None
        assert self._find(dlg, "Change Permissions") is not None
        assert self._find(dlg, "Resign") is not None

    def test_tooltips_present(self, qtbot):
        dlg = self._make_dialog(qtbot, UIMode.ADVANCED)
        btn = self._find(dlg, "Remove License")
        assert btn is not None
        assert btn.toolTip()

    def test_mitigative_badges_dangerous(self, qtbot):
        dlg = self._make_dialog(qtbot, UIMode.MITIGATIVE)
        btn = self._find(dlg, "Resign")
        assert btn is not None
        assert "⛔" in btn.text()

    def test_beginner_has_no_badges(self, qtbot):
        dlg = self._make_dialog(qtbot, UIMode.BEGINNER)
        for btn in dlg.findChildren(QPushButton):
            assert "⛔" not in btn.text()


class TestMainWindowModeSelector:
    def test_mode_combo_exists(self, qtbot, monkeypatch):
        from ui.main_window import MainWindow

        monkeypatch.setattr(
            "ui.app_controller.get_installed_apps", lambda: [],
        )
        w = MainWindow()
        qtbot.addWidget(w)
        assert w.mode_combo.count() == 3

    def test_switching_mode_updates_state(self, qtbot, monkeypatch):
        from ui.main_window import MainWindow

        monkeypatch.setattr(
            "ui.app_controller.get_installed_apps", lambda: [],
        )
        w = MainWindow()
        qtbot.addWidget(w)
        w.mode_combo.setCurrentIndex(2)  # advanced
        assert get_ui_mode() is UIMode.ADVANCED
        w.mode_combo.setCurrentIndex(0)  # beginner
        assert get_ui_mode() is UIMode.BEGINNER
