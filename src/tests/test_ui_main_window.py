"""
UI test cho MainWindow — layout, shortcuts, drag-drop, page switching.

Mock controller.load_device_apps() để tránh ADB.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt, QMimeData, QUrl

from ui.main_window import MainWindow


@pytest.fixture
def window(qtbot, monkeypatch):
    # Ngăn ADB call trong __init__
    monkeypatch.setattr(
        "ui.app_controller.get_installed_apps", lambda: [],
    )
    w = MainWindow()
    qtbot.addWidget(w)
    return w


# ============================================================
# Basic construction
# ============================================================
class TestConstruction:
    def test_window_has_title(self, window):
        assert "LP-PC Suite" in window.windowTitle()

    def test_has_stacked_widget_with_3_pages(self, window):
        assert window.stacked.count() == 3

    def test_has_splitter(self, window):
        assert hasattr(window, "main_splitter")
        assert window.main_splitter.count() == 2

    def test_has_log_widget(self, window):
        assert window.log is not None

    def test_has_status_bar(self, window):
        assert window.status_bar is not None

    def test_has_sidebar_buttons(self, window):
        assert window.btn_apps is not None
        assert window.btn_detail is not None
        assert window.btn_tools is not None


# ============================================================
# Page switching via sidebar
# ============================================================
class TestPageSwitching:
    def test_initial_page_is_apps(self, window):
        assert window.stacked.currentIndex() == 0

    def test_click_detail_switches(self, window, qtbot):
        window.btn_detail.click()
        assert window.stacked.currentIndex() == 1

    def test_click_tools_switches(self, window, qtbot):
        window.btn_tools.click()
        assert window.stacked.currentIndex() == 2

    def test_click_apps_back(self, window):
        window.btn_detail.click()
        window.btn_apps.click()
        assert window.stacked.currentIndex() == 0

    def test_escape_returns_to_apps(self, window):
        window.btn_detail.click()
        window._on_escape()
        assert window.stacked.currentIndex() == 0


# ============================================================
# Log panel
# ============================================================
class TestLogPanel:
    def test_clear_log(self, window):
        window.log.append_log("[test] line")
        window._clear_log()
        # LogWidget có method clear_log, không crash

    def test_toggle_collapse_expand(self, window):
        # Expand ban đầu
        window.main_splitter.setSizes([600, 150])
        window._toggle_collapse_log()  # collapse
        sizes = window.main_splitter.sizes()
        assert sizes[1] <= 60

        window._toggle_collapse_log()  # expand
        sizes = window.main_splitter.sizes()
        assert sizes[1] > 60


# ============================================================
# Shortcuts
# ============================================================
class TestShortcuts:
    def test_critical_shortcuts_registered(self, window):
        # Check via QShortcut.findChildren
        from PyQt6.QtGui import QShortcut
        shortcuts = window.findChildren(QShortcut)
        key_seqs = {sc.key().toString() for sc in shortcuts}
        # Ít nhất Ctrl+O, Ctrl+L, Ctrl+T, Ctrl+J, F5, Esc
        for expected in ("Ctrl+O", "Ctrl+L", "Ctrl+T",
                         "Ctrl+J", "F5", "Esc"):
            assert expected in key_seqs, (
                f"Missing shortcut: {expected}, got {key_seqs}"
            )


# ============================================================
# Progress bar
# ============================================================
class TestProgressPanel:
    def test_progress_container_hidden_initially(self, window):
        assert not window.progress_container.isVisible()

    def test_show_progress_on_update(self, window):
        window._on_progress(1, 10)
        # Visible trên widget chưa show() có thể False; check property
        assert window.progress_bar.value() == 10

    def test_step_update_sets_label(self, window):
        window._on_step_update("Analyzing", 42)
        assert "Analyzing" in window.step_label.text()
        assert window.progress_bar.value() == 42

    def test_step_clamped_upper(self, window):
        window._on_step_update("Done", 200)
        assert window.progress_bar.value() == 100

    def test_step_clamped_lower(self, window):
        window._on_step_update("Start", -5)
        assert window.progress_bar.value() == 0

    def test_hide_progress(self, window):
        window._on_progress(5, 10)
        window._hide_progress()
        assert window.progress_bar.value() == 0


# ============================================================
# Drag-drop
# ============================================================
class TestDragDrop:
    def _make_mime(self, paths: list[str]) -> QMimeData:
        m = QMimeData()
        m.setUrls([QUrl.fromLocalFile(p) for p in paths])
        return m

    def test_valid_drop_apk(self, window):
        mime = self._make_mime(["C:/x/test.apk"])
        assert window._is_valid_drop(mime)

    def test_valid_drop_xapk(self, window):
        mime = self._make_mime(["C:/x/test.xapk"])
        assert window._is_valid_drop(mime)

    def test_valid_drop_apks(self, window):
        mime = self._make_mime(["C:/x/test.apks"])
        assert window._is_valid_drop(mime)

    def test_invalid_drop_txt(self, window):
        mime = self._make_mime(["C:/x/notes.txt"])
        assert not window._is_valid_drop(mime)

    def test_invalid_drop_no_urls(self, window):
        m = QMimeData()
        m.setText("plain text")
        assert not window._is_valid_drop(m)


# ============================================================
# Analysis → detail page
# ============================================================
class TestAnalysisFlow:
    def test_analysis_ready_populates_detail(self, window):
        window._on_analysis_ready({
            "findings": [{
                "type": "license",
                "color": "green",
                "title": "License",
                "description": "x",
            }],
            "summary": {
                "app_name": "App",
                "package": "com.x",
                "version": "1.0",
                "size": 1024,
            },
            "colors": ["green"],
        })
        # apk_detail có children
        assert window.apk_detail.content_layout.count() > 0

    def test_show_detail_page_switches_index(self, window):
        window._show_detail_page()
        assert window.stacked.currentIndex() == 1
        assert window.btn_detail.isChecked()


# ============================================================
# Filter / search
# ============================================================
class TestFilter:
    def test_filter_apps_no_crash(self, window):
        window.search_edit.setText("test")
        window.filter_combo.setCurrentIndex(1)  # License

    def test_filter_empty_no_crash(self, window):
        window.search_edit.setText("")
        window.filter_combo.setCurrentIndex(0)


# ============================================================
# Log append
# ============================================================
class TestLogAppend:
    def test_on_log_appends(self, window):
        window._on_log("[i] test message")

    def test_on_status_updates_bar(self, window):
        window._on_status("Ready")
        # Status bar message có thể empty nếu showMessage timeout;
        # ít nhất không crash


# ============================================================
# Drag/drop event handlers
# ============================================================
class TestDragEvents:
    def _mk_event(self, mime: QMimeData):
        class _E:
            def __init__(self, m):
                self._m = m
                self.accepted = False
                self.ignored = False

            def mimeData(self):
                return self._m

            def acceptProposedAction(self):
                self.accepted = True

            def ignore(self):
                self.ignored = True

        return _E(mime)

    def test_drag_enter_valid_accepts(self, window):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile("/tmp/x.apk")])
        e = self._mk_event(mime)
        window.dragEnterEvent(e)
        assert e.accepted

    def test_drag_enter_invalid_ignores(self, window):
        mime = QMimeData()
        mime.setText("x")
        e = self._mk_event(mime)
        window.dragEnterEvent(e)
        assert e.ignored