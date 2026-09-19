"""
Menu of Patches dạng cây — mô phỏng Lucky Patcher.
Double-click để kích hoạt action.

v2 (2026):
  - Action key chuẩn cho change_perms.
  - Preselect finding action nếu có (vd: license → highlight License submenu).
  - Sync signals với MenuOfPatchesDialog.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QLabel, QPushButton, QHBoxLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal


_COLOR_LABELS = {
    "green": "🟢 License",
    "blue": "🔵 Ads",
    "yellow": "🟡 Custom patch",
    "purple": "🟣 System (boot)",
    "orange": "🟠 System",
    "red": "🔴 Protected",
    "white": "⚪ Clean",
}


class MenuOfPatchesTreeDialog(QDialog):
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

        self.setWindowTitle(
            f"Menu of Patches (Tree) - {app_name}"
        )

        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            self.resize(
                min(600, int(avail.width() * 0.5)),
                min(720, int(avail.height() * 0.85)),
            )
            self.setMinimumSize(520, 400)
        else:
            self.resize(600, 720)

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

        # Color badges
        if self.colors:
            badges = "  |  ".join(
                _COLOR_LABELS.get(c, c) for c in self.colors
            )
            badge = QLabel(badges)
            badge.setStyleSheet(
                "color:#58a6ff; font-size:11px;"
            )
            badge.setWordWrap(True)
            layout.addWidget(badge)

        # Hint
        hint = QLabel(
            "<i style='color:#6e7681; font-size:10px;'>"
            "Double-click để chạy action</i>"
        )
        layout.addWidget(hint)

        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(20)
        self.tree.setAnimated(True)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self._build_tree()
        layout.addWidget(self.tree, 1)

        # Close button
        btns = QHBoxLayout()
        btns.addStretch()
        close = QPushButton("Đóng")
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        layout.addLayout(btns)

    # ============================================================
    # TREE
    # ============================================================
    def _build_tree(self) -> None:
        root = QTreeWidgetItem(self.tree, ["📋 Menu of Patches"])
        root.setExpanded(True)

        # === Create Modified APK section ===
        rebuild = QTreeWidgetItem(
            root, ["🔨 Create Modified APK File"]
        )
        rebuild.setExpanded(True)

        self._add_leaf(
            rebuild, "📦 Multi-patch (chọn nhiều)",
            "open_rebuild",
        )

        # License submenu
        lic = QTreeWidgetItem(
            rebuild, ["🔑 APK không có Giấy phép Xác minh"]
        )
        lic.setExpanded(self._has_finding("license"))
        self._add_leaf(lic, "Chế độ tự động", "license:auto")
        self._add_leaf(lic, "Chế độ tự động (dex)", "license:dex")
        self._add_leaf(lic, "Chế độ đảo ngược", "license:reverse")
        self._add_leaf(lic, "Chế độ cực đoan", "license:extreme")
        self._add_leaf(lic, "Amazon Market", "license:amazon")
        self._add_leaf(lic, "Samsung Apps", "license:samsung")

        # Ads submenu
        ads = QTreeWidgetItem(
            rebuild, ["🚫 APK không có Google Ads"]
        )
        ads.setExpanded(self._has_finding("ads"))
        self._add_leaf(ads, "Xóa activity quảng cáo", "ads:remove")
        self._add_leaf(ads, "Offline mode", "ads:offline")
        self._add_leaf(ads, "Xóa URL quảng cáo", "ads:links")
        self._add_leaf(ads, "Full offline", "ads:full_offline")

        # IAP submenu
        iap = QTreeWidgetItem(
            rebuild, ["💳 Giả lập InApp & LVL"]
        )
        iap.setExpanded(self._has_finding("iap"))
        self._add_leaf(iap, "Reassembly Dex", "iap:dex")
        self._add_leaf(iap, "Proxy Server", "iap:proxy")
        self._add_leaf(iap, "AIDL Proxy", "aidl_proxy")

        # Misc
        misc = QTreeWidgetItem(rebuild, ["⚙️ Khác"])
        misc.setExpanded(True)
        self._add_leaf(misc, "Đổi quyền (Permissions)",
                       "change_perms")
        self._add_leaf(misc, "Ký lại APK (Resign)", "resign")
        self._add_leaf(misc, "Custom Patch", "custom")
        self._add_leaf(misc, "Sig Disable", "sig_disable")
        self._add_leaf(misc, "Sig Integrity", "sig_integrity")
        self._add_leaf(misc, "Sig Fake Archive", "sig_fake_archive")

        # === Direct actions ===
        layout = QTreeWidgetItem(root, ["🎯 Hành động trực tiếp"])
        layout.setExpanded(True)

        self._add_leaf(
            layout, "🔑 Remove License Verification",
            "remove_license",
        )
        self._add_leaf(
            layout, "🚫 Remove Google Ads",
            "remove_ads",
        )
        self._add_leaf(
            layout, "💳 IAP Emulation",
            "iap_emulation",
        )
        self._add_leaf(
            layout, "📄 Apply Custom Patch",
            "apply_custom_patch",
        )
        self._add_leaf(
            layout, "⚙️ Change Permissions",
            "change_perms",
        )

        # === Other ===
        other = QTreeWidgetItem(root, ["ℹ️ Khác"])
        other.setExpanded(True)
        self._add_leaf(other, "💾 Backup App", "backup")
        self._add_leaf(other, "▶ Launch App", "launch")
        self._add_leaf(other, "ℹ App Info", "info")

    def _add_leaf(
        self,
        parent: QTreeWidgetItem,
        text: str,
        action: str,
    ) -> None:
        item = QTreeWidgetItem(parent, [text])
        item.setData(0, Qt.ItemDataRole.UserRole, action)
        item.setToolTip(0, f"Action: {action}")

    def _has_finding(self, ftype: str) -> bool:
        return any(
            f.get("type") == ftype for f in self.findings
        )

    # ============================================================
    # EVENT
    # ============================================================
    def _on_double_click(
        self, item: QTreeWidgetItem, _col: int,
    ) -> None:
        action = item.data(0, Qt.ItemDataRole.UserRole)
        if not action:
            return
        self.action_requested.emit(action)
        self.accept()