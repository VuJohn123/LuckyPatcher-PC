"""
AppController — tách logic business khỏi MainWindow.

v4 (2026):
  - Intercept RebuildTreeDialog submissions → route qua _on_rebuild_submit.
  - Special modes (change_perms/resign/clone) mở dialog trước pipeline.
  - Log chi tiết permission sẽ xóa.
  - Cleanup env vars sau pipeline.
  - Debug logs để trace flow.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QFileDialog, QMessageBox, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit,
)

from scanner.installed_apps import get_installed_apps
from scanner.app_classifier import AppDeepAnalyzer
from patcher.iap_manager import IAPManager
from core.pipeline_signals import PipelineSignals
from core.apk_downloader import APKDownloader

logger = logging.getLogger(__name__)

# Modes cần dialog riêng trước khi chạy pipeline
_SPECIAL_MODES = frozenset({
    "change_perms", "resign", "clone",
})


class AppController(QObject):
    """Controller chính — delegate signals cho MainWindow."""

    # ---- Public signals ----
    analysis_ready = pyqtSignal(dict)
    log_message = pyqtSignal(str)
    status_message = pyqtSignal(str)
    progress_update = pyqtSignal(int, int)
    progress_hide = pyqtSignal()
    show_detail_page = pyqtSignal()
    step_update = pyqtSignal(str, int)
    safety_prompt_requested = pyqtSignal(str, dict, int, object)
    _suggest_signal = pyqtSignal(list)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.apk_path: str | None = None
        self.iap_manager = IAPManager()
        self.last_findings: list[dict] = []
        self.last_colors: list[str] = ["white"]
        self.last_package: str = ""
        self.last_app_name: str = ""

        self._suggest_signal.connect(
            self._handle_suggestions_on_main
        )

    # ============================================================
    # APK LOADING
    # ============================================================
    def browse_apk(self) -> None:
        file, _ = QFileDialog.getOpenFileName(
            self.window,
            "Chọn APK / XAPK / APKS",
            "",
            "Android packages (*.apk *.xapk *.apks);;"
            "APK (*.apk);;XAPK (*.xapk);;APKS (*.apks);;"
            "All files (*.*)",
        )
        if file:
            self.load_apk(file)

    def load_apk(self, file: str) -> None:
        file_lower = file.lower()

        if file_lower.endswith((".apks", ".xapk")):
            self.log_message.emit(
                f"[*] Phát hiện bundle: {Path(file).name}"
            )
            self.log_message.emit("[*] Đang convert sang .apk...")
            try:
                file = self._convert_bundle(file)
                self.log_message.emit(f"[✔] Đã convert: {file}")
            except Exception as e:
                QMessageBox.critical(
                    self.window, "Convert thất bại",
                    f"Không thể convert bundle:\n{e}",
                )
                return

        self.apk_path = file
        self.status_message.emit(f"Đã tải: {Path(file).name}")
        self.log_message.emit(f"[*] Đã chọn: {file}")

        try:
            size = Path(file).stat().st_size
        except Exception:
            size = 0

        basic_info = {
            "findings": [],
            "summary": {
                "app_name": Path(file).stem,
                "package": "Đang phân tích...",
                "version": "",
                "apk_path": file,
                "size": size,
            },
            "colors": ["white"],
        }
        self.analysis_ready.emit(basic_info)
        self.show_detail_page.emit()

        threading.Thread(
            target=self._analyze_worker, args=(file,), daemon=True
        ).start()

    def _convert_bundle(self, file: str) -> str:
        from core.xapk_converter import convert_xapk_to_apk, is_xapk
        from core.apks_converter import convert_apks_to_apk, is_apks

        file_lower = file.lower()
        if file_lower.endswith(".xapk") or is_xapk(file):
            return convert_xapk_to_apk(
                file, log_callback=self.log_message.emit
            )
        if file_lower.endswith(".apks") or is_apks(file):
            return convert_apks_to_apk(
                file, log_callback=self.log_message.emit
            )
        return file

    def _analyze_worker(self, file: str) -> None:
        try:
            analyzer = AppDeepAnalyzer(file)
            findings = analyzer.analyze()
            summary = analyzer.get_summary()
            colors = analyzer.get_colors()

            self.last_findings = findings
            self.last_colors = colors
            self.last_package = summary.get("package", "")
            self.last_app_name = summary.get("app_name", "")

            result = {
                "findings": findings,
                "summary": summary,
                "colors": colors,
            }
            self.analysis_ready.emit(result)

            color_names = {
                "green": "License", "blue": "Ads",
                "yellow": "Custom Patch", "purple": "System Boot",
                "orange": "System", "red": "Protected",
            }
            names = ", ".join(
                color_names.get(c, c) for c in colors
            )
            self.log_message.emit(
                f"[✔] Phân tích xong. Đặc điểm: {names}"
            )
            for f in findings:
                self.log_message.emit(
                    f"    • {f.get('title', '?')}: "
                    f"{f.get('description', '')}"
                )

            self._show_smart_suggestions(findings)
        except Exception as e:
            self.log_message.emit(f"[!] Lỗi phân tích: {e}")
            logger.exception("Analysis failed")

    def _show_smart_suggestions(self, findings: list[dict]) -> None:
        self._suggest_signal.emit(findings)

    def _handle_suggestions_on_main(self, findings: list[dict]) -> None:
        # Không auto popup — user tự click Quick Actions.
        return

    # ============================================================
    # PIPELINE
    # ============================================================
    def run_pipeline(
        self,
        mode: str,
        key_type: str = "testkey",
        forced_package_id: int | None = None,
        fast_mode: bool = True,
        use_gda: bool = True,
    ) -> None:
        if not self.apk_path:
            QMessageBox.warning(
                self.window, "Chưa chọn APK",
                "Vui lòng chọn APK trước.",
            )
            return

        if forced_package_id is not None and (
            not isinstance(forced_package_id, int)
            or forced_package_id <= 0
        ):
            forced_package_id = None

        signals = PipelineSignals()
        signals.progress.connect(
            lambda c, t: self.progress_update.emit(c, t)
        )
        signals.step.connect(self.step_update.emit)
        signals.status.connect(self.log_message.emit)
        signals.finished.connect(self._on_pipeline_finished)
        signals.safety_prompt.connect(
            self.safety_prompt_requested.emit
        )

        self.log_message.emit(f"[*] Bắt đầu pipeline: mode={mode}")
        self.show_detail_page.emit()

        from main import run_pipeline

        def _worker():
            try:
                success, out, _ = run_pipeline(
                    self.apk_path,
                    mode=mode,
                    log_callback=self.log_message.emit,
                    key_type=key_type,
                    forced_package_id=forced_package_id,
                    fast_mode=fast_mode,
                    use_gda=use_gda,
                    apktool_jobs=4,
                    apktool_memory="4096m",
                    signals=signals,
                )
                signals.finished.emit(success, out if out else "")
            except Exception as e:
                self.log_message.emit(f"[!] Pipeline exception: {e}")
                logger.exception("Pipeline crashed")
                signals.finished.emit(False, "")

        threading.Thread(target=_worker, daemon=True).start()

    def _on_pipeline_finished(self, success: bool, output: str) -> None:
        self.progress_hide.emit()

        # Cleanup env vars sau pipeline
        for key in (
            "LP_PERMS_TO_REMOVE",
            "LP_CLONE_PACKAGE", "LP_CLONE_APP_NAME",
            "LP_CUSTOM_PATCH",
            "LP_RESIGN_KEY_TYPE", "LP_RESIGN_FORCED_ID",
        ):
            os.environ.pop(key, None)

        if success:
            self.log_message.emit(
                f"[✔] Hoàn thành! Output: {output}"
            )
            self.status_message.emit(f"Hoàn thành: {output}")
        else:
            self.log_message.emit("[!] Patch thất bại.")
            self.status_message.emit("Patch thất bại")

    # ============================================================
    # MENU OF PATCHES
    # ============================================================
    def open_menu_of_patches(
        self, pkg: str, app_name: str,
        colors: list[str], findings: list[dict] | None = None,
        use_tree: bool = False,
    ) -> None:
        findings = findings or []
        if use_tree:
            from .menu_of_patches_tree import MenuOfPatchesTreeDialog
            dlg = MenuOfPatchesTreeDialog(
                app_name, pkg, colors, findings, self.window
            )
        else:
            from .menu_of_patches import MenuOfPatchesDialog
            dlg = MenuOfPatchesDialog(
                app_name, pkg, colors, findings, self.window
            )
        dlg.action_requested.connect(
            lambda action: self._handle_menu_action(action, findings)
        )
        dlg.exec()

    def on_app_double_click(self, item) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        self.open_menu_of_patches(
            data["package"],
            data["name"],
            data["colors"],
            data.get("findings", []),
        )

    # ============================================================
    # CENTRAL MENU ACTION HANDLER
    # ============================================================
    def _handle_menu_action(
        self, action: str, findings: list[dict] | None = None,
    ) -> None:
        """Central handler cho mọi menu action."""
        self.log_message.emit(f"[*] [Menu] action='{action}'")

        # === Rebuild / multi-patch ===
        if action in ("open_rebuild", "multi_patch"):
            self.open_rebuild_dialog(
                preselected=None
                if action == "open_rebuild" else "multi_patch"
            )
            return

        # === Special dialogs ===
        if action in ("change_perms", "manage_permissions"):
            self.log_message.emit(
                "[*] [Menu] → Mở Permission Picker dialog"
            )
            self._open_permission_picker()
            return

        if action == "resign":
            self.log_message.emit(
                "[*] [Menu] → Mở Resign dialog"
            )
            self._open_resign_dialog()
            return

        if action == "clone":
            self.log_message.emit("[*] [Menu] → Mở Clone dialog")
            self._open_clone_dialog()
            return

        # === Rebuild with specific mode ===
        if (action.startswith("license:")
                or action.startswith("ads:")
                or action.startswith("iap:")):
            self._open_rebuild_with_mode(action)
            return
        if action in ("custom", "aidl_proxy",
                      "sig_disable", "sig_integrity",
                      "sig_fake_archive"):
            self._open_rebuild_with_mode(action)
            return

        # === Direct actions ===
        if action == "remove_license":
            self.run_pipeline("license:auto")
        elif action == "remove_ads":
            self.run_pipeline("ads:remove")
        elif action == "iap_emulation":
            self.run_pipeline("iap:dex")
        elif action == "apply_custom_patch":
            self._apply_custom_patch()
        elif action == "backup":
            self._backup_apk()
        elif action == "launch":
            self.log_message.emit(
                "[i] Launch chỉ hoạt động khi có ADB + device."
            )
        elif action == "info":
            self.open_rebuild_dialog()
        else:
            self.log_message.emit(
                f"[!] [Menu] Unknown action: '{action}'"
            )

    # ============================================================
    # REBUILD SUBMIT — CENTRAL INTERCEPT
    # ============================================================
    def _on_rebuild_submit(
        self, mode_string: str, dlg,
    ) -> None:
        """
        Nhận mode string từ RebuildTreeDialog.
        Nếu chứa special mode → mở dialog tương ứng.
        Ngược lại → chạy pipeline với normal modes.
        """
        self.log_message.emit(
            f"[*] [Rebuild] Submit modes='{mode_string}'"
        )

        modes = [
            m.strip() for m in mode_string.split(",") if m.strip()
        ]
        if not modes:
            self.log_message.emit("[!] [Rebuild] Không có mode nào")
            return

        key_type = dlg.get_key_type() if dlg else "testkey"
        forced_id = (
            dlg.get_forced_package_id() if dlg else None
        )

        # Phân loại modes
        special = [m for m in modes if m in _SPECIAL_MODES]
        normal = [m for m in modes if m not in _SPECIAL_MODES]

        # Case 1: chỉ 1 special, không có normal → mở dialog
        if len(special) == 1 and not normal:
            self._dispatch_special_mode(special[0])
            return

        # Case 2: có special + normal → cảnh báo + chạy normal
        if special and normal:
            self.log_message.emit(
                f"[!] [Rebuild] Special modes ({special}) "
                f"không thể mix với normal ({normal}). "
                f"Chạy normal pipeline trước."
            )

        # Case 3: nhiều special → cảnh báo
        if len(special) > 1:
            self.log_message.emit(
                f"[!] [Rebuild] Chỉ xử lý 1 special mode/lần. "
                f"Bỏ qua: {special[1:]}"
            )
            self._dispatch_special_mode(special[0])
            return

        # Case 4: chạy normal
        if normal:
            self.run_pipeline(
                ",".join(normal),
                key_type=key_type,
                forced_package_id=forced_id,
            )

    def _dispatch_special_mode(self, mode: str) -> None:
        """Mở dialog tương ứng với special mode."""
        if mode == "change_perms":
            self.log_message.emit(
                "[*] [Rebuild] → Mở Permission Picker"
            )
            self._open_permission_picker()
        elif mode == "resign":
            self.log_message.emit(
                "[*] [Rebuild] → Mở Resign dialog"
            )
            self._open_resign_dialog()
        elif mode == "clone":
            self.log_message.emit(
                "[*] [Rebuild] → Mở Clone dialog"
            )
            self._open_clone_dialog()

    # ============================================================
    # SPECIAL DIALOG WRAPPERS
    # ============================================================
    def _open_permission_picker(self) -> None:
        if not self.apk_path:
            QMessageBox.warning(
                self.window, "Chưa chọn APK",
                "Vui lòng chọn APK trước.",
            )
            return

        try:
            from .permission_picker_dialog import (
                PermissionPickerDialog,
            )
        except ImportError as e:
            QMessageBox.critical(
                self.window, "Missing module",
                f"Không load được permission_picker_dialog:\n{e}",
            )
            return

        self.log_message.emit(
            "[*] [Picker] Đang load permissions từ APK..."
        )

        try:
            dlg = PermissionPickerDialog(
                self.apk_path,
                package=self.last_package,
                app_name=self.last_app_name,
                parent=self.window,
            )
        except Exception as e:
            QMessageBox.critical(
                self.window, "Lỗi",
                f"Không tạo được PermissionPickerDialog:\n{e}",
            )
            logger.exception("PermissionPicker init failed")
            return

        self.log_message.emit(
            f"[*] [Picker] Tìm thấy {len(dlg.permissions)} permission(s)"
        )

        if not dlg.exec():
            self.log_message.emit("[i] [Picker] User cancelled")
            return

        selected = dlg.get_selected_permissions()
        if not selected:
            self.log_message.emit(
                "[i] [Picker] Không chọn permission nào"
            )
            return

        # Bridge qua env var
        os.environ["LP_PERMS_TO_REMOVE"] = ",".join(selected)

        # Log chi tiết từng permission sẽ xóa
        self.log_message.emit(
            f"[✔] [Picker] {len(selected)} permission(s) sẽ bị xóa:"
        )
        for perm in selected:
            short = perm
            if len(short) > 60:
                short = "..." + short[-57:]
            self.log_message.emit(f"      • {short}")

        self.run_pipeline("change_perms")

    def _open_resign_dialog(self) -> None:
        if not self.apk_path:
            QMessageBox.warning(
                self.window, "Chưa chọn APK",
                "Vui lòng chọn APK trước.",
            )
            return

        try:
            from .resign_dialog import ResignDialog
        except ImportError as e:
            QMessageBox.critical(
                self.window, "Missing module",
                f"Không load được resign_dialog:\n{e}",
            )
            return

        dlg = ResignDialog(
            self.last_app_name or "APK", self.window,
        )
        if not dlg.exec():
            return

        self.run_pipeline(
            "resign",
            key_type=dlg.get_key_type(),
            forced_package_id=dlg.get_forced_package_id(),
        )

    def _open_clone_dialog(self) -> None:
        if not self.apk_path:
            QMessageBox.warning(
                self.window, "Chưa chọn APK",
                "Vui lòng chọn APK trước.",
            )
            return

        try:
            from .clone_dialog import CloneDialog
        except ImportError as e:
            QMessageBox.critical(
                self.window, "Missing module",
                f"Không load được clone_dialog:\n{e}",
            )
            return

        dlg = CloneDialog(
            self.last_app_name or "APK",
            self.last_package or "com.unknown",
            self.window,
        )
        if not dlg.exec():
            return

        os.environ["LP_CLONE_PACKAGE"] = dlg.get_new_package()
        os.environ["LP_CLONE_APP_NAME"] = dlg.get_new_name()
        self.run_pipeline("clone")

    def _open_rebuild_with_mode(self, mode: str) -> None:
        if not self.apk_path:
            QMessageBox.warning(
                self.window, "Chưa chọn APK",
                "Vui lòng chọn APK trước.",
            )
            return
        from .rebuild_tree_dialog import RebuildTreeDialog
        dlg = RebuildTreeDialog(
            self.last_app_name or Path(self.apk_path).stem,
            self.last_package,
            preselected_action=mode,
            parent=self.window,
        )
        dlg.rebuild_requested.connect(
            lambda m, d=dlg: self._on_rebuild_submit(m, d)
        )
        dlg.exec()

    def open_rebuild_dialog(
        self, preselected: str | None = None,
    ) -> None:
        if not self.apk_path:
            QMessageBox.warning(
                self.window, "Chưa chọn APK",
                "Vui lòng chọn APK trước (Browse APK).",
            )
            return
        from .rebuild_tree_dialog import RebuildTreeDialog
        dlg = RebuildTreeDialog(
            self.last_app_name or Path(self.apk_path).stem,
            self.last_package,
            preselected_action=preselected,
            parent=self.window,
        )
        dlg.rebuild_requested.connect(
            lambda m, d=dlg: self._on_rebuild_submit(m, d)
        )
        dlg.exec()

    def handle_detail_action(self, action: str) -> None:
        self._handle_menu_action(action)

    def _apply_custom_patch(self) -> None:
        if not self.apk_path:
            QMessageBox.warning(
                self.window, "Chưa chọn APK",
                "Vui lòng chọn APK trước.",
            )
            return
        patch_file, _ = QFileDialog.getOpenFileName(
            self.window, "Chọn Custom Patch", "",
            "Patch files (*.txt *.lpzip);;All files (*.*)",
        )
        if not patch_file:
            return
        os.environ["LP_CUSTOM_PATCH"] = patch_file
        self.run_pipeline("custom")

    def _backup_apk(self) -> None:
        if not self.apk_path:
            QMessageBox.warning(
                self.window, "Chưa chọn APK",
                "Vui lòng chọn APK trước.",
            )
            return
        import shutil
        backup_dir = os.path.join(
            os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))
            ), "workspace", "backups",
        )
        os.makedirs(backup_dir, exist_ok=True)
        dst = os.path.join(backup_dir, Path(self.apk_path).name)
        try:
            shutil.copy2(self.apk_path, dst)
            self.log_message.emit(f"[✔] Backup: {dst}")
        except Exception as e:
            self.log_message.emit(f"[!] Backup failed: {e}")

    # ============================================================
    # WORKSPACE
    # ============================================================
    def open_workspace(self) -> None:
        import subprocess
        workspace = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "workspace",
        )
        if not os.path.exists(workspace):
            QMessageBox.information(
                self.window, "Workspace",
                f"Thư mục workspace chưa tồn tại:\n{workspace}",
            )
            return
        if sys.platform == "win32":
            os.startfile(workspace)
        elif sys.platform == "darwin":
            subprocess.run(["open", workspace])
        else:
            subprocess.run(["xdg-open", workspace])

    # ============================================================
    # APP LIST
    # ============================================================
    def load_device_apps(self) -> None:
        try:
            apps = get_installed_apps()
        except Exception as e:
            self.log_message.emit(f"[!] Không thể load apps: {e}")
            apps = []

        if not apps:
            self.log_message.emit(
                "[i] Không tìm thấy app qua ADB — dùng demo."
            )
            self._load_demo_apps()
            return

        for app in apps:
            colors = self._quick_classify(app["package"])
            self.window.app_list.add_app(
                app["name"], app["package"], colors
            )

        self.log_message.emit(
            f"[✔] Đã tải {len(apps)} ứng dụng từ thiết bị"
        )

    def _quick_classify(self, package: str) -> list[str]:
        pkg = package.lower()
        colors: list[str] = []
        if any(k in pkg for k in (
            "google", "facebook", "unity", "game",
            "applovin", "ads", "admob",
        )):
            colors.append("blue")
        if any(k in pkg for k in ("pro", "premium", "paid", "license")):
            colors.append("green")
        if pkg.startswith(("com.android.", "com.google.android.")):
            colors = ["purple"]
        return colors or ["white"]

    def _load_demo_apps(self) -> None:
        demo = [
            ("Minecraft Trial", "com.mojang.minecrafttrial",
             ["green", "blue"]),
            ("Instagram", "com.instagram.android", ["blue"]),
            ("Pro PDF Editor", "com.pro.pdfeditor.paid", ["green"]),
            ("System UI", "com.android.systemui", ["purple"]),
            ("Subway Surfers", "com.kiloo.subwaysurf",
             ["blue", "yellow"]),
            ("Nova Launcher Prime",
             "com.teslacoilsw.launcher.prime", ["green"]),
            ("Spotify Music", "com.spotify.music", ["blue"]),
            ("Solid Explorer", "pl.solidexplorer2",
             ["green", "yellow"]),
        ]
        for name, pkg, colors in demo:
            self.window.app_list.add_app(name, pkg, colors)
        self.log_message.emit(
            f"[i] Đã tải {len(demo)} ứng dụng demo "
            f"(thiết bị chưa kết nối qua ADB)"
        )

    # ============================================================
    # DOWNLOAD APK
    # ============================================================
    def download_apk_dialog(self) -> None:
        dlg = QDialog(self.window)
        dlg.setWindowTitle("📥 Tải APK")
        dlg.setMinimumSize(540, 460)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(QLabel(
            "<b style='font-size:14px;'>Tải APK từ nhiều nguồn</b>"
        ))
        layout.addWidget(QLabel(
            "Nhập package name hoặc URL Google Play:"
        ))

        pkg_row = QHBoxLayout()
        pkg_input = QLineEdit()
        pkg_input.setPlaceholderText("com.example.app")
        pkg_row.addWidget(pkg_input)
        btn_search = QPushButton("🔍 Tìm kiếm")
        btn_search.clicked.connect(
            lambda: self._search_google_play(dlg, pkg_input)
        )
        pkg_row.addWidget(btn_search)
        layout.addLayout(pkg_row)

        layout.addWidget(QLabel("Nguồn tải:"))
        source_combo = QComboBox()
        source_combo.addItems([
            "APKPure", "APKMody", "Uptodown",
            "APKPure (via Google Play info)",
        ])
        layout.addWidget(source_combo)

        layout.addWidget(QLabel(
            "Hoặc dán URL trực tiếp (.apk / .xapk):"
        ))
        url_input = QLineEdit()
        url_input.setPlaceholderText("https://example.com/app.apk")
        layout.addWidget(url_input)

        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setMaximumHeight(160)
        info_text.setVisible(False)
        info_text.setObjectName("downloadInfoText")
        layout.addWidget(info_text)

        btn_row = QHBoxLayout()
        btn_download = QPushButton("📥 Tải xuống")
        btn_download.clicked.connect(lambda: self._execute_download(
            dlg, pkg_input.text().strip(),
            url_input.text().strip(), source_combo.currentText(),
        ))
        btn_download.setStyleSheet(
            "background-color: #238636; color: white; "
            "font-weight: bold; padding: 8px 20px; border-radius: 6px;"
        )
        btn_cancel = QPushButton("Hủy")
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_download)
        layout.addLayout(btn_row)

        dlg.exec()

    def _search_google_play(
        self, dialog: QDialog, pkg_input: QLineEdit,
    ) -> None:
        package = pkg_input.text().strip()
        if not package:
            return
        downloader = APKDownloader(log_callback=self.log_message.emit)
        info = downloader.get_google_play_app_info(package)
        info_text = dialog.findChild(
            QTextEdit, "downloadInfoText"
        )
        if not info_text:
            return
        info_text.setVisible(True)
        if info:
            info_text.setText(
                f"Tên: {info.get('title', 'N/A')}\n"
                f"Package: {info.get('package', 'N/A')}\n"
                f"Phiên bản: {info.get('version', 'N/A')}\n"
                f"Kích thước: {info.get('size', 'N/A')}\n"
                f"Lượt cài: {info.get('installs', 'N/A')}\n"
                f"Đánh giá: {info.get('score', 'N/A')}\n"
                f"Mô tả: {info.get('description', 'N/A')}"
            )
        else:
            info_text.setText("Không tìm thấy thông tin ứng dụng.")

    def _execute_download(
        self, dialog: QDialog, package: str,
        direct_url: str, source: str,
    ) -> None:
        if not package and not direct_url:
            QMessageBox.warning(
                self.window, "Lỗi",
                "Vui lòng nhập package name hoặc URL.",
            )
            return

        downloader = APKDownloader(log_callback=self.log_message.emit)
        dialog.accept()

        def _worker():
            try:
                apk_path = None
                if direct_url:
                    apk_path = downloader.download_from_direct_url(
                        direct_url
                    )
                elif source == "APKPure":
                    apk_path = downloader.download_from_apkpure(package)
                elif source == "APKMody":
                    apk_path = downloader.download_from_apkmody(package)
                elif source == "Uptodown":
                    apk_path = downloader.download_from_uptodown(
                        package
                    )
                else:
                    apk_path = downloader.download_from_apkpure(package)

                if apk_path:
                    self.status_message.emit(
                        f"Đã tải: {Path(apk_path).name}"
                    )
                    self.load_apk(apk_path)
                else:
                    QMessageBox.warning(
                        self.window, "Tải thất bại",
                        "Không thể tải APK. Vui lòng thử nguồn khác.",
                    )
            except Exception as e:
                QMessageBox.critical(self.window, "Lỗi tải", str(e))

        threading.Thread(target=_worker, daemon=True).start()