"""Đăng ký mode + nhóm song song."""
from __future__ import annotations

MODE_MAP: dict[str, str] = {
    # License
    "license:auto_dex": "license",
    "license:auto": "license",
    "license:reverse_auto": "license_reverse",
    "license:extreme": "license_extreme",
    "license:manual": "license",
    "license:amazon": "license_amazon",
    "license:samsung": "license_samsung",
    # Ads
    "ads:remove_links": "ads",
    "ads:break_receiver": "ads_break",
    "ads:offline": "ads_offline",
    "ads:other": "ads_other",
    "ads:full_offline": "ads_full_offline",
    # IAP
    "iap:support_lvl_inapp": "iap_proxy",
    "iap:dex": "iap_dex",
    "iap:proxy": "iap_proxy",
    "iap:update": "iap_update",
    # Signature
    "signature:disable_verify": "sig_disable",
    "signature:remove_integrity": "sig_integrity",
    "signature:fake_archive": "sig_fake_archive",
    # Resign
    "resign:change_name": "resign_name",
    "resign:change_version": "resign_version",
    "resign:change_min_sdk": "resign_min_sdk",
    "resign:change_target_sdk": "resign_target_sdk",
    "resign:change_shared_id": "resign_shared_id",
    "resign:copy_signature": "resign_copy_sig",
    "resign:original_signature": "resign_original",
    # Shortcut modes
    "perms:change": "change_perms",
    "backup": "backup",
    "save_purchase": "save_purchase",
    "auto_repeat": "auto_repeat",
    "sig_disable": "sig_disable",
    "sig_integrity": "sig_integrity",
    "sig_fake_archive": "sig_fake_archive",
    "sig_zip_disable": "sig_zip_disable",
    "clone": "clone",
    "cloud_patch": "cloud_patch",
    "iap_update": "iap_update",
    "gms_spoof": "gms_spoof",
    "event_logger": "event_logger",
}

PARALLEL_GROUPS: dict[str, list[str]] = {
    "license_group": ["license", "license_reverse", "license_extreme",
                      "license_amazon", "license_samsung"],
    "ads_group": ["ads", "ads_break", "ads_offline", "ads_other", "ads_full_offline"],
    "sig_group": ["sig_disable", "sig_integrity", "sig_fake_archive"],
}


def get_mode_group(mode_name: str) -> str | None:
    for group, modes in PARALLEL_GROUPS.items():
        if mode_name in modes:
            return group
    return None