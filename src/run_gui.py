"""Entry point cho GUI — chạy LP-PC Suite với giao diện đồ họa."""
from __future__ import annotations

import logging
import sys
import os

# Đảm bảo src/ trong path
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

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

    # Silence androguard sub-loggers triệt để
    for name in list(logging.root.manager.loggerDict):
        if name == "androguard" or name.startswith("androguard."):
            lg = logging.getLogger(name)
            lg.setLevel(logging.ERROR)
            lg.propagate = False

    for noisy in ("urllib3", "requests", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class _UpdaterBridge(QObject):
    """Bridge: worker thread → Qt main thread."""
    update_available = pyqtSignal(object)


def _check_for_updates(bridge: _UpdaterBridge, window: MainWindow) -> None:
    """Chạy sau khi GUI hiện — non-blocking."""
    from core.github_updater import GitHubUpdater

    def _on_result(info):
        # Chạy trong worker thread → emit signal (Qt queue về main)
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
    setup_logging()

    print(f"[i] Regex engine: {RE_ENGINE}")
    print(f"[i] Fast JSON:   {JSON_FAST}")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(MATERIAL_DARK_STYLE)

    window = MainWindow()
    window.show()

    # Check update — chạy sau 1s để GUI kịp render
    bridge = _UpdaterBridge()
    bridge.update_available.connect(
        lambda info: _show_update_dialog(window, info)
    )

    from PyQt6.QtCore import QTimer
    QTimer.singleShot(1000, lambda: _check_for_updates(bridge, window))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())