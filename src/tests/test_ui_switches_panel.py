"""UI test cho SwitchesPanel + ToggleSwitch."""
from __future__ import annotations

import pytest

from core.i18n import set_language
from ui.switches_panel import SwitchesPanel, ToggleSwitch


class FakeIAP:
    """Fake IAP manager — không dùng MagicMock vì hasattr check."""

    def __init__(self):
        self.billing_enabled = True
        self.proxy_enabled = True
        self.auto_repeat_enabled = False
        self.save_for_restore_enabled = False


@pytest.fixture(autouse=True)
def _force_vi():
    set_language("vi")
    yield
    set_language("vi")


@pytest.fixture
def iap():
    return FakeIAP()


@pytest.fixture
def panel(qtbot, iap):
    p = SwitchesPanel(iap)
    qtbot.addWidget(p)
    return p


# ============================================================
# ToggleSwitch
# ============================================================
class TestToggleSwitch:
    def test_default_off(self, qtbot):
        s = ToggleSwitch("Test")
        qtbot.addWidget(s)
        assert s.isChecked() is False
        assert "TẮT" in s.text()

    def test_initial_true(self, qtbot):
        s = ToggleSwitch("Test", initial=True)
        qtbot.addWidget(s)
        assert s.isChecked() is True
        assert "BẬT" in s.text()

    def test_checkable(self, qtbot):
        s = ToggleSwitch("X")
        qtbot.addWidget(s)
        assert s.isCheckable()

    def test_fixed_height(self, qtbot):
        s = ToggleSwitch("X")
        qtbot.addWidget(s)
        assert s.height() == 34

    def test_toggle_updates_text(self, qtbot):
        s = ToggleSwitch("X")
        qtbot.addWidget(s)
        s.setChecked(True)
        assert "BẬT" in s.text()

    def test_toggle_updates_property(self, qtbot):
        s = ToggleSwitch("X")
        qtbot.addWidget(s)
        s.setChecked(True)
        assert s.property("state") == "on"
        s.setChecked(False)
        assert s.property("state") == "off"

    def test_tooltip_set(self, qtbot):
        s = ToggleSwitch("X", tooltip="Mô tả")
        qtbot.addWidget(s)
        assert "Mô tả" in s.toolTip()

    def test_label_embedded(self, qtbot):
        s = ToggleSwitch("💰 Billing")
        qtbot.addWidget(s)
        assert "Billing" in s.text()


# ============================================================
# SwitchesPanel construction
# ============================================================
class TestPanelConstruction:
    def test_panel_has_4_toggles(self, panel):
        assert panel.btn_billing is not None
        assert panel.btn_proxy is not None
        assert panel.btn_autorepeat is not None
        assert panel.btn_save is not None

    def test_panel_has_reset(self, panel):
        assert panel.btn_reset is not None

    def test_panel_fixed_height(self, panel):
        assert panel.height() == 52

    def test_default_billing_on(self, panel):
        assert panel.btn_billing.isChecked() is True

    def test_default_proxy_on(self, panel):
        assert panel.btn_proxy.isChecked() is True

    def test_default_autorepeat_off(self, panel):
        assert panel.btn_autorepeat.isChecked() is False

    def test_default_save_off(self, panel):
        assert panel.btn_save.isChecked() is False


# ============================================================
# Toggle → IAP manager updates
# ============================================================
class TestToggleIAPManager:
    def test_billing_off_updates_manager(self, panel, iap):
        panel.btn_billing.setChecked(False)
        assert iap.billing_enabled is False

    def test_billing_on_updates_manager(self, panel, iap):
        panel.btn_billing.setChecked(False)
        panel.btn_billing.setChecked(True)
        assert iap.billing_enabled is True

    def test_proxy_off_updates_manager(self, panel, iap):
        panel.btn_proxy.setChecked(False)
        assert iap.proxy_enabled is False

    def test_autorepeat_on_updates_manager(self, panel, iap):
        panel.btn_autorepeat.setChecked(True)
        assert iap.auto_repeat_enabled is True

    def test_save_on_updates_manager(self, panel, iap):
        panel.btn_save.setChecked(True)
        assert iap.save_for_restore_enabled is True

    def test_manager_without_billing_attr_no_crash(self, qtbot):
        """IAP manager không có billing_enabled → hasattr=False."""
        class MinimalIAP:
            auto_repeat_enabled = False
            save_for_restore_enabled = False

        p = SwitchesPanel(MinimalIAP())
        qtbot.addWidget(p)
        p.btn_billing.setChecked(False)
        # Không crash


# ============================================================
# Reset
# ============================================================
class TestReset:
    def test_reset_restores_defaults(self, panel):
        panel.btn_billing.setChecked(False)
        panel.btn_proxy.setChecked(False)
        panel.btn_autorepeat.setChecked(True)
        panel.btn_save.setChecked(True)

        panel._reset()

        assert panel.btn_billing.isChecked() is True
        assert panel.btn_proxy.isChecked() is True
        assert panel.btn_autorepeat.isChecked() is False
        assert panel.btn_save.isChecked() is False

    def test_reset_updates_manager(self, panel, iap):
        panel.btn_billing.setChecked(False)
        assert iap.billing_enabled is False
        panel._reset()
        assert iap.billing_enabled is True

    def test_reset_button_click(self, panel):
        panel.btn_billing.setChecked(False)
        panel.btn_reset.click()
        assert panel.btn_billing.isChecked() is True