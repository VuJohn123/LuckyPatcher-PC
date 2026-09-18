"""Tiện ích xử lý APK — decompile, recompile, sign, verify, merge split."""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import threading
import time
import zipfile
from typing import Callable

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
TOOLS_DIR = os.path.join(_PROJECT_ROOT, "tools")
NAILGUN = shutil.which("ng")

# Fail tolerance cho copytree (5% file fail → cache considered broken)
_COPY_FAIL_TOLERANCE = 0.05

# Disk threshold riêng cho READ vs WRITE
_DISK_MIN_READ_PCT = 3.0    # cache LOAD chỉ cần đọc
_DISK_MIN_WRITE_PCT = 15.0  # cache SAVE cần không gian


# ============================================================
# JAVA SUBPROCESS WITH STREAMING + HEARTBEAT
# ============================================================
def _run_java_with_heartbeat(
    cmd: list[str],
    log_callback: Callable[[str], None],
    label: str,
    timeout_sec: int = 1800,
    heartbeat_sec: int = 10,
) -> tuple[int, str]:
    """Chạy Java subprocess với streaming output + heartbeat."""
    start = time.monotonic()
    log_callback(f"[*] [{label}] Starting...")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as e:
        log_callback(f"[!] [{label}] Không chạy được: {e}")
        return -1, ""

    stop_hb = threading.Event()
    output_lines: list[str] = []
    killed = {"flag": False}

    def _heartbeat():
        while not stop_hb.wait(heartbeat_sec):
            elapsed = time.monotonic() - start
            log_callback(f"[i] [{label}] vẫn đang chạy... ({elapsed:.0f}s)")
            if elapsed > timeout_sec:
                log_callback(f"[!] [{label}] Timeout {timeout_sec}s — kill")
                killed["flag"] = True
                try:
                    proc.kill()
                except OSError:
                    pass
                return

    def _stream():
        try:
            if proc.stdout:
                for line in proc.stdout:
                    s = line.rstrip()
                    if s:
                        log_callback(f"    {s}")
                        output_lines.append(s)
                        if len(output_lines) > 300:
                            output_lines.pop(0)
        except Exception:
            pass

    hb_thread = threading.Thread(target=_heartbeat, daemon=True)
    stream_thread = threading.Thread(target=_stream, daemon=True)
    hb_thread.start()
    stream_thread.start()

    try:
        rc = proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        killed["flag"] = True
        try:
            proc.kill()
        except OSError:
            pass
        rc = -1

    stop_hb.set()
    stream_thread.join(timeout=3)

    elapsed = time.monotonic() - start
    if killed["flag"]:
        log_callback(f"[!] [{label}] Killed sau {elapsed:.1f}s")
    else:
        log_callback(f"[*] [{label}] Xong trong {elapsed:.1f}s (rc={rc})")

    return rc, "\n".join(output_lines)


# ============================================================
# SYMLINK / JUNCTION FAST PATH
# ============================================================
def _try_link(src: str, dst: str) -> bool:
    """
    Thử tạo symlink/junction thay vì copy → gần như tức thời.
    Windows: junction (mklink /J) — không cần admin.
    Unix: os.symlink.
    Trả True nếu thành công.
    """
    # Cleanup dst
    try:
        if os.path.islink(dst) or os.path.isfile(dst):
            os.remove(dst)
        elif os.path.isdir(dst):
            shutil.rmtree(dst, ignore_errors=True)
    except OSError:
        return False

    try:
        if os.name == "nt":
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", dst, src],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        else:
            os.symlink(src, dst, target_is_directory=True)
            return True
    except (OSError, subprocess.SubprocessError):
        return False


# ============================================================
# SAFE COPYTREE — mode read/write + verify count
# ============================================================
def _safe_copytree(
    src: str,
    dst: str,
    log_callback: Callable[[str], None],
    label: str = "Cache",
    heartbeat_sec: int = 15,
    mode: str = "write",          # "read" (cache load) | "write" (cache save)
    fail_tolerance: float = _COPY_FAIL_TOLERANCE,
) -> bool:
    """
    Copy tree với:
      - mode=read: thử symlink/junction trước (near-instant)
      - disk check theo mode (read=3%, write=15%)
      - verify count: fail nếu >fail_tolerance file fail

    Trả True nếu OK (hoặc link thành công). Raise RuntimeError nếu
    fail quá nhiều.
    """
    # ---- mode=read: fast path link ----
    if mode == "read":
        if _try_link(src, dst):
            log_callback(f"[✔] [{label}] Linked (junction/symlink) — no disk cost")
            return True
        # Fallback to copy

    # ---- Disk check theo mode ----
    min_pct = _DISK_MIN_READ_PCT if mode == "read" else _DISK_MIN_WRITE_PCT
    try:
        usage = shutil.disk_usage(os.path.dirname(dst) or dst)
        free_pct = usage.free * 100 / usage.total
        if free_pct < min_pct:
            log_callback(
                f"[i] [{label}] Disk còn {free_pct:.1f}% (<{min_pct}%) "
                f"— skip {mode}"
            )
            return False
    except OSError:
        pass

    # ---- Count files ----
    try:
        total = sum(len(files) for _, _, files in os.walk(src))
        log_callback(f"[*] [{label}] Copy {total} files → {dst}")
    except OSError:
        total = 0

    # ---- Cleanup dst ----
    if os.path.exists(dst):
        shutil.rmtree(dst, ignore_errors=True)

    # ---- Copy with heartbeat + per-file verify ----
    start = time.monotonic()
    stop_hb = threading.Event()

    def _heartbeat():
        while not stop_hb.wait(heartbeat_sec):
            elapsed = time.monotonic() - start
            log_callback(f"[i] [{label}] vẫn đang copy... ({elapsed:.0f}s)")

    hb = threading.Thread(target=_heartbeat, daemon=True)
    hb.start()

    copied = 0
    failed = 0
    failed_samples: list[str] = []

    try:
        for root, dirs, files in os.walk(src):
            rel = os.path.relpath(root, src)
            target_root = dst if rel == "." else os.path.join(dst, rel)
            try:
                os.makedirs(target_root, exist_ok=True)
            except OSError as e:
                log_callback(f"[!] [{label}] makedirs {target_root}: {e}")
                failed += len(files)
                continue
            for f in files:
                s = os.path.join(root, f)
                t = os.path.join(target_root, f)
                try:
                    shutil.copy2(s, t)
                    copied += 1
                except (OSError, shutil.Error) as e:
                    failed += 1
                    if len(failed_samples) < 3:
                        failed_samples.append(f"{f}: {e}")
    finally:
        stop_hb.set()
        hb.join(timeout=3)

    elapsed = time.monotonic() - start
    grand = copied + failed
    fail_ratio = failed / grand if grand else 0.0

    for sample in failed_samples:
        log_callback(f"[i] [{label}] skip: {sample}")

    if failed > 0:
        log_callback(
            f"[!] [{label}] {failed}/{grand} file fail "
            f"({fail_ratio*100:.2f}%) sau {elapsed:.1f}s"
        )

    if fail_ratio > fail_tolerance:
        raise RuntimeError(
            f"[{label}] Copy fail ratio {fail_ratio*100:.2f}% > "
            f"{fail_tolerance*100:.0f}% — cache sẽ bị corrupt, bỏ."
        )

    log_callback(f"[✔] [{label}] Copied {copied}/{grand} in {elapsed:.1f}s")
    return True


# ============================================================
# TOOL PATH
# ============================================================
def get_tool_path(name: str) -> str:
    organized = os.path.join(TOOLS_DIR, "bin", name)
    if os.path.exists(organized):
        return organized
    return os.path.join(TOOLS_DIR, name)


# ============================================================
# HASHING / CACHE
# ============================================================
def get_apk_hash(apk_path: str) -> str:
    hasher = hashlib.md5()
    with open(apk_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_cache_dir(apk_path: str, base_cache_dir: str | None = None) -> str:
    if base_cache_dir is None:
        base_cache_dir = os.path.join(_PROJECT_ROOT, "workspace", "cache")
    cache_dir = os.path.join(base_cache_dir, get_apk_hash(apk_path))
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _java_cmd(jar_name: str, memory: str = "4096m") -> list[str]:
    jar = get_tool_path(jar_name)
    if NAILGUN:
        return [NAILGUN, jar]
    return ["java", f"-Xmx{memory}", "-jar", jar]


# ============================================================
# DECOMPILE — cache TTL + heartbeat
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
    if jobs is None:
        jobs = max(1, (os.cpu_count() or 4) - 1)

    # ---------------- Cache lookup ----------------
    if use_cache and not force:
        cache_dir = get_cache_dir(apk_path)
        cached_yml = os.path.join(cache_dir, "apktool.yml")
        if os.path.exists(cached_yml):
            age_days = (
                time.time() - os.path.getmtime(cached_yml)
            ) / 86400
            if age_days <= cache_ttl_days:
                log_callback(
                    f"[*] Cache hit (age {age_days:.1f}d ≤ "
                    f"{cache_ttl_days}d) — dùng cache"
                )
                try:
                    ok = _safe_copytree(
                        cache_dir, output_dir,
                        log_callback=log_callback,
                        label="Cache load",
                        heartbeat_sec=15,
                        mode="read",         # ← FIX: cho phép link/read
                    )
                    if ok:
                        return output_dir
                    log_callback(
                        "[i] Cache load skip — decompile lại từ đầu"
                    )
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

        rc, _ = _run_java_with_heartbeat(
            cmd,
            log_callback=log_callback,
            label="Apktool",
            timeout_sec=1800,
            heartbeat_sec=10,
        )

        if rc == 0:
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
    """Lưu decompiled vào cache. Verify count — không silent partial."""
    try:
        cache_dir = get_cache_dir(apk_path)
        _safe_copytree(
            output_dir, cache_dir,
            log_callback=log_callback,
            label="Cache save",
            heartbeat_sec=15,
            mode="write",
        )
    except RuntimeError as e:
        log_callback(f"[!] [Cache] Save aborted (partial fail): {e}")
    except Exception as e:
        log_callback(f"[i] [Cache] Disabled: {e}")


# ============================================================
# RECOMPILE — verify + fallback
# ============================================================
def recompile_apk(
    decompiled_path: str,
    output_apk: str,
    forced_package_id: int | None = None,
    log_callback=print,
    max_retries: int = 1,
    verify: bool = True,
    input_apk_for_delta: str | None = None,
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

        rc, _ = _run_java_with_heartbeat(
            cmd,
            log_callback=log_callback,
            label="Apktool Recompile",
            timeout_sec=1800,
            heartbeat_sec=10,
        )

        if rc == 0:
            if verify:
                _verify_recompiled_apk(
                    output_apk, log_callback,
                    input_apk_for_delta=input_apk_for_delta,
                )
            return output_apk

        if attempt == 0:
            use_aapt2 = True

    raise RuntimeError(
        f"Recompile failed after {max_retries + 1} attempts"
    )


def _verify_recompiled_apk(
    apk_path: str,
    log_callback,
    input_apk_for_delta: str | None = None,
) -> None:
    """Verify APK output sau recompile (ZIP + manifest + dex + size delta)."""
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
        raise RuntimeError(f"APK không phải ZIP hợp lệ: {e}")

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

        rc, _ = _run_java_with_heartbeat(
            cmd,
            log_callback=log_callback,
            label="Signer",
            timeout_sec=600,
            heartbeat_sec=10,
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
    """Verify APK có META-INF signature entries (v1)."""
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
        raise RuntimeError(f"Signed APK corrupt: {e}")

    if not has_v1:
        log_callback(
            "[!] [Verify] Không thấy v1 signature trong META-INF/ "
            "(có thể chỉ có v2/v3 — vẫn OK)"
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