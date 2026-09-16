"""Phát hiện xung đột giữa các mode patch."""
from __future__ import annotations

MODE_TARGETS: dict[str, list[str]] = {
    "license": ["LicenseValidator", "LicenseChecker"],
    "license_reverse": ["ServerManagedPolicy"],
    "license_extreme": ["LicenseChecker", "ILicensingService"],
    "ads": ["AndroidManifest.xml"],
    "ads_offline": ["isOnline", "isConnected"],
    "ads_other": ["AndroidManifest.xml"],
    "sig_disable": ["verifyPurchase", "checkSignature"],
    "sig_integrity": ["MessageDigest", "Signature"],
    "sig_fake_archive": ["ZipEntry"],
    "iap_dex": ["BillingClient", "IInAppBillingService"],
    "iap_proxy": ["IInAppBillingService", "AndroidManifest.xml"],
    "change_perms": ["AndroidManifest.xml"],
    "clone": ["AndroidManifest.xml", "smali"],
    "aidl_proxy": ["IInAppBillingServiceProxy", "AndroidManifest.xml"],
}


def detect_conflicts(modes: list[str]) -> list[tuple[str, str, list[str]]]:
    """
    Trả về list các cặp (mode1, mode2, overlapping_targets).
    Rỗng nếu không có xung đột.
    """
    conflicts: list[tuple[str, str, list[str]]] = []
    for i in range(len(modes)):
        for j in range(i + 1, len(modes)):
            ti = set(MODE_TARGETS.get(modes[i], []))
            tj = set(MODE_TARGETS.get(modes[j], []))
            overlap = ti & tj
            if overlap:
                conflicts.append((modes[i], modes[j], sorted(overlap)))
    return conflicts