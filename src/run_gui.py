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
from ui.main_window import MainWindow
from ui.styles import MATERIAL_DARK_STYLE
from core.smali_utils import RE_ENGINE, JSON_FAST


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Tắt debug noisy của androguard
    logging.getLogger("androguard").setLevel(logging.WARNING)


def main() -> int:
    setup_logging()

    print(f"[i] Regex engine: {RE_ENGINE}")
    print(f"[i] Fast JSON:   {JSON_FAST}")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(MATERIAL_DARK_STYLE)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())