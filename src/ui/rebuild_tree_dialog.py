"""
Rebuild dialog dạng cây — tree cho từng patch, checkbox để chọn.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTreeWidget, QTreeWidgetItem, QCheckBox, QWidget,
    QGroupBox, QComboBox, QSpinBox, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from .patch_config_dialog import PatchConfigDialog
from .preview_dialog import PreviewDialog


class RebuildTreeDialog(QDialog):
    rebuild_requested = pyqtSignal(str)

    def __init__(self, app_name: str, package: str = "",
                 preselected_action: str | None = None, parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self.package = package
        self.preselected = preselected_action

        self.mode_map: dict[str, str | None] = {}
        self.chk_map: dict[str, QCheckBox] = {}

        self.setWindowTitle(f"Rebuild (Tree) - {app_name}")
        self.setMinimumSize(620, 760)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"<b>{self.app_name}</b>"))
        layout.addWidget(QLabel(f"Package: {self.package}"))

        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(18)
        self.tree.setAnimated(True)
        self._build_tree()
        layout.addWidget(self.tree, 1)

        # Advanced
        adv = QGroupBox("Tùy chọn nâng cao")
        adv_layout = QVBoxLayout(adv)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Loại chữ ký:"))
        self.key_combo = QComboBox()
        self.key_combo.addItems(["testkey", "platform", "media", "shared"])
        row1.addWidget(self.key_combo)
        adv_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Forced Package ID:"))
        self.pkg_spin = QSpinBox()
        self.pkg_spin.setRange(1, 127)
        self.pkg_spin.setValue(127)
        row2.addWidget(self.pkg_spin)
        adv_layout.addLayout(row2)

        layout.addWidget(adv)

        # Bottom buttons
        btns = QHBoxLayout()
        preview = QPushButton("🔍 Xem trước")
        preview.clicked.connect(self._show_preview)
        btns.addWidget(preview)

        btns.addStretch()

        build = QPushButton("🛠 Xây dựng lại")
        build.setStyleSheet("background-color:#238636; color:white; font-weight:bold; padding:8px 20px;")
        build.clicked.connect(self._on_build)
        btns.addWidget(build)

        cancel = QPushButton("Hủy")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        layout.addLayout(btns)

    def _build_tree(self) -> None:
        root = QTreeWidgetItem(self.tree, ["📦 Chọn patch"])
        root.setExpanded(True)

        # License
        lic = QTreeWidgetItem(root, ["🔑 License"])
        lic.setExpanded(True)
        self._add_leaf(lic, "Chế độ tự động", "license", "auto")
        self._add_leaf(lic, "Chế độ tự động (dex)", "license", "dex")
        self._add_leaf(lic, "Đảo ngược", "license", "reverse")
        self._add_leaf(lic, "Cực đoan", "license", "extreme")
        self._add_leaf(lic, "Amazon Market", "license", "amazon")
        self._add_leaf(lic, "Samsung Apps", "license", "samsung")

        # Ads
        ads = QTreeWidgetItem(root, ["🚫 Ads"])
        ads.setExpanded(True)
        self._add_leaf(ads, "Xóa Activity", "ads", "remove")
        self._add_leaf(ads, "Offline mode", "ads", "offline")
        self._add_leaf(ads, "Xóa URL", "ads", "links")
        self._add_leaf(ads, "Full offline", "ads", "full_offline")

        # IAP
        iap = QTreeWidgetItem(root, ["💳 IAP"])
        iap.setExpanded(True)
        self._add_leaf(iap, "Reassembly Dex", "iap", "dex")
        self._add_leaf(iap, "Proxy Server", "iap", "proxy")
        self._add_leaf(iap, "AIDL Proxy", "aidl_proxy", None)

        # Others
        misc = QTreeWidgetItem(root, ["⚙️ Khác"])
        misc.setExpanded(True)
        self._add_leaf(misc, "Đổi quyền", "change_perms", None)
        self._add_leaf(misc, "Ký lại APK", "resign", None)
        self._add_leaf(misc, "Custom Patch", "custom", None)

    def _add_leaf(self, parent: QTreeWidgetItem, text: str,
                  name: str, mode: str | None) -> None:
        item = QTreeWidgetItem(parent, [text])
        chk = QCheckBox()
        chk.setChecked(False)
        self.tree.setItemWidget(item, 0, chk)
        key = f"{name}:{mode}" if mode else name
        self.chk_map[key] = chk
        self.mode_map[key] = mode

    def _collect_selection(self) -> list[str]:
        out = []
        for key, chk in self.chk_map.items():
            if chk.isChecked():
                out.append(key)
        return out

    def _show_preview(self) -> None:
        selected = self._collect_selection()
        if not selected:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn ít nhất 1 patch")
            return
        items = []
        for s in selected:
            if ":" in s:
                name, mode = s.split(":", 1)
                items.append({"label": name, "mode": mode})
            else:
                items.append({"label": s})
        dlg = PreviewDialog(items, self)
        if dlg.exec():
            self._on_build()

    def _on_build(self) -> None:
        selected = self._collect_selection()
        if not selected:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn ít nhất 1 patch")
            return
        self.rebuild_requested.emit(",".join(selected))
        self.accept()

    def get_key_type(self) -> str:
        return self.key_combo.currentText()

    def get_forced_package_id(self) -> int | None:
        v = self.pkg_spin.value()
        return None if v == 127 else v