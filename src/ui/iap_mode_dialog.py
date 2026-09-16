"""Dialog chọn chế độ IAP emulation."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QRadioButton, QPushButton,
    QButtonGroup, QHBoxLayout, QLabel,
)


class IAPModeDialog(QDialog):
    OPTIONS = [
        ("iap_dex", "Reassembly Dex — Im lặng & Tự động"),
        ("iap_proxy", "Proxy Server — cần ADB + PC proxy"),
        ("aidl_proxy", "AIDL Proxy — nhúng service vào APK"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("IAP Emulation Mode")
        self.setMinimumSize(450, 300)
        self._selected = "iap_dex"
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Chọn phương pháp IAP:</b>"))

        self._group = QButtonGroup(self)
        for key, label in self.OPTIONS:
            rb = QRadioButton(label)
            rb.setChecked(key == self._selected)
            rb.toggled.connect(lambda on, k=key: self._select(k) if on else None)
            self._group.addButton(rb)
            layout.addWidget(rb)

        btns = QHBoxLayout()
        ok = QPushButton("Tiếp tục")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Hủy")
        cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)

    def _select(self, key: str) -> None:
        self._selected = key

    def get_mode(self) -> str:
        return self._selected