"""
Output filename builder — {package}.{Patch1}.{Patch2}.apk

Ví dụ:
    package="net.mobigame.zombietsunami"
    modes=["iap_dex", "license"]
    → "net.mobigame.zombietsunami.IAP-Dex.License.apk"

Design:
  - Package giữ nguyên dấu '.' (đúng convention Android).
  - Patch labels PascalCase, dash-separated (Windows-safe).
  - Fallback: package rỗng → dùng stem của APK gốc.
  - Max filename = 180 ký tự (Windows MAX_PATH safe).
"""
from __future__ import annotations

import hashlib
import os
import re

# Mode name → human label. Unknown mode → fallback (chỉ capitalize).
MODE_TO_LABEL: dict[str, str] = {
    # License
    "license": "License",
    "license_reverse": "License-Reverse",
    "license_extreme": "License-Extreme",
    "license_amazon": "License-Amazon",
    "license_samsung": "License-Samsung",
    # Ads
    "ads": "Ads",
    "ads_break": "Ads-Break",
    "ads_offline": "Ads-Offline",
    "ads_full_offline": "Ads-Full-Offline",
    "ads_other": "Ads-Other",
    # IAP
    "iap_dex": "IAP-Dex",
    "iap_proxy": "IAP-Proxy",
    "iap_update": "IAP-Update",
    # Signature
    "sig_disable": "Sig-Disable",
    "sig_integrity": "Sig-Integrity",
    "sig_fake_archive": "Sig-Fake-Archive",
    "sig_zip_disable": "Sig-Zip-Disable",
    # Permissions
    "change_perms": "Change-Perms",
    # Resign
    "resign_name": "Resign-Name",
    "resign_version": "Resign-Version",
    "resign_min_sdk": "Resign-Min-SDK",
    "resign_target_sdk": "Resign-Target-SDK",
    "resign_shared_id": "Resign-Shared-ID",
    "resign_copy_sig": "Resign-Copy-Sig",
    "resign_original": "Resign-Original",
    # Extras
    "gms_spoof": "GMS-Spoof",
    "clone": "Clone",
    "backup": "Backup",
    "save_purchase": "Save-Purchase",
    "auto_repeat": "Auto-Repeat",
    "cloud_patch": "Cloud-Patch",
    "event_logger": "Event-Logger",
}

_MAX_FILENAME_LEN = 180
_SAFE_PKG_RE = re.compile(r"[^A-Za-z0-9._-]")


def _label_for_mode(mode: str) -> str:
    """Map internal mode → human label. Unknown → capitalize words."""
    if mode in MODE_TO_LABEL:
        return MODE_TO_LABEL[mode]
    # Fallback: "unknown_mode" → "Unknown-Mode"
    return "-".join(
        p.capitalize() for p in mode.replace("-", "_").split("_") if p
    )


def _sanitize_package(package: str) -> str:
    """Package giữ dấu '.', thay ký tự không an toàn."""
    cleaned = _SAFE_PKG_RE.sub("_", package or "").strip("._-")
    return cleaned or "unknown"


def build_output_filename(
    package_name: str,
    mapped_modes: list[str],
    fallback_stem: str = "output",
    extension: str = ".apk",
) -> str:
    """
    Build output filename từ package + modes.

    Args:
        package_name: android package (vd "com.example.app")
        mapped_modes: list internal mode names (vd ["iap_dex", "license"])
        fallback_stem: dùng khi package rỗng (thường là tên file APK gốc)
        extension: thường ".apk"

    Returns:
        Filename (không có path), đã sanitize + truncate nếu cần.
    """
    pkg = _sanitize_package(package_name) or _sanitize_package(fallback_stem)

    # Dedup mode labels, giữ order
    labels: list[str] = []
    seen: set[str] = set()
    for m in mapped_modes:
        label = _label_for_mode(m)
        if label not in seen:
            seen.add(label)
            labels.append(label)

    if not labels:
        labels = ["Patched"]

    filename = f"{pkg}.{'.'.join(labels)}{extension}"

    # Truncate nếu quá dài (giữ prefix + hash suffix)
    if len(filename) > _MAX_FILENAME_LEN:
        h = hashlib.md5(filename.encode("utf-8")).hexdigest()[:8]
        # Cắt bớt labels từ cuối
        keep = pkg
        for label in labels:
            candidate = f"{keep}.{label}"
            if len(candidate) + len(extension) + 10 > _MAX_FILENAME_LEN:
                break
            keep = candidate
        filename = f"{keep}._more-{h}{extension}"

    return filename


def build_output_path(
    output_dir: str,
    package_name: str,
    mapped_modes: list[str],
    fallback_stem: str = "output",
) -> str:
    """Full path — wrapper của build_output_filename."""
    fn = build_output_filename(package_name, mapped_modes, fallback_stem)
    return os.path.join(output_dir, fn)