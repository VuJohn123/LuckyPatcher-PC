"""
Tool updater — check latest version của các tool trong tools/.

KHÔNG auto-download. Chỉ:
  1. Query GitHub releases API
  2. So sánh với version đã cài (từ tool --version hoặc filename)
  3. Notify user (log warning hoặc GUI toast)

Env:
  LP_TOOL_UPDATER_DISABLE=1  → tắt hoàn toàn
  LP_TOOL_UPDATER_CACHE_HOURS=24 (default)

Reference:
  - apktool: https://api.github.com/repos/iBotPeaches/Apktool/releases/latest
  - uber-apk-signer: https://api.github.com/repos/patrickfav/uber-apk-signer/releases/latest
  - bundletool: https://api.github.com/repos/google/bundletool/releases/latest
  - smali/baksmali: https://api.github.com/repos/google/smali/releases/latest  (redirect from JesusFreke)
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_DISABLE = os.environ.get(
    "LP_TOOL_UPDATER_DISABLE", ""
).strip().lower() in ("1", "true", "yes", "on")

_CACHE_HOURS = int(os.environ.get("LP_TOOL_UPDATER_CACHE_HOURS", "24") or "24")

# Registry: tool name → GitHub repo + cách detect version local
_TOOL_REGISTRY = {
    "apktool": {
        "repo": "iBotPeaches/Apktool",
        "jar": "apktool.jar",
        "version_cmd": ["java", "-jar", "{jar}", "--version"],
        "version_regex": r"(\d+\.\d+\.\d+)",
    },
    "uber-apk-signer": {
        "repo": "patrickfav/uber-apk-signer",
        "jar": "uber-apk-signer.jar",
        "version_cmd": None,  # jarsigner không có --version chuẩn
        "version_regex": None,
    },
    "bundletool": {
        "repo": "google/bundletool",
        "jar": "bundletool.jar",
        "version_cmd": ["java", "-jar", "{jar}", "version"],
        "version_regex": r"(\d+\.\d+\.\d+)",
    },
    "smali": {
        "repo": "google/smali",
        "jar": "smali.jar",
        "version_cmd": ["java", "-jar", "{jar}", "--version"],
        "version_regex": r"(\d+\.\d+\.\d+)",
    },
    "baksmali": {
        "repo": "google/smali",
        "jar": "baksmali.jar",
        "version_cmd": ["java", "-jar", "{jar}", "--version"],
        "version_regex": r"(\d+\.\d+\.\d+)",
    },
}


@dataclass
class ToolUpdateInfo:
    name: str
    installed: str        # "" nếu không detect được
    latest: str
    update_available: bool
    download_url: str


def check_all_updates(
    tools_dir: str,
    log_callback=print,
    timeout_sec: float = 8.0,
) -> list[ToolUpdateInfo]:
    """
    Check all tools. Non-blocking spirit — chỉ HTTP GET GitHub API.

    Return list of ToolUpdateInfo (chỉ những tool có update).
    """
    if _DISABLE:
        log_callback("[i] [ToolUpdater] Disabled via env")
        return []

    # Cache check
    cache_path = Path(tools_dir) / ".update_cache.json"
    cached = _load_cache(cache_path)
    if cached is not None:
        log_callback(f"[i] [ToolUpdater] Dùng cache ({len(cached)} tools)")
        return cached

    results: list[ToolUpdateInfo] = []

    for name, cfg in _TOOL_REGISTRY.items():
        jar_path = Path(tools_dir) / "bin" / cfg["jar"]
        if not jar_path.exists():
            continue

        # 1. Local version
        installed = _detect_local_version(jar_path, cfg)

        # 2. Remote latest
        latest_info = _fetch_latest_release(cfg["repo"], timeout_sec)
        if not latest_info:
            continue
        latest_version = latest_info.get("version", "")
        download_url = latest_info.get("download_url", "")

        if not latest_version:
            continue

        # 3. Compare
        needs_update = _is_newer(latest_version, installed)
        if needs_update:
            results.append(ToolUpdateInfo(
                name=name,
                installed=installed or "?",
                latest=latest_version,
                update_available=True,
                download_url=download_url,
            ))
            log_callback(
                f"[!] [ToolUpdater] {name}: {installed or '?'} → "
                f"{latest_version} (dowload: {download_url})"
            )
        else:
            logger.debug(
                "ToolUpdater %s: %s = latest", name, installed
            )

    _save_cache(cache_path, results)
    return results


# ============================================================
# HELPERS
# ============================================================
def _detect_local_version(jar_path: Path, cfg: dict) -> str:
    """Chạy tool --version nếu có, parse bằng regex."""
    cmd_tpl = cfg.get("version_cmd")
    regex = cfg.get("version_regex")
    if not cmd_tpl or not regex:
        # Fallback: parse từ filename
        m = re.search(r"(\d+\.\d+\.\d+)", jar_path.name)
        return m.group(1) if m else ""

    cmd = [c.format(jar=str(jar_path)) for c in cmd_tpl]
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=10, encoding="utf-8", errors="replace",
        )
        out = (r.stdout or "") + (r.stderr or "")
        m = re.search(regex, out)
        return m.group(1) if m else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _fetch_latest_release(repo: str, timeout_sec: float) -> dict | None:
    """Query GitHub releases API."""
    try:
        import urllib.request
        import urllib.error
    except ImportError:
        return None

    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "LP-PC-Suite-ToolUpdater/1.0",
    })

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug("GitHub API fail %s: %s", repo, e)
        return None

    tag = data.get("tag_name", "")
    m = re.search(r"(\d+\.\d+\.\d+)", tag)
    version = m.group(1) if m else ""

    # Tìm asset jar phù hợp
    download_url = ""
    for asset in data.get("assets", []):
        name = asset.get("name", "").lower()
        if name.endswith(".jar"):
            download_url = asset.get("browser_download_url", "")
            break

    return {"version": version, "download_url": download_url}


def _is_newer(latest: str, installed: str) -> bool:
    """True nếu latest > installed. installed="" → True (coi như cần update)."""
    if not installed:
        return True
    try:
        def _parts(v):
            return tuple(int(x) for x in v.split(".")[:4])
        return _parts(latest) > _parts(installed)
    except Exception:
        return False


def _load_cache(cache_path: Path) -> list[ToolUpdateInfo] | None:
    if not cache_path.exists():
        return None
    try:
        age = time.time() - cache_path.stat().st_mtime
        if age > _CACHE_HOURS * 3600:
            return None
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return [ToolUpdateInfo(**d) for d in data]
    except Exception:
        return None


def _save_cache(cache_path: Path, results: list[ToolUpdateInfo]) -> None:
    try:
        payload = [r.__dict__ for r in results]
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, cache_path)
    except Exception as e:
        logger.debug("Cache save fail: %s", e)