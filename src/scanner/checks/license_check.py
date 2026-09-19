"""
License detection — tìm LVL, LicenseValidator, PairIP trong DEX.

v3 (2026):
  - FAST PATH: ASCII regex trên raw dex bytes (~0.3s/dex) thay vì
    androguard DEX() + get_methods() (~6s/dex).
  - FALLBACK: androguard cho test mock (bytes < 1KB).
  - PairIP detection emit finding riêng (red, unpackable).
"""
from __future__ import annotations

import logging
import re

from androguard.core.dex import DEX

logger = logging.getLogger(__name__)

_ASCII_RE = re.compile(rb"[\x20-\x7e]{4,}")
_CLASS_DESC_STR_RE = re.compile(r"L[\w/$]+;")
_FAST_THRESHOLD = 1024

_BLACKLIST = (
    "OfflineLicenseHelper",
    "LicenseManager",
    "BidToken",
    "Moloco",
    "ImpLvlRevData",
    "ClientBidToken",
    "LicensingListener",
)

_PAIRIP_MARKERS = (
    "com/pairip/licensecheck",
    "com/pairip/license",
    "Lcom/pairip/licensecheck",
    "Lcom/pairip/license",
)

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


def _extract_ascii_strings(dex_bytes: bytes) -> list[str]:
    """Fast ASCII run extraction."""
    try:
        return [
            m.decode("latin-1", errors="ignore")
            for m in _ASCII_RE.findall(dex_bytes)
        ]
    except Exception:
        return []


def _scan_license_via_dex(
    dex_bytes: bytes,
) -> tuple[str, str | None, list[str]] | None:
    """
    Test mock path — androguard.
    Return (kind, class_name, methods):
      kind: "pairip" | "lvl"
    """
    try:
        dex = DEX(dex_bytes)
    except Exception:
        return None
    try:
        classes = dex.get_classes()
    except Exception:
        return None

    for cls in classes:
        try:
            cname = cls.get_name()
        except Exception:
            continue

        if _is_pairip(cname):
            return ("pairip", cname, [])

        if any(bl in cname for bl in _BLACKLIST):
            continue

        if _LICENSE_RE.search(cname):
            methods: list[str] = []
            try:
                for m in cls.get_methods():
                    mn = m.get_name()
                    if _METHOD_RE.search(mn):
                        methods.append(mn)
            except Exception:
                pass
            return ("lvl", cname, methods)
    return None


def _scan_license_fast(
    dex_bytes: bytes,
) -> tuple[str, str | None, list[str]] | None:
    """Fast path — ASCII blob match."""
    strings = _extract_ascii_strings(dex_bytes)
    if not strings:
        return None
    blob = "\n".join(strings)

    for m in _CLASS_DESC_STR_RE.finditer(blob):
        cname = m.group(0)
        if _is_pairip(cname):
            return ("pairip", cname, [])
        if any(bl in cname for bl in _BLACKLIST):
            continue
        if _LICENSE_RE.search(cname):
            methods: list[str] = []
            for mm in _METHOD_RE.finditer(blob):
                mn = mm.group(0)
                if mn not in methods:
                    methods.append(mn)
                if len(methods) >= 3:
                    break
            return ("lvl", cname, methods)
    return None


def check_license(
    apk, apk_path, get_all_dex_bytes, findings, available_patches,
) -> None:
    """Populate findings + available_patches với license info."""
    pairip_hit: str | None = None

    for dex_name, dex_bytes in get_all_dex_bytes():
        if not dex_bytes:
            continue

        if len(dex_bytes) < _FAST_THRESHOLD:
            result = _scan_license_via_dex(dex_bytes)
        else:
            result = _scan_license_fast(dex_bytes)

        if not result:
            continue

        kind, cname, methods = result

        if kind == "pairip":
            pairip_hit = cname
            continue

        # kind == "lvl"
        findings.append({
            "type": "license",
            "color": "green",
            "title": "License Verification Found",
            "description": f"Class: {cname}",
            "details": (
                methods[:3] if methods
                else ["License check detected"]
            ),
            "action": "remove_license",
        })
        if "license" not in available_patches:
            available_patches.append("license")

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

    # Fallback manifest activity
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