"""Ads detection — scan manifest activities/providers."""
from __future__ import annotations

import re

_AD_NETWORKS = {
    "AdMob": [r"com\.google\.android\.gms\.ads", r"AdActivity", r"AdMob"],
    "Facebook Ads": [r"com\.facebook\.ads"],
    "Unity Ads": [r"com\.unity3d\.ads"],
    "AppLovin": [r"com\.applovin"],
    "IronSource": [r"com\.ironsource"],
    "Vungle": [r"com\.vungle"],
    "Chartboost": [r"com\.chartboost"],
    "AdColony": [r"com\.adcolony"],
    "MoPub": [r"com\.mopub"],
    "InMobi": [r"com\.inmobi"],
    "StartApp": [r"com\.startapp"],
}

_COMPILED = {
    name: [re.compile(p) for p in pats]
    for name, pats in _AD_NETWORKS.items()
}


def check_ads(apk, findings, available_patches) -> None:
    try:
        activities = apk.get_activities()
    except Exception:
        activities = []

    try:
        providers = apk.get_providers()
    except Exception:
        providers = []

    found: list[str] = []
    for item in list(activities) + list(providers):
        for name, patterns in _COMPILED.items():
            if name in found:
                continue
            for pat in patterns:
                if pat.search(item):
                    found.append(name)
                    break

    if found:
        findings.append({
            "type": "ads",
            "color": "blue",
            "title": "Google Ads Detected",
            "description": f'Ad networks: {", ".join(found)}',
            "details": found,
            "action": "remove_ads",
        })
        available_patches.append("ads")
    else:
        findings.append({
            "type": "no_ads",
            "color": None,
            "title": "Google Ads",
            "description": "Not detected",
            "details": ["No ad networks found"],
            "action": None,
        })