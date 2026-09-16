"""License detection — tìm LVL, LicenseValidator trong DEX."""
from __future__ import annotations

import logging
import re

from androguard.core.dex import DEX

logger = logging.getLogger(__name__)

_BLACKLIST = (
    "OfflineLicenseHelper",   # ExoPlayer DRM
    "LicenseManager",
    "BidToken",               # Moloco
    "Moloco",
    "ImpLvlRevData",
    "ClientBidToken",
    "LicensingListener",      # Amazon DRM
)

_LICENSE_RE = re.compile(
    r"(license|licensing|lvl|LicenseCheck|LicenseValidat)",
    re.IGNORECASE,
)
_METHOD_RE = re.compile(
    r"(checkAccess|allow|verify|checkLicense|isLicensed)",
    re.IGNORECASE,
)


def check_license(apk, apk_path, get_all_dex_bytes, findings, available_patches) -> None:
    """Populate findings + available_patches với license info."""
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

            if any(bl in class_name for bl in _BLACKLIST):
                continue

            if _LICENSE_RE.search(class_name):
                methods = []
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
                    "details": methods[:3] if methods else ["License check detected"],
                    "action": "remove_license",
                })
                available_patches.append("license")
                return

    # Fallback: manifest-based
    try:
        activities = apk.get_activities()
    except Exception:
        activities = []

    for activity in activities:
        if "license" in activity.lower() and "exoplayer" not in activity.lower():
            findings.append({
                "type": "license",
                "color": "green",
                "title": "License Verification Found",
                "description": f"Activity: {activity}",
                "details": ["License-related activity detected"],
                "action": "remove_license",
            })
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