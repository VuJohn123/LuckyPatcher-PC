"""
IAP detection — BILLING permission + BillingClient + Unity IAP.

v2 (2026):
  - FAST PATH: ASCII regex trên raw dex bytes (~0.3s/dex) thay vì
    androguard DEX().get_classes() (~5s/dex).
  - FALLBACK: androguard cho test mock (bytes < 1KB).
"""
from __future__ import annotations

import logging
import re

from androguard.core.dex import DEX

logger = logging.getLogger(__name__)

_ASCII_RE = re.compile(rb"[\x20-\x7e]{4,}")
_FAST_THRESHOLD = 1024

_IAP_SIGNATURES: tuple[tuple[str, str], ...] = (
    ("com/android/billingclient/api/BillingClient", "Google Play Billing"),
    ("IInAppBillingService", "AIDL Billing"),
    ("com/unity3d/purchasing/", "Unity IAP (v3)"),
    ("com/unity/purchasing/", "Unity IAP (v4+)"),
    ("Lcom/unity3d/plugin/", "Unity Plugin"),
    ("IStoreListener", "Unity IStoreListener"),
    ("UnityPurchasing", "Unity IAP main"),
    ("com/android/vending/billing/", "Vending Billing"),
)


def _extract_ascii_strings(dex_bytes: bytes) -> list[str]:
    """Fast ASCII run extraction."""
    try:
        return [
            m.decode("latin-1", errors="ignore")
            for m in _ASCII_RE.findall(dex_bytes)
        ]
    except Exception:
        return []


def _match_vendor(class_name: str) -> str | None:
    for prefix, label in _IAP_SIGNATURES:
        if prefix in class_name:
            return label
    return None


def _scan_iap_via_dex(dex_bytes: bytes) -> tuple[str, str] | None:
    """Test mock path — androguard. Return (class_name, vendor)."""
    try:
        dex = DEX(dex_bytes)
    except Exception:
        return None
    try:
        for cls in dex.get_classes():
            try:
                cname = cls.get_name()
            except Exception:
                continue
            vendor = _match_vendor(cname)
            if vendor:
                return (cname, vendor)
    except Exception:
        return None
    return None


def _scan_iap_fast(dex_bytes: bytes) -> tuple[str, str] | None:
    """Fast path — ASCII blob match. Return (class_name, vendor)."""
    strings = _extract_ascii_strings(dex_bytes)
    if not strings:
        return None
    blob = "\n".join(strings)

    for prefix, label in _IAP_SIGNATURES:
        idx = blob.find(prefix)
        if idx < 0:
            continue
        start = blob.rfind("L", 0, idx)
        if start < 0 or start > idx:
            start = idx
        end = blob.find(";", idx)
        cname = blob[start:end + 1] if end > idx else prefix
        return (cname, label)
    return None


def check_iap(apk, get_all_dex_bytes, findings, available_patches) -> None:
    try:
        perms = apk.get_permissions()
    except Exception:
        perms = []

    if "com.android.vending.BILLING" in perms:
        findings.append({
            "type": "iap",
            "color": "green",
            "title": "InApp Purchases Available",
            "description": "Manifest requests BILLING permission",
            "details": ["com.android.vending.BILLING permission found"],
            "action": "iap_emulation",
        })
        if "iap" not in available_patches:
            available_patches.append("iap")
        return

    for dex_name, dex_bytes in get_all_dex_bytes():
        if not dex_bytes:
            continue

        if len(dex_bytes) < _FAST_THRESHOLD:
            result = _scan_iap_via_dex(dex_bytes)
        else:
            result = _scan_iap_fast(dex_bytes)

        if result:
            cname, vendor = result
            findings.append({
                "type": "iap",
                "color": "green",
                "title": "InApp Purchases Available",
                "description": f"{vendor} — class {cname}",
                "details": [vendor, cname],
                "action": "iap_emulation",
            })
            if "iap" not in available_patches:
                available_patches.append("iap")
            return

    findings.append({
        "type": "no_iap",
        "color": None,
        "title": "InApp Purchases",
        "description": "Not detected",
        "details": ["No billing found"],
        "action": None,
    })