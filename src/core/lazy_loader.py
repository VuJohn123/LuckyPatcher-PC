"""Lazy load patcher — chỉ import khi cần."""
from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)

PATCHER_MAP: dict[str, str] = {
    "license": "patcher.license_patcher",
    "license_reverse": "patcher.license_patcher",
    "license_extreme": "patcher.license_extreme",
    "license_amazon": "patcher.license_extreme",
    "license_samsung": "patcher.license_extreme",
    "ads": "patcher.ad_remover",
    "ads_break": "patcher.ads_blocklist",
    "ads_offline": "patcher.ads_blocklist",
    "ads_other": "patcher.ads_blocklist",
    "ads_full_offline": "patcher.ads_blocklist",
    "iap_dex": "patcher.iap_bypass",
    "iap_proxy": "patcher.iap_bypass",
    "sig_disable": "patcher.signature_patcher",
    "sig_integrity": "patcher.signature_integrity_patcher",
    "sig_fake_archive": "patcher.signature_fake_archive_patcher",
    "change_perms": "patcher.permission_changer",
    "custom": "patcher.custom_patch",
    "gms_spoof": "patcher.gms_spoofer",
    "event_logger": "patcher.event_logger",
    "aidl_proxy": "patcher.aidl_proxy_patcher",
}

CLASS_NAME_MAP: dict[str, str] = {
    "license": "LicensePatcher",
    "license_reverse": "LicensePatcher",
    "license_extreme": "LicenseExtremePatcher",
    "license_amazon": "LicenseExtremePatcher",
    "license_samsung": "LicenseExtremePatcher",
    "ads": "AdRemover",
    "ads_break": "AdsBlocklistPatcher",
    "ads_offline": "AdsBlocklistPatcher",
    "ads_other": "AdsBlocklistPatcher",
    "ads_full_offline": "AdsBlocklistPatcher",
    "iap_dex": "IAPBypass",
    "iap_proxy": "IAPBypass",
    "sig_disable": "SignatureVerifyPatcher",
    "sig_integrity": "SignatureIntegrityPatcher",
    "sig_fake_archive": "SignatureFakeArchivePatcher",
    "change_perms": "PermissionChanger",
    "custom": "CustomPatchApplier",
    "gms_spoof": "GMSSpoofer",
    "event_logger": "EventLogger",
    "aidl_proxy": "AIDLProxyPatcher",
}

_cache: dict[str, type | None] = {}


def get_patcher_class(mode_name: str):
    """Trả về class patcher hoặc None nếu không có."""
    if mode_name in _cache:
        return _cache[mode_name]

    module_path = PATCHER_MAP.get(mode_name)
    class_name = CLASS_NAME_MAP.get(mode_name)

    if not module_path or not class_name:
        _cache[mode_name] = None
        return None

    try:
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name, None)
        _cache[mode_name] = cls
        return cls
    except Exception as e:
        logger.warning("Không load được patcher %s: %s", mode_name, e)
        _cache[mode_name] = None
        return None