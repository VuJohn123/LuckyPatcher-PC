"""Dialog cấu hình 1 patch đơn lẻ (radio options)."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QRadioButton, QPushButton,
    QButtonGroup, QHBoxLayout, QLabel,
)


class PatchConfigDialog(QDialog):
    def __init__(self, patch_name: str, options: dict[str, str],
                 current_mode: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Cấu hình {patch_name}")
        self.setMinimumSize(400, 300)
        self._selected = current_mode or next(iter(options), "")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<b>{patch_name}</b>"))

        self._group = QButtonGroup(self)
        for key, desc in options.items():
            rb = QRadioButton(f"{key}: {desc}")
            rb.setChecked(key == self._selected)
            rb.toggled.connect(lambda on, k=key: self._select(k) if on else None)
            self._group.addButton(rb)
            layout.addWidget(rb)

        btns = QHBoxLayout()
        ok = QPushButton("OK")
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