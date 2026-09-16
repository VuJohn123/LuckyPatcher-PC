"""Global exception hook cho GUI — bắt mọi unhandled exception."""
from __future__ import annotations

import logging
import sys
import traceback
from datetime import datetime

from PyQt6.QtWidgets import QMessageBox

logger = logging.getLogger(__name__)


def install_gui_exception_hook(
    log_path: str = "logs/pipeline.log",
    show_dialog: bool = True,
) -> None:
    """
    Cài global exception hook. Khi có exception không bắt được:
      1. Ghi vào log file
      2. Hiện QMessageBox (nếu show_dialog)
      3. Gọi sys.__excepthook__ để không phá vỡ chuỗi

    Idempotent — gọi nhiều lần OK.
    """
    if getattr(sys, "_lp_exception_hook_installed", False):
        return
    sys._lp_exception_hook_installed = True

    def _hook(exc_type, exc_value, exc_tb):
        # Bỏ qua KeyboardInterrupt — user muốn thoát
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        # Format traceback
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        tb_text = "".join(tb_lines)

        # Log
        logger.critical(
            "Unhandled exception:\n%s", tb_text, exc_info=False
        )

        # Ghi file riêng cho crash report
        try:
            crash_dir = "logs"
            import os
            os.makedirs(crash_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            crash_file = os.path.join(crash_dir, f"crash_{ts}.log")
            with open(crash_file, "w", encoding="utf-8") as f:
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Python: {sys.version}\n")
                f.write(f"Platform: {sys.platform}\n\n")
                f.write(tb_text)
        except Exception:
            pass  # không để crash hook tự crash

        # Hiện dialog
        if show_dialog:
            try:
                from PyQt6.QtWidgets import QApplication
                if QApplication.instance() is not None:
                    msg = QMessageBox()
                    msg.setIcon(QMessageBox.Icon.Critical)
                    msg.setWindowTitle("Lỗi không mong đợi")
                    msg.setText(
                        f"<b>{exc_type.__name__}:</b> {exc_value}"
                    )
                    msg.setInformativeText(
                        f"Đã ghi log vào:\n{log_path}\n\n"
                        "Ứng dụng có thể không ổn định. "
                        "Vui lòng gửi log cho developer."
                    )
                    msg.setDetailedText(tb_text[-2000:])
                    msg.setStandardButtons(QMessageBox.StandardButton.Ok)
                    msg.exec()
            except Exception:
                pass  # không để crash trong hook

        # Vẫn gọi default hook để stderr có traceback
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
    logger.info("Global exception hook installed")