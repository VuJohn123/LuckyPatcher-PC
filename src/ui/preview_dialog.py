"""Dialog xem trước các patch sẽ chạy."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QPushButton, QLabel,
    QHBoxLayout, QTextEdit,
)


class PreviewDialog(QDialog):
    def __init__(self, patches: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Xem trước thay đổi")
        self.setMinimumSize(550, 450)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Các bản vá sẽ được áp dụng:</b>"))

        text = QTextEdit()
        text.setReadOnly(True)
        lines = []
        for p in patches:
            lines.append(f"• {p.get('label', '?')}")
            if p.get("mode"):
                lines.append(f"  Mode: {p['mode']}")
            if p.get("description"):
                lines.append(f"  {p['description']}")
            lines.append("")
        text.setText("\n".join(lines))
        layout.addWidget(text)

        btns = QHBoxLayout()
        ok = QPushButton("Tiếp tục xây dựng")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Quay lại")
        cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)