"""
AppController — tách logic business khỏi MainWindow.
MainWindow chỉ lo UI; controller lo xử lý APK, download, pipeline.

Pattern: View (MainWindow) ↔ Controller (AppController)
Controller emit Qt signals → View cập nhật UI.

Thread-safety:
  - Worker thread CHỈ emit signal, KHÔNG chạm Qt widget.
  - Mọi dialog phải show trên main thread qua signal nội bộ.
"""
from __future__ import annotations

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


class AppController(QObject):
    """Controller chính — delegate signals cho MainWindow."""

    # Public signals (MainWindow lắng nghe)
    analysis_ready = pyqtSignal(dict)
    log_message = pyqtSignal(str)
    status_message = pyqtSignal(str)
    progress_update = pyqtSignal(int, int)
    progress_hide = pyqtSignal()
    show_detail_page = pyqtSignal()
    step_update = pyqtSignal(str, int)          # (step_name, pct 0-100)

    # Nội bộ: worker thread → main thread (không expose ra MainWindow)
    _suggest_signal = pyqtSignal(list)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.apk_path: str | None = None
        self.iap_manager = IAPManager()

        # Kết nối signal nội bộ: worker emit → main thread slot
        self._suggest_signal.connect(self._handle_suggestions_on_main)

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
        """Chuẩn hóa bundle (.apks/.xapk) rồi bắt đầu phân tích."""
        file_lower = file.lower()

        # --- Convert bundle nếu cần ---
        if file_lower.endswith((".apks", ".xapk")):
            self.log_message.emit(f"[*] Phát hiện bundle: {Path(file).name}")
            self.log_message.emit("[*] Đang convert sang .apk...")
            try:
                file = self._convert_bundle(file)
                self.log_message.emit(f"[✔] Đã convert: {file}")
            except Exception as e:
                QMessageBox.critical(
                    self.window, "Convert thất bại",
                    f"Không thể convert bundle:\n{e}",
                )
                self.log_message.emit(f"[!] Convert error: {e}")
                return

        self.apk_path = file
        self.status_message.emit(f"Đã tải: {Path(file).name}")
        self.log_message.emit(f"[*] Đã chọn: {file}")

        # --- Populate basic info ngay ---
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

        # --- Phân tích async ---
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
            result = {
                "findings": findings,
                "summary": analyzer.get_summary(),
                "colors": analyzer.get_colors(),
            }
            self.analysis_ready.emit(result)

            color_names = {
                "green": "License", "blue": "Ads",
                "yellow": "Custom Patch", "purple": "System Boot",
                "orange": "System", "red": "Protected",
            }
            names = ", ".join(color_names.get(c, c) for c in result["colors"])
            self.log_message.emit(f"[✔] Phân tích xong. Đặc điểm: {names}")
            for f in findings:
                self.log_message.emit(
                    f"    • {f.get('title', '?')}: {f.get('description', '')}"
                )

            self._show_smart_suggestions(findings)
        except Exception as e:
            self.log_message.emit(f"[!] Lỗi phân tích: {e}")

    # ============================================================
    # SMART SUGGESTIONS — thread-safe
    # ============================================================
    def _show_smart_suggestions(self, findings: list[dict]) -> None:
        """Gọi từ worker thread — chỉ emit signal, không tạo Qt widget."""
        self._suggest_signal.emit(findings)

    def _handle_suggestions_on_main(self, findings: list[dict]) -> None:
        """Chạy trên MAIN THREAD — an toàn để tạo QMessageBox."""
        has_iap = any(f.get("type") == "iap" for f in findings)
        has_license = any(f.get("type") == "license" for f in findings)
        has_ads = any(f.get("type") == "ads" for f in findings)

        suggestions = []
        if has_iap:
            suggestions.append(
                "💳 Phát hiện In-App Purchase.\n"
                "   → Áp dụng 'IAP Im lặng' (Dex mode)."
            )
        if has_license:
            suggestions.append(
                "🔑 Phát hiện License Check.\n"
                "   → Gỡ bỏ để dùng app trả phí miễn phí."
            )
        if has_ads:
            suggestions.append(
                "🚫 Phát hiện Quảng cáo.\n"
                "   → Xóa toàn bộ quảng cáo khỏi APK."
            )

        if not suggestions:
            return

        msg = QMessageBox(self.window)
        msg.setWindowTitle("💡 Gợi ý thông minh")
        msg.setText("Phát hiện các đặc điểm sau trong APK:")
        msg.setInformativeText(
            "\n\n".join(suggestions)
            + "\n\nBạn có muốn áp dụng các patch được đề xuất?"
        )
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        msg.setWindowModality(Qt.WindowModality.ApplicationModal)

        if msg.exec() == QMessageBox.StandardButton.Yes:
            modes = []
            if has_iap:
                modes.append("iap:dex")
            if has_license:
                modes.append("license:auto")
            if has_ads:
                modes.append("ads:full_offline")
            if modes:
                self.run_pipeline(",".join(modes))

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
                "Vui lòng chọn APK trước."
            )
            return

        if forced_package_id is not None and (
            not isinstance(forced_package_id, int) or forced_package_id <= 0
        ):
            forced_package_id = None

        signals = PipelineSignals()
        signals.progress.connect(
            lambda c, t: self.progress_update.emit(c, t)
        )
        signals.step.connect(self.step_update.emit)
        signals.status.connect(self.log_message.emit)
        signals.finished.connect(self._on_pipeline_finished)

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
                signals.finished.emit(False, "")

        threading.Thread(target=_worker, daemon=True).start()

    def _on_pipeline_finished(self, success: bool, output: str) -> None:
        self.progress_hide.emit()
        if success:
            self.log_message.emit(f"[✔] Hoàn thành! Output: {output}")
            self.status_message.emit(f"Hoàn thành: {output}")
        else:
            self.log_message.emit("[!] Patch thất bại.")
            self.status_message.emit("Patch thất bại")

    # ============================================================
    # MENU OF PATCHES / REBUILD
    # ============================================================
    def open_menu_of_patches(
        self, pkg: str, app_name: str,
        colors: list[str], findings: list[dict] | None = None,
    ) -> None:
        from .menu_of_patches import MenuOfPatchesDialog
        findings = findings or []
        dlg = MenuOfPatchesDialog(
            app_name, pkg, colors, findings, self.window
        )
        dlg.action_requested.connect(self.handle_detail_action)
        dlg.exec()

    def on_app_double_click(self, item) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        self.open_menu_of_patches(
            data["package"],
            data["name"],
            data["colors"],
            data.get("findings", []),
        )

    def open_rebuild_dialog(self) -> None:
        if not self.apk_path:
            QMessageBox.warning(
                self.window, "Chưa chọn APK",
                "Vui lòng chọn APK trước (Browse APK)."
            )
            return
        from .rebuild_dialog import RebuildDialog
        dlg = RebuildDialog(
            Path(self.apk_path).stem, "unknown", parent=self.window
        )
        dlg.rebuild_requested.connect(self.run_pipeline)
        dlg.exec()

    def handle_detail_action(self, action: str) -> None:
        if not self.apk_path:
            QMessageBox.warning(
                self.window, "Chưa chọn APK",
                "Vui lòng chọn APK trước."
            )
            return
        if action == "open_rebuild":
            self.open_rebuild_dialog()
            return

        mode_map = {
            "remove_license": "license",
            "remove_ads": "ads",
            "iap_emulation": "iap_dex",
            "apply_custom_patch": "custom",
        }
        mode = mode_map.get(action)
        if not mode:
            return

        if mode == "custom":
            patch_file, _ = QFileDialog.getOpenFileName(
                self.window,
                "Select Custom Patch",
                "",
                "Patch files (*.txt *.lpzip)",
            )
            if not patch_file:
                return
            os.environ["LP_CUSTOM_PATCH"] = patch_file

        self.run_pipeline(mode)

    # ============================================================
    # WORKSPACE
    # ============================================================
    def open_workspace(self) -> None:
        import subprocess
        workspace = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "workspace", "decompiled",
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
    # APP LIST LOADING
    # ============================================================
    def load_device_apps(self) -> None:
        try:
            apps = get_installed_apps()
        except Exception as e:
            self.log_message.emit(f"[!] Không thể load apps: {e}")
            apps = []

        if not apps:
            self.log_message.emit(
                "[i] Không tìm thấy app qua ADB — hiển thị danh sách demo."
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
            ("Minecraft Trial", "com.mojang.minecrafttrial", ["green", "blue"]),
            ("Instagram", "com.instagram.android", ["blue"]),
            ("Pro PDF Editor", "com.pro.pdfeditor.paid", ["green"]),
            ("System UI", "com.android.systemui", ["purple"]),
            ("Subway Surfers", "com.kiloo.subwaysurf", ["blue", "yellow"]),
            ("Nova Launcher Prime", "com.teslacoilsw.launcher.prime", ["green"]),
            ("Spotify Music", "com.spotify.music", ["blue"]),
            ("Solid Explorer", "pl.solidexplorer2", ["green", "yellow"]),
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
        layout.addWidget(QLabel("Nhập package name hoặc URL Google Play:"))

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

        layout.addWidget(QLabel("Hoặc dán URL trực tiếp (.apk / .xapk):"))
        url_input = QLineEdit()
        url_input.setPlaceholderText("https://example.com/app.apk")
        layout.addWidget(url_input)

        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setMaximumHeight(160)
        info_text.setVisible(False)
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
        self, dialog: QDialog, pkg_input: QLineEdit
    ) -> None:
        package = pkg_input.text().strip()
        if not package:
            return
        downloader = APKDownloader(log_callback=self.log_message.emit)
        info = downloader.get_google_play_app_info(package)
        info_text = dialog.findChild(QTextEdit)
        if info:
            info_text.setVisible(True)
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
            info_text.setVisible(True)
            info_text.setText("Không tìm thấy thông tin ứng dụng.")

    def _execute_download(
        self, dialog: QDialog, package: str,
        direct_url: str, source: str,
    ) -> None:
        if not package and not direct_url:
            QMessageBox.warning(
                self.window, "Lỗi",
                "Vui lòng nhập package name hoặc URL."
            )
            return

        downloader = APKDownloader(log_callback=self.log_message.emit)
        dialog.accept()

        def _worker():
            try:
                apk_path = None
                if direct_url:
                    apk_path = downloader.download_from_direct_url(direct_url)
                elif source == "APKPure":
                    apk_path = downloader.download_from_apkpure(package)
                elif source == "APKMody":
                    apk_path = downloader.download_from_apkmody(package)
                elif source == "Uptodown":
                    apk_path = downloader.download_from_uptodown(package)
                elif source == "APKPure (via Google Play info)":
                    self.log_message.emit(
                        "[i] Google Play Scraper chỉ dùng để lấy info. "
                        "Đang tải qua APKPure..."
                    )
                    apk_path = downloader.download_from_apkpure(package)
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
                        "Không thể tải APK. Vui lòng thử nguồn khác."
                    )
            except Exception as e:
                QMessageBox.critical(self.window, "Lỗi tải", str(e))

        threading.Thread(target=_worker, daemon=True).start()