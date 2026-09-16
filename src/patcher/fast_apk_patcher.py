"""Fast patcher — sửa trực tiếp file cụ thể, không decompile toàn bộ."""
from __future__ import annotations

import logging
import os
import re
import tempfile
import zipfile

logger = logging.getLogger(__name__)


class FastAPKPatcher:
    """
    Sửa trực tiếp nội dung file trong APK (ZIP) mà không cần decompile.
    Chỉ phù hợp với thay đổi nhỏ (manifest string, specific smali).
    """

    def __init__(self, apk_path: str, log_callback=print):
        self.apk_path = apk_path
        self.log = log_callback

    def patch_zip_entry(self, entry_name: str, pattern: str,
                        replacement: str, output_apk: str | None = None) -> str | None:
        """Thay thế pattern trong 1 file entry của APK."""
        if output_apk is None:
            output_apk = self.apk_path.replace(".apk", "_patched.apk")

        tmp = tempfile.mkdtemp(prefix="fast_")
        try:
            with zipfile.ZipFile(self.apk_path, "r") as zin:
                with zipfile.ZipFile(output_apk, "w", zipfile.ZIP_DEFLATED) as zout:
                    for item in zin.infolist():
                        data = zin.read(item.filename)
                        if item.filename == entry_name:
                            try:
                                text = data.decode("utf-8", errors="ignore")
                                text = re.sub(pattern, replacement, text)
                                data = text.encode("utf-8")
                            except Exception as e:
                                logger.warning("Patch entry failed: %s", e)
                        zout.writestr(item, data)
            return output_apk
        except (zipfile.BadZipFile, OSError) as e:
            self.log(f"[!] FastAPKPatcher failed: {e}")
            return None
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def patch(self) -> int:
        """Interface tương thích — trả về 0 vì cần tham số cụ thể."""
        return 0