"""Tiện ích xử lý APK — decompile, recompile, sign, merge split."""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import zipfile

logger = logging.getLogger(__name__)

# Project root: file này ở <root>/src/core/apk_utils.py → parents[2]
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
TOOLS_DIR = os.path.join(_PROJECT_ROOT, "tools")
NAILGUN = shutil.which("ng")


def get_tool_path(name: str) -> str:
    """
    Resolve tool path — hỗ trợ cả layout cũ (tools/*.jar) và mới (tools/bin/*).
    Trả về path mới nếu tồn tại, else fallback legacy.
    """
    organized = os.path.join(TOOLS_DIR, "bin", name)
    if os.path.exists(organized):
        return organized
    return os.path.join(TOOLS_DIR, name)


def get_apk_hash(apk_path: str) -> str:
    hasher = hashlib.md5()
    with open(apk_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_cache_dir(apk_path: str, base_cache_dir: str | None = None) -> str:
    """
    Cache dir cho 1 APK.
    Default base: <project_root>/workspace/cache (KHÔNG phải src/workspace).
    """
    if base_cache_dir is None:
        base_cache_dir = os.path.join(_PROJECT_ROOT, "workspace", "cache")
    cache_dir = os.path.join(base_cache_dir, get_apk_hash(apk_path))
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _java_cmd(jar_name: str, memory: str = "4096m") -> list[str]:
    """Trả về prefix lệnh Java, ưu tiên Nailgun nếu có."""
    jar = get_tool_path(jar_name)
    if NAILGUN:
        return [NAILGUN, jar]
    return ["java", f"-Xmx{memory}", "-jar", jar]


def decompile_apk(
    apk_path: str,
    output_dir: str,
    force: bool = True,
    no_res: bool = True,
    jobs: int | None = None,
    max_memory: str = "4096m",
    log_callback=print,
    max_retries: int = 2,
    use_cache: bool = True,
) -> str:
    if jobs is None:
        jobs = max(1, (os.cpu_count() or 4) - 1)

    if use_cache and not force:
        cache_dir = get_cache_dir(apk_path)
        if os.path.exists(os.path.join(cache_dir, "apktool.yml")):
            log_callback("[*] Cache hit — dùng decompiled đã cache")
            if os.path.exists(output_dir):
                shutil.rmtree(output_dir, ignore_errors=True)
            shutil.copytree(cache_dir, output_dir)
            return output_dir

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
        proc = subprocess.run(cmd, capture_output=True, text=True)

        if proc.stdout:
            log_callback(proc.stdout[-500:])
        if proc.stderr:
            log_callback(proc.stderr[-500:])

        if proc.returncode == 0:
            if use_cache:
                _safe_save_cache(output_dir, apk_path, log_callback)
            return output_dir

        if attempt == 0:
            use_no_res = True
        elif attempt == 1:
            current_jobs, current_mem = 1, "8192m"

    raise RuntimeError(f"Decompile failed after {max_retries + 1} attempts")


def _safe_save_cache(
    output_dir: str, apk_path: str, log_callback
) -> None:
    """
    Lưu decompiled vào cache. Không crash pipeline nếu gặp lỗi
    (long path Windows, permission, ...).
    """
    try:
        cache_dir = get_cache_dir(apk_path)
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir, ignore_errors=True)
        try:
            shutil.copytree(output_dir, cache_dir)
            log_callback("[*] [Cache] Decompiled saved")
        except shutil.Error as e:
            # copytree raise shutil.Error với list (src, dst, msg)
            n = len(e.args[0]) if e.args else 0
            log_callback(
                f"[i] [Cache] Bỏ qua {n} file lỗi "
                f"(thường do path > 260 ký tự trên Windows)"
            )
        except OSError as e:
            log_callback(f"[i] [Cache] Save failed: {e}")
    except Exception as e:
        log_callback(f"[i] [Cache] Disabled: {e}")


def recompile_apk(
    decompiled_path: str,
    output_apk: str,
    forced_package_id: int | None = None,
    log_callback=print,
    max_retries: int = 1,
) -> str:
    use_aapt2 = False
    for attempt in range(max_retries + 1):
        cmd = _java_cmd("apktool.jar")
        cmd += ["b", decompiled_path, "-o", output_apk]
        if forced_package_id is not None:
            cmd += ["--forced-package-id", str(forced_package_id)]
        if use_aapt2:
            cmd.append("--use-aapt2")

        log_callback(f"[*] [Apktool] Recompile attempt {attempt + 1}")
        proc = subprocess.run(cmd, capture_output=True, text=True)

        if proc.stdout:
            log_callback(proc.stdout[-500:])
        if proc.stderr:
            log_callback(proc.stderr[-500:])

        if proc.returncode == 0:
            return output_apk

        if attempt == 0:
            use_aapt2 = True

    raise RuntimeError(f"Recompile failed after {max_retries + 1} attempts")


def sign_apk(apk_path: str, key_type: str = "testkey", log_callback=print) -> str:
    log_callback(f"[*] [Signer] Signing with {key_type}...")

    if key_type == "testkey":
        cmd = _java_cmd("uber-apk-signer.jar")
        cmd += ["--apks", apk_path]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"Signing failed: {proc.stderr}")
        return apk_path.replace(".apk", "-aligned-debugSigned.apk")

    from core.sign_with_key import APKSigner
    return APKSigner(TOOLS_DIR).sign_apk(apk_path, key_type)


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