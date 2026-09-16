"""Panel công tắc — toggle switch kiểu Lucky Patcher."""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt


class ToggleSwitch(QPushButton):
    """iOS/LP-style toggle switch — animated màu, bo tròn."""

    def __init__(self, label: str, initial: bool = False, parent=None):
        super().__init__(parent)
        self._label = label
        self.setCheckable(True)
        self.setChecked(initial)
        self.setFixedHeight(34)
        self.setMinimumWidth(150)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.toggled.connect(self._refresh)
        self._refresh(initial)

    def _refresh(self, on: bool) -> None:
        state = "ON" if on else "OFF"
        self.setText(f"{self._label}: {state}")

        if on:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #238636;
                    color: #ffffff;
                    border: 1px solid #2ea043;
                    border-radius: 17px;
                    padding: 6px 18px;
                    font-weight: bold;
                    font-size: 12px;
                    text-align: left;
                }
                QPushButton:hover {
                    background-color: #2ea043;
                    border-color: #3fb950;
                }
                QPushButton:pressed {
                    background-color: #1a6b2a;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #21262d;
                    color: #8b949e;
                    border: 1px solid #30363d;
                    border-radius: 17px;
                    padding: 6px 18px;
                    font-weight: bold;
                    font-size: 12px;
                    text-align: left;
                }
                QPushButton:hover {
                    background-color: #30363d;
                    color: #c9d1d9;
                    border-color: #484f58;
                }
                QPushButton:pressed {
                    background-color: #161b22;
                }
            """)


class SwitchesPanel(QWidget):
    """Panel chứa các toggle switch runtime: Billing / Proxy / Auto-repeat / Save."""

    def __init__(self, iap_manager, parent=None):
        super().__init__(parent)
        self.iap = iap_manager
        self.setObjectName("switchesPanel")
        self.setFixedHeight(52)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # --- Billing toggle ---
        self.btn_billing = ToggleSwitch("💰 Billing", initial=True)
        self.btn_billing.toggled.connect(self._toggle_billing)
        layout.addWidget(self.btn_billing)

        # --- Proxy toggle ---
        self.btn_proxy = ToggleSwitch("🌐 Proxy", initial=True)
        self.btn_proxy.toggled.connect(self._toggle_proxy)
        layout.addWidget(self.btn_proxy)

        # --- Auto-repeat toggle ---
        self.btn_autorepeat = ToggleSwitch("🔄 Auto-repeat", initial=False)
        self.btn_autorepeat.toggled.connect(self._toggle_autorepeat)
        layout.addWidget(self.btn_autorepeat)

        # --- Save toggle ---
        self.btn_save = ToggleSwitch("💾 Save", initial=False)
        self.btn_save.toggled.connect(self._toggle_save)
        layout.addWidget(self.btn_save)

        layout.addStretch()

        # --- Reset button ---
        self.btn_reset = QPushButton("♻️ Reset")
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.setFixedHeight(34)
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
            QPushButton:pressed {
                background-color: #0d1117;
            }
        """)
        self.btn_reset.clicked.connect(self._reset)
        layout.addWidget(self.btn_reset)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _toggle_billing(self, on: bool) -> None:
        """Bật/tắt billing emulation — cập nhật iap_manager nếu có API."""
        try:
            if hasattr(self.iap, "billing_enabled"):
                self.iap.billing_enabled = on
        except Exception:
            pass

    def _toggle_proxy(self, on: bool) -> None:
        """Bật/tắt proxy emulation."""
        try:
            if hasattr(self.iap, "proxy_enabled"):
                self.iap.proxy_enabled = on
        except Exception:
            pass

    def _toggle_autorepeat(self, on: bool) -> None:
        """Bật/tắt tự động lặp giao dịch IAP đã lưu."""
        try:
            self.iap.auto_repeat_enabled = on
        except Exception:
            pass

    def _toggle_save(self, on: bool) -> None:
        """Bật/tắt lưu giao dịch IAP để phục hồi sau."""
        try:
            self.iap.save_for_restore_enabled = on
        except Exception:
            pass

    def _reset(self) -> None:
        """Reset toàn bộ toggle về trạng thái mặc định."""
        self.btn_billing.setChecked(True)
        self.btn_proxy.setChecked(True)
        self.btn_autorepeat.setChecked(False)
        self.btn_save.setChecked(False)