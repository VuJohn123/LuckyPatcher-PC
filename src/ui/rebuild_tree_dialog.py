"""
Rebuild dialog dạng cây — tree cho từng patch, checkbox để chọn.

v3 (2026):
  - Fix: summary label tạo TRƯỚC _build_tree.
  - Fix: _update_summary method được định nghĩa.
  - Signal rebuild_requested(str) — controller intercept.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTreeWidget, QTreeWidgetItem, QGroupBox, QComboBox, QSpinBox,
    QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from .preview_dialog import PreviewDialog


class RebuildTreeDialog(QDialog):
    rebuild_requested = pyqtSignal(str)

    TREE_STRUCTURE = [
        ("🔑 License", [
            ("Chế độ tự động", "license", "auto"),
            ("Chế độ tự động (dex)", "license", "dex"),
            ("Đảo ngược", "license", "reverse"),
            ("Cực đoan", "license", "extreme"),
            ("Amazon Market", "license", "amazon"),
            ("Samsung Apps", "license", "samsung"),
        ]),
        ("🚫 Ads", [
            ("Xóa Activity", "ads", "remove"),
            ("Offline mode", "ads", "offline"),
            ("Xóa URL", "ads", "links"),
            ("Full offline", "ads", "full_offline"),
        ]),
        ("💳 IAP", [
            ("Reassembly Dex", "iap", "dex"),
            ("Proxy Server", "iap", "proxy"),
            ("AIDL Proxy", "aidl_proxy", None),
        ]),
        ("⚙️ Khác", [
            ("Đổi quyền", "change_perms", None),
            ("Ký lại APK", "resign", None),
            ("Custom Patch", "custom", None),
            ("Sig Disable", "sig_disable", None),
            ("Sig Integrity", "sig_integrity", None),
        ]),
    ]

    def __init__(
        self,
        app_name: str,
        package: str = "",
        preselected_action: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.app_name = app_name
        self.package = package
        self.preselected = preselected_action
        self.item_map: dict[str, QTreeWidgetItem] = {}

        # Summary label reference (khởi tạo None — set trong _init_ui)
        self.summary_lbl: QLabel | None = None

        self.setWindowTitle(f"Rebuild (Tree) - {app_name}")

        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            w = min(640, int(avail.width() * 0.5))
            h = min(720, int(avail.height() * 0.85))
            self.resize(w, h)
            self.setMinimumSize(520, 400)
        else:
            self.resize(640, 720)

        self._init_ui()
        if preselected_action:
            self._preselect(preselected_action)

    # ============================================================
    # UI
    # ============================================================
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(QLabel(f"<b>{self.app_name}</b>"))
        pkg = QLabel(f"Package: {self.package}")
        pkg.setStyleSheet("color:#8b949e; font-size:11px;")
        pkg.setWordWrap(True)
        layout.addWidget(pkg)

        # === Tree ===
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(18)
        self.tree.setAnimated(True)
        self.tree.itemChanged.connect(self._on_item_changed)

        # === Summary label TRƯỚC _build_tree ===
        self.summary_lbl = QLabel("Đã chọn: 0 patch")
        self.summary_lbl.setStyleSheet(
            "color:#58a6ff; font-size:11px; font-weight:bold;"
        )

        # Build tree SAU khi có summary_lbl
        self._build_tree()
        layout.addWidget(self.tree, 1)

        # Add summary label to layout
        layout.addWidget(self.summary_lbl)

        # Advanced
        adv = QGroupBox("Tùy chọn nâng cao")
        adv_layout = QVBoxLayout(adv)
        adv_layout.setSpacing(6)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Loại chữ ký:"))
        self.key_combo = QComboBox()
        self.key_combo.addItems(
            ["testkey", "platform", "media", "shared"]
        )
        row1.addWidget(self.key_combo)
        row1.addStretch()
        adv_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Forced Package ID (127=auto):"))
        self.pkg_spin = QSpinBox()
        self.pkg_spin.setRange(1, 127)
        self.pkg_spin.setValue(127)
        row2.addWidget(self.pkg_spin)
        row2.addStretch()
        adv_layout.addLayout(row2)

        layout.addWidget(adv)

        # Buttons
        btns = QHBoxLayout()
        preview = QPushButton("🔍 Xem trước")
        preview.clicked.connect(self._show_preview)
        btns.addWidget(preview)

        select_all = QPushButton("✔️ Chọn tất cả")
        select_all.clicked.connect(self._select_all)
        btns.addWidget(select_all)

        deselect = QPushButton("✖️ Bỏ chọn")
        deselect.clicked.connect(self._deselect_all)
        btns.addWidget(deselect)

        btns.addStretch()

        build = QPushButton("🛠 Xây dựng lại")
        build.setStyleSheet(
            "background-color:#238636; color:white; font-weight:bold;"
            " padding:8px 20px; border-radius:6px;"
        )
        build.clicked.connect(self._on_build)
        btns.addWidget(build)

        cancel = QPushButton("Hủy")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        layout.addLayout(btns)

    # ============================================================
    # TREE BUILD
    # ============================================================
    def _build_tree(self) -> None:
        self.tree.blockSignals(True)

        root = QTreeWidgetItem(self.tree, ["📦 Chọn patch"])
        root.setExpanded(True)
        root.setFlags(
            root.flags() & ~Qt.ItemFlag.ItemIsUserCheckable
        )

        for group_label, leaves in self.TREE_STRUCTURE:
            grp = QTreeWidgetItem(root, [group_label])
            grp.setExpanded(True)
            grp.setFlags(
                grp.flags() | Qt.ItemFlag.ItemIsAutoTristate
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            grp.setCheckState(0, Qt.CheckState.Unchecked)

            for leaf_label, name, mode in leaves:
                self._add_leaf(grp, leaf_label, name, mode)

        self.tree.blockSignals(False)
        self._update_summary()   # ← giờ an toàn vì summary_lbl đã có

    def _add_leaf(
        self,
        parent: QTreeWidgetItem,
        text: str,
        name: str,
        mode: str | None,
    ) -> None:
        item = QTreeWidgetItem(parent, [text])
        item.setFlags(
            item.flags() | Qt.ItemFlag.ItemIsUserCheckable
        )
        item.setCheckState(0, Qt.CheckState.Unchecked)
        key = f"{name}:{mode}" if mode else name
        self.item_map[key] = item

    # ============================================================
    # SUMMARY — giờ được định nghĩa
    # ============================================================
    def _update_summary(self) -> None:
        """Cập nhật label đếm số patch đã chọn."""
        if self.summary_lbl is None:
            return
        n = len(self._collect_selection())
        self.summary_lbl.setText(f"Đã chọn: {n} patch")

    # ============================================================
    # PRESELECT / SELECTION
    # ============================================================
    def _preselect(self, action: str) -> None:
        for key, item in self.item_map.items():
            if key == action or key.startswith(action + ":"):
                item.setCheckState(0, Qt.CheckState.Checked)

    def _select_all(self) -> None:
        for item in self.item_map.values():
            item.setCheckState(0, Qt.CheckState.Checked)

    def _deselect_all(self) -> None:
        for item in self.item_map.values():
            item.setCheckState(0, Qt.CheckState.Unchecked)

    def _collect_selection(self) -> list[str]:
        return [
            key for key, item in self.item_map.items()
            if item.checkState(0) == Qt.CheckState.Checked
        ]

    def _on_item_changed(self, _item, _col) -> None:
        self._update_summary()

    # ============================================================
    # ACTIONS
    # ============================================================
    def _show_preview(self) -> None:
        selected = self._collect_selection()
        if not selected:
            QMessageBox.warning(
                self, "Chưa chọn", "Vui lòng chọn ít nhất 1 patch"
            )
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
            QMessageBox.warning(
                self, "Chưa chọn", "Vui lòng chọn ít nhất 1 patch"
            )
            return
        self.rebuild_requested.emit(",".join(selected))
        self.accept()

    # ============================================================
    # PUBLIC
    # ============================================================
    def get_key_type(self) -> str:
        return self.key_combo.currentText()

    def get_forced_package_id(self) -> int | None:
        v = self.pkg_spin.value()
        return None if v == 127 else v