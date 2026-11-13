"""Dialog chọn chế độ Ads removal."""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from core.i18n import t


class AdsPatchDialog(QDialog):
    patch_requested = pyqtSignal(str)

    OPTIONS = [
        ("remove", "dialog.ads_patch.opt_remove"),
        ("offline", "dialog.ads_patch.opt_offline"),
        ("links", "dialog.ads_patch.opt_links"),
        ("full_offline", "dialog.ads_patch.opt_full_offline"),
    ]

    def __init__(self, app_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("dialog.ads_patch.title", name=app_name))
        self.setMinimumSize(450, 320)
        self._selected = "remove"
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(t("dialog.ads_patch.choose_mode")))

        self._group = QButtonGroup(self)
        for key, label_key in self.OPTIONS:
            rb = QRadioButton(t(label_key))
            rb.setChecked(key == self._selected)
            rb.toggled.connect(lambda on, k=key: self._select(k) if on else None)
            self._group.addButton(rb)
            layout.addWidget(rb)

        btns = QHBoxLayout()
        ok = QPushButton(t("dialog.ads_patch.btn_apply"))
        ok.clicked.connect(self._apply)
        cancel = QPushButton(t("dialog.ads_patch.btn_cancel"))
        cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)

    def _select(self, key: str) -> None:
        self._selected = key

    def _apply(self) -> None:
        self.patch_requested.emit(f"ads:{self._selected}")
        self.accept()
