"""App list widget — card-style items với màu phân loại."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QListWidget, QListWidgetItem, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QMenu, QApplication, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


_COLOR_MAP = {
    "green": "#3fb950",
    "yellow": "#d29922",
    "blue": "#58a6ff",
    "purple": "#a371f7",
    "orange": "#db6d28",
    "red": "#f85149",
    "white": "#8b949e",
}

_COLOR_EMOJI = {
    "green": "🔑",
    "yellow": "🧩",
    "blue": "📢",
    "purple": "⚙️",
    "orange": "📦",
    "red": "🔒",
    "white": "📱",
}


class _AppItemWidget(QWidget):
    """Card-style item — stripe màu + icon + text vertical-center."""

    def __init__(self, name: str, package: str, colors: list[str],
                 is_patched: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("appItem")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumHeight(64)

        primary = colors[0] if colors else "white"
        primary_hex = _COLOR_MAP.get(primary, "#8b949e")
        emoji = _COLOR_EMOJI.get(primary, "📱")

        # === Base style (background + border-radius) ===
        self.setStyleSheet(f"""
            QWidget#appItem {{
                background-color: #161b22;
                border: 1px solid #21262d;
                border-radius: 8px;
            }}
            QWidget#appItem:hover {{
                background-color: #1c232c;
                border-color: #30363d;
            }}
            QWidget#appItem[selected="true"] {{
                background-color: #1f6feb22;
                border-color: #1f6feb;
            }}
        """)

        # === Outer layout: stripe | content ===
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- Left stripe (colored) ---
        stripe = QFrame()
        stripe.setFixedWidth(4)
        stripe.setStyleSheet(
            f"background-color: {primary_hex};"
            "border-top-left-radius: 8px;"
            "border-bottom-left-radius: 8px;"
        )
        outer.addWidget(stripe)

        # --- Content area (padding bên trong) ---
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(14, 8, 16, 8)
        content_layout.setSpacing(14)

        # Icon 42x42
        icon = QLabel(emoji)
        icon.setFixedSize(42, 42)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"background-color: {primary_hex}22;"
            f"border: 1px solid {primary_hex}55;"
            "border-radius: 10px;"
            "font-size: 20px;"
        )
        content_layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)

        # Text column (VERTICAL CENTER)
        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        text_col.setContentsMargins(0, 0, 0, 0)

        # Row 1: name + clover + badges
        top = QHBoxLayout()
        top.setSpacing(8)
        top.setContentsMargins(0, 0, 0, 0)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            "color: #f0f6fc; font-size: 13px; font-weight: 600;"
            "background: transparent;"
        )
        top.addWidget(name_lbl)

        if is_patched:
            clover = QLabel("🍀")
            clover.setToolTip("Đã patch bởi LP-PC Suite")
            clover.setStyleSheet("font-size: 14px; background: transparent;")
            top.addWidget(clover)

        if "purple" in colors or "orange" in colors:
            top.addWidget(self._badge("SYS", "#d29922"))
        if "red" in colors:
            top.addWidget(self._badge("PROTECTED", "#f85149"))

        top.addStretch()
        text_col.addLayout(top)

        # Row 2: package
        pkg_lbl = QLabel(package)
        pkg_lbl.setStyleSheet(
            "color: #6e7681; font-size: 10px; background: transparent;"
        )
        text_col.addWidget(pkg_lbl)

        # Wrap text_col trong widget để vertical-center
        text_wrap = QWidget()
        text_wrap.setStyleSheet("background: transparent;")
        text_wrap.setLayout(text_col)
        content_layout.addWidget(text_wrap, 1, Qt.AlignmentFlag.AlignVCenter)

        # Right: color dots
        dots_wrap = QWidget()
        dots_wrap.setStyleSheet("background: transparent;")
        dots = QHBoxLayout(dots_wrap)
        dots.setSpacing(5)
        dots.setContentsMargins(0, 0, 0, 0)
        for c in colors[:6]:
            dot = QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(
                f"background-color: {_COLOR_MAP.get(c, '#8b949e')};"
                "border-radius: 5px;"
            )
            dot.setToolTip(c.capitalize())
            dots.addWidget(dot)
        content_layout.addWidget(dots_wrap, 0, Qt.AlignmentFlag.AlignVCenter)

        outer.addWidget(content, 1)

        # Tooltip
        tooltip = [f"<b>{name}</b>", package]
        if colors:
            tooltip.append(
                "Màu: " + ", ".join(c.capitalize() for c in colors)
            )
        if is_patched:
            tooltip.append("🍀 Đã patch")
        self.setToolTip("<br>".join(tooltip))

    def _badge(self, text: str, color: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"""
            color: {color};
            background-color: {color}22;
            border: 1px solid {color}55;
            border-radius: 3px;
            padding: 1px 6px;
            font-size: 9px;
            font-weight: bold;
        """)
        return lbl


class AppListWidget(QListWidget):
    """List widget — card-style items, hover/selected do widget tự xử lý."""

    app_context_menu_requested = pyqtSignal(str, str, list, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setSpacing(4)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setUniformItemSizes(False)

        # Custom widget tự vẽ background → tắt selection style mặc định
        self.setStyleSheet("""
            QListWidget {
                background-color: #0d1117;
                border: none;
                outline: none;
                padding: 6px;
            }
            QListWidget::item {
                background: transparent;
                border: none;
                padding: 0;
                margin: 0;
            }
            QListWidget::item:selected,
            QListWidget::item:hover {
                background: transparent;
            }
        """)

        self.all_items: list[QListWidgetItem] = []
        self.currentItemChanged.connect(self._on_current_changed)

    # ------------------------------------------------------------------
    def add_app(self, name: str, package: str, colors: list[str],
                is_patched: bool = False) -> None:
        findings = self._colors_to_findings(colors)
        item = QListWidgetItem()
        widget = _AppItemWidget(name, package, colors, is_patched)
        # Đảm bảo sizeHint = minimum height của widget
        item.setSizeHint(widget.sizeHint())
        item.setData(Qt.ItemDataRole.UserRole, {
            "name": name,
            "package": package,
            "colors": colors,
            "findings": findings,
            "is_patched": is_patched,
        })
        self.addItem(item)
        self.setItemWidget(item, widget)
        self.all_items.append(item)

    # ------------------------------------------------------------------
    def _on_current_changed(self, current, previous) -> None:
        """Highlight selected card bằng property selector."""
        for it in (previous, current):
            if it is None:
                continue
            w = self.itemWidget(it)
            if w is not None:
                w.setProperty("selected", it is current)
                w.style().unpolish(w)
                w.style().polish(w)
                w.update()

    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    def _show_context_menu(self, pos):
        item = self.itemAt(pos)
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)

        menu = QMenu(self)

        act_patches = menu.addAction("🧩  Open Menu of Patches")
        act_patches.triggered.connect(
            lambda: self.app_context_menu_requested.emit(
                data["package"], data["name"],
                data["colors"], data["findings"],
            )
        )

        act_rebuild = menu.addAction("🔨  Create Modified APK")
        act_rebuild.triggered.connect(
            lambda: self.app_context_menu_requested.emit(
                data["package"], data["name"],
                data["colors"], data["findings"],
            )
        )

        menu.addSeparator()

        act_copy_pkg = menu.addAction("📋  Copy package")
        act_copy_pkg.triggered.connect(
            lambda: QApplication.clipboard().setText(data["package"])
        )

        act_copy_name = menu.addAction("📋  Copy app name")
        act_copy_name.triggered.connect(
            lambda: QApplication.clipboard().setText(data["name"])
        )

        menu.exec(self.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------
    def filter(self, text: str, filter_type: str = "All") -> None:
        text = (text or "").lower()
        for item in self.all_items:
            data = item.data(Qt.ItemDataRole.UserRole)
            colors = data.get("colors", [])
            name = data.get("name", "").lower()
            package = data.get("package", "").lower()

            visible = True
            if text and text not in name and text not in package:
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

    # ------------------------------------------------------------------
    def clear_all(self) -> None:
        self.clear()
        self.all_items.clear()