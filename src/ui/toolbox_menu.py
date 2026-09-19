"""
Toolbox menu — patch hệ thống + công cụ bổ trợ.

v2 (2026):
  - Wire to controller cho các action cần backend.
  - Menu signal handlers có try/except.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QMenu, QInputDialog, QMessageBox
from PyQt6.QtCore import pyqtSignal


class ToolboxMenu(QMenu):
    patch_requested = pyqtSignal(str, dict)
    clone_requested = pyqtSignal()
    iap_manager_requested = pyqtSignal()
    download_patch_requested = pyqtSignal()
    system_tool_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("🧰 Toolbox", parent)
        self._build()

    def _build(self) -> None:
        # Patch to Android
        android = self.addMenu("🔧 Patch to Android")
        self.act_sig_true = android.addAction(
            "Signature Verification always True"
        )
        self.act_sig_true.setCheckable(True)

        self.act_disable_apk_sig = android.addAction(
            "Disable .apk Signature Verification"
        )
        self.act_disable_apk_sig.setCheckable(True)

        self.act_disable_zip_sig = android.addAction(
            "Disable Zip Signature Verification"
        )
        self.act_disable_zip_sig.setCheckable(True)

        android.addSeparator()
        android.addAction(
            "▶ Apply Selected Patches", self._apply_system_patches
        )
        android.addAction(
            "✔ Run Test For Patch", self._run_test
        )

        self.addSeparator()

        self.addAction(
            "📦 Install Modded Google Play Store",
            self._install_modded_playstore,
        )
        self.addAction(
            "🔓 Force set root check", self._force_root_check
        )

        # Xposed
        xposed = self.addMenu("🧩 Xposed Settings")
        xposed.addAction(
            "Support IAP & LVL Emulation",
            lambda: self.system_tool_requested.emit("xposed_iap"),
        )
        xposed.addAction(
            "Enable Xposed Module",
            lambda: self.system_tool_requested.emit("xposed_enable"),
        )

        self.addSeparator()

        # Batch
        batch = self.addMenu("📚 Batch Operations")
        batch.addAction(
            "💾 Backup selected APK",
            lambda: self.system_tool_requested.emit("backup"),
        )
        batch.addAction(
            "🗑 Remove saved IAP purchases",
            self._open_iap_manager,
        )

        # Tools
        tools = self.addMenu("🛠 Tools")
        tools.addAction(
            "Install SuperSU",
            lambda: self.system_tool_requested.emit("install_supersu"),
        )
        tools.addAction(
            "Install/Update BusyBox",
            lambda: self.system_tool_requested.emit("install_busybox"),
        )
        tools.addAction(
            "Clear Dalvik Cache",
            lambda: self.system_tool_requested.emit("clear_dalvik"),
        )
        tools.addAction(
            "Move App to /system/app/",
            lambda: self.system_tool_requested.emit("move_system"),
        )

        self.addSeparator()

        self.addAction("📱 Clone App", self._clone_app)

        self.addSeparator()

        self.addAction(
            "⚙️ Disable Google Billing Emulation",
            lambda: self.system_tool_requested.emit("disable_billing"),
        )
        self.addAction(
            "📂 Change Directory",
            lambda: self.system_tool_requested.emit("change_dir"),
        )
        self.addAction(
            "🌐 Download Custom Patches",
            self._download_patch,
        )

    # ============================================================
    # Handlers
    # ============================================================
    def _apply_system_patches(self) -> None:
        features = {}
        if self.act_sig_true.isChecked():
            features["signature_verification_always_true"] = True
        if self.act_disable_apk_sig.isChecked():
            features["disable_apk_signature_verification"] = True
        if self.act_disable_zip_sig.isChecked():
            features["disable_zip_signature_verification"] = True
        if not features:
            QMessageBox.information(
                self, "Info", "Chưa chọn patch nào"
            )
            return
        self.patch_requested.emit("system_patch", features)

    def _run_test(self) -> None:
        self.patch_requested.emit("test_patch", {})

    def _install_modded_playstore(self) -> None:
        QMessageBox.information(
            self, "Modded Play Store",
            "Tính năng này cần APK modded Play Store.\n"
            "Vui lòng tải thủ công từ nguồn tin cậy.",
        )

    def _force_root_check(self) -> None:
        try:
            from core.device_bridge import check_root
            ok = check_root()
        except Exception:
            ok = False
        if ok:
            QMessageBox.information(
                self, "Root", "Thiết bị đã có root"
            )
        else:
            QMessageBox.warning(
                self, "Root", "Không có root / thiếu ADB"
            )

    def _open_iap_manager(self) -> None:
        self.iap_manager_requested.emit()

    def _clone_app(self) -> None:
        # Emit signal — controller sẽ mở CloneDialog (cần biết APK hiện tại)
        self.clone_requested.emit()

    def _download_patch(self) -> None:
        self.download_patch_requested.emit()