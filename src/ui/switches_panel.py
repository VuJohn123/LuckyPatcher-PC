"""Panel công tắc — toggle switch kiểu Lucky Patcher (i18n)."""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt

from core.i18n import t


class ToggleSwitch(QPushButton):
    def __init__(
        self, label: str, initial: bool = False,
        tooltip: str = "", parent=None,
    ):
        super().__init__(parent)
        self._label = label
        self.setCheckable(True)
        self.setChecked(initial)
        self.setFixedHeight(34)
        self.setMinimumWidth(150)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        if tooltip:
            self.setToolTip(tooltip)

        self.setStyleSheet("""
            QPushButton {
                border-radius: 17px;
                padding: 6px 18px;
                font-weight: bold;
                font-size: 12px;
                text-align: left;
                border: 1px solid #30363d;
                background-color: #21262d;
                color: #8b949e;
            }
            QPushButton[state="on"] {
                background-color: #238636;
                color: #ffffff;
                border-color: #2ea043;
            }
            QPushButton[state="on"]:hover {
                background-color: #2ea043;
                border-color: #3fb950;
            }
            QPushButton[state="off"]:hover {
                background-color: #30363d;
                color: #c9d1d9;
                border-color: #484f58;
            }
        """)
        self.toggled.connect(self._refresh)
        self._refresh(initial)

    def _refresh(self, on: bool) -> None:
        state = t("switches.on") if on else t("switches.off")
        self.setText(f"{self._label}: {state}")
        self.setProperty("state", "on" if on else "off")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class SwitchesPanel(QWidget):
    def __init__(self, iap_manager, parent=None):
        super().__init__(parent)
        self.iap = iap_manager
        self.setObjectName("switchesPanel")
        self.setFixedHeight(52)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        self.btn_billing = ToggleSwitch(
            t("switches.billing"), initial=True,
            tooltip=t("switches.billing_tip"),
        )
        self.btn_billing.toggled.connect(self._toggle_billing)
        layout.addWidget(self.btn_billing)

        self.btn_proxy = ToggleSwitch(
            t("switches.proxy"), initial=True,
            tooltip=t("switches.proxy_tip"),
        )
        self.btn_proxy.toggled.connect(self._toggle_proxy)
        layout.addWidget(self.btn_proxy)

        self.btn_autorepeat = ToggleSwitch(
            t("switches.autorepeat"), initial=False,
            tooltip=t("switches.autorepeat_tip"),
        )
        self.btn_autorepeat.toggled.connect(self._toggle_autorepeat)
        layout.addWidget(self.btn_autorepeat)

        self.btn_save = ToggleSwitch(
            t("switches.save"), initial=False,
            tooltip=t("switches.save_tip"),
        )
        self.btn_save.toggled.connect(self._toggle_save)
        layout.addWidget(self.btn_save)

        layout.addStretch()

        self.btn_reset = QPushButton(t("switches.reset"))
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.setFixedHeight(34)
        self.btn_reset.setToolTip("Reset tất cả switch về mặc định")
        self.btn_reset.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #8b949e;
                border: 1px solid #30363d;
                border-radius: 17px;
                padding: 6px 18px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #21262d;
                color: #f0f6fc;
                border-color: #58a6ff;
            }
        """)
        self.btn_reset.clicked.connect(self._reset)
        layout.addWidget(self.btn_reset)

    def _toggle_billing(self, on: bool) -> None:
        try:
            if hasattr(self.iap, "billing_enabled"):
                self.iap.billing_enabled = on
        except Exception:
            pass

    def _toggle_proxy(self, on: bool) -> None:
        try:
            if hasattr(self.iap, "proxy_enabled"):
                self.iap.proxy_enabled = on
        except Exception:
            pass

    def _toggle_autorepeat(self, on: bool) -> None:
        try:
            self.iap.auto_repeat_enabled = on
        except Exception:
            pass

    def _toggle_save(self, on: bool) -> None:
        try:
            self.iap.save_for_restore_enabled = on
        except Exception:
            pass

    def _reset(self) -> None:
        self.btn_billing.setChecked(True)
        self.btn_proxy.setChecked(True)
        self.btn_autorepeat.setChecked(False)
        self.btn_save.setChecked(False)