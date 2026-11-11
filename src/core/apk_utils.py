"""
APK utilities — public API for decompile/recompile/sign/verify/merge.

Internal helpers đã tách:
  - core/subprocess_runner  : java subprocess + watchdog
  - core/fs_utils           : junction/robocopy/safe copy
  - core/archive_utils      : 7z/zip archive
  - core/cache_manager      : decompiled cache dispatcher

v2 fixes:
  - Import `_run_java_with_heartbeat` alias (missing re-export bug).
  - Import `_decide_cache_format`, `_cache_save`, `_cache_load` aliases.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import zipfile

from core.archive_utils import (
    archive_via_7z as _archive_via_7z,
)
from core.archive_utils import (
    archive_via_python as _archive_via_python,
)
from core.archive_utils import (
    extract_via_7z as _extract_via_7z,
)
from core.archive_utils import (
    extract_via_python as _extract_via_python,
)
from core.archive_utils import (
    find_7zip as _find_7zip,
)
from core.cache_manager import (
    cache_is_valid,
    cache_load,
    cache_mtime,
    cache_save,
    get_apk_hash,
    get_cache_dir,
)
from core.cache_manager import (
    cache_load as _cache_load,
)
from core.cache_manager import (
    cache_save as _cache_save,
)
from core.cache_manager import (
    decide_cache_format as _decide_cache_format,
)
from core.fs_utils import (
    has_robocopy as _find_robocopy,
)
from core.fs_utils import (
    is_link_to as _is_link_to,
)

# Backward compat re-exports — tests + callers import trực tiếp từ apk_utils
from core.fs_utils import (
    remove_dst as _remove_dst,
)
from core.fs_utils import (
    robocopy_copy as _robocopy_copy,
)
from core.fs_utils import (
    safe_copytree as _safe_copytree,
)
from core.fs_utils import (
    try_link as _try_link,
)
from core.subprocess_runner import (
    run_java_with_heartbeat,
)
from core.subprocess_runner import (
    run_java_with_heartbeat as _run_java_with_heartbeat,
)

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
TOOLS_DIR = os.path.join(_PROJECT_ROOT, "tools")
NAILGUN = shutil.which("ng")

# apktool/smali diagnostics that mean a patcher emitted invalid smali.
# Re-decompiling with resources cannot fix these — fail fast instead.
_SMALI_ERROR_MARKERS = (
    "Could not smali file",
    "An abstract method cannot have any instructions",
    "Invalid directive",
    "Error for input",
)


class SmaliAssemblyError(RuntimeError):
    """Patcher output cannot be assembled (retrying decompile won't help)."""


# ============================================================
# TOOL PATH
# ============================================================
def get_tool_path(name: str) -> str:
    organized = os.path.join(TOOLS_DIR, "bin", name)
    if os.path.exists(organized):
        return organized
    return os.path.join(TOOLS_DIR, name)


def _java_cmd(jar_name: str, memory: str = "4096m") -> list[str]:
    jar = get_tool_path(jar_name)
    if NAILGUN:
        return [NAILGUN, jar]
    return ["java", f"-Xmx{memory}", "-jar", jar]


# ============================================================
# DECOMPILE
# ============================================================
def decompile_apk(
    apk_path: str,
    output_dir: str,
    force: bool = False,
    no_res: bool = True,
    jobs: int | None = None,
    max_memory: str = "4096m",
    log_callback=print,
    max_retries: int = 2,
    use_cache: bool = True,
    cache_ttl_days: int = 7,
) -> str:
    import time

    if jobs is None:
        jobs = max(1, (os.cpu_count() or 4) - 1)

    if use_cache and not force:
        # Cache key includes the decode profile: a no-res tree cannot
        # satisfy a mode that needs resources.
        cache_dir = get_cache_dir(
            apk_path, profile="nores" if no_res else "full"
        )
        if cache_is_valid(cache_dir):
            age_days = (time.time() - cache_mtime(cache_dir)) / 86400
            if age_days <= cache_ttl_days:
                log_callback(
                    f"[*] Cache hit (age {age_days:.1f}d ≤ "
                    f"{cache_ttl_days}d) — dùng cache"
                )
                try:
                    ok = cache_load(cache_dir, output_dir, log_callback)
                    if ok:
                        return output_dir
                    log_callback("[i] Cache load skip — decompile lại")
                except RuntimeError as e:
                    log_callback(f"[!] Cache corrupt: {e} — decompile lại")
            else:
                log_callback(
                    f"[i] Cache cũ ({age_days:.1f}d) — decompile lại"
                )

    current_jobs, current_mem, use_no_res = jobs, max_memory, no_res

    for attempt in range(max_retries + 1):
        cmd = _java_cmd("apktool.jar", current_mem)
        cmd += ["d", apk_path, "-o", output_dir, "-f",
                "--jobs", str(current_jobs)]
        if use_no_res:
            cmd.append("--no-res")

        log_callback(
            f"[*] [Apktool] Attempt {attempt + 1}/{max_retries + 1}: "
            f"jobs={current_jobs}, no_res={use_no_res}"
        )

        rc, _ = run_java_with_heartbeat(
            cmd,
            log_callback=log_callback,
            label="Apktool",
            timeout_sec=1800,
            heartbeat_sec=30,
        )

        if rc == 0:
            if use_cache:
                try:
                    # Save under the profile actually decoded (a retry
                    # may downgrade to no-res).
                    cache_save(
                        output_dir,
                        get_cache_dir(
                            apk_path,
                            profile="nores" if use_no_res else "full",
                        ),
                        log_callback,
                    )
                except Exception as e:
                    log_callback(f"[i] [Cache] Save failed: {e}")
            return output_dir

        _remove_dst(output_dir)

        if attempt == 0:
            use_no_res = True
        elif attempt == 1:
            current_jobs, current_mem = 1, "8192m"

    raise RuntimeError(
        f"Decompile failed after {max_retries + 1} attempts"
    )


# ============================================================
# RECOMPILE
# ============================================================
def recompile_apk(
    decompiled_path: str,
    output_apk: str,
    forced_package_id: int | None = None,
    log_callback=print,
    max_retries: int = 1,
    verify: bool = True,
    input_apk_for_delta: str | None = None,
    jobs: int | None = None,
) -> str:
    outputs: list[str] = []
    for attempt in range(max_retries + 1):
        cmd = _java_cmd("apktool.jar")
        cmd += ["b", decompiled_path, "-o", output_apk]
        if jobs is not None:
            # apktool defaults to one job per logical CPU. Builds mix CPU
            # (smaling) with first-touch reads, so 2x CPU measured faster
            # on the 4-core audit machine (301.9s -> 242.9s mean).
            cmd += ["--jobs", str(jobs)]
        if forced_package_id is not None:
            cmd += ["--forced-package-id", str(forced_package_id)]
        # NOTE: apktool 3.x defaults to aapt2; --use-aapt2 was removed (error: Unrecognized option)

        log_callback(f"[*] [Apktool] Recompile attempt {attempt + 1}")

        rc, out = run_java_with_heartbeat(
            cmd,
            log_callback=log_callback,
            label="Apktool Recompile",
            timeout_sec=1800,
            heartbeat_sec=30,
        )
        outputs.append(out)

        if rc == 0:
            if verify:
                _verify_recompiled_apk(
                    output_apk, log_callback,
                    input_apk_for_delta=input_apk_for_delta,
                )
            return output_apk

        if attempt == 0:
            pass  # retry once with single job for OOM-prone big APKs
            log_callback("[i] [Apktool] Retrying recompile...")

    last_output = "\n".join(outputs)
    if any(marker in last_output for marker in _SMALI_ERROR_MARKERS):
        bad = re.search(
            r"Could not smali file:\s*(.+)", last_output,
        )
        detail = f": {bad.group(1).strip()}" if bad else ""
        raise SmaliAssemblyError(
            f"Recompile failed: patcher emitted invalid smali{detail}"
        )

    raise RuntimeError(
        f"Recompile failed after {max_retries + 1} attempts"
    )


def _verify_recompiled_apk(
    apk_path: str,
    log_callback,
    input_apk_for_delta: str | None = None,
) -> None:
    if not os.path.exists(apk_path):
        raise RuntimeError(f"Output APK không tồn tại: {apk_path}")

    size = os.path.getsize(apk_path)
    if size < 100:
        raise RuntimeError(f"Output APK quá nhỏ ({size} byte) — corrupt")

    try:
        with zipfile.ZipFile(apk_path, "r") as z:
            bad = z.testzip()
            if bad is not None:
                raise RuntimeError(f"APK có entry corrupt: {bad}")
            names = z.namelist()
    except zipfile.BadZipFile as e:
        raise RuntimeError(
            f"APK không phải ZIP hợp lệ: {e}"
        ) from e

    if "AndroidManifest.xml" not in names:
        raise RuntimeError("APK thiếu AndroidManifest.xml — recompile fail")

    dex_count = sum(1 for n in names if n.endswith(".dex"))
    if dex_count == 0:
        raise RuntimeError("APK không có file .dex — recompile fail")

    delta_msg = ""
    if input_apk_for_delta and os.path.exists(input_apk_for_delta):
        try:
            input_size = os.path.getsize(input_apk_for_delta)
            if input_size > 0:
                ratio = size / input_size
                delta_msg = f", delta {ratio:.2f}x vs input"
                if ratio > 10:
                    log_callback(
                        f"[!] [Verify] Output lớn bất thường "
                        f"({ratio:.1f}x input) — kiểm tra lại"
                    )
        except OSError:
            pass

    log_callback(
        f"[✔] [Verify] APK valid: "
        f"{size / 1024 / 1024:.1f} MB, {dex_count} dex, "
        f"{len(names)} entries{delta_msg}"
    )


# ============================================================
# SIGN
# ============================================================
def sign_apk(
    apk_path: str,
    key_type: str = "testkey",
    log_callback=print,
    verify: bool = True,
) -> str:
    log_callback(f"[*] [Signer] Signing with {key_type}...")

    if key_type == "testkey":
        cmd = _java_cmd("uber-apk-signer.jar")
        cmd += ["--apks", apk_path]

        rc, _ = run_java_with_heartbeat(
            cmd,
            log_callback=log_callback,
            label="Signer",
            timeout_sec=600,
            heartbeat_sec=30,
        )
        if rc != 0:
            raise RuntimeError(f"Signing failed (rc={rc})")
        signed = apk_path.replace(".apk", "-aligned-debugSigned.apk")
    else:
        from core.sign_with_key import APKSigner
        signed = APKSigner(TOOLS_DIR).sign_apk(apk_path, key_type)

    if verify:
        _verify_signed_apk(signed, log_callback)

    return signed


def _verify_signed_apk(apk_path: str, log_callback) -> None:
    if not os.path.exists(apk_path):
        raise RuntimeError(f"Signed APK không tồn tại: {apk_path}")

    try:
        with zipfile.ZipFile(apk_path, "r") as z:
            names = z.namelist()
            has_v1 = any(
                n.startswith("META-INF/") and
                (n.endswith(".RSA") or n.endswith(".DSA")
                 or n.endswith(".EC") or n.endswith(".SF"))
                for n in names
            )
    except zipfile.BadZipFile as e:
        raise RuntimeError(f"Signed APK corrupt: {e}") from e

    if not has_v1:
        log_callback(
            "[!] [Verify] Không thấy v1 signature trong META-INF/"
        )
    else:
        log_callback("[✔] [Verify] Signature present (v1 scheme)")


# ============================================================
# MERGE SPLIT APKS
# ============================================================
def merge_split_apks(input_dir: str, output_apk: str, log_callback=print) -> str:
    apk_files = sorted(f for f in os.listdir(input_dir) if f.endswith(".apk"))
    if not apk_files:
        raise ValueError("Không có APK nào trong folder")

    base_apk = next(
        (f for f in apk_files if "base" in f.lower() or "master" in f.lower()),
        apk_files[0],
    )
    shutil.copy2(os.path.join(input_dir, base_apk), output_apk)

    existing = set()
    with zipfile.ZipFile(output_apk, "r") as z:
        existing = set(z.namelist())

    with zipfile.ZipFile(output_apk, "a") as zout:
        for f in apk_files:
            if f == base_apk:
                continue
            try:
                with zipfile.ZipFile(os.path.join(input_dir, f), "r") as zin:
                    for item in zin.namelist():
                        if item not in existing:
                            zout.writestr(item, zin.read(item))
                            existing.add(item)
            except (zipfile.BadZipFile, OSError) as e:
                log_callback(f"[!] Bỏ qua split lỗi {f}: {e}")

    log_callback(f"[*] Merged {len(apk_files)} split APKs → {output_apk}")
    return output_apk


# ============================================================
# RE-EXPORT (backward compat)
# ============================================================
__all__ = [
    # Public API
    "decompile_apk", "recompile_apk", "sign_apk", "merge_split_apks",
    "get_tool_path", "get_apk_hash", "get_cache_dir",
    # Private (tests import trực tiếp)
    "_safe_copytree", "_find_7zip", "_archive_via_7z",
    "_extract_via_7z", "_archive_via_python", "_extract_via_python",
    "_cache_save", "_cache_load", "_decide_cache_format",
    "_run_java_with_heartbeat", "_remove_dst", "_try_link",
    "_is_link_to", "_robocopy_copy", "_find_robocopy",
]
