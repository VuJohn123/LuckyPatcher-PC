"""
MainWindow — UI shell cho LP-PC Suite.

v4 (2026):
  - Log panel RESIZABLE qua QSplitter (drag handle giữa content/log).
  - i18n integration: dùng core.i18n.t() cho các string chính.
  - Giữ collapse button cho quick toggle.
  - Drag & drop + shortcuts.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QToolBar, QStatusBar, QComboBox, QLineEdit,
    QStackedWidget, QFrame, QProgressBar, QMessageBox, QSplitter,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QKeySequence, QShortcut

from .app_list_widget import AppListWidget
from .log_widget import LogWidget
from .apk_detail_widget import APKDetailWidget
from .switches_panel import SwitchesPanel
from .app_controller import AppController
from .toolbox_menu import ToolboxMenu
from core.i18n import t


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(t("main_window.title"))

        # Responsive sizing
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            w = min(1280, int(avail.width() * 0.92))
            h = min(820, int(avail.height() * 0.92))
            self.resize(w, h)
            self.setMinimumSize(900, 600)
        else:
            self.resize(1280, 820)

        self.setAcceptDrops(True)

        self.controller = AppController(self)
        self._build_ui()
        self._wire_controller()
        self._wire_toolbox()
        self._install_shortcuts()

        self._on_log("[i] LP-PC Suite v4.0.0 khởi động")
        self._on_log(
            "[i] Sẵn sàng nhận APK hoặc kết nối thiết bị ADB"
        )
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

        self.switches_panel = SwitchesPanel(
            self.controller.iap_manager
        )
        right_layout.addWidget(self.switches_panel)

        # Stacked pages
        self.stacked = QStackedWidget()
        self.stacked.addWidget(self._build_apps_page())
        self.stacked.addWidget(self._build_detail_page())
        self.stacked.addWidget(self._build_tools_page())

        # === SPLITTER giữa content và log (RESIZABLE) ===
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setObjectName("mainSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(4)
        splitter.addWidget(self.stacked)
        splitter.addWidget(self._build_log_panel())
        splitter.setStretchFactor(0, 4)   # content chiếm 4/5
        splitter.setStretchFactor(1, 1)   # log chiếm 1/5
        splitter.setSizes([600, 150])     # initial size

        self.main_splitter = splitter
        right_layout.addWidget(splitter, 1)

        root.addWidget(right, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(t("status.ready"))

    # ------------------------------------------------------------
    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 20, 8, 20)
        layout.setSpacing(6)

        logo = QLabel(t("sidebar.logo"))
        logo.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        logo.setStyleSheet("color: #58a6ff; padding: 12px 8px;")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)
        layout.addSpacing(20)

        self.btn_apps = QPushButton(t("sidebar.apps"))
        self.btn_apps.setCheckable(True)
        self.btn_apps.setChecked(True)
        self.btn_apps.setAutoExclusive(True)

        self.btn_detail = QPushButton(t("sidebar.detail"))
        self.btn_detail.setCheckable(True)
        self.btn_detail.setAutoExclusive(True)

        self.btn_tools = QPushButton(t("sidebar.tools"))
        self.btn_tools.setCheckable(True)
        self.btn_tools.setAutoExclusive(True)

        layout.addWidget(self.btn_apps)
        layout.addWidget(self.btn_detail)
        layout.addWidget(self.btn_tools)
        layout.addStretch()

        version = QLabel(t("sidebar.version"))
        version.setStyleSheet("color: #484f58; font-size: 11px;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        self.btn_apps.clicked.connect(
            lambda: self.stacked.setCurrentIndex(0)
        )
        self.btn_detail.clicked.connect(
            lambda: self.stacked.setCurrentIndex(1)
        )
        self.btn_tools.clicked.connect(
            lambda: self.stacked.setCurrentIndex(2)
        )
        return sidebar

    # ------------------------------------------------------------
    def _build_toolbar(self) -> QToolBar:
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            t("toolbar.search_placeholder")
        )
        self.search_edit.setMinimumWidth(220)
        self.search_edit.textChanged.connect(
            lambda _: self._filter_apps()
        )
        tb.addWidget(self.search_edit)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems([
            t("toolbar.filter_all"),
            t("toolbar.filter_license"),
            t("toolbar.filter_ads"),
            t("toolbar.filter_custom"),
            t("toolbar.filter_system"),
        ])
        self.filter_combo.currentTextChanged.connect(
            lambda _: self._filter_apps()
        )
        tb.addWidget(self.filter_combo)
        tb.addSeparator()

        btn_browse = QPushButton(t("toolbar.browse"))
        btn_browse.clicked.connect(self._on_browse_clicked)
        tb.addWidget(btn_browse)

        btn_download = QPushButton(t("toolbar.download"))
        btn_download.clicked.connect(self._on_download_clicked)
        tb.addWidget(btn_download)

        btn_workspace = QPushButton(t("toolbar.workspace"))
        btn_workspace.clicked.connect(self._on_workspace_clicked)
        tb.addWidget(btn_workspace)

        btn_reload = QPushButton(t("toolbar.reload"))
        btn_reload.clicked.connect(self._on_reload_clicked)
        tb.addWidget(btn_reload)

        tb.addSeparator()

        self.btn_toolbox = QPushButton(t("toolbar.toolbox"))
        self.btn_toolbox.clicked.connect(self._on_toolbox_clicked)
        tb.addWidget(self.btn_toolbox)

        return tb

    # ------------------------------------------------------------
    def _build_progress_panel(self) -> QWidget:
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
        self.app_list.itemDoubleClicked.connect(
            self._on_app_double_click
        )
        layout.addWidget(self.app_list)
        return page

    def _build_detail_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        back_bar = QWidget()
        back_bar.setStyleSheet(
            "background-color: #161b22;"
            "border-bottom: 1px solid #30363d;"
        )
        back_layout = QHBoxLayout(back_bar)
        back_layout.setContentsMargins(12, 6, 12, 6)

        back_btn = QPushButton(t("detail.back"))
        back_btn.setFixedHeight(28)
        back_btn.setStyleSheet(
            "QPushButton {"
            "  background: transparent; color: #58a6ff;"
            "  border: none; font-weight: bold;"
            "  text-align: left; padding: 4px 8px;"
            "}"
            "QPushButton:hover { color: #79c0ff; }"
        )
        back_btn.clicked.connect(
            lambda: self.stacked.setCurrentIndex(0)
        )
        back_layout.addWidget(back_btn)
        back_layout.addStretch()
        layout.addWidget(back_bar)

        self.apk_detail = APKDetailWidget()
        self.apk_detail.patch_action_requested.connect(
            self._on_detail_action
        )
        self.apk_detail.rebuild_requested.connect(
            self._on_rebuild_clicked
        )
        self.apk_detail.menu_of_patches_requested.connect(
            self._on_menu_of_patches_clicked
        )
        layout.addWidget(self.apk_detail, 1)
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
        """
        Log panel giờ là 1 QWidget trong QSplitter — resizable
        bằng cách kéo handle giữa content và log.
        """
        container = QWidget()
        container.setObjectName("logContainer")
        container.setMinimumHeight(60)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setObjectName("logHeader")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 4, 8, 4)
        h_layout.setSpacing(8)

        title = QLabel(t("log_panel.title"))
        title.setStyleSheet(
            "color: #8b949e; font-size: 11px; font-weight: bold;"
        )
        h_layout.addWidget(title)
        h_layout.addStretch()

        self.btn_clear_log = QPushButton(t("log_panel.clear"))
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

        # Collapse button (vẫn giữ để quick toggle)
        self.btn_collapse_log = QPushButton("⤓")
        self.btn_collapse_log.setFixedSize(24, 22)
        self.btn_collapse_log.setStyleSheet("""
            QPushButton {
                background: transparent; color: #8b949e;
                border: none; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { color: #58a6ff; }
        """)
        self.btn_collapse_log.setToolTip(
            t("log_panel.expand_tooltip")
        )
        self.btn_collapse_log.clicked.connect(
            self._toggle_collapse_log
        )
        h_layout.addWidget(self.btn_collapse_log)

        layout.addWidget(header)

        self.log = LogWidget()
        self.log.setMinimumHeight(40)
        layout.addWidget(self.log)

        return container

    # ============================================================
    # WIRING
    # ============================================================
    def _wire_controller(self) -> None:
        self.controller.log_message.connect(self._on_log)
        self.controller.status_message.connect(self._on_status)
        self.controller.analysis_ready.connect(self._on_analysis_ready)
        self.controller.progress_update.connect(self._on_progress)
        self.controller.progress_hide.connect(self._hide_progress)
        self.controller.show_detail_page.connect(
            self._show_detail_page
        )
        self.controller.step_update.connect(self._on_step_update)
        self.controller.safety_prompt_requested.connect(
            self._on_safety_prompt
        )

    def _wire_toolbox(self) -> None:
        self.toolbox = ToolboxMenu(self)
        self.toolbox.clone_requested.connect(
            self.controller._open_clone_dialog
        )
        self.toolbox.iap_manager_requested.connect(
            self._on_iap_manager
        )
        self.toolbox.download_patch_requested.connect(
            self._on_download_patch
        )
        self.toolbox.system_tool_requested.connect(
            self._on_system_tool
        )
        self.toolbox.patch_requested.connect(
            self._on_system_patch
        )

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+O"), self, self._on_browse_clicked)
        QShortcut(QKeySequence("Ctrl+D"), self, self._on_download_clicked)
        QShortcut(QKeySequence("Ctrl+W"), self, self._on_workspace_clicked)
        QShortcut(QKeySequence("Ctrl+L"), self, self._clear_log)
        QShortcut(QKeySequence("F5"), self, self._on_reload_clicked)
        QShortcut(QKeySequence("Esc"), self, self._on_escape)
        QShortcut(
            QKeySequence("Ctrl+F"), self,
            lambda: self.search_edit.setFocus(),
        )
        QShortcut(QKeySequence("Ctrl+T"), self, self._on_toolbox_clicked)
        QShortcut(QKeySequence("Ctrl+J"), self,
                  self._toggle_collapse_log)

    # ============================================================
    # EVENT HANDLERS
    # ============================================================
    def _on_browse_clicked(self) -> None:
        self.controller.browse_apk()

    def _on_download_clicked(self) -> None:
        self.controller.download_apk_dialog()

    def _on_workspace_clicked(self) -> None:
        self.controller.open_workspace()

    def _on_reload_clicked(self) -> None:
        self.app_list.clear_all()
        self.controller.load_device_apps()

    def _on_toolbox_clicked(self) -> None:
        btn = self.btn_toolbox
        pos = btn.mapToGlobal(btn.rect().bottomLeft())
        self.toolbox.exec(pos)

    def _on_escape(self) -> None:
        if self.stacked.currentIndex() != 0:
            self.stacked.setCurrentIndex(0)
            self.btn_apps.setChecked(True)

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

    def _on_menu_of_patches_clicked(self) -> None:
        self.controller.open_menu_of_patches(
            self.controller.last_package,
            self.controller.last_app_name,
            self.controller.last_colors,
            self.controller.last_findings,
            use_tree=True,
        )

    def _on_iap_manager(self) -> None:
        from .iap_manager_dialog import IAPManagerDialog
        dlg = IAPManagerDialog(
            self.controller.iap_manager, self.window()
        )
        dlg.exec()

    def _on_download_patch(self) -> None:
        from PyQt6.QtWidgets import QInputDialog
        url, ok = QInputDialog.getText(
            self, "Download Custom Patch",
            "URL của custom patch (.txt / .lpzip):",
        )
        if ok and url.strip():
            self._on_log(f"[*] Sẽ tải custom patch: {url}")

    def _on_system_tool(self, tool_name: str) -> None:
        messages = {
            "xposed_iap": "Xposed: Support IAP & LVL Emulation",
            "xposed_enable": "Xposed: Enable module",
            "backup": "Backup selected APK",
            "install_supersu": "Install SuperSU",
            "install_busybox": "Install/Update BusyBox",
            "clear_dalvik": "Clear Dalvik Cache",
            "move_system": "Move App to /system/app/",
            "disable_billing": "Disable Google Billing Emulation",
            "change_dir": "Change working directory",
        }
        msg = messages.get(tool_name, tool_name)
        self._on_log(f"[i] [Toolbox] {msg}")

    def _on_system_patch(
        self, action: str, features: dict
    ) -> None:
        if action == "system_patch":
            enabled = [k for k, v in features.items() if v]
            self._on_log(
                f"[*] [Toolbox] System patch: {', '.join(enabled)}"
            )
            QMessageBox.information(
                self, "System Patch",
                "System patch yêu cầu root + ADB.\n"
                "Đang phát triển.",
            )
        elif action == "test_patch":
            self._on_log("[*] [Toolbox] Chạy test patch...")

    def _filter_apps(self) -> None:
        text = self.search_edit.text().lower()
        filt = self.filter_combo.currentText()
        self.app_list.filter(text, filt)

    # ============================================================
    # CONTROLLER → UI
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
            self.progress_container.setVisible(True)
            self.progress_bar.setValue(pct)

    def _on_step_update(self, step_name: str, pct: int) -> None:
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
    # SAFETY PROMPT
    # ============================================================
    def _on_safety_prompt(
        self, reason: str, details: dict, count: int, callback
    ) -> None:
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(t("dialog.warning_title"))
        msg.setTextFormat(Qt.TextFormat.RichText)

        msg.setText(
            f"<b>Phát hiện <span style='color:#f85149;'>"
            f"{reason.upper()}</span> vượt ngưỡng {count} lần!</b>"
        )

        detail_lines = [
            f"&nbsp;&nbsp;• <b>{k}</b>: {v}"
            for k, v in details.items()
        ]
        msg.setInformativeText(
            "<b>Chi tiết:</b><br>"
            + "<br>".join(detail_lines)
            + "<br><br>"
            f"<b>{t('dialog.continue')}</b>: nâng ngưỡng +5% "
            f"và tiếp tục<br>"
            f"<b>{t('dialog.stop')}</b>: dừng pipeline an toàn"
        )

        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
        )
        msg.button(QMessageBox.StandardButton.Yes).setText(
            t("dialog.continue")
        )
        msg.button(QMessageBox.StandardButton.No).setText(
            t("dialog.stop")
        )
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        msg.setWindowModality(Qt.WindowModality.ApplicationModal)

        user_continue = msg.exec() == QMessageBox.StandardButton.Yes

        self.log.append_log(
            f"[{'✔' if user_continue else '✘'}] [Safety] User chọn "
            f"{'CONTINUE' if user_continue else 'STOP'}"
        )

        try:
            callback(user_continue)
        except Exception:
            pass

    # ============================================================
    # LOG PANEL — collapse toggle
    # ============================================================
    def _toggle_collapse_log(self) -> None:
        """Collapse/expand log bằng cách set splitter sizes."""
        if not hasattr(self, "main_splitter"):
            return

        sizes = self.main_splitter.sizes()
        if sizes[1] <= 60:
            # Expand
            total = sum(sizes)
            self.main_splitter.setSizes([int(total * 0.75), int(total * 0.25)])
            self.btn_collapse_log.setText("⤓")
        else:
            # Collapse
            total = sum(sizes)
            self.main_splitter.setSizes([total - 40, 40])
            self.btn_collapse_log.setText("⤒")

    def _clear_log(self) -> None:
        self.log.clear_log()

    # ============================================================
    # DRAG & DROP
    # ============================================================
    _DROP_EXTS = (".apk", ".xapk", ".apks")

    def _is_valid_drop(self, mime) -> bool:
        if not mime.hasUrls():
            return False
        for url in mime.urls():
            p = url.toLocalFile().lower()
            if p.endswith(self._DROP_EXTS):
                return True
        return False

    def dragEnterEvent(self, event) -> None:
        if self._is_valid_drop(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._is_valid_drop(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p.lower().endswith(self._DROP_EXTS):
                self._on_log(f"[*] Drop file: {p}")
                self.controller.load_apk(p)
                event.acceptProposedAction()
                return
        event.ignore()

    # ============================================================
    # CLOSE
    # ============================================================
    def closeEvent(self, event) -> None:
        self._on_log("[i] Đóng LP-PC Suite")
        event.accept()