"""
UI test cho AppController — dispatch logic, env var bridge.

Không chạy pipeline thật — mock run_pipeline và threads.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from ui.app_controller import (
    AppController,
    _SPECIAL_MODES,
)


@pytest.fixture
def fake_window(qtbot):
    """Minimal QWidget stub với .app_list để controller cần."""
    from PyQt6.QtWidgets import QMainWindow
    w = QMainWindow()
    w.app_list = MagicMock()
    w.app_list.add_app = MagicMock()
    w.app_list.clear_all = MagicMock()
    qtbot.addWidget(w)
    return w


@pytest.fixture
def controller(qtbot, fake_window, monkeypatch):
    monkeypatch.setattr(
        "ui.app_controller.get_installed_apps", lambda: [],
    )
    c = AppController(fake_window)
    return c


# ============================================================
# Classify
# ============================================================
class TestQuickClassify:
    def test_game_package_returns_blue(self, controller):
        """
        Fix: 'subwaysurf' không chứa keyword nào. Dùng package
        có 'game' keyword để test nhánh.
        """
        colors = controller._quick_classify("com.example.mygame.app")
        assert "blue" in colors

    def test_google_package_returns_blue(self, controller):
        assert "blue" in controller._quick_classify("com.google.foo")

    def test_premium_returns_green(self, controller):
        colors = controller._quick_classify("com.x.pro")
        assert "green" in colors

    def test_android_system_returns_purple(self, controller):
        colors = controller._quick_classify("com.android.systemui")
        assert colors == ["purple"]

    def test_clean_returns_white(self, controller):
        assert controller._quick_classify("com.xyz.thing") == ["white"]

    def test_ads_keyword_triggers_blue(self, controller):
        assert "blue" in controller._quick_classify("com.x.ads")

    def test_unity_keyword_triggers_blue(self, controller):
        assert "blue" in controller._quick_classify("com.unity.game")


# ============================================================
# Menu action dispatch
# ============================================================
class TestHandleMenuAction:
    def test_open_rebuild_calls_open_rebuild_dialog(
        self, controller, monkeypatch,
    ):
        called: list = []
        monkeypatch.setattr(
            controller, "open_rebuild_dialog",
            lambda preselected=None: called.append(preselected),
        )
        controller._handle_menu_action("open_rebuild")
        assert called == [None]

    def test_multi_patch_preselected(self, controller, monkeypatch):
        called: list = []
        monkeypatch.setattr(
            controller, "open_rebuild_dialog",
            lambda preselected=None: called.append(preselected),
        )
        controller._handle_menu_action("multi_patch")
        assert called == ["multi_patch"]

    def test_change_perms_routes_to_picker(
        self, controller, monkeypatch,
    ):
        called: list = []
        monkeypatch.setattr(
            controller, "_open_permission_picker",
            lambda: called.append("picker"),
        )
        controller._handle_menu_action("change_perms")
        assert called == ["picker"]

    def test_manage_permissions_alias(
        self, controller, monkeypatch,
    ):
        called: list = []
        monkeypatch.setattr(
            controller, "_open_permission_picker",
            lambda: called.append("picker"),
        )
        controller._handle_menu_action("manage_permissions")
        assert called == ["picker"]

    def test_resign_routes_to_resign_dialog(
        self, controller, monkeypatch,
    ):
        called: list = []
        monkeypatch.setattr(
            controller, "_open_resign_dialog",
            lambda: called.append("resign"),
        )
        controller._handle_menu_action("resign")
        assert called == ["resign"]

    def test_clone_routes_to_clone_dialog(
        self, controller, monkeypatch,
    ):
        called: list = []
        monkeypatch.setattr(
            controller, "_open_clone_dialog",
            lambda: called.append("clone"),
        )
        controller._handle_menu_action("clone")
        assert called == ["clone"]

    def test_remove_license_runs_pipeline(
        self, controller, monkeypatch,
    ):
        calls: list = []
        monkeypatch.setattr(
            controller, "run_pipeline",
            lambda *a, **kw: calls.append((a, kw)),
        )
        controller._handle_menu_action("remove_license")
        assert calls, "run_pipeline not called"
        assert calls[0][0][0] == "license:auto"

    def test_remove_ads_runs_pipeline_ads_remove(
        self, controller, monkeypatch,
    ):
        calls: list = []
        monkeypatch.setattr(
            controller, "run_pipeline",
            lambda *a, **kw: calls.append(a),
        )
        controller._handle_menu_action("remove_ads")
        assert calls[0][0] == "ads:remove"

    def test_iap_emulation_runs_iap_dex(
        self, controller, monkeypatch,
    ):
        calls: list = []
        monkeypatch.setattr(
            controller, "run_pipeline",
            lambda *a, **kw: calls.append(a),
        )
        controller._handle_menu_action("iap_emulation")
        assert calls[0][0] == "iap:dex"

    def test_license_colon_mode_routes_to_rebuild(
        self, controller, monkeypatch,
    ):
        called: list = []
        monkeypatch.setattr(
            controller, "_open_rebuild_with_mode",
            lambda m: called.append(m),
        )
        controller._handle_menu_action("license:extreme")
        assert called == ["license:extreme"]

    def test_unknown_action_logs(self, controller, qtbot):
        """Variant 2: dùng qtbot.waitSignal 2 lần qua 2 lần gọi."""
        texts: list[str] = []
        controller.log_message.connect(texts.append)
        controller._handle_menu_action("bogus_xyz")
        # qtbot.waitUntil để flush Qt event queue
        qtbot.waitUntil(lambda: len(texts) >= 2, timeout=500)
        assert any("Unknown" in t for t in texts), texts
        assert any("bogus_xyz" in t for t in texts), texts


# ============================================================
# Rebuild submit intercept
# ============================================================
class TestRebuildSubmit:
    def _mk_dlg(self):
        d = MagicMock()
        d.get_key_type.return_value = "testkey"
        d.get_forced_package_id.return_value = None
        return d

    def test_single_special_dispatches(self, controller, monkeypatch):
        called: list = []
        monkeypatch.setattr(
            controller, "_dispatch_special_mode",
            lambda m: called.append(m),
        )
        controller._on_rebuild_submit("change_perms", self._mk_dlg())
        assert called == ["change_perms"]

    def test_multi_special_takes_first(self, controller, monkeypatch):
        called: list = []
        monkeypatch.setattr(
            controller, "_dispatch_special_mode",
            lambda m: called.append(m),
        )
        controller._on_rebuild_submit(
            "change_perms,resign", self._mk_dlg(),
        )
        assert called == ["change_perms"]

    def test_special_plus_normal_warns_but_runs_normal(
        self, controller, monkeypatch,
    ):
        run_calls: list = []
        monkeypatch.setattr(
            controller, "run_pipeline",
            lambda *a, **kw: run_calls.append(a),
        )
        controller._on_rebuild_submit(
            "license:auto,change_perms", self._mk_dlg(),
        )
        assert run_calls
        assert "license:auto" in run_calls[0][0]

    def test_normal_only_runs_pipeline(
        self, controller, monkeypatch,
    ):
        calls: list = []
        monkeypatch.setattr(
            controller, "run_pipeline",
            lambda *a, **kw: calls.append(a),
        )
        controller._on_rebuild_submit("license:auto,ads:remove",
                                      self._mk_dlg())
        assert calls
        assert "license:auto" in calls[0][0]
        assert "ads:remove" in calls[0][0]

    def test_empty_modes_no_pipeline(self, controller, monkeypatch):
        called: list = []
        monkeypatch.setattr(
            controller, "run_pipeline",
            lambda *a, **kw: called.append(a),
        )
        controller._on_rebuild_submit("", self._mk_dlg())
        assert not called

    def test_normal_uses_key_type_from_dlg(
        self, controller, monkeypatch,
    ):
        calls: list = []
        monkeypatch.setattr(
            controller, "run_pipeline",
            lambda *a, **kw: calls.append((a, kw)),
        )
        dlg = self._mk_dlg()
        dlg.get_key_type.return_value = "platform"
        controller._on_rebuild_submit("license:auto", dlg)
        _, kw = calls[0]
        assert kw["key_type"] == "platform"


# ============================================================
# Env var cleanup
# ============================================================
class TestEnvCleanup:
    def test_cleanup_removes_env_vars(self, controller):
        for k in (
            "LP_PERMS_TO_REMOVE", "LP_CLONE_PACKAGE",
            "LP_CLONE_APP_NAME", "LP_CUSTOM_PATCH",
        ):
            os.environ[k] = "sentinel"
        controller._on_pipeline_finished(True, "/out.apk")
        for k in (
            "LP_PERMS_TO_REMOVE", "LP_CLONE_PACKAGE",
            "LP_CLONE_APP_NAME", "LP_CUSTOM_PATCH",
        ):
            assert k not in os.environ, f"{k} not cleaned"


# ============================================================
# Constants
# ============================================================
class TestConstants:
    def test_special_modes_set(self):
        assert "change_perms" in _SPECIAL_MODES
        assert "resign" in _SPECIAL_MODES
        assert "clone" in _SPECIAL_MODES