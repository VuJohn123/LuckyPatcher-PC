"""Tải APK từ nhiều nguồn — có retry, timeout, graceful degradation."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import zipfile
from urllib.parse import unquote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


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
        adapter = HTTPAdapter(max_retries=retry)
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

    # ---------------- APKPURE ----------------
    def download_from_apkpure(self, package_name: str, output_path: str | None = None) -> str | None:
        url = f"{self.BASE_URLS['apkpure']}/{package_name}?version=latest"
        return self._download(url, output_path or self._out_path(package_name, "apkpure"))

    # ---------------- APKMODY ----------------
    def download_from_apkmody(self, package_name: str, output_path: str | None = None) -> str | None:
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
                    link["href"], output_path or self._out_path(package_name, "apkmody")
                )
            self.log("[!] APKMody: không tìm thấy link tải")
        except requests.RequestException as e:
            self.log(f"[!] APKMody network error: {e}")
        return None

    # ---------------- UPTODOWN ----------------
    def download_from_uptodown(self, package_name: str, output_path: str | None = None) -> str | None:
        url = f"{self.BASE_URLS['uptodown']}/apps/{package_name}"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code != 200:
                return None
            data = resp.json()
            version = data.get("data", {}).get("latest_version", {})
            dl = version.get("download_url", "")
            if dl:
                return self._download(dl, output_path or self._out_path(package_name, "uptodown"))
        except (requests.RequestException, ValueError) as e:
            self.log(f"[!] Uptodown error: {e}")
        return None

    # ---------------- DIRECT URL ----------------
    def download_from_direct_url(self, url: str, output_path: str | None = None) -> str | None:
        return self._download(url, output_path)

    # ---------------- INTERNAL ----------------
    def _download(self, url: str, output_path: str | None) -> str | None:
        self.log(f"[*] [Downloader] GET {url}")
        try:
            resp = self.session.get(url, stream=True, timeout=self.timeout)
            resp.raise_for_status()

            if output_path is None:
                output_path = os.path.join(self.download_dir, self._filename(url, resp))

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            total = int(resp.headers.get("content-length", 0) or 0)
            downloaded = 0
            last_pct = -10

            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = int(downloaded * 100 / total)
                        if pct - last_pct >= 10:
                            self.log(f"[*] [Downloader] {pct}%")
                            last_pct = pct

            self.log(f"[✔] [Downloader] {output_path} ({downloaded} bytes)")
            return output_path

        except requests.Timeout:
            self.log(f"[!] Download timeout: {url}")
        except requests.RequestException as e:
            self.log(f"[!] Download network error: {e}")
        except OSError as e:
            self.log(f"[!] Download I/O error: {e}")
        return None

    def _out_path(self, package_name: str, source: str) -> str:
        return os.path.join(self.download_dir, f"{package_name}_{source}.apk")

    def _filename(self, url: str, resp) -> str:
        cd = resp.headers.get("Content-Disposition", "")
        if "filename=" in cd:
            if "filename*=" in cd:
                m = re.search(r"filename\*=UTF-8''(.+)", cd)
                if m:
                    return unquote(m.group(1))
            m = re.search(r'filename="?(.+?)"?$', cd)
            if m:
                return m.group(1).strip('"')
        path = urlparse(url).path
        name = os.path.basename(path)
        if name and "." in name:
            return unquote(name)
        return "downloaded.apk"