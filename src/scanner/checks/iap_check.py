"""IAP detection — BILLING permission + BillingClient class."""
from __future__ import annotations

import logging

from androguard.core.dex import DEX

logger = logging.getLogger(__name__)


def check_iap(apk, get_all_dex_bytes, findings, available_patches) -> None:
    # Cách 1: BILLING permission
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

    # Cách 2: Scan DEX
    for dex_name, dex_bytes in get_all_dex_bytes():
        try:
            dex = DEX(dex_bytes)
        except Exception:
            continue

        try:
            for cls in dex.get_classes():
                cname = cls.get_name()
                if "com/android/billingclient/api/BillingClient" in cname:
                    findings.append({
                        "type": "iap",
                        "color": "green",
                        "title": "InApp Purchases Available",
                        "description": "BillingClient library found",
                        "details": [cname],
                        "action": "iap_emulation",
                    })
                    if "iap" not in available_patches:
                        available_patches.append("iap")
                    return
                if "IInAppBillingService" in cname:
                    findings.append({
                        "type": "iap",
                        "color": "green",
                        "title": "InApp Purchases Available",
                        "description": "IInAppBillingService detected",
                        "details": [cname],
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