"""
MainWindow — UI shell cho LP-PC Suite.
Logic business chuyển sang AppController (src/ui/app_controller.py).

Layout:
  Sidebar | Toolbar / Progress / Switches / Stacked Pages / Log (collapsible)
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QToolBar, QStatusBar, QComboBox, QLineEdit,
    QStackedWidget, QFrame, QProgressBar, QMessageBox,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont

from .app_list_widget import AppListWidget
from .log_widget import LogWidget
from .apk_detail_widget import APKDetailWidget
from .switches_panel import SwitchesPanel
from .app_controller import AppController


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LP-PC Suite v4 – Professional Modding Tool")
        self.resize(1280, 820)

        # --- Controller TRƯỚC (không phụ thuộc UI trong __init__) ---
        self.controller = AppController(self)

        # --- UI shell ---
        self._build_ui()

        # --- Wire controller signals → UI slots ---
        self._wire_controller()

        # --- Bootstrap ---
        self._on_log("[i] LP-PC Suite v4.0.0 khởi động")
        self._on_log("[i] Sẵn sàng nhận APK hoặc kết nối thiết bị ADB")
        self.controller.load_device_apps()

    # ============================================================
    # UI CONSTRUCTION
    # ============================================================
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        right_layout.addWidget(self._build_toolbar())
        right_layout.addWidget(self._build_progress_panel())

        # Switches panel — dùng iap_manager từ controller
        self.switches_panel = SwitchesPanel(self.controller.iap_manager)
        right_layout.addWidget(self.switches_panel)

        # Stacked pages
        self.stacked = QStackedWidget()
        self.stacked.addWidget(self._build_apps_page())
        self.stacked.addWidget(self._build_detail_page())
        self.stacked.addWidget(self._build_tools_page())
        right_layout.addWidget(self.stacked, 1)

        # Collapsible log
        right_layout.addWidget(self._build_log_panel())

        root.addWidget(right, 1)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Sẵn sàng")

    # ------------------------------------------------------------
    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 20, 8, 20)
        layout.setSpacing(6)

        logo = QLabel("🛠 LP-PC Suite")
        logo.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        logo.setStyleSheet("color: #58a6ff; padding: 12px 8px;")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)
        layout.addSpacing(20)

        self.btn_apps = QPushButton("📱  Installed Apps")
        self.btn_apps.setCheckable(True)
        self.btn_apps.setChecked(True)
        self.btn_apps.setAutoExclusive(True)

        self.btn_detail = QPushButton("🔍  APK Detail")
        self.btn_detail.setCheckable(True)
        self.btn_detail.setAutoExclusive(True)

        self.btn_tools = QPushButton("⚙️  Tools")
        self.btn_tools.setCheckable(True)
        self.btn_tools.setAutoExclusive(True)

        layout.addWidget(self.btn_apps)
        layout.addWidget(self.btn_detail)
        layout.addWidget(self.btn_tools)
        layout.addStretch()

        version = QLabel("v4.0.0")
        version.setStyleSheet("color: #484f58; font-size: 11px;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        # Wire navigation (lambda resolve self.stacked khi click)
        self.btn_apps.clicked.connect(lambda: self.stacked.setCurrentIndex(0))
        self.btn_detail.clicked.connect(lambda: self.stacked.setCurrentIndex(1))
        self.btn_tools.clicked.connect(lambda: self.stacked.setCurrentIndex(2))
        return sidebar

    # ------------------------------------------------------------
    def _build_toolbar(self) -> QToolBar:
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍  Search apps...")
        self.search_edit.setMinimumWidth(220)
        self.search_edit.textChanged.connect(self._filter_apps)
        tb.addWidget(self.search_edit)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(
            ["All", "License check", "Ads", "Custom patch", "System"]
        )
        self.filter_combo.currentTextChanged.connect(self._filter_apps)
        tb.addWidget(self.filter_combo)
        tb.addSeparator()

        btn_browse = QPushButton("📁  Browse APK")
        btn_browse.clicked.connect(self._on_browse_clicked)
        tb.addWidget(btn_browse)

        btn_download = QPushButton("📥  Download APK")
        btn_download.clicked.connect(self._on_download_clicked)
        tb.addWidget(btn_download)

        btn_workspace = QPushButton("📂  Workspace")
        btn_workspace.clicked.connect(self._on_workspace_clicked)
        tb.addWidget(btn_workspace)

        return tb

    # ------------------------------------------------------------
    def _build_progress_panel(self) -> QWidget:
        """Progress panel LP-style: step label + progress bar."""
        container = QWidget()
        container.setObjectName("progressContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(4)

        self.step_label = QLabel("")
        self.step_label.setStyleSheet(
            "color: #58a6ff; font-size: 11px; font-weight: bold;"
        )
        layout.addWidget(self.step_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        container.setVisible(False)
        self.progress_container = container
        return container

    # ------------------------------------------------------------
    def _build_apps_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.app_list = AppListWidget()
        self.app_list.app_context_menu_requested.connect(
            self._on_app_context_menu
        )
        self.app_list.itemDoubleClicked.connect(self._on_app_double_click)
        layout.addWidget(self.app_list)
        return page

    def _build_detail_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.apk_detail = APKDetailWidget()
        self.apk_detail.patch_action_requested.connect(
            self._on_detail_action
        )
        self.apk_detail.rebuild_requested.connect(self._on_rebuild_clicked)
        layout.addWidget(self.apk_detail)
        return page

    def _build_tools_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(12)

        title = QLabel(
            "<b style='font-size:16px;'>🧰 Tools & System Patches</b>"
        )
        title.setStyleSheet("color: #f0f6fc;")
        layout.addWidget(title)

        desc = QLabel(
            "Các công cụ hệ thống đang được phát triển.\n"
            "Sử dụng menu Toolbox (🧰) trên thanh toolbar "
            "để truy cập nhanh."
        )
        desc.setStyleSheet("color: #8b949e; font-size: 12px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addStretch()
        return page

    # ------------------------------------------------------------
    def _build_log_panel(self) -> QWidget:
        container = QWidget()
        container.setObjectName("logContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setObjectName("logHeader")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 4, 8, 4)
        h_layout.setSpacing(8)

        title = QLabel("📋  Nhật ký hoạt động")
        title.setStyleSheet(
            "color: #8b949e; font-size: 11px; font-weight: bold;"
        )
        h_layout.addWidget(title)
        h_layout.addStretch()

        self.btn_clear_log = QPushButton("Xóa")
        self.btn_clear_log.setFixedSize(52, 22)
        self.btn_clear_log.setStyleSheet("""
            QPushButton {
                background: transparent; color: #8b949e;
                border: 1px solid #30363d; border-radius: 4px;
                font-size: 10px; padding: 2px 8px;
            }
            QPushButton:hover { color: #f0f6fc; border-color: #58a6ff; }
        """)
        self.btn_clear_log.clicked.connect(self._clear_log)
        h_layout.addWidget(self.btn_clear_log)

        self.btn_expand_log = QPushButton("▲")
        self.btn_expand_log.setFixedSize(24, 22)
        self.btn_expand_log.setStyleSheet("""
            QPushButton {
                background: transparent; color: #8b949e;
                border: none; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { color: #58a6ff; }
        """)
        self.btn_expand_log.setCheckable(True)
        self.btn_expand_log.setToolTip("Mở rộng / thu gọn log")
        self.btn_expand_log.toggled.connect(self._toggle_log_expand)
        h_layout.addWidget(self.btn_expand_log)

        layout.addWidget(header)

        self.log = LogWidget()
        self.log.setMinimumHeight(80)
        self.log.setMaximumHeight(120)
        layout.addWidget(self.log)

        return container

    # ============================================================
    # WIRING (View ↔ Controller)
    # ============================================================
    def _wire_controller(self) -> None:
        self.controller.log_message.connect(self._on_log)
        self.controller.status_message.connect(self._on_status)
        self.controller.analysis_ready.connect(self._on_analysis_ready)
        self.controller.progress_update.connect(self._on_progress)
        self.controller.progress_hide.connect(self._hide_progress)
        self.controller.show_detail_page.connect(self._show_detail_page)
        self.controller.step_update.connect(self._on_step_update)
        # Safety prompt: controller emits → main thread dialog
        self.controller.safety_prompt_requested.connect(
            self._on_safety_prompt
        )

    # ============================================================
    # EVENT HANDLERS → delegate controller
    # ============================================================
    def _on_browse_clicked(self) -> None:
        self.controller.browse_apk()

    def _on_download_clicked(self) -> None:
        self.controller.download_apk_dialog()

    def _on_workspace_clicked(self) -> None:
        self.controller.open_workspace()

    def _on_app_context_menu(
        self, pkg: str, name: str,
        colors: list[str], findings: list[dict],
    ) -> None:
        self.controller.open_menu_of_patches(pkg, name, colors, findings)

    def _on_app_double_click(self, item) -> None:
        self.controller.on_app_double_click(item)

    def _on_detail_action(self, action: str) -> None:
        self.controller.handle_detail_action(action)

    def _on_rebuild_clicked(self) -> None:
        self.controller.open_rebuild_dialog()

    def _filter_apps(self) -> None:
        text = self.search_edit.text().lower()
        filt = self.filter_combo.currentText()
        self.app_list.filter(text, filt)

    # ============================================================
    # CONTROLLER SIGNALS → UI UPDATE
    # ============================================================
    def _on_log(self, message: str) -> None:
        self.log.append_log(message)

    def _on_status(self, message: str) -> None:
        self.status_bar.showMessage(message)

    def _on_analysis_ready(self, result: dict) -> None:
        self.apk_detail.populate(result)

    def _on_progress(self, current: int, total: int) -> None:
        if total > 0:
            pct = int(current * 100 / total)
            if self.progress_container.isVisible():
                self.progress_bar.setValue(pct)

    def _on_step_update(self, step_name: str, pct: int) -> None:
        """LP-style step: hiển thị label + cập nhật %."""
        self.progress_container.setVisible(True)
        self.step_label.setText(f"⏳ {step_name}")
        self.progress_bar.setValue(max(0, min(100, pct)))

    def _hide_progress(self) -> None:
        self.progress_container.setVisible(False)
        self.step_label.setText("")
        self.progress_bar.setValue(0)

    def _show_detail_page(self) -> None:
        self.btn_detail.setChecked(True)
        self.stacked.setCurrentIndex(1)

    # ============================================================
    # SAFETY PROMPT — Y/N dialog khi vượt ngưỡng N lần
    # ============================================================
    def _on_safety_prompt(
        self, reason: str, details: dict, count: int, callback
    ) -> None:
        """
        Chạy trên main thread (Qt signal queue từ worker thread).
        Block worker thread tối đa 60s (config: prompt_timeout_sec).

        FIX: setTextFormat(RichText) để render HTML đúng.
        """
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("⚠️ Cảnh báo an toàn")

        # === FIX: bật RichText cho CẢ text() và informativeText() ===
        msg.setTextFormat(Qt.TextFormat.RichText)

        msg.setText(
            f"<b>Phát hiện <span style='color:#f85149;'>"
            f"{reason.upper()}</span> vượt ngưỡng {count} lần liên tiếp!</b>"
        )

        detail_lines = [
            f"&nbsp;&nbsp;• <b>{k}</b>: {v}"
            for k, v in details.items()
        ]
        msg.setInformativeText(
            "<b>Chi tiết:</b><br>"
            + "<br>".join(detail_lines)
            + "<br><br>"
            "<b>Continue</b>: nâng ngưỡng +5% và tiếp tục "
            "(chấp nhận rủi ro)<br>"
            "<b>Stop</b>: dừng pipeline an toàn"
        )

        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.button(QMessageBox.StandardButton.Yes).setText("Continue")
        msg.button(QMessageBox.StandardButton.No).setText("Stop")
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        msg.setWindowModality(Qt.WindowModality.ApplicationModal)

        user_continue = msg.exec() == QMessageBox.StandardButton.Yes

        self.log.append_log(
            f"[{'✔' if user_continue else '✘'}] [Safety] User chọn "
            f"{'CONTINUE' if user_continue else 'STOP'}"
        )

        # Trả kết quả về worker thread đang chờ
        try:
            callback(user_continue)
        except Exception:
            pass

    # ============================================================
    # LOG PANEL HELPERS
    # ============================================================
    def _toggle_log_expand(self, expanded: bool) -> None:
        if expanded:
            self.log.setMaximumHeight(400)
            self.btn_expand_log.setText("▼")
        else:
            self.log.setMaximumHeight(120)
            self.btn_expand_log.setText("▲")

    def _clear_log(self) -> None:
        self.log.clear_log()

    # ============================================================
    # CLOSE
    # ============================================================
    def closeEvent(self, event) -> None:
        self._on_log("[i] Đóng LP-PC Suite")
        event.accept()