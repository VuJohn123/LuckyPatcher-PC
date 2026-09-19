"""
Resign APK — ký lại với testkey hoặc custom key.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile

from core.apk_utils import sign_apk
from core.smali_utils import get_all_smali_files

logger = logging.getLogger(__name__)


def _get_output_dir() -> str:
    """Output dir = workspace/output (không hardcode ~/Desktop)."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(base, "workspace", "output")
    os.makedirs(out, exist_ok=True)
    return out


class ResignPatcher:
    def __init__(self, apk_path: str, log_callback=print):
        self.apk_path = apk_path
        self.log = log_callback

    def resign_with_testkey(self) -> str | None:
        try:
            return sign_apk(
                self.apk_path, key_type="testkey",
                log_callback=self.log,
            )
        except Exception as e:
            self.log(f"[!] Resign failed: {e}")
            return None

    def change_package_name(self, new_package: str) -> str | None:
        from core.apk_utils import decompile_apk, recompile_apk

        tmp = tempfile.mkdtemp(prefix="resign_")
        decompiled = os.path.join(tmp, "decompiled")
        try:
            decompile_apk(
                self.apk_path, decompiled, force=True,
                log_callback=self.log,
            )

            manifest = os.path.join(decompiled, "AndroidManifest.xml")
            with open(manifest, "r", encoding="utf-8") as f:
                content = f.read()

            match = re.search(r'package="([^"]+)"', content)
            if not match:
                return None
            old = match.group(1)

            content = content.replace(old, new_package)
            with open(manifest, "w", encoding="utf-8") as f:
                f.write(content)

            old_path = old.replace(".", "/")
            new_path = new_package.replace(".", "/")
            for filepath in get_all_smali_files(decompiled):
                try:
                    with open(filepath, "r", encoding="utf-8",
                              errors="ignore") as f:
                        c = f.read()
                    if old_path in c:
                        c = c.replace(old_path, new_path)
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(c)
                except OSError:
                    continue

            out_apk = os.path.join(tmp, "renamed.apk")
            recompile_apk(decompiled, out_apk, log_callback=self.log)
            signed = sign_apk(out_apk, log_callback=self.log)

            # Output theo workspace, không Desktop
            dest = os.path.join(_get_output_dir(), os.path.basename(signed))
            shutil.copy2(signed, dest)
            self.log(f"[✔] [Resign] → {dest}")
            return dest
        except Exception as e:
            self.log(f"[!] Rename failed: {e}")
            return None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def patch(self) -> int:
        return 1 if self.resign_with_testkey() else 0