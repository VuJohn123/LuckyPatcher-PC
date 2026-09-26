"""UI test cho ToolboxMenu — QMenu với nested actions + signals."""
from __future__ import annotations

import pytest

from ui.toolbox_menu import ToolboxMenu


@pytest.fixture
def menu(qtbot):
    m = ToolboxMenu()
    qtbot.addWidget(m)
    return m


class TestConstruction:
    def test_menu_title(self, menu):
        assert "Toolbox" in menu.title()

    def test_has_actions(self, menu):
        assert len(menu.actions()) >= 5

    def test_has_submenus(self, menu):
        # Ít nhất: Patch to Android, Xposed, Batch, Tools
        submenu_count = sum(
            1 for a in menu.actions() if a.menu() is not None
        )
        assert submenu_count >= 4


class TestApplySystemPatches:
    def test_no_selection_shows_info(self, menu, monkeypatch):
        called: list = []
        monkeypatch.setattr(
            "ui.toolbox_menu.QMessageBox.information",
            lambda *a, **kw: called.append(True),
        )
        menu._apply_system_patches()
        assert called

    def test_one_selected_emits(self, menu, qtbot):
        menu.act_sig_true.setChecked(True)
        with qtbot.waitSignal(
            menu.patch_requested, timeout=500,
        ) as blocker:
            menu._apply_system_patches()
        action, features = blocker.args
        assert action == "system_patch"
        assert features["signature_verification_always_true"] is True

    def test_multiple_selected_emits_all(self, menu, qtbot):
        menu.act_sig_true.setChecked(True)
        menu.act_disable_apk_sig.setChecked(True)
        menu.act_disable_zip_sig.setChecked(True)
        with qtbot.waitSignal(
            menu.patch_requested, timeout=500,
        ) as blocker:
            menu._apply_system_patches()
        _, features = blocker.args
        assert len(features) == 3
        assert features["disable_apk_signature_verification"] is True
        assert features["disable_zip_signature_verification"] is True


class TestRunTest:
    def test_run_test_emits(self, menu, qtbot):
        with qtbot.waitSignal(
            menu.patch_requested, timeout=500,
        ) as blocker:
            menu._run_test()
        assert list(blocker.args) == ["test_patch", {}]


class TestSimpleSignals:
    def test_clone_emits(self, menu, qtbot):
        with qtbot.waitSignal(menu.clone_requested, timeout=500):
            menu._clone_app()

    def test_iap_manager_emits(self, menu, qtbot):
        with qtbot.waitSignal(
            menu.iap_manager_requested, timeout=500,
        ):
            menu._open_iap_manager()

    def test_download_patch_emits(self, menu, qtbot):
        with qtbot.waitSignal(
            menu.download_patch_requested, timeout=500,
        ):
            menu._download_patch()


class TestForceRootCheck:
    def test_root_ok_shows_info(self, menu, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(
            "ui.toolbox_menu.QMessageBox.information",
            lambda *a, **kw: calls.append("info"),
        )
        monkeypatch.setattr(
            "ui.toolbox_menu.QMessageBox.warning",
            lambda *a, **kw: calls.append("warn"),
        )
        # Mock device_bridge.check_root
        from core import device_bridge
        monkeypatch.setattr(device_bridge, "check_root", lambda: True)
        menu._force_root_check()
        assert "info" in calls

    def test_root_fail_shows_warning(self, menu, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(
            "ui.toolbox_menu.QMessageBox.information",
            lambda *a, **kw: calls.append("info"),
        )
        monkeypatch.setattr(
            "ui.toolbox_menu.QMessageBox.warning",
            lambda *a, **kw: calls.append("warn"),
        )
        from core import device_bridge
        monkeypatch.setattr(device_bridge, "check_root", lambda: False)
        menu._force_root_check()
        assert "warn" in calls

    def test_import_error_treated_as_fail(self, menu, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(
            "ui.toolbox_menu.QMessageBox.information",
            lambda *a, **kw: calls.append("info"),
        )
        monkeypatch.setattr(
            "ui.toolbox_menu.QMessageBox.warning",
            lambda *a, **kw: calls.append("warn"),
        )
        # Force ImportError by hiding module
        import sys
        saved = sys.modules.pop("core.device_bridge", None)
        try:
            menu._force_root_check()
        finally:
            if saved is not None:
                sys.modules["core.device_bridge"] = saved
        assert "warn" in calls


class TestInstallModdedPlaystore:
    def test_shows_info(self, menu, monkeypatch):
        calls: list = []
        monkeypatch.setattr(
            "ui.toolbox_menu.QMessageBox.information",
            lambda *a, **kw: calls.append(True),
        )
        menu._install_modded_playstore()
        assert calls