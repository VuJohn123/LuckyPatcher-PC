"""
Ads blocklist — chặn URL quảng cáo + offline mode.

v3 (LP parity):
  - Load `assets/AdsBlockList.txt` + `assets/AdsBlockList_user_edit.txt`
    (LP-format 2 sections: [HTTP] + [ALL_STRINGS]).
  - Fallback DEFAULT_BLOCKLIST nếu không có file.
  - ReDoS-safe regex qua core.regex_safe.
  - Path prefilter + progress bar.
"""
from __future__ import annotations

import logging
import os
import re

from core.regex_safe import safe_sub
from patcher.base import BasePatcher

logger = logging.getLogger(__name__)

# ---- Default fallback (nếu không có assets/) ----
DEFAULT_BLOCKLIST = (
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
)

OFFLINE_METHODS = (
    "isOnline",
    "isConnected",
    "hasInternetConnection",
    "checkNetwork",
)

_METHOD_MODS = (
    r"(?:(?:public|private|protected|static|final|synthetic|abstract)\s+)+"
)

# Compile sẵn regex offline method
_OFFLINE_REGEX = {
    m: re.compile(
        r"(\.method\s+" + _METHOD_MODS + m
        + r"\(.*?\)Z.*?\.end\s+method)",
        re.DOTALL,
    )
    for m in OFFLINE_METHODS
}


# ============================================================
# LP-FORMAT PARSER
# ============================================================
def parse_ads_blocklist(filepath: str) -> tuple[list[str], list[str]]:
    """
    Parse file LP-format AdsBlockList.txt.

    Format:
        [HTTP]
        pattern1
        pattern2
        [ALL_STRINGS]
        string1
        string2

    Return (http_patterns, all_strings).
    Lines bắt đầu `#` hoặc trống → skip.
    """
    http: list[str] = []
    strings: list[str] = []
    section: str | None = None

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1].strip().upper()
                    continue
                if section == "HTTP":
                    http.append(line)
                elif section == "ALL_STRINGS":
                    strings.append(line)
    except OSError as e:
        logger.warning("Không đọc được AdsBlockList: %s", e)

    return http, strings


# ============================================================
# PATCHER
# ============================================================
class AdsBlocklistPatcher(BasePatcher):
    def __init__(
        self,
        decompiled_path: str,
        blocklist_file: str | None = None,
        log_callback=print,
        file_cache=None,
    ):
        super().__init__(decompiled_path, log_callback, file_cache)

        if blocklist_file and os.path.exists(blocklist_file):
            # User-specified file → chỉ dùng file đó
            http_pats, strings = parse_ads_blocklist(blocklist_file)
            self.http_patterns = list(http_pats) or list(DEFAULT_BLOCKLIST)
            self.all_strings = strings
            self.log(
                f"[*] [AdsBlocklist] Custom file "
                f"({len(self.http_patterns)} HTTP + "
                f"{len(self.all_strings)} strings)"
            )
        else:
            # Auto-load từ assets/ (LP parity)
            http_pats, strings = self._load_lp_blocklists()
            if http_pats or strings:
                self.http_patterns = http_pats
                self.all_strings = strings
                self.log(
                    f"[*] [AdsBlocklist] LP-format loaded "
                    f"({len(http_pats)} HTTP + {len(strings)} strings)"
                )
            else:
                self.http_patterns = list(DEFAULT_BLOCKLIST)
                self.all_strings = []
                self.log(
                    f"[*] [AdsBlocklist] Default "
                    f"({len(self.http_patterns)} patterns)"
                )

    # ============================================================
    # LOAD LP BLOCKLISTS
    # ============================================================
    def _load_lp_blocklists(self) -> tuple[list[str], list[str]]:
        """
        Load LP-format blocklists từ assets/.
        Merge AdsBlockList.txt + AdsBlockList_user_edit.txt.

        Return (http_patterns, all_strings).
        """
        base = os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        ))
        assets_dir = os.path.join(base, "assets")

        http_patterns: list[str] = []
        all_strings: list[str] = []

        for fname in ("AdsBlockList.txt",
                      "AdsBlockList_user_edit.txt"):
            path = os.path.join(assets_dir, fname)
            if not os.path.exists(path):
                continue
            h, s = parse_ads_blocklist(path)
            http_patterns.extend(h)
            all_strings.extend(s)

        # Dedup (preserve order)
        http_patterns = list(dict.fromkeys(http_patterns))
        all_strings = list(dict.fromkeys(all_strings))

        return http_patterns, all_strings

    # ============================================================
    # REMOVE URLS
    # ============================================================
    def remove_ad_urls_from_smali(self) -> int:
        """
        Replace ad URLs với 127.0.0.1 loopback.
        Path prefilter: chỉ scan file có chứa `"http`.
        """
        self.log("[*] [AdsBlocklist] Removing ad URLs")

        # Prebuild patterns — escape domain rồi build regex
        patterns: list[str] = []
        for domain in self.http_patterns:
            escaped = re.escape(domain)
            patterns.append(
                r'"https?://[^"]*' + escaped + r'[^"]*"'
            )

        replacement = '"http://127.0.0.1"'

        def _transform(content: str, filepath: str) -> str | None:
            original = content
            for pat in patterns:
                new, ok = safe_sub(
                    pat, replacement, content,
                    log_callback=self.log,
                )
                if ok and new != content:
                    content = new
            return content if content != original else None

        return self.patch_files(
            _transform,
            prefilter_keywords=('"http', '"https'),
            label="AdsBlocklist-URL",
        )

    # ============================================================
    # OFFLINE MODE
    # ============================================================
    def make_ads_offline(self) -> int:
        """
        Force network-check methods → return false.
        Path prefilter: chỉ scan file có chứa method name.
        """
        self.log("[*] [AdsBlocklist] Making ads offline")

        def _transform(content: str, filepath: str) -> str | None:
            original = content
            for method, regex in _OFFLINE_REGEX.items():
                for match in regex.finditer(content):
                    full = match.group(0)
                    # Skip method có annotation phức tạp
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
                    break  # 1 method/loại/file
            return content if content != original else None

        return self.patch_files(
            _transform,
            prefilter_keywords=OFFLINE_METHODS,
            label="AdsBlocklist-Offline",
        )

    # ============================================================
    # REMOVE STRINGS (LP ALL_STRINGS section)
    # ============================================================
    def remove_ad_strings(self) -> int:
        """
        Remove exact string literals (LP ALL_STRINGS section).
        """
        if not self.all_strings:
            return 0
        self.log("[*] [AdsBlocklist] Removing ad strings")

        # Prebuild patterns cho từng string
        string_patterns: list[str] = []
        for s in self.all_strings:
            escaped = re.escape(s)
            string_patterns.append(r'"' + escaped + r'"')

        def _transform(content: str, filepath: str) -> str | None:
            original = content
            for pat in string_patterns:
                new, ok = safe_sub(
                    pat, '""', content,
                    log_callback=self.log,
                )
                if ok:
                    content = new
            return content if content != original else None

        return self.patch_files(
            _transform,
            label="AdsBlocklist-Strings",
        )

    # ============================================================
    # MAIN
    # ============================================================
    def patch(self) -> int:
        """Interface tương thích lazy_loader."""
        total = 0
        total += self.remove_ad_urls_from_smali()
        total += self.remove_ad_strings()
        total += self.make_ads_offline()
        return total