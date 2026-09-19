"""Clone dialog — đổi package + app name."""
from __future__ import annotations

import re

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox,
)


class CloneDialog(QDialog):
    def __init__(
        self, app_name: str, package: str, parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Clone App")
        self.setMinimumSize(480, 260)
        self.original_package = package
        self.original_name = app_name
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(QLabel(
            f"<b>Clone: {self.original_name}</b>"
        ))
        layout.addWidget(QLabel(
            f"Package gốc: <code>{self.original_package}</code>"
        ))

        # New package
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Package mới:"))
        self.pkg_input = QLineEdit()
        self.pkg_input.setText(f"{self.original_package}.clone")
        self.pkg_input.setPlaceholderText("com.example.app.clone")
        row1.addWidget(self.pkg_input, 1)
        layout.addLayout(row1)

        # New app name
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Tên mới:"))
        self.name_input = QLineEdit()
        self.name_input.setText(f"{self.original_name} (Clone)")
        row2.addWidget(self.name_input, 1)
        layout.addLayout(row2)

        hint = QLabel(
            "<span style='color:#8b949e; font-size:11px;'>"
            "💡 App clone sẽ chạy song song với app gốc. "
            "Cần có chữ ký khác (dùng testkey để tự ký)."
            "</span>"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch()

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Hủy")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        ok = QPushButton("Clone")
        ok.setStyleSheet(
            "background-color:#238636; color:white;"
            "font-weight:bold; padding:8px 20px; border-radius:6px;"
        )
        ok.clicked.connect(self._on_ok)
        btns.addWidget(ok)
        layout.addLayout(btns)

    def _on_ok(self) -> None:
        pkg = self.pkg_input.text().strip()
        if not pkg:
            QMessageBox.warning(self, "Lỗi", "Package không hợp lệ")
            return
        # Basic validate
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9._]*$", pkg):
            QMessageBox.warning(
                self, "Lỗi",
                "Package phải bắt đầu bằng chữ cái và chỉ chứa "
                "chữ, số, dấu chấm.",
            )
            return
        if pkg == self.original_package:
            QMessageBox.warning(
                self, "Lỗi",
                "Package mới phải khác package gốc.",
            )
            return
        self.accept()

    def get_new_package(self) -> str:
        return self.pkg_input.text().strip()

    def get_new_name(self) -> str:
        return self.name_input.text().strip()