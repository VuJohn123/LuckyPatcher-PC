"""
Ads blocklist — chặn URL quảng cáo + offline mode.
Fix bug: regex modifier multi-match cho method có nhiều modifier.
"""
from __future__ import annotations

import logging
import os
import re

from core.smali_utils import get_all_smali_files

logger = logging.getLogger(__name__)

DEFAULT_BLOCKLIST = [
    "doubleclick.net",
    "googleadservices.com",
    "googlesyndication.com",
    "admob.com",
    "applovin.com",
    "unity3d.com/ads",
    "facebook.com/ads",
    "ironsrc.com",
    "vungle.com",
    "chartboost.com",
    "adcolony.com",
    "mopub.com",
    "inmobi.com",
    "startapp.com",
]

OFFLINE_METHODS = (
    "isOnline",
    "isConnected",
    "hasInternetConnection",
    "checkNetwork",
)

# Modifier pattern — match nhiều modifier (public static, private final, ...)
_METHOD_MODS = (
    r"(?:(?:public|private|protected|static|final|synthetic|abstract)\s+)+"
)

# Compile sẵn regex cho từng method offline
_OFFLINE_REGEX = {
    m: re.compile(
        r"(\.method\s+" + _METHOD_MODS + m + r"\(.*?\)Z.*?\.end\s+method)",
        re.DOTALL,
    )
    for m in OFFLINE_METHODS
}


class AdsBlocklistPatcher:
    def __init__(
        self,
        decompiled_path: str,
        blocklist_file: str | None = None,
        log_callback=print,
        file_cache=None,
    ):
        self.decompiled_path = decompiled_path
        self.log = log_callback
        self.file_cache = file_cache
        self.blocklist = self._load_blocklist(blocklist_file)

    def _load_blocklist(self, filepath: str | None) -> list[str]:
        if filepath and os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return [
                    ln.strip() for ln in f
                    if ln.strip() and not ln.startswith("#")
                ]
        return list(DEFAULT_BLOCKLIST)

    def _read(self, path: str) -> str:
        if self.file_cache:
            return self.file_cache.read(path)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _write(self, path: str, content: str) -> None:
        if self.file_cache:
            self.file_cache.write(path, content)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

    def remove_ad_urls_from_smali(self) -> int:
        """Thay thế URL quảng cáo bằng 127.0.0.1."""
        self.log("[*] [AdsBlocklist] Removing ad URLs...")
        count = 0
        for filepath in get_all_smali_files(self.decompiled_path):
            if len(filepath) > 250:
                continue
            content = self._read(filepath)
            modified = False
            for domain in self.blocklist:
                pattern = (
                    r'"https?://[^"]*' + re.escape(domain) + r'[^"]*"'
                )
                new_content, n = re.subn(
                    pattern, '"http://127.0.0.1"', content
                )
                if n > 0:
                    content = new_content
                    modified = True
                    count += n
            if modified:
                self._write(filepath, content)
        self.log(f"[*] [AdsBlocklist] Removed {count} ad URLs")
        return count

    def make_ads_offline(self) -> int:
        """Ép các method kiểm tra mạng trả về false."""
        self.log("[*] [AdsBlocklist] Making ads offline...")
        count = 0
        for filepath in get_all_smali_files(self.decompiled_path):
            if len(filepath) > 250:
                continue
            content = self._read(filepath)
            original = content
            modified = False

            for method, regex in _OFFLINE_REGEX.items():
                for match in regex.finditer(content):
                    full = match.group(0)
                    # Bỏ qua method có annotation phức tạp
                    if ".annotation" in full.split(".end method")[0]:
                        continue
                    header = full.split("\n")[0]
                    replacement = (
                        f"{header}\n"
                        "    .locals 1\n"
                        "    const/4 v0, 0x0\n"
                        "    return v0\n"
                        ".end method"
                    )
                    content = content.replace(full, replacement)
                    modified = True
                    count += 1
                    break  # 1 method/loại/file

            if modified and content != original:
                self._write(filepath, content)

        self.log(f"[*] [AdsBlocklist] Offline mode: {count} methods")
        return count

    def patch(self) -> int:
        """Interface tương thích lazy_loader."""
        return self.remove_ad_urls_from_smali() + self.make_ads_offline()