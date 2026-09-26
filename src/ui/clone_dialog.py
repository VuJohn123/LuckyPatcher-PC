"""Clone dialog — đổi package + app name."""
from __future__ import annotations

import re

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox,
)

from core.i18n import t


class CloneDialog(QDialog):
    def __init__(
        self, app_name: str, package: str, parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(t("dialog.clone.title"))
        self.setMinimumSize(480, 260)
        self.original_package = package
        self.original_name = app_name
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(QLabel(
            "<b>" + t("dialog.clone.header", name=self.original_name) + "</b>"
        ))
        layout.addWidget(QLabel(
            f"{t('dialog.clone.orig_pkg')} "
            f"<code>{self.original_package}</code>"
        ))

        # New package
        row1 = QHBoxLayout()
        row1.addWidget(QLabel(t("dialog.clone.new_pkg")))
        self.pkg_input = QLineEdit()
        self.pkg_input.setText(
            self.original_package + t("dialog.clone.suffix_pkg")
        )
        self.pkg_input.setPlaceholderText("com.example.app.clone")
        row1.addWidget(self.pkg_input, 1)
        layout.addLayout(row1)

        # New app name
        row2 = QHBoxLayout()
        row2.addWidget(QLabel(t("dialog.clone.new_name")))
        self.name_input = QLineEdit()
        self.name_input.setText(
            self.original_name + t("dialog.clone.suffix_name")
        )
        row2.addWidget(self.name_input, 1)
        layout.addLayout(row2)

        hint = QLabel(
            f"<span style='color:#8b949e; font-size:11px;'>"
            f"{t('dialog.clone.hint')}</span>"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch()

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton(t("dialog.common.cancel"))
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        ok = QPushButton(t("dialog.clone.btn_ok"))
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
            QMessageBox.warning(
                self, t("dialog.common.error"),
                t("dialog.clone.warn_empty_pkg"),
            )
            return
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9._]*$", pkg):
            QMessageBox.warning(
                self, t("dialog.common.error"),
                t("dialog.clone.warn_regex_pkg"),
            )
            return
        if pkg == self.original_package:
            QMessageBox.warning(
                self, t("dialog.common.error"),
                t("dialog.clone.warn_same_pkg"),
            )
            return
        self.accept()

    def get_new_package(self) -> str:
        return self.pkg_input.text().strip()

    def get_new_name(self) -> str:
        return self.name_input.text().strip()