"""Panel công tắc — bật/tắt các tính năng runtime."""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton


class SwitchesPanel(QWidget):
    def __init__(self, iap_manager, parent=None):
        super().__init__(parent)
        self.iap = iap_manager
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self.btn_billing = QPushButton("💰 Billing: ON")
        self.btn_billing.setCheckable(True)
        self.btn_billing.setChecked(True)
        self.btn_billing.toggled.connect(self._toggle_billing)
        layout.addWidget(self.btn_billing)

        self.btn_proxy = QPushButton("🌐 Proxy: ON")
        self.btn_proxy.setCheckable(True)
        self.btn_proxy.setChecked(True)
        self.btn_proxy.toggled.connect(self._toggle_proxy)
        layout.addWidget(self.btn_proxy)

        self.btn_autorepeat = QPushButton("🔄 Auto-repeat: OFF")
        self.btn_autorepeat.setCheckable(True)
        self.btn_autorepeat.toggled.connect(self._toggle_autorepeat)
        layout.addWidget(self.btn_autorepeat)

        self.btn_save = QPushButton("💾 Save: OFF")
        self.btn_save.setCheckable(True)
        self.btn_save.toggled.connect(self._toggle_save)
        layout.addWidget(self.btn_save)

        self.btn_reset = QPushButton("♻️ Reset")
        self.btn_reset.clicked.connect(self._reset)
        layout.addWidget(self.btn_reset)

        layout.addStretch()

    def _toggle_billing(self, on: bool) -> None:
        self.btn_billing.setText(f"💰 Billing: {'ON' if on else 'OFF'}")

    def _toggle_proxy(self, on: bool) -> None:
        self.btn_proxy.setText(f"🌐 Proxy: {'ON' if on else 'OFF'}")

    def _toggle_autorepeat(self, on: bool) -> None:
        self.btn_autorepeat.setText(f"🔄 Auto-repeat: {'ON' if on else 'OFF'}")
        try:
            self.iap.auto_repeat_enabled = on
        except Exception:
            pass

    def _toggle_save(self, on: bool) -> None:
        self.btn_save.setText(f"💾 Save: {'ON' if on else 'OFF'}")
        try:
            self.iap.save_for_restore_enabled = on
        except Exception:
            pass

    def _reset(self) -> None:
        self.btn_billing.setChecked(True)
        self.btn_proxy.setChecked(True)
        self.btn_autorepeat.setChecked(False)
        self.btn_save.setChecked(False)