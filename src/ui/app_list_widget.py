"""App list widget — hiển thị danh sách app với màu phân loại."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QListWidget, QListWidgetItem, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QMenu,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor


_COLOR_MAP = {
    "green": "#238636",
    "yellow": "#d29922",
    "blue": "#1f6feb",
    "purple": "#8957e5",
    "orange": "#d29922",
    "red": "#da3633",
    "white": "#8b949e",
}


class _AppItemWidget(QWidget):
    def __init__(self, name: str, package: str, colors: list[str]):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        top = QHBoxLayout()
        dot = QLabel()
        dot.setFixedSize(12, 12)
        primary = colors[0] if colors else "white"
        dot.setStyleSheet(
            f"background-color: {_COLOR_MAP.get(primary, '#8b949e')};"
            "border-radius: 6px;"
        )
        top.addWidget(dot)

        name_lbl = QLabel(name)
        name_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        top.addWidget(name_lbl)
        top.addStretch()
        layout.addLayout(top)

        pkg_lbl = QLabel(package)
        pkg_lbl.setStyleSheet("color: #8b949e; font-size: 10px;")
        layout.addWidget(pkg_lbl)

        self.setToolTip(f"{name}\n{package}\nColors: {', '.join(colors)}")


class AppListWidget(QListWidget):
    app_context_menu_requested = pyqtSignal(str, str, list, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.all_items: list[QListWidgetItem] = []

    def add_app(self, name: str, package: str, colors: list[str]) -> None:
        findings = self._colors_to_findings(colors)
        item = QListWidgetItem()
        widget = _AppItemWidget(name, package, colors)
        item.setSizeHint(widget.sizeHint())
        item.setData(Qt.ItemDataRole.UserRole, {
            "name": name,
            "package": package,
            "colors": colors,
            "findings": findings,
        })
        self.addItem(item)
        self.setItemWidget(item, widget)
        self.all_items.append(item)

    def _colors_to_findings(self, colors: list[str]) -> list[dict]:
        findings = []
        if "green" in colors:
            findings.append({"type": "license", "color": "green",
                             "description": "License found"})
        if "blue" in colors:
            findings.append({"type": "ads", "color": "blue",
                             "description": "Ads found"})
        if "purple" in colors:
            findings.append({"type": "system_boot", "color": "purple",
                             "description": "System boot"})
        if "orange" in colors:
            findings.append({"type": "system", "color": "orange",
                             "description": "System app"})
        if "yellow" in colors:
            findings.append({"type": "custom_patch", "color": "yellow",
                             "description": "Custom patch available"})
        if "red" in colors:
            findings.append({"type": "protected", "color": "red",
                             "description": "Cannot patch"})
        return findings

    def _show_context_menu(self, pos):
        item = self.itemAt(pos)
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction("Open Menu of Patches", lambda: self.app_context_menu_requested.emit(
            data["package"], data["name"], data["colors"], data["findings"]
        ))
        menu.addAction("Create Modified APK", lambda: self.app_context_menu_requested.emit(
            data["package"], data["name"], data["colors"], data["findings"]
        ))
        menu.addSeparator()
        menu.addAction("Copy package", lambda: self._copy(data["package"]))
        menu.exec(self.viewport().mapToGlobal(pos))

    def _copy(self, text: str) -> None:
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

    def filter(self, text: str, filter_type: str = "All") -> None:
        text = (text or "").lower()
        for item in self.all_items:
            data = item.data(Qt.ItemDataRole.UserRole)
            colors = data.get("colors", [])
            name = data.get("name", "").lower()

            visible = True
            if text and text not in name:
                visible = False
            if filter_type == "License check" and "green" not in colors:
                visible = False
            elif filter_type == "Ads" and "blue" not in colors:
                visible = False
            elif filter_type == "Custom patch" and "yellow" not in colors:
                visible = False
            elif filter_type == "System" and not (
                "purple" in colors or "orange" in colors
            ):
                visible = False
            item.setHidden(not visible)