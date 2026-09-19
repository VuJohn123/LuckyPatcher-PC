"""
Tải custom patch từ patch.chelpus.com với retry + timeout.

v2 fixes:
  - URL security: validate scheme (chỉ https), block private IP,
    block metadata endpoint (SSRF guard).
  - Sanitize patch_name → filename (không path traversal).
  - Size limit download (max_download_size_mb từ config).
  - Kiểm tra content-length trước khi ghi.
"""
from __future__ import annotations

import logging
import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# URL security helpers — optional, dùng nếu có
try:
    from core.url_security import (
        sanitize_filename as _sanitize_filename,
        validate_url as _validate_url,
    )
    _HAS_URL_SEC = True
except ImportError:
    _HAS_URL_SEC = False
    logger.warning(
        "core.url_security không khả dụng — bỏ qua SSRF guard"
    )


BASE_URL = "https://patch.chelpus.com"
_DEFAULT_MAX_DOWNLOAD_MB = 500


def _safe_filename(name: str) -> str:
    """Basename + strip traversal + limit length."""
    if _HAS_URL_SEC:
        try:
            return _sanitize_filename(name)
        except Exception:
            pass
    # Fallback
    base = os.path.basename(name.replace("\\", "/"))
    safe = "".join(
        c for c in base if c.isalnum() or c in "._-"
    )
    return safe[:200] or "patch.bin"


def _is_url_safe(url: str) -> tuple[bool, str]:
    """Return (is_safe, reason)."""
    if _HAS_URL_SEC:
        try:
            _validate_url(url)
            return True, ""
        except Exception as e:
            return False, str(e)
    # Fallback: check scheme
    if not url.startswith("https://"):
        return False, "URL phải bắt đầu bằng https://"
    return True, ""


class CustomPatchDownloader:
    def __init__(
        self,
        download_dir: str | None = None,
        log_callback=print,
        config: dict | None = None,
    ):
        if download_dir is None:
            download_dir = os.path.join(
                os.path.expanduser("~"), "Documents",
                "LP_PC_Suite", "patches",
            )
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)
        self.log = log_callback

        net = (config or {}).get("network", {})
        self.timeout = (
            net.get("connect_timeout", 10),
            net.get("read_timeout", 30),
        )
        self.max_download_mb = net.get(
            "max_download_size_mb", _DEFAULT_MAX_DOWNLOAD_MB
        )

        self.session = requests.Session()
        retry = Retry(
            total=net.get("max_retries", 3),
            backoff_factor=net.get("backoff_factor", 1.5),
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def download_patch(self, patch_name: str) -> str | None:
        # 1. Sanitize patch_name (ngăn path traversal)
        safe_name = _safe_filename(patch_name)
        if not safe_name:
            self.log(f"[!] [PatchDL] Tên patch không hợp lệ: {patch_name!r}")
            return None

        # 2. Build URL
        url = f"{BASE_URL}/{safe_name}"

        # 3. Validate URL (SSRF guard)
        is_safe, reason = _is_url_safe(url)
        if not is_safe:
            self.log(f"[!] [PatchDL] URL không an toàn: {reason}")
            return None

        dest = os.path.join(self.download_dir, safe_name)
        max_bytes = self.max_download_mb * 1024 * 1024

        try:
            self.log(f"[*] [PatchDL] GET {url}")
            resp = self.session.get(
                url, stream=True, timeout=self.timeout,
                allow_redirects=True,
            )
            resp.raise_for_status()

            # 4. Content-length check (nếu server cung cấp)
            cl = resp.headers.get("Content-Length")
            if cl and cl.isdigit() and int(cl) > max_bytes:
                self.log(
                    f"[!] [PatchDL] Quá lớn: "
                    f"{int(cl) // 1024 // 1024} MB "
                    f"> {self.max_download_mb} MB"
                )
                return None

            # 5. Stream download với size limit
            written = 0
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > max_bytes:
                        self.log(
                            f"[!] [PatchDL] Vượt giới hạn "
                            f"{self.max_download_mb} MB — abort"
                        )
                        f.close()
                        try:
                            os.remove(dest)
                        except OSError:
                            pass
                        return None
                    f.write(chunk)

            self.log(
                f"[✔] [PatchDL] Downloaded: {dest} "
                f"({written // 1024} KB)"
            )
            return dest

        except requests.RequestException as e:
            self.log(f"[!] [PatchDL] Download failed: {e}")
        except OSError as e:
            self.log(f"[!] [PatchDL] File write failed: {e}")
        return None