"""Tải APK từ nhiều nguồn — có retry, timeout, URL validation, size limit."""
from __future__ import annotations

import ipaddress
import logging
import os
import re
import socket
import zipfile
from urllib.parse import unquote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


# ============================================================
# SECURITY CONSTANTS
# ============================================================
ALLOWED_SCHEMES = frozenset({"http", "https"})
MAX_DOWNLOAD_SIZE = 500 * 1024 * 1024          # 500 MB
MAX_REDIRECTS = 5
BLOCKED_HOSTS = frozenset({
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
    "169.254.169.254",                          # AWS metadata
})


class UnsafeDownloadError(Exception):
    """URL không an toàn — SSRF, scheme lạ, kích thước vượt giới hạn."""


def _validate_url(url: str) -> str:
    """
    Validate URL trước khi download. Chống:
      - Non-http(s) scheme (file://, ftp://, gopher://)
      - SSRF vào localhost / metadata endpoint / private IP
      - URL rỗng / không parse được
    """
    if not url or not isinstance(url, str):
        raise UnsafeDownloadError("URL rỗng hoặc không hợp lệ")

    parsed = urlparse(url.strip())

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeDownloadError(
            f"Scheme không được phép: {parsed.scheme!r} "
            f"(chỉ {sorted(ALLOWED_SCHEMES)})"
        )

    host = (parsed.hostname or "").lower()
    if not host:
        raise UnsafeDownloadError("URL thiếu host")

    # Block hostname đen
    if host in BLOCKED_HOSTS:
        raise UnsafeDownloadError(f"Host bị chặn: {host}")

    # Block IP private/link-local/loopback nếu host là IP
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise UnsafeDownloadError(f"IP nội bộ bị chặn: {host}")
    except ValueError:
        # host là domain, không phải IP → OK
        pass

    # Chỉ cho phép ký tự hợp lệ trong hostname
    if not re.match(r"^[a-z0-9.\-]+$", host):
        raise UnsafeDownloadError(f"Hostname chứa ký tự lạ: {host}")

    return url.strip()


class APKDownloader:
    """Tải APK từ APKPure, APKMody, Uptodown, URL trực tiếp."""

    BASE_URLS = {
        "apkpure": "https://d.apkpure.com/b/APK",
        "apkmody": "https://apkmody.io",
        "uptodown": "https://api.uptodown.com/v4",
    }

    def __init__(self, download_dir: str | None = None,
                 log_callback=print, config: dict | None = None):
        self.download_dir = download_dir or os.path.join(
            os.path.expanduser("~"), "Downloads", "LP_Downloads"
        )
        os.makedirs(self.download_dir, exist_ok=True)
        self.log = log_callback

        net_cfg = (config or {}).get("network", {})
        self.timeout = (
            net_cfg.get("connect_timeout", 10),
            net_cfg.get("read_timeout", 60),
        )
        self.max_size = net_cfg.get("max_download_size", MAX_DOWNLOAD_SIZE)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        })
        retry = Retry(
            total=net_cfg.get("max_retries", 3),
            backoff_factor=net_cfg.get("backoff_factor", 1.5),
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
        )
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=10,
            pool_maxsize=20,
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    # ---------------- GOOGLE PLAY (info only) ----------------
    def get_google_play_app_info(self, package_name: str) -> dict | None:
        try:
            from google_play_scraper import app as gp_app
            info = gp_app(package_name)
            return {
                "title": info["title"],
                "package": package_name,
                "developer": info["developer"],
                "version": info.get("version", ""),
                "size": info.get("size", ""),
                "installs": info.get("installs", ""),
                "score": info.get("score", 0),
                "icon": info.get("icon", ""),
                "description": (info.get("description", "") or "")[:200] + "...",
            }
        except ImportError:
            self.log("[!] google-play-scraper chưa cài")
            return None
        except Exception as e:
            self.log(f"[!] Google Play error: {e}")
            return None

    # ---------------- SOURCE-SPECIFIC ----------------
    def download_from_apkpure(self, package_name: str,
                              output_path: str | None = None) -> str | None:
        url = f"{self.BASE_URLS['apkpure']}/{package_name}?version=latest"
        return self._download(
            url, output_path or self._out_path(package_name, "apkpure")
        )

    def download_from_apkmody(self, package_name: str,
                              output_path: str | None = None) -> str | None:
        url = f"https://apkmody.io/download?package={package_name}"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            try:
                from bs4 import BeautifulSoup
            except ImportError:
                self.log("[!] beautifulsoup4 chưa cài")
                return None
            soup = BeautifulSoup(resp.text, "html.parser")
            link = soup.find("a", {"class": "download-btn"})
            if link and link.get("href"):
                return self._download(
                    link["href"],
                    output_path or self._out_path(package_name, "apkmody"),
                )
            self.log("[!] APKMody: không tìm thấy link tải")
        except requests.RequestException as e:
            self.log(f"[!] APKMody network error: {e}")
        return None

    def download_from_uptodown(self, package_name: str,
                               output_path: str | None = None) -> str | None:
        url = f"{self.BASE_URLS['uptodown']}/apps/{package_name}"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code != 200:
                return None
            data = resp.json()
            version = data.get("data", {}).get("latest_version", {})
            dl = version.get("download_url", "")
            if dl:
                return self._download(
                    dl,
                    output_path or self._out_path(package_name, "uptodown"),
                )
        except (requests.RequestException, ValueError) as e:
            self.log(f"[!] Uptodown error: {e}")
        return None

    def download_from_direct_url(self, url: str,
                                 output_path: str | None = None) -> str | None:
        return self._download(url, output_path)

    # ---------------- INTERNAL ----------------
    def _download(self, url: str, output_path: str | None) -> str | None:
        # === SECURITY GATE ===
        try:
            url = _validate_url(url)
        except UnsafeDownloadError as e:
            self.log(f"[!] [Security] URL bị từ chối: {e}")
            logger.warning("Unsafe URL rejected: %s", e)
            return None

        self.log(f"[*] [Downloader] GET {url}")
        try:
            resp = self.session.get(
                url, stream=True, timeout=self.timeout,
                allow_redirects=True, max_redirects=MAX_REDIRECTS,
            )
            resp.raise_for_status()

            # === SIZE LIMIT ===
            content_length = int(resp.headers.get("content-length", 0) or 0)
            if content_length > self.max_size:
                self.log(
                    f"[!] File quá lớn: {content_length / 1024 / 1024:.1f} MB "
                    f"(giới hạn {self.max_size / 1024 / 1024:.0f} MB)"
                )
                return None

            if output_path is None:
                output_path = os.path.join(
                    self.download_dir, self._filename(url, resp)
                )

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            downloaded = 0
            last_pct = -10

            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    downloaded += len(chunk)

                    # Kiểm tra size ngay cả khi không có Content-Length
                    if downloaded > self.max_size:
                        f.close()
                        os.remove(output_path)
                        self.log(
                            f"[!] Vượt giới hạn dung lượng "
                            f"({self.max_size / 1024 / 1024:.0f} MB) — hủy"
                        )
                        return None

                    f.write(chunk)

                    if content_length:
                        pct = int(downloaded * 100 / content_length)
                        if pct - last_pct >= 10:
                            self.log(f"[*] [Downloader] {pct}%")
                            last_pct = pct

            self.log(
                f"[✔] [Downloader] {output_path} "
                f"({downloaded / 1024 / 1024:.1f} MB)"
            )
            return output_path

        except requests.Timeout:
            self.log(f"[!] Download timeout: {url}")
        except requests.RequestException as e:
            self.log(f"[!] Download network error: {e}")
        except OSError as e:
            self.log(f"[!] Download I/O error: {e}")
        except Exception as e:
            self.log(f"[!] Download unexpected: {e}")
            logger.exception("Download crashed")
        return None

    def _out_path(self, package_name: str, source: str) -> str:
        # Sanitize package name để tránh path traversal
        safe_pkg = re.sub(r"[^a-zA-Z0-9._\-]", "_", package_name)[:100]
        return os.path.join(
            self.download_dir, f"{safe_pkg}_{source}.apk"
        )

    def _filename(self, url: str, resp) -> str:
        cd = resp.headers.get("Content-Disposition", "")
        if "filename=" in cd:
            if "filename*=" in cd:
                m = re.search(r"filename\*=UTF-8''(.+)", cd)
                if m:
                    name = unquote(m.group(1))
                    return self._sanitize_filename(name)
            m = re.search(r'filename="?(.+?)"?$', cd)
            if m:
                return self._sanitize_filename(m.group(1).strip('"'))

        path = urlparse(url).path
        name = os.path.basename(path)
        if name and "." in name:
            return self._sanitize_filename(unquote(name))
        return "downloaded.apk"

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Chỉ giữ basename + ký tự hợp lệ — chống path traversal."""
        name = os.path.basename(name.replace("\\", "/"))
        name = re.sub(r"[^\w.\-]", "_", name)
        return name[:200] or "download.apk"