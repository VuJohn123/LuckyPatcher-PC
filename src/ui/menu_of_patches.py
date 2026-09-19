"""
Menu of Patches — dialog trung tâm cho các hành động vá.

v2 (2026):
  - Action key chuẩn: change_perms (không dùng manage_permissions).
  - Hiển thị feature list có icon màu.
  - Disable button nếu finding tương ứng không tồn tại.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QPushButton, QLabel, QFrame, QHBoxLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class MenuOfPatchesDialog(QDialog):
    action_requested = pyqtSignal(str)

    def __init__(
        self,
        app_name: str,
        package: str,
        colors: list[str] | None = None,
        findings: list[dict] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.app_name = app_name
        self.package = package
        self.colors = colors or []
        self.findings = findings or []

        self.setWindowTitle(f"Menu of Patches - {app_name}")
        self.setMinimumSize(520, 620)

        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            self.resize(
                min(560, int(avail.width() * 0.45)),
                min(680, int(avail.height() * 0.85)),
            )

        self._init_ui()

    # ============================================================
    # UI
    # ============================================================
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Header
        title = QLabel(
            f"<b style='font-size:14px;'>{self.app_name}</b>"
        )
        title.setStyleSheet("color: #f0f6fc;")
        layout.addWidget(title)

        pkg = QLabel(f"Package: {self.package}")
        pkg.setStyleSheet("color:#8b949e; font-size:11px;")
        pkg.setWordWrap(True)
        layout.addWidget(pkg)

        # Detected features
        if self.findings:
            layout.addWidget(QLabel(
                "<i style='color:#8b949e;'>Phát hiện:</i>"
            ))
            for f in self.findings:
                desc = f.get("description", "")
                if not desc:
                    continue
                color = f.get("color") or "white"
                icon = {
                    "green": "🟢", "blue": "🔵", "yellow": "🟡",
                    "purple": "🟣", "orange": "🟠", "red": "🔴",
                }.get(color, "⚪")
                row = QLabel(f"  {icon}  {desc}")
                row.setStyleSheet(
                    "color: #c9d1d9; font-size: 11px;"
                )
                row.setWordWrap(True)
                layout.addWidget(row)

        layout.addWidget(self._separator())

        # Feature detection helpers
        has_license = self._has_finding("license")
        has_ads = self._has_finding("ads")
        has_iap = self._has_finding("iap")
        has_custom = self._has_finding("custom_patch")

        # === Primary actions ===
        self._add_button(
            layout, "🔨 Create Modified APK File",
            "open_rebuild",
        )

        self._add_button(
            layout, "🔑 Remove License Verification",
            "remove_license", enabled=has_license,
        )

        self._add_button(
            layout, "🚫 Remove Google Ads",
            "remove_ads", enabled=has_ads,
        )

        self._add_button(
            layout, "💳 IAP Emulation",
            "iap_emulation", enabled=has_iap,
        )

        self._add_button(
            layout, "📄 Custom Patch",
            "apply_custom_patch", enabled=has_custom,
        )

        self._add_button(
            layout, "⚙️ Change Permissions",
            "change_perms",   # ← key chuẩn
        )

        self._add_button(
            layout, "✍️ Resign APK",
            "resign",
        )

        layout.addWidget(self._separator())

        # === Other actions ===
        layout.addWidget(QLabel(
            "<i style='color:#8b949e;'>Khác:</i>"
        ))

        self._add_button(layout, "💾 Backup App", "backup")
        self._add_button(layout, "▶ Launch App", "launch")
        self._add_button(layout, "ℹ App Info", "info")

        layout.addStretch()

        # Close
        btns = QHBoxLayout()
        btns.addStretch()
        close = QPushButton("Đóng")
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        layout.addLayout(btns)

    def _separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#30363d; background:#30363d;")
        line.setFixedHeight(1)
        return line

    def _has_finding(self, ftype: str) -> bool:
        return any(
            f.get("type") == ftype for f in self.findings
        )

    def _add_button(
        self,
        layout: QVBoxLayout,
        label: str,
        action: str,
        enabled: bool = True,
    ) -> None:
        btn = QPushButton(label)
        btn.setEnabled(enabled)
        btn.setMinimumHeight(38)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 8px 14px;
                background-color: #161b22;
                color: #c9d1d9;
                border: 1px solid #30363d;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #21262d;
                border-color: #58a6ff;
                color: #f0f6fc;
            }
            QPushButton:disabled {
                color: #484f58;
                background-color: #0d1117;
            }
        """)
        btn.clicked.connect(
            lambda _=None, a=action: self._emit_and_close(a)
        )
        layout.addWidget(btn)

    def _emit_and_close(self, action: str) -> None:
        self.action_requested.emit(action)
        self.accept()