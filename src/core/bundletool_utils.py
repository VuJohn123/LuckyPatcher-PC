"""
Chuyển AAB → APK bằng bundletool.jar.
Graceful: báo lỗi rõ nếu thiếu jar.

v2 (2026):
  - `mode` parameter ("universal" | "default") — default=universal
    backward compat.
  - `device_id` → `--device-id=<serial>` cho device-specific APK.
  - Signing options: `keystore`, `ks_pass`, `ks_key_alias`.
  - `list_apks_entries()` diagnostic helper.
  - `extract_apks_to_folder()` — extract all APKs từ .apks bundle.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import zipfile

logger = logging.getLogger(__name__)

# Bundletool modes supported
_VALID_MODES = frozenset({
    "universal", "default", "system", "persistent", "instant",
})

# Max entries to log in list_apks_entries
_MAX_LIST_LOG = 50


def _find_bundletool_jar() -> str:
    """Locate tools/bundletool.jar relative to this file."""
    tools_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tools",
    )
    return os.path.join(tools_dir, "bundletool.jar")


def _build_build_apks_cmd(
    bundletool: str,
    aab_path: str,
    apks_out: str,
    mode: str,
    device_id: str | None,
    keystore: str | None,
    ks_pass: str | None,
    ks_key_alias: str | None,
) -> list[str]:
    """Build argv cho `bundletool build-apks`."""
    cmd = [
        "java", "-jar", bundletool, "build-apks",
        f"--bundle={aab_path}",
        f"--output={apks_out}",
        f"--mode={mode}",
        "--overwrite",
    ]
    if device_id:
        cmd.append(f"--device-id={device_id}")
    if keystore:
        cmd.append(f"--ks={keystore}")
        if ks_pass:
            cmd.append(f"--ks-pass=pass:{ks_pass}")
        if ks_key_alias:
            cmd.append(f"--ks-key-alias={ks_key_alias}")
    return cmd


def _pick_apk_entry(
    names: list[str], mode: str,
) -> str | None:
    """
    Chọn entry APK phù hợp từ list entries trong .apks.

    Priority:
      1. universal.apk (mode=universal)
      2. standalones/standalone-*.apk (fallback)
      3. splits/base-master.apk (mode=default, no merge)
    Return None nếu không có candidate.
    """
    if mode == "universal":
        for n in names:
            if n.endswith(".apk") and "universal" in n.lower():
                return n
    # Fallback: standalone
    for n in names:
        if n.startswith("standalones/") and n.endswith(".apk"):
            return n
    # Last-resort: base-master.apk từ splits (không merge)
    for n in names:
        if n.endswith("/base-master.apk") or n == "base-master.apk":
            return n
    return None


def aab_to_apk(
    aab_path: str,
    output_dir: str | None = None,
    *,
    mode: str = "universal",
    device_id: str | None = None,
    keystore: str | None = None,
    ks_pass: str | None = None,
    ks_key_alias: str | None = None,
    log_callback=print,
) -> str | None:
    """
    Convert AAB → APK qua bundletool.

    Args:
        aab_path: path tới .aab file
        output_dir: output folder (default: cùng folder với aab)
        mode: "universal" (single APK) | "default" (split APKs)
        device_id: target serial cho device-specific APK
        keystore: signing keystore path (optional)
        ks_pass: keystore password
        ks_key_alias: key alias trong keystore
        log_callback: logging function

    Returns:
        Path tới extracted .apk (file đơn), hoặc None nếu fail.
    """
    if mode not in _VALID_MODES:
        log_callback(
            f"[!] [Bundletool] Invalid mode: {mode} "
            f"(valid: {sorted(_VALID_MODES)})"
        )
        return None

    bundletool = _find_bundletool_jar()
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
        cmd = _build_build_apks_cmd(
            bundletool, aab_path, apks, mode, device_id,
            keystore, ks_pass, ks_key_alias,
        )
        log_callback(
            f"[*] [Bundletool] Building APK set "
            f"(mode={mode}"
            + (f", device={device_id}" if device_id else "")
            + ")"
        )
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            log_callback(
                f"[!] Bundletool failed: {proc.stderr[:300]}"
            )
            return None

        # Bước 2: extract APK từ bundle
        if not os.path.exists(apks):
            log_callback("[!] .apks file không được tạo")
            return None

        with zipfile.ZipFile(apks, "r") as z:
            names = z.namelist()
            candidate = _pick_apk_entry(names, mode)
            if not candidate:
                log_callback(
                    "[!] Không tìm thấy APK entry trong bundle "
                    f"(mode={mode})"
                )
                return None

            with z.open(candidate) as src, open(apk_out, "wb") as dst:
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


def extract_apks_to_folder(
    apks_path: str,
    out_folder: str,
    log_callback=print,
) -> int:
    """
    Extract tất cả APK từ `.apks` bundle vào 1 folder.

    Returns: số APK đã extract (0 nếu fail).
    """
    if not os.path.exists(apks_path):
        log_callback(f"[!] .apks không tồn tại: {apks_path}")
        return 0

    os.makedirs(out_folder, exist_ok=True)
    extracted = 0
    try:
        with zipfile.ZipFile(apks_path, "r") as z:
            for name in z.namelist():
                if not name.endswith(".apk"):
                    continue
                # Flatten: standalones/foo.apk → foo.apk
                out_name = os.path.basename(name)
                if not out_name:
                    continue
                out_path = os.path.join(out_folder, out_name)
                try:
                    with z.open(name) as src, open(
                        out_path, "wb"
                    ) as dst:
                        shutil.copyfileobj(src, dst)
                    extracted += 1
                except (OSError, zipfile.BadZipFile) as e:
                    logger.debug(
                        "Skip %s: %s", name, e,
                    )
        log_callback(
            f"[✔] [Bundletool] Extracted {extracted} APK → "
            f"{out_folder}"
        )
        return extracted
    except (OSError, zipfile.BadZipFile) as e:
        log_callback(f"[!] Extract failed: {e}")
        return 0


def list_apks_entries(
    apks_path: str,
    log_callback=print,
) -> list[str]:
    """
    List tất cả entries trong `.apks` file (diagnostic helper).

    Returns: list entries (rỗng nếu fail).
    """
    if not os.path.exists(apks_path):
        log_callback(f"[!] .apks không tồn tại: {apks_path}")
        return []

    try:
        with zipfile.ZipFile(apks_path, "r") as z:
            names = z.namelist()
    except (OSError, zipfile.BadZipFile) as e:
        log_callback(f"[!] Không đọc được .apks: {e}")
        return []

    log_callback(
        f"[*] [Bundletool] {apks_path}: {len(names)} entries"
    )
    for n in names[:_MAX_LIST_LOG]:
        log_callback(f"      • {n}")
    if len(names) > _MAX_LIST_LOG:
        log_callback(f"      ... +{len(names) - _MAX_LIST_LOG} more")
    return names