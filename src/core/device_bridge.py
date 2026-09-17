"""ADB bridge — install/uninstall/check root/reverse port."""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import zipfile

logger = logging.getLogger(__name__)


def _adb_available() -> bool:
    return shutil.which("adb") is not None


def _extract_package_from_apk(apk_path: str) -> str | None:
    """Extract package name từ AndroidManifest.xml (binary) qua androguard."""
    try:
        from androguard.core.apk import APK
        return APK(apk_path).get_package()
    except Exception:
        # Fallback: dùng aapt nếu có
        try:
            proc = subprocess.run(
                ["aapt", "dump", "badging", apk_path],
                capture_output=True, text=True, timeout=10,
            )
            m = re.search(r"package: name='([^']+)'", proc.stdout)
            return m.group(1) if m else None
        except Exception:
            return None


def install_apk(
    apk_path: str,
    timeout: int = 120,
    auto_uninstall_on_mismatch: bool = True,
) -> bool:
    """
    Cài APK qua ADB. Raise RuntimeError nếu thất bại.

    Nếu `INSTALL_FAILED_UPDATE_INCOMPATIBLE` → auto-uninstall app cũ
    (do signature mismatch) và thử lại 1 lần.
    """
    if not _adb_available():
        raise RuntimeError("adb không có trong PATH")

    try:
        _do_install(apk_path, timeout)
        return True
    except RuntimeError as e:
        msg = str(e)
        if (
            auto_uninstall_on_mismatch
            and "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in msg
        ):
            logger.warning(
                "Signature mismatch — auto-uninstall app cũ và retry"
            )
            pkg = _extract_package_from_apk(apk_path)
            if pkg:
                subprocess.run(
                    ["adb", "uninstall", pkg],
                    capture_output=True, text=True, timeout=60,
                )
                logger.info("Uninstalled %s, retry install", pkg)
                _do_install(apk_path, timeout)
                return True
            else:
                raise RuntimeError(
                    f"{msg}\n"
                    f"Không extract được package name để uninstall"
                ) from e
        else:
            raise


def _do_install(apk_path: str, timeout: int) -> None:
    cmd = ["adb", "install", "-r", apk_path]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"ADB install timeout sau {timeout}s") from e

    if proc.returncode != 0 or "Success" not in proc.stdout:
        raise RuntimeError(
            f"ADB install failed: {proc.stderr or proc.stdout}"
        )


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