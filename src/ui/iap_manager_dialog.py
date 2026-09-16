"""Dialog quản lý giao dịch IAP đã lưu."""
from __future__ import annotations

import time

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QHBoxLayout, QMessageBox,
)
from PyQt6.QtCore import Qt


class IAPManagerDialog(QDialog):
    def __init__(self, iap_manager, parent=None):
        super().__init__(parent)
        self.iap = iap_manager
        self.setWindowTitle("Quản lý giao dịch IAP")
        self.resize(600, 400)

        layout = QVBoxLayout(self)
        self.list = QListWidget()
        layout.addWidget(self.list)

        btns = QHBoxLayout()
        refresh = QPushButton("🔄 Làm mới")
        refresh.clicked.connect(self._load)
        delete = QPushButton("🗑 Xóa")
        delete.clicked.connect(self._delete)
        repeat = QPushButton("▶ Lặp lại")
        repeat.clicked.connect(self._repeat)
        close = QPushButton("Đóng")
        close.clicked.connect(self.accept)
        btns.addWidget(refresh)
        btns.addWidget(delete)
        btns.addWidget(repeat)
        btns.addStretch()
        btns.addWidget(close)
        layout.addLayout(btns)

        self._load()

    def _load(self) -> None:
        self.list.clear()
        try:
            transactions = self.iap.get_saved_purchases()
        except Exception:
            transactions = []
        for t in transactions:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(t.get("timestamp", 0)))
            text = f"[{t.get('id')}] {t.get('package')} :: {t.get('product')} ({ts})"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, t.get("id"))
            self.list.addItem(item)

    def _delete(self) -> None:
        item = self.list.currentItem()
        if not item:
            return
        tid = item.data(Qt.ItemDataRole.UserRole)
        try:
            self.iap.delete_purchase(tid)
            self._load()
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", str(e))

    def _repeat(self) -> None:
        item = self.list.currentItem()
        if not item:
            return
        tid = item.data(Qt.ItemDataRole.UserRole)
        for t in self.iap.get_saved_purchases():
            if t.get("id") == tid:
                self.iap.auto_repeat(t.get("package"), t.get("product"))
                QMessageBox.information(self, "OK", "Đã lặp lại")
                return