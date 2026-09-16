"""
MainWindow — UI shell cho LP-PC Suite.
Logic business chuyển sang AppController (src/ui/app_controller.py).

Layout:
  Sidebar | Toolbar / Switches / Stacked Pages / Log (collapsible)
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QToolBar, QStatusBar, QComboBox, QLineEdit,
    QStackedWidget, QFrame, QProgressBar,
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

        # --- UI shell (giờ có thể access self.controller) ---
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

        # Progress bar (hidden)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        right_layout.addWidget(self.progress_bar)

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

        # Wire navigation (lazy — self.stacked sẽ tồn tại khi click)
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
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(current)

    def _hide_progress(self) -> None:
        self.progress_bar.setVisible(False)

    def _show_detail_page(self) -> None:
        self.btn_detail.setChecked(True)
        self.stacked.setCurrentIndex(1)

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