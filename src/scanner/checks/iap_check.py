"""IAP detection — BILLING permission + BillingClient + Unity IAP."""
from __future__ import annotations

import logging

from androguard.core.dex import DEX

logger = logging.getLogger(__name__)

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


def _match_vendor(class_name: str) -> str | None:
    for prefix, label in _IAP_SIGNATURES:
        if prefix in class_name:
            return label
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
        try:
            dex = DEX(dex_bytes)
        except Exception:
            continue

        try:
            for cls in dex.get_classes():
                cname = cls.get_name()
                vendor = _match_vendor(cname)
                if vendor:
                    # Description PHẢI chứa class name (test compat) +
                    # vendor label (UX).
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
        except Exception as e:
            logger.debug("DEX scan failed %s: %s", dex_name, e)
            continue

    findings.append({
        "type": "no_iap",
        "color": None,
        "title": "InApp Purchases",
        "description": "Not detected",
        "details": ["No billing found"],
        "action": None,
    })