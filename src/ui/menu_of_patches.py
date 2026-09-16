"""Menu of Patches — dialog trung tâm cho các hành động vá."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QPushButton, QLabel, QFrame, QHBoxLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal


class MenuOfPatchesDialog(QDialog):
    action_requested = pyqtSignal(str)

    def __init__(self, app_name: str, package: str,
                 colors: list[str] | None = None,
                 findings: list[dict] | None = None,
                 parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self.package = package
        self.colors = colors or []
        self.findings = findings or []

        self.setWindowTitle(f"Menu of Patches - {app_name}")
        self.setMinimumSize(480, 520)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Header
        title = QLabel(f"<b style='font-size:14px;'>{self.app_name}</b>")
        layout.addWidget(title)

        pkg = QLabel(f"Package: {self.package}")
        pkg.setStyleSheet("color:#8b949e; font-size:11px;")
        pkg.setWordWrap(True)
        layout.addWidget(pkg)

        # Detected features
        if self.findings:
            layout.addWidget(QLabel("<i>Phát hiện:</i>"))
            for f in self.findings:
                desc = f.get("description", "")
                if desc:
                    layout.addWidget(QLabel(f"  • {desc}"))

        layout.addWidget(self._separator())

        # Main actions
        rebuild = QPushButton("🔨 Create Modified APK File")
        rebuild.clicked.connect(lambda: self._emit_and_close("open_rebuild"))
        layout.addWidget(rebuild)

        license_btn = QPushButton("🔑 Remove License Verification")
        has_license = any(f.get("type") == "license" for f in self.findings)
        license_btn.setEnabled(has_license)
        license_btn.clicked.connect(lambda: self._emit_and_close("remove_license"))
        layout.addWidget(license_btn)

        ads_btn = QPushButton("🚫 Remove Google Ads")
        has_ads = any(f.get("type") == "ads" for f in self.findings)
        ads_btn.setEnabled(has_ads)
        ads_btn.clicked.connect(lambda: self._emit_and_close("remove_ads"))
        layout.addWidget(ads_btn)

        custom_btn = QPushButton("📄 Custom Patch")
        custom_btn.clicked.connect(lambda: self._emit_and_close("apply_custom_patch"))
        layout.addWidget(custom_btn)

        perms_btn = QPushButton("⚙️ Change Permissions")
        perms_btn.clicked.connect(lambda: self._emit_and_close("manage_permissions"))
        layout.addWidget(perms_btn)

        layout.addWidget(self._separator())

        # Other actions
        other = QLabel("<i>Khác:</i>")
        layout.addWidget(other)

        backup_btn = QPushButton("💾 Backup App")
        backup_btn.clicked.connect(lambda: self._emit_and_close("backup"))
        layout.addWidget(backup_btn)

        launch_btn = QPushButton("▶ Launch App")
        launch_btn.clicked.connect(lambda: self._emit_and_close("launch"))
        layout.addWidget(launch_btn)

        info_btn = QPushButton("ℹ App Info")
        info_btn.clicked.connect(lambda: self._emit_and_close("info"))
        layout.addWidget(info_btn)

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
        line.setStyleSheet("color:#30363d;")
        return line

    def _emit_and_close(self, action: str) -> None:
        self.action_requested.emit(action)
        self.accept()