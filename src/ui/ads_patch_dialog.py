"""Dialog chọn chế độ Ads removal."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QRadioButton, QPushButton,
    QButtonGroup, QHBoxLayout, QLabel,
)
from PyQt6.QtCore import pyqtSignal


class AdsPatchDialog(QDialog):
    patch_requested = pyqtSignal(str)

    OPTIONS = [
        ("remove", "Xóa activity quảng cáo khỏi manifest"),
        ("offline", "Làm module nghĩ rằng offline"),
        ("links", "Xóa URL quảng cáo trong smali"),
        ("full_offline", "Full offline (kết hợp)"),
    ]

    def __init__(self, app_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Remove Ads - {app_name}")
        self.setMinimumSize(450, 320)
        self._selected = "remove"
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Chọn chế độ Ads:</b>"))

        self._group = QButtonGroup(self)
        for key, label in self.OPTIONS:
            rb = QRadioButton(label)
            rb.setChecked(key == self._selected)
            rb.toggled.connect(lambda on, k=key: self._select(k) if on else None)
            self._group.addButton(rb)
            layout.addWidget(rb)

        btns = QHBoxLayout()
        ok = QPushButton("Áp dụng")
        ok.clicked.connect(self._apply)
        cancel = QPushButton("Hủy")
        cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)

    def _select(self, key: str) -> None:
        self._selected = key

    def _apply(self) -> None:
        self.patch_requested.emit(f"ads:{self._selected}")
        self.accept()