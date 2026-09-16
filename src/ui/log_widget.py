"""Log widget — dùng QPlainTextEdit cho hiệu suất + block limit."""
from __future__ import annotations

from PyQt6.QtWidgets import QPlainTextEdit
from PyQt6.QtGui import QTextCursor
from PyQt6.QtCore import pyqtSlot


class LogWidget(QPlainTextEdit):
    MAX_BLOCKS = 5000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        # QPlainTextEdit có setMaximumBlockCount
        self.setMaximumBlockCount(self.MAX_BLOCKS)
        self.setStyleSheet(
            "font-family: 'Cascadia Code', Consolas, monospace; font-size: 12px;"
        )

    @pyqtSlot(str)
    def append_log(self, message: str) -> None:
        if not message:
            return
        self.appendPlainText(message)
        # Auto-scroll xuống cuối
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

    def clear_log(self) -> None:
        self.clear()

    # Tương thích API cũ nếu code khác gọi self.log.append(...)
    def append(self, text: str) -> None:
        self.append_log(text)