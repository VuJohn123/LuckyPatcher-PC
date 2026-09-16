"""
Chuyển AAB → APK bằng bundletool.jar.
Graceful: báo lỗi rõ nếu thiếu jar.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import zipfile

logger = logging.getLogger(__name__)


def aab_to_apk(aab_path: str, output_dir: str | None = None,
               log_callback=print) -> str | None:
    tools_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tools",
    )
    bundletool = os.path.join(tools_dir, "bundletool.jar")

    if not os.path.exists(bundletool):
        log_callback("[!] bundletool.jar không có — không convert được AAB")
        return None

    if output_dir is None:
        output_dir = os.path.dirname(aab_path)
    os.makedirs(output_dir, exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="aab_")
    apks = os.path.join(tmp, "app.apks")
    apk_out = os.path.join(
        output_dir,
        os.path.splitext(os.path.basename(aab_path))[0] + ".apk",
    )

    try:
        # Bước 1: build apks set
        cmd = [
            "java", "-jar", bundletool, "build-apks",
            f"--bundle={aab_path}",
            f"--output={apks}",
            "--mode=universal",
            "--overwrite",
        ]
        log_callback("[*] [Bundletool] Building APK set...")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            log_callback(f"[!] Bundletool failed: {proc.stderr[:300]}")
            return None

        # Bước 2: extract universal.apk
        if not os.path.exists(apks):
            return None

        with zipfile.ZipFile(apks, "r") as z:
            candidates = [
                n for n in z.namelist()
                if n.endswith(".apk") and "universal" in n.lower()
            ]
            if not candidates:
                candidates = [
                    n for n in z.namelist()
                    if n.startswith("standalones/") and n.endswith(".apk")
                ]
            if not candidates:
                log_callback("[!] Không tìm thấy universal APK trong bundle")
                return None

            with z.open(candidates[0]) as src, open(apk_out, "wb") as dst:
                shutil.copyfileobj(src, dst)

        log_callback(f"[✔] [Bundletool] APK: {apk_out}")
        return apk_out
    except subprocess.TimeoutExpired:
        log_callback("[!] Bundletool timeout")
        return None
    except (OSError, zipfile.BadZipFile) as e:
        log_callback(f"[!] Bundletool error: {e}")
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)