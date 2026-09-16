"""
Menu of Patches dạng cây — mô phỏng Lucky Patcher.
Mỗi mục là 1 hành động; double-click để kích hoạt.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QLabel, QPushButton, QHBoxLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class MenuOfPatchesTreeDialog(QDialog):
    action_requested = pyqtSignal(str, str)  # (category, action)

    # category: "direct" | "open_rebuild"
    def __init__(self, app_name: str, package: str,
                 colors: list[str] | None = None,
                 findings: list[dict] | None = None,
                 parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self.package = package
        self.colors = colors or []
        self.findings = findings or []

        self.setWindowTitle(f"Menu of Patches (Tree) - {app_name}")
        self.setMinimumSize(560, 680)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel(f"<b style='font-size:14px;'>{self.app_name}</b>")
        layout.addWidget(title)

        pkg = QLabel(f"Package: {self.package}")
        pkg.setStyleSheet("color:#8b949e; font-size:11px;")
        pkg.setWordWrap(True)
        layout.addWidget(pkg)

        color_names = {
            "green": "🟢 License",
            "blue": "🔵 Ads",
            "yellow": "🟡 Custom patch",
            "purple": "🟣 System (boot)",
            "orange": "🟠 System",
            "red": "🔴 Protected",
        }
        if self.colors:
            badges = " | ".join(color_names.get(c, c) for c in self.colors)
            badge = QLabel(badges)
            badge.setStyleSheet("color:#58a6ff; font-size:11px;")
            layout.addWidget(badge)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(20)
        self.tree.setAnimated(True)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self._build_tree()
        layout.addWidget(self.tree)

        btns = QHBoxLayout()
        btns.addStretch()
        close = QPushButton("Đóng")
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        layout.addLayout(btns)

    def _build_tree(self) -> None:
        root = QTreeWidgetItem(self.tree, ["📋 Menu of Patches"])
        root.setExpanded(True)

        # ============ Create Modified APK ============
        rebuild_root = QTreeWidgetItem(root, ["🔨 Create Modified APK File"])
        rebuild_root.setExpanded(True)

        multi = QTreeWidgetItem(rebuild_root, ["📦 Multi-patch (chọn nhiều)"])
        multi.setData(0, Qt.ItemDataRole.UserRole, ("open_rebuild", "multi_patch"))

        # License submenu
        lic_parent = QTreeWidgetItem(rebuild_root, ["🔑 APK không có Giấy phép Xác minh"])
        self._add_leaf(lic_parent, "Chế độ tự động", "open_rebuild", "license:auto")
        self._add_leaf(lic_parent, "Chế độ tự động (dex)", "open_rebuild", "license:dex")
        self._add_leaf(lic_parent, "Chế độ đảo ngược", "open_rebuild", "license:reverse")
        self._add_leaf(lic_parent, "Chế độ cực đoan", "open_rebuild", "license:extreme")
        self._add_leaf(lic_parent, "Amazon Market", "open_rebuild", "license:amazon")
        self._add_leaf(lic_parent, "Samsung Apps", "open_rebuild", "license:samsung")

        # Ads submenu
        ads_parent = QTreeWidgetItem(rebuild_root, ["🚫 APK không có Google Ads"])
        self._add_leaf(ads_parent, "Xóa activity quảng cáo", "open_rebuild", "ads:remove")
        self._add_leaf(ads_parent, "Offline mode", "open_rebuild", "ads:offline")
        self._add_leaf(ads_parent, "Xóa URL quảng cáo", "open_rebuild", "ads:links")
        self._add_leaf(ads_parent, "Full offline", "open_rebuild", "ads:full_offline")

        # IAP submenu
        iap_parent = QTreeWidgetItem(rebuild_root, ["💳 Giả lập InApp & LVL"])
        self._add_leaf(iap_parent, "Reassembly Dex", "open_rebuild", "iap:dex")
        self._add_leaf(iap_parent, "Proxy Server", "open_rebuild", "iap:proxy")
        self._add_leaf(iap_parent, "AIDL Proxy", "open_rebuild", "aidl_proxy")

        # Others
        self._add_leaf(rebuild_root, "⚙️ Đổi quyền",
                       "open_rebuild", "change_perms")
        self._add_leaf(rebuild_root, "✍️ Ký lại APK",
                       "open_rebuild", "resign")

        # ============ Direct actions ============
        self._add_leaf(root, "🔑 Remove License Verification",
                       "direct", "remove_license")
        self._add_leaf(root, "🚫 Remove Google Ads",
                       "direct", "remove_ads")
        self._add_leaf(root, "📄 Apply Custom Patch",
                       "direct", "apply_custom_patch")
        self._add_leaf(root, "⚙️ Change Permissions",
                       "direct", "change_perms")
        self._add_leaf(root, "💾 Backup App",
                       "direct", "backup_app")
        self._add_leaf(root, "▶ Launch App",
                       "direct", "launch")
        self._add_leaf(root, "ℹ App Info",
                       "direct", "info")

    def _add_leaf(self, parent: QTreeWidgetItem, text: str,
                  category: str, action: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent, [text])
        item.setData(0, Qt.ItemDataRole.UserRole, (category, action))
        return item

    def _on_double_click(self, item: QTreeWidgetItem, _col: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        category, action = data
        self.action_requested.emit(category, action)
        self.accept()