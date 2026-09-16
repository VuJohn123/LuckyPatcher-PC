"""Ad scanner — tìm ad activities trong manifest."""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

AD_PATTERNS = [
    re.compile(r"com\.google\.android\.gms\.ads\..*"),
    re.compile(r"com\.facebook\.ads\..*"),
    re.compile(r"com\.unity3d\.ads\..*"),
    re.compile(r"com\.applovin\..*"),
    re.compile(r"com\.ironsource\..*"),
    re.compile(r"com\.mopub\..*"),
    re.compile(r"com\.inmobi\..*"),
    re.compile(r"com\.vungle\..*"),
    re.compile(r"com\.chartboost\..*"),
    re.compile(r"com\.adcolony\..*"),
    re.compile(r"com\.startapp\..*"),
    re.compile(r".*\.AdActivity$"),
    re.compile(r".*\.InterstitialAd.*"),
    re.compile(r".*\.RewardedVideo.*"),
    re.compile(r".*\.RewardedAd.*"),
]


class AdScanner:
    def __init__(self, apk_path: str):
        from androguard.core.apk import APK
        self.apk = APK(apk_path)

    def scan_manifest(self) -> tuple[list[str], list[str]]:
        ad_activities: list[str] = []
        ad_providers: list[str] = []

        try:
            activities = self.apk.get_activities()
        except Exception as e:
            logger.warning("get_activities failed: %s", e)
            activities = []

        try:
            providers = self.apk.get_providers()
        except Exception as e:
            logger.warning("get_providers failed: %s", e)
            providers = []

        for activity in activities:
            for pat in AD_PATTERNS:
                if pat.match(activity):
                    ad_activities.append(activity)
                    break

        for provider in providers:
            for pat in AD_PATTERNS:
                if pat.match(provider):
                    ad_providers.append(provider)
                    break

        return ad_activities, ad_providers