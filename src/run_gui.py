"""Entry point cho GUI — chạy LP-PC Suite với giao diện đồ họa."""
from __future__ import annotations

import logging
import sys
import os

# Đảm bảo src/ trong path
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


# =============================================================
# UTILITIES: UTF-8 + LOG SILENCE
# Gọi TRƯỚC mọi import khác (ui.* có thể import androguard)
# =============================================================
def _ensure_utf8_console() -> None:
    """Windows cmd.exe cp1252 → UTF-8."""
    if sys.platform != "win32":
        return
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _silence_androguard() -> None:
    """Silence androguard logs (loguru + stdlib fallback)."""
    if os.environ.get("LP_ANDROGUARD_LOG", "").strip().lower() in (
        "1", "true", "yes", "on"
    ):
        return

    # Loguru (androguard 4.x)
    try:
        from loguru import logger as _loguru
        _loguru.disable("androguard")
    except ImportError:
        pass
    except Exception:
        pass

    # Stdlib fallback
    for name in list(logging.root.manager.loggerDict.keys()):
        if name == "androguard" or name.startswith("androguard."):
            lg = logging.getLogger(name)
            lg.setLevel(logging.CRITICAL)
            lg.propagate = False
            lg.disabled = True

    _ag = logging.getLogger("androguard")
    _ag.setLevel(logging.CRITICAL)
    _ag.propagate = False


def _silence_noisy_libs() -> None:
    for noisy, level in (
        ("urllib3", logging.WARNING),
        ("requests", logging.WARNING),
        ("asyncio", logging.WARNING),
        ("PIL", logging.WARNING),
    ):
        logging.getLogger(noisy).setLevel(level)


def _setup_environment() -> None:
    _ensure_utf8_console()
    _silence_androguard()
    _silence_noisy_libs()


# Gọi ngay khi module load — trước mọi import Qt/ui
_setup_environment()


from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal

from ui.main_window import MainWindow
from ui.styles import MATERIAL_DARK_STYLE
from core.smali_utils import RE_ENGINE, JSON_FAST


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # Silence qua helper (loguru + stdlib)
    _silence_androguard()
    _silence_noisy_libs()


class _UpdaterBridge(QObject):
    """Bridge: worker thread → Qt main thread."""
    update_available = pyqtSignal(object)


def _check_for_updates(bridge: _UpdaterBridge, window: MainWindow) -> None:
    """Chạy sau khi GUI hiện — non-blocking."""
    from core.github_updater import GitHubUpdater

    def _on_result(info):
        bridge.update_available.emit(info)

    GitHubUpdater().check_async(_on_result)


def _show_update_dialog(window: MainWindow, info) -> None:
    """Slot chạy trên main thread."""
    if info is None:
        return
    from PyQt6.QtWidgets import QMessageBox
    from PyQt6.QtGui import QDesktopServices
    from PyQt6.QtCore import QUrl

    msg = QMessageBox(window)
    msg.setWindowTitle("🎉 Có bản cập nhật mới")
    msg.setTextFormat(0x0004)  # RichText
    msg.setText(info.to_html())
    msg.setStandardButtons(
        QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Close
    )
    msg.button(QMessageBox.StandardButton.Open).setText("Mở trang tải")
    msg.button(QMessageBox.StandardButton.Close).setText("Để sau")

    if msg.exec() == QMessageBox.StandardButton.Open and info.download_url:
        QDesktopServices.openUrl(QUrl(info.download_url))


def main() -> int:
    _setup_environment()
    setup_logging()

    print(f"[i] Regex engine: {RE_ENGINE}")
    print(f"[i] Fast JSON:   {JSON_FAST}")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(MATERIAL_DARK_STYLE)

    from ui.exception_hook import install_gui_exception_hook
    install_gui_exception_hook()

    window = MainWindow()
    window.show()

    bridge = _UpdaterBridge()
    bridge.update_available.connect(
        lambda info: _show_update_dialog(window, info)
    )

    from PyQt6.QtCore import QTimer
    QTimer.singleShot(1000, lambda: _check_for_updates(bridge, window))

    return app.exec()


if __name__ == "__main__":
    _setup_environment()
    sys.exit(main())