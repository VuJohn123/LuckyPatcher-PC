"""ADB bridge — install/uninstall/check root/reverse port."""
from __future__ import annotations

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


def _adb_available() -> bool:
    return shutil.which("adb") is not None


def install_apk(apk_path: str, timeout: int = 120) -> bool:
    """Cài APK qua ADB. Raise RuntimeError nếu thất bại."""
    if not _adb_available():
        raise RuntimeError("adb không có trong PATH")

    cmd = ["adb", "install", "-r", apk_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"ADB install timeout sau {timeout}s") from e

    if proc.returncode != 0 or "Success" not in proc.stdout:
        raise RuntimeError(f"ADB install failed: {proc.stderr or proc.stdout}")
    return True


def uninstall_app(package_name: str, timeout: int = 60) -> bool:
    if not _adb_available():
        return False
    try:
        subprocess.run(
            ["adb", "uninstall", package_name],
            capture_output=True, text=True, timeout=timeout,
        )
        return True
    except subprocess.SubprocessError as e:
        logger.warning("uninstall failed: %s", e)
        return False


def setup_reverse_port(remote_port: int, local_port: int) -> bool:
    """Setup adb reverse tcp:remote → tcp:local."""
    if not _adb_available():
        return False
    try:
        proc = subprocess.run(
            ["adb", "reverse", f"tcp:{remote_port}", f"tcp:{local_port}"],
            capture_output=True, text=True, timeout=10,
        )
        return proc.returncode == 0
    except subprocess.SubprocessError:
        return False


def check_root(timeout: int = 5) -> bool:
    """Kiểm tra thiết bị có root không."""
    if not _adb_available():
        return False
    try:
        proc = subprocess.run(
            ["adb", "shell", "su", "-c", "id"],
            capture_output=True, text=True, timeout=timeout,
        )
        return "uid=0" in proc.stdout
    except subprocess.SubprocessError:
        return False


def list_devices() -> list[str]:
    """Liệt kê ADB devices đang kết nối."""
    if not _adb_available():
        return []
    try:
        proc = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True, timeout=10,
        )
        lines = proc.stdout.strip().splitlines()[1:]
        return [ln.split()[0] for ln in lines if ln.strip() and "\tdevice" in ln]
    except subprocess.SubprocessError:
        return []