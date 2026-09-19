"""
License detection — tìm LVL, LicenseValidator, PairIP trong DEX.

v2 (LP parity):
  - PairIP detection: emit finding riêng (red, unpackable) khi phát hiện
    `com.pairip.licensecheck.*` — không false-positive "License found"
    như LVL bình thường.
  - Blacklist mở rộng: LicenseManager generic, BidToken, Moloco, ...
  - Fallback manifest activity check có ExoPlayer skip.
"""
from __future__ import annotations

import logging
import re

from androguard.core.dex import DEX

logger = logging.getLogger(__name__)

# Class name cần bỏ qua — không phải license thật
_BLACKLIST = (
    "OfflineLicenseHelper",   # ExoPlayer DRM
    "LicenseManager",         # quá generic
    "BidToken",               # Moloco
    "Moloco",
    "ImpLvlRevData",
    "ClientBidToken",
    "LicensingListener",      # Amazon DRM
)

# Packer license check — không patch được static
_PAIRIP_MARKERS = (
    "com/pairip/licensecheck",
    "com/pairip/license",
    "Lcom/pairip/licensecheck",
    "Lcom/pairip/license",
)

# LVL detection regex
_LICENSE_RE = re.compile(
    r"(license|licensing|lvl|LicenseCheck|LicenseValidat)",
    re.IGNORECASE,
)
_METHOD_RE = re.compile(
    r"(checkAccess|allow|verify|checkLicense|isLicensed)",
    re.IGNORECASE,
)


def _is_pairip(class_name: str) -> bool:
    cn = class_name.lower()
    return any(marker.lower() in cn for marker in _PAIRIP_MARKERS)


def check_license(
    apk, apk_path, get_all_dex_bytes, findings, available_patches,
) -> None:
    """Populate findings + available_patches với license info."""
    pairip_hit: str | None = None

    for dex_name, dex_bytes in get_all_dex_bytes():
        try:
            dex = DEX(dex_bytes)
        except Exception as e:
            logger.debug("DEX parse failed %s: %s", dex_name, e)
            continue

        try:
            classes = dex.get_classes()
        except Exception as e:
            logger.debug("get_classes failed %s: %s", dex_name, e)
            continue

        for cls in classes:
            try:
                class_name = cls.get_name()
            except Exception:
                continue

            # ---- PairIP detection (before blacklist) ----
            if _is_pairip(class_name):
                pairip_hit = class_name
                continue  # không đếm như LVL bình thường

            # ---- Blacklist filter ----
            if any(bl in class_name for bl in _BLACKLIST):
                continue

            # ---- LVL detection ----
            if _LICENSE_RE.search(class_name):
                methods: list[str] = []
                try:
                    for method in cls.get_methods():
                        mn = method.get_name()
                        if _METHOD_RE.search(mn):
                            methods.append(mn)
                except Exception:
                    pass

                findings.append({
                    "type": "license",
                    "color": "green",
                    "title": "License Verification Found",
                    "description": f"Class: {class_name}",
                    "details": (
                        methods[:3] if methods
                        else ["License check detected"]
                    ),
                    "action": "remove_license",
                })
                if "license" not in available_patches:
                    available_patches.append("license")

                # Nếu đã phát hiện PairIP, thêm finding cảnh báo
                if pairip_hit:
                    findings.append({
                        "type": "license_packed",
                        "color": "red",
                        "title": "License (PairIP packed)",
                        "description": (
                            "PairIP license check — native VM. "
                            "Patch static có thể không hiệu quả."
                        ),
                        "details": [pairip_hit],
                        "action": None,
                    })
                return

    # ---- Nếu chỉ có PairIP (không LVL standard) ----
    if pairip_hit:
        findings.append({
            "type": "license",
            "color": "red",
            "title": "License (PairIP packed)",
            "description": (
                f"PairIP license check: {pairip_hit} — "
                f"native VM, không patch static được"
            ),
            "details": [pairip_hit],
            "action": None,
        })
        return

    # ---- Fallback manifest activity check ----
    try:
        activities = apk.get_activities()
    except Exception:
        activities = []

    for activity in activities:
        a_lower = activity.lower()
        if "license" in a_lower and "exoplayer" not in a_lower:
            findings.append({
                "type": "license",
                "color": "green",
                "title": "License Verification Found",
                "description": f"Activity: {activity}",
                "details": ["License-related activity detected"],
                "action": "remove_license",
            })
            if "license" not in available_patches:
                available_patches.append("license")
            return

    findings.append({
        "type": "no_license",
        "color": None,
        "title": "License Verification",
        "description": "Not detected",
        "details": ["No LVL or license check found"],
        "action": None,
    })