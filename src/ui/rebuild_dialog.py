"""
Dialog tạo APK đã sửa — cho phép chọn nhiều patch với cấu hình riêng.
"""
from __future__ import annotations

import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QWidget, QCheckBox, QFrame, QMessageBox,
    QComboBox, QSpinBox, QGroupBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from .patch_config_dialog import PatchConfigDialog
from .preview_dialog import PreviewDialog


class RebuildDialog(QDialog):
    rebuild_requested = pyqtSignal(str)

    PATCHES = [
        {
            "name": "license",
            "label": "🔑 Gỡ xác minh giấy phép (License)",
            "configurable": True,
            "default_mode": "auto",
            "options": {
                "auto": "Chế độ tự động",
                "dex": "Chế độ tự động (dex)",
                "extreme": "Cực đoan (Bytecode Pattern)",
                "reverse": "Đảo ngược (Reverse Auto)",
            },
        },
        {
            "name": "ads",
            "label": "🚫 Xóa Google Ads",
            "configurable": True,
            "default_mode": "remove",
            "options": {
                "remove": "Xóa Activity quảng cáo",
                "offline": "Làm hỏng nhận quảng cáo (Offline)",
                "links": "Xoá liên kết quảng cáo",
                "full_offline": "Tạo ngoại tuyến đầy đủ",
            },
        },
        {
            "name": "iap",
            "label": "💳 Mô phỏng InApp Purchase",
            "configurable": True,
            "default_mode": "dex",
            "options": {
                "dex": "Tái cấu trúc Dex",
                "proxy": "Máy chủ Proxy",
                "aidl": "AIDL Proxy",
            },
        },
        {
            "name": "change_perms",
            "label": "⚙️ Thay đổi quyền (Permissions)",
            "configurable": False,
            "default_mode": None,
            "options": {},
        },
        {
            "name": "custom",
            "label": "📄 Custom Patch (.txt/.lpzip)",
            "configurable": False,
            "default_mode": None,
            "options": {},
        },
        {
            "name": "resign",
            "label": "✍️ Ký lại APK",
            "configurable": False,
            "default_mode": None,
            "options": {},
        },
    ]

    EXTRA_OPTIONS = [
        ("save_purchase", "💾 Lưu giao dịch IAP"),
        ("auto_repeat", "🔄 Tự động lặp lại IAP"),
        ("sig_disable", "🔓 Vô hiệu hóa self-signature"),
        ("sig_integrity", "🛡️ Bỏ kiểm tra integrity"),
        ("sig_fake_archive", "📦 Giả mạo archive"),
    ]

    def __init__(self, app_name: str, package: str = "", parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self.package = package
        self.patch_widgets: dict[str, dict] = {}
        self.extra_widgets: dict[str, QCheckBox] = {}

        self.setWindowTitle(f"Create Modified APK - {app_name}")
        # Size hợp lý, không stretch vô hạn
        self.resize(640, 700)
        self.setMinimumSize(560, 500)
        self.setMaximumHeight(900)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel(
            f"<b style='font-size:13px;'>"
            f"Chọn patch cho {self.app_name}</b>"
        )
        layout.addWidget(title)

        # Scroll area — chiếm phần lớn, nhưng không stretch dialog
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        content = QWidget()
        self.scroll_layout = QVBoxLayout(content)
        self.scroll_layout.setSpacing(6)
        self.scroll_layout.setContentsMargins(4, 4, 4, 4)

        for patch in self.PATCHES:
            self.scroll_layout.addWidget(self._create_patch_row(patch))

        self.scroll_layout.addSpacing(8)
        self.scroll_layout.addWidget(QLabel("<b>Tùy chọn bổ sung:</b>"))
        for key, label in self.EXTRA_OPTIONS:
            chk = QCheckBox(label)
            self.scroll_layout.addWidget(chk)
            self.extra_widgets[key] = chk

        # Advanced
        adv_group = QGroupBox("Tùy chọn nâng cao")
        adv_layout = QVBoxLayout(adv_group)

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("Loại chữ ký:"))
        self.key_combo = QComboBox()
        self.key_combo.addItems(
            ["testkey", "platform", "media", "shared"]
        )
        key_row.addWidget(self.key_combo)
        adv_layout.addLayout(key_row)

        pkg_row = QHBoxLayout()
        pkg_row.addWidget(QLabel("Forced Package ID (127=auto):"))
        self.pkg_spin = QSpinBox()
        self.pkg_spin.setRange(1, 127)
        self.pkg_spin.setValue(127)
        pkg_row.addWidget(self.pkg_spin)
        adv_layout.addLayout(pkg_row)

        self.scroll_layout.addWidget(adv_group)
        self.scroll_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # Bottom buttons — luôn ở dưới, không bị kéo
        btns = QHBoxLayout()
        preview = QPushButton("🔍 Xem trước")
        preview.clicked.connect(self._show_preview)
        btns.addWidget(preview)

        btns.addStretch()

        build = QPushButton("🛠 Xây dựng lại")
        build.setStyleSheet(
            "background-color:#238636; color:white; "
            "font-weight:bold; padding:8px 20px; border-radius:6px;"
        )
        build.clicked.connect(self._on_build)
        btns.addWidget(build)

        cancel = QPushButton("Hủy")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        layout.addLayout(btns)

    def _create_patch_row(self, patch: dict) -> QFrame:
        row = QFrame()
        row.setFrameShape(QFrame.Shape.StyledPanel)
        row.setStyleSheet(
            "QFrame { padding:4px; background:#161b22; "
            "border:1px solid #30363d; border-radius:6px; }"
        )
        rl = QHBoxLayout(row)
        rl.setContentsMargins(8, 6, 8, 6)

        chk = QCheckBox()
        rl.addWidget(chk)

        label = QLabel(patch["label"])
        label.setFont(QFont("Segoe UI", 10))
        rl.addWidget(label, 1)

        if patch["configurable"]:
            btn = QPushButton("⚙️")
            btn.setFixedSize(30, 30)
            btn.setToolTip("Cấu hình chế độ")
            btn.clicked.connect(
                lambda _=None, p=patch: self._open_config(p)
            )
            rl.addWidget(btn)

        self.patch_widgets[patch["name"]] = {
            "checkbox": chk,
            "mode": patch["default_mode"],
        }
        return row

    def _open_config(self, patch: dict) -> None:
        current = self.patch_widgets[patch["name"]]["mode"]
        dlg = PatchConfigDialog(
            patch["label"], patch["options"], current, self
        )
        if dlg.exec():
            self.patch_widgets[patch["name"]]["mode"] = dlg.get_mode()

    def _collect_selection(self) -> list[str]:
        selected: list[str] = []
        for patch in self.PATCHES:
            name = patch["name"]
            w = self.patch_widgets[name]
            if not w["checkbox"].isChecked():
                continue
            mode = w["mode"]
            if mode:
                selected.append(f"{name}:{mode}")
            else:
                selected.append(name)
        for key, chk in self.extra_widgets.items():
            if chk.isChecked():
                selected.append(key)
        return selected

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
        mode_string = ",".join(selected)
        self.rebuild_requested.emit(mode_string)
        self.accept()

    def get_key_type(self) -> str:
        return self.key_combo.currentText()

    def get_forced_package_id(self) -> int | None:
        v = self.pkg_spin.value()
        return None if v == 127 else v