"""
APKDetailWidget — hiển thị thông tin chi tiết APK.

v4 (2026):
  - i18n integration: dùng core.i18n.t() cho label chính.
  - Row background color cho mỗi finding theo loại.
  - Packer warning box.
  - "Open Menu of Patches" button.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QGroupBox, QGridLayout, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from core.i18n import t


# ============================================================
# COLOR SCHEME
# ============================================================
_COLOR_MAP = {
    "green":  ("🟢 License", "#3fb950"),
    "yellow": ("🟡 Custom Patch", "#d29922"),
    "blue":   ("🔵 Ads", "#58a6ff"),
    "purple": ("🟣 System (Boot)", "#a371f7"),
    "orange": ("🟠 System App", "#db6d28"),
    "red":    ("🔴 Protected", "#f85149"),
    "white":  ("⚪ No special", "#8b949e"),
}

_ROW_BG = {
    "green":  "#0d2818",
    "blue":   "#0d1e3d",
    "yellow": "#2b1e0d",
    "purple": "#1e0d3d",
    "orange": "#2b1409",
    "red":    "#3d0d0d",
}

_ACTION_STYLE = {
    "green": (
        "background-color:#238636; color:#fff;"
        "border:1px solid #2ea043;"
    ),
    "blue": (
        "background-color:#1f6feb; color:#fff;"
        "border:1px solid #388bfd;"
    ),
    "yellow": (
        "background-color:#9e6a03; color:#fff;"
        "border:1px solid #bb8009;"
    ),
    "orange": (
        "background-color:#bd561d; color:#fff;"
        "border:1px solid #db6d28;"
    ),
    "default": (
        "background-color:#21262d; color:#c9d1d9;"
        "border:1px solid #30363d;"
    ),
}

# Derive action từ finding.type nếu finding.action trống
_TYPE_TO_ACTION = {
    "license":      "remove_license",
    "ads":          "remove_ads",
    "iap":          "iap_emulation",
    "custom_patch": "apply_custom_patch",
    "permissions":  "manage_permissions",
}


class APKDetailWidget(QWidget):
    patch_action_requested = pyqtSignal(str)
    rebuild_requested = pyqtSignal()
    menu_of_patches_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("apkDetailWidget")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(16, 16, 16, 16)
        self.content_layout.setSpacing(14)
        scroll.setWidget(self.content_widget)
        main_layout.addWidget(scroll)

    # ============================================================
    # PUBLIC
    # ============================================================
    def clear(self) -> None:
        while self.content_layout.count():
            child = self.content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def populate(self, analyzer_result: dict) -> None:
        self.clear()
        findings = analyzer_result.get("findings", [])
        summary = analyzer_result.get("summary", {})
        colors = analyzer_result.get("colors", ["white"])

        self._add_header(summary)
        self._add_primary_actions()
        self._add_color_bar(colors)
        self._add_packer_warning(findings)
        self._add_features(findings)
        self._add_quick_actions(findings)
        self.content_layout.addStretch()

    # ============================================================
    # HEADER
    # ============================================================
    def _add_header(self, summary: dict) -> None:
        header = QWidget()
        h = QHBoxLayout(header)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)

        icon = QLabel("📱")
        icon.setFont(QFont("Segoe UI", 36))
        icon.setFixedSize(64, 64)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            "background-color:#161b22; border:1px solid #30363d;"
            "border-radius:12px;"
        )
        h.addWidget(icon)

        info = QVBoxLayout()
        info.setSpacing(4)

        app_name = summary.get("app_name", "Unknown")
        name = QLabel()
        name.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        name.setStyleSheet("color: #f0f6fc;")
        name.setText(self._elide(app_name, 60))
        name.setToolTip(app_name)
        info.addWidget(name)

        package = summary.get("package", "N/A")
        pkg = QLabel()
        pkg.setStyleSheet("color: #8b949e; font-size: 12px;")
        pkg.setText(f"Package: {self._elide(package, 55)}")
        pkg.setToolTip(package)
        info.addWidget(pkg)

        ver = QLabel(
            f"Version: {summary.get('version', 'N/A')} | "
            f"Size: {self._format_size(summary.get('size', 0))}"
        )
        ver.setStyleSheet("color: #6e7681; font-size: 11px;")
        info.addWidget(ver)

        h.addLayout(info, 1)
        self.content_layout.addWidget(header)

    # ============================================================
    # PRIMARY ACTIONS
    # ============================================================
    def _add_primary_actions(self) -> None:
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        btn_rebuild = QPushButton(t("detail.rebuild_btn"))
        btn_rebuild.setStyleSheet(
            "background-color:#238636; color:white; font-weight:bold;"
            "padding:12px; font-size:13px; border-radius:6px;"
        )
        btn_rebuild.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_rebuild.clicked.connect(self.rebuild_requested.emit)
        rl.addWidget(btn_rebuild, 1)

        btn_menu = QPushButton(t("detail.menu_btn"))
        btn_menu.setStyleSheet(
            "background-color:#1f6feb; color:white; font-weight:bold;"
            "padding:12px; font-size:13px; border-radius:6px;"
        )
        btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_menu.clicked.connect(self.menu_of_patches_requested.emit)
        rl.addWidget(btn_menu, 1)

        self.content_layout.addWidget(row)

    # ============================================================
    # COLOR BAR
    # ============================================================
    def _add_color_bar(self, colors: list[str]) -> None:
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(12)

        for c in colors:
            text, clr = _COLOR_MAP.get(c, ("", "#8b949e"))
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"color: {clr}; font-weight: bold; font-size: 12px;"
            )
            lbl.setToolTip(c.capitalize())
            rl.addWidget(lbl)

        rl.addStretch()
        self.content_layout.addWidget(row)

    # ============================================================
    # PACKER WARNING
    # ============================================================
    def _add_packer_warning(self, findings: list[dict]) -> None:
        for f in findings:
            if f.get("type") == "packer":
                warn = QFrame()
                warn.setStyleSheet(
                    "background-color:#3d1c1c;"
                    "border:1px solid #f85149;"
                    "border-radius:6px;"
                )
                wl = QVBoxLayout(warn)
                wl.setContentsMargins(12, 10, 12, 10)

                title = QLabel(
                    f"<b style='color:#f85149;'>"
                    f"⚠️ {f.get('title', 'Packer detected')}</b>"
                )
                wl.addWidget(title)

                desc = QLabel(f.get("description", ""))
                desc.setStyleSheet(
                    "color: #c9d1d9; font-size: 11px;"
                )
                desc.setWordWrap(True)
                wl.addWidget(desc)

                details = f.get("details", [])
                if details:
                    det = QLabel("• " + "\n• ".join(details))
                    det.setStyleSheet(
                        "color: #8b949e; font-size: 10px;"
                    )
                    det.setWordWrap(True)
                    wl.addWidget(det)

                self.content_layout.addWidget(warn)
                return

    # ============================================================
    # FEATURES — with colored rows
    # ============================================================
    def _add_features(self, findings: list[dict]) -> None:
        if not findings:
            return

        group = QGroupBox(t("detail.features_title"))
        outer = QVBoxLayout(group)
        outer.setSpacing(6)
        outer.setContentsMargins(12, 20, 12, 12)

        for f in findings:
            row_widget = self._make_feature_row(f)
            outer.addWidget(row_widget)

        self.content_layout.addWidget(group)

    def _make_feature_row(self, finding: dict) -> QFrame:
        color = finding.get("color")
        bg = _ROW_BG.get(color, "#161b22")
        border = _COLOR_MAP.get(color, ("", "#30363d"))[1]

        row = QFrame()
        row.setStyleSheet(
            f"QFrame {{"
            f"  background-color: {bg};"
            f"  border: 1px solid #30363d;"
            f"  border-left: 3px solid {border};"
            f"  border-radius: 4px;"
            f"}}"
        )
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(10)

        icon_txt = {
            "green": "🟢", "blue": "🔵", "yellow": "🟡",
            "purple": "🟣", "orange": "🟠", "red": "🔴",
        }.get(color, "⚪")
        icon = QLabel(icon_txt)
        icon.setFixedWidth(22)
        icon.setStyleSheet("background: transparent;")
        h.addWidget(icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)

        title = QLabel(finding.get("title", ""))
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title.setStyleSheet(
            "color: #f0f6fc; background: transparent;"
        )
        title.setWordWrap(True)
        text_col.addWidget(title)

        desc_text = finding.get("description", "")
        if desc_text:
            desc = QLabel(self._elide(desc_text, 130))
            desc.setStyleSheet(
                "color: #8b949e; font-size: 11px; background: transparent;"
            )
            desc.setWordWrap(True)
            desc.setToolTip(desc_text)
            text_col.addWidget(desc)

        h.addLayout(text_col, 1)
        return row

    # ============================================================
    # QUICK ACTIONS — robust + i18n
    # ============================================================
    def _add_quick_actions(self, findings: list[dict]) -> None:
        action_items = []
        seen_actions: set[str] = set()

        for f in findings:
            action = self._derive_action(f)
            if not action or action in seen_actions:
                continue
            seen_actions.add(action)
            action_items.append(action)

        if not action_items:
            return

        group = QGroupBox(t("detail.quick_actions"))
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 20, 12, 12)

        for action in action_items:
            btn = self._create_action_button(action)
            if btn is None:
                continue
            wrap = QWidget()
            wl = QHBoxLayout(wrap)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.addWidget(btn)
            wl.addStretch()
            layout.addWidget(wrap)

        self.content_layout.addWidget(group)

    def _derive_action(self, finding: dict) -> str | None:
        action = finding.get("action")
        if action:
            return action
        ftype = finding.get("type", "")
        return _TYPE_TO_ACTION.get(ftype)

    def _create_action_button(
        self, action: str,
    ) -> QPushButton | None:
        # action_key → (i18n_key, style_key)
        action_map = {
            "remove_license": (
                "detail.action_remove_license", "green",
            ),
            "remove_ads": (
                "detail.action_remove_ads", "blue",
            ),
            "iap_emulation": (
                "detail.action_iap", "orange",
            ),
            "apply_custom_patch": (
                "detail.action_custom", "yellow",
            ),
            "manage_permissions": (
                "detail.action_perms", "default",
            ),
            "change_perms": (
                "detail.action_perms", "default",
            ),
            "resign": (
                "detail.action_resign", "default",
            ),
        }
        info = action_map.get(action)
        if not info:
            return None
        i18n_key, style_key = info
        label = t(i18n_key)

        btn = QPushButton(label)
        style = _ACTION_STYLE.get(
            style_key, _ACTION_STYLE["default"]
        )
        btn.setStyleSheet(
            f"QPushButton {{ {style}"
            "  border-radius:6px; padding:10px 16px;"
            "  font-weight:bold; text-align:left;"
            "}"
            "QPushButton:hover { border-color:#58a6ff; }"
        )
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(38)
        btn.clicked.connect(
            lambda _=None, a=action:
            self.patch_action_requested.emit(a)
        )
        return btn

    # ============================================================
    # HELPERS
    # ============================================================
    def _elide(self, text: str, max_chars: int) -> str:
        if not text:
            return ""
        if len(text) <= max_chars:
            return text
        return text[:max_chars - 3] + "..."

    def _format_size(self, size_bytes: int) -> str:
        if not size_bytes:
            return "0 B"
        sizes = ["B", "KB", "MB", "GB"]
        i = 0
        size = float(size_bytes)
        while size >= 1024 and i < len(sizes) - 1:
            size /= 1024.0
            i += 1
        return f"{size:.1f} {sizes[i]}"