"""Clone app — đổi package name + rebuild."""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile

from core.apk_utils import decompile_apk, recompile_apk, sign_apk
from core.smali_utils import get_all_smali_files

logger = logging.getLogger(__name__)

_PKG_RE = re.compile(r'package="([^"]+)"')


def _get_output_dir() -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(base, "workspace", "output", "clones")
    os.makedirs(out, exist_ok=True)
    return out


class AppCloner:
    def __init__(self, apk_path: str, new_package: str, log_callback=print):
        self.apk_path = apk_path
        self.new_package = new_package
        self.log = log_callback
        self.temp_dir = tempfile.mkdtemp(prefix="clone_")

    def clone(self) -> str | None:
        self.log(f"[*] [AppCloner] Cloning → {self.new_package}")
        decompiled = os.path.join(self.temp_dir, "decompiled")

        try:
            decompile_apk(
                self.apk_path, decompiled, force=True,
                log_callback=self.log,
            )
        except Exception as e:
            self.log(f"[!] Decompile failed: {e}")
            return None

        manifest = os.path.join(decompiled, "AndroidManifest.xml")
        try:
            with open(manifest, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            return None

        match = _PKG_RE.search(content)
        if not match:
            self.log("[!] Không tìm thấy package trong manifest")
            return None
        old_package = match.group(1)

        content = content.replace(old_package, self.new_package)
        try:
            with open(manifest, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError:
            return None

        old_path = old_package.replace(".", "/")
        new_path = self.new_package.replace(".", "/")
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

        out_apk = os.path.join(self.temp_dir, "cloned.apk")
        try:
            recompile_apk(decompiled, out_apk, log_callback=self.log)
            signed = sign_apk(out_apk, log_callback=self.log)
        except Exception as e:
            self.log(f"[!] Rebuild failed: {e}")
            return None

        # Output trong workspace/clones, không Desktop
        dest = os.path.join(_get_output_dir(), os.path.basename(signed))
        try:
            shutil.copy2(signed, dest)
        except OSError:
            return None

        self.log(f"[✔] [AppCloner] {dest}")
        return dest

    def cleanup(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def patch(self) -> int:
        return 1 if self.clone() else 0