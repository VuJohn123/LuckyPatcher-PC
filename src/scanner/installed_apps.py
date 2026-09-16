"""Liệt kê app đã cài qua ADB — graceful fallback."""
from __future__ import annotations

import logging
import re
import shutil
import subprocess

logger = logging.getLogger(__name__)

_PKG_RE = re.compile(r"^package:(.+)$", re.MULTILINE)


def _adb_available() -> bool:
    return shutil.which("adb") is not None


def get_installed_apps(third_party_only: bool = True) -> list[dict]:
    """Trả về list [{name, package}]. Rỗng nếu ADB không có."""
    if not _adb_available():
        logger.info("ADB không có — trả về danh sách rỗng")
        return []

    cmd = ["adb", "shell", "pm", "list", "packages"]
    if third_party_only:
        cmd.append("-3")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except subprocess.SubprocessError as e:
        logger.warning("ADB list failed: %s", e)
        return []

    packages = _PKG_RE.findall(proc.stdout or "")
    return [
        {"name": pkg.split(".")[-1].capitalize(), "package": pkg}
        for pkg in packages
        if pkg.strip()
    ]