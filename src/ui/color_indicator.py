"""Color indicator — widget nhỏ hiển thị màu phân loại."""
from __future__ import annotations

from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt


_COLOR_MAP = {
    "green": "#238636", "yellow": "#d29922", "blue": "#1f6feb",
    "purple": "#8957e5", "orange": "#d29922", "red": "#da3633",
    "white": "#8b949e",
}


class ColorIndicator(QLabel):
    def __init__(self, color: str = "white", size: int = 12, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.set_color(color)

    def set_color(self, color: str) -> None:
        hex_color = _COLOR_MAP.get(color, "#8b949e")
        self.setStyleSheet(
            f"background-color: {hex_color};"
            f"border-radius: {self.width() // 2}px;"
        )
        self.setToolTip(color.capitalize())