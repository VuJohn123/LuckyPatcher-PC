"""Tải custom patch từ patch.chelpus.com với retry + timeout."""
from __future__ import annotations

import logging
import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

BASE_URL = "https://patch.chelpus.com"


class CustomPatchDownloader:
    def __init__(self, download_dir: str | None = None,
                 log_callback=print, config: dict | None = None):
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

        self.session = requests.Session()
        retry = Retry(
            total=net.get("max_retries", 3),
            backoff_factor=net.get("backoff_factor", 1.5),
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def download_patch(self, patch_name: str) -> str | None:
        url = f"{BASE_URL}/{patch_name}"
        dest = os.path.join(self.download_dir, patch_name)
        try:
            self.log(f"[*] [PatchDL] GET {url}")
            resp = self.session.get(url, stream=True, timeout=self.timeout)
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
            self.log(f"[✔] Downloaded: {dest}")
            return dest
        except requests.RequestException as e:
            self.log(f"[!] Download failed: {e}")
        except OSError as e:
            self.log(f"[!] File write failed: {e}")
        return None