"""Resign dialog — chọn key_type + forced package ID."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QSpinBox, QPushButton, QGroupBox, QRadioButton, QButtonGroup,
)


class ResignDialog(QDialog):
    KEY_INFO = {
        "testkey":    "Key test mặc định — dùng cho hầu hết app",
        "platform":   "Key platform — app hệ thống Android",
        "media":      "Key media — app media hệ thống",
        "shared":     "Key shared — library dùng chung",
    }

    def __init__(self, app_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Ký lại APK - {app_name}")
        self.setMinimumSize(460, 340)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(QLabel(
            "<b>Chọn loại chữ ký và cấu hình</b>"
        ))

        # Key type
        key_group = QGroupBox("Loại chữ ký")
        kg_layout = QVBoxLayout(key_group)
        self._key_group = QButtonGroup(self)
        for i, (key, desc) in enumerate(self.KEY_INFO.items()):
            rb = QRadioButton(f"<b>{key}</b> — {desc}")
            rb.setChecked(key == "testkey")
            rb.toggled.connect(
                lambda on, k=key: self._set_key(k) if on else None
            )
            self._key_group.addButton(rb)
            kg_layout.addWidget(rb)
        layout.addWidget(key_group)

        self._key_type = "testkey"

        # Forced package ID
        pkg_group = QGroupBox("Forced Package ID")
        pg_layout = QHBoxLayout(pkg_group)
        pg_layout.addWidget(QLabel("ID (127 = auto):"))
        self.pkg_spin = QSpinBox()
        self.pkg_spin.setRange(1, 127)
        self.pkg_spin.setValue(127)
        pg_layout.addWidget(self.pkg_spin)
        pg_layout.addStretch()
        layout.addWidget(pkg_group)

        layout.addStretch()

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Hủy")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        ok = QPushButton("Ký lại")
        ok.setStyleSheet(
            "background-color:#238636; color:white;"
            "font-weight:bold; padding:8px 20px; border-radius:6px;"
        )
        ok.clicked.connect(self.accept)
        btns.addWidget(ok)
        layout.addLayout(btns)

    def _set_key(self, key: str) -> None:
        self._key_type = key

    def get_key_type(self) -> str:
        return self._key_type

    def get_forced_package_id(self) -> int | None:
        v = self.pkg_spin.value()
        return None if v == 127 else v