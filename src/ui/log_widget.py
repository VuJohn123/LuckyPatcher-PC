"""Log widget — dùng QPlainTextEdit cho hiệu suất + block limit + copy-paste support."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QAction, QKeySequence, QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit


class LogWidget(QPlainTextEdit):
    MAX_BLOCKS = 5000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(self.MAX_BLOCKS)
        self.setStyleSheet(
            "font-family: 'Cascadia Code', Consolas, monospace; font-size: 12px;"
        )
        # Enable context menu for copy
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        # Keyboard shortcuts
        self._setup_shortcuts()

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts for copy/select all."""
        copy_action = QAction(self)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.triggered.connect(self.copy)
        self.addAction(copy_action)

        select_all_action = QAction(self)
        select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        select_all_action.triggered.connect(self.selectAll)
        self.addAction(select_all_action)

    def _show_context_menu(self, pos):
        """Show context menu with copy options."""
        menu = self.createStandardContextMenu()
        menu.addSeparator()

        # Copy action
        copy_action = menu.addAction("📋 Copy")
        copy_action.triggered.connect(self.copy)
        copy_action.setEnabled(self.textCursor().hasSelection())

        # Copy all action
        copy_all_action = menu.addAction("📋 Copy All")
        copy_all_action.triggered.connect(self._copy_all)

        # Save action
        save_action = menu.addAction("💾 Save Log...")
        save_action.triggered.connect(self._save_log)

        menu.exec(self.mapToGlobal(pos))

    def _copy_all(self):
        """Copy entire log to clipboard."""
        self.selectAll()
        self.copy()
        # Clear selection
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)

    def _save_log(self):
        """Save log to file."""
        from datetime import datetime

        from PyQt6.QtWidgets import QFileDialog

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Log",
            f"lp_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt);;All Files (*)"
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.toPlainText())
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Save Failed", f"Failed to save log: {e}")

    @pyqtSlot(str)
    def append_log(self, message: str) -> None:
        if not message:
            return
        bar = self.verticalScrollBar()
        at_bottom = bar is not None and bar.value() >= bar.maximum() - 1

        self.appendPlainText(message)
        if not at_bottom:
            return
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

    def clear_log(self) -> None:
        self.clear()

    def append(self, text: str) -> None:
        self.append_log(text)
