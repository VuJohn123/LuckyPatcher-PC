"""Wizard đơn giản cho người mới."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QRadioButton, QPushButton,
    QButtonGroup, QHBoxLayout, QLabel,
)


class WizardDialog(QDialog):
    OPTIONS = [
        ("iap_dex", "🎮 Chơi game miễn phí (IAP bypass)"),
        ("ads_full_offline", "🚫 Xóa quảng cáo"),
        ("license:extreme", "🔑 Dùng app trả phí miễn phí"),
        ("multi:license,ads,iap_dex", "⭐ Full patch (tất cả)"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LP-PC Suite Wizard")
        self.setMinimumSize(450, 320)
        self._selected = "iap_dex"

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Bạn muốn làm gì?</b>"))

        self._group = QButtonGroup(self)
        for key, label in self.OPTIONS:
            rb = QRadioButton(label)
            rb.setChecked(key == self._selected)
            rb.toggled.connect(lambda on, k=key: self._select(k) if on else None)
            self._group.addButton(rb)
            layout.addWidget(rb)

        btns = QHBoxLayout()
        ok = QPushButton("Bắt đầu")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Thoát")
        cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)

    def _select(self, key: str) -> None:
        self._selected = key

    def get_mode(self) -> str:
        return self._selected