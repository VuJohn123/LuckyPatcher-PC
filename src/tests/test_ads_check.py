"""Test ads detection — AdMob, Facebook, Unity, etc."""
from unittest.mock import MagicMock

from scanner.checks.ads_check import check_ads


def test_no_ads():
    apk = MagicMock()
    apk.get_activities.return_value = ["com.example.MainActivity"]
    apk.get_providers.return_value = []
    findings: list = []
    patches: list = []

    check_ads(apk, findings, patches)

    assert findings[0]["type"] == "no_ads"
    assert patches == []


def test_admob_activity_detected():
    apk = MagicMock()
    apk.get_activities.return_value = [
        "com.google.android.gms.ads.AdActivity",
    ]
    apk.get_providers.return_value = []
    findings: list = []
    patches: list = []

    check_ads(apk, findings, patches)

    assert findings[0]["type"] == "ads"
    assert findings[0]["color"] == "blue"
    assert "AdMob" in findings[0]["details"]
    assert "ads" in patches


def test_facebook_ads_detected():
    apk = MagicMock()
    apk.get_activities.return_value = ["com.facebook.ads.InterstitialAd"]
    apk.get_providers.return_value = []
    findings: list = []
    patches: list = []

    check_ads(apk, findings, patches)

    assert findings[0]["type"] == "ads"
    assert "Facebook Ads" in findings[0]["details"]


def test_unity_ads_detected():
    apk = MagicMock()
    apk.get_activities.return_value = ["com.unity3d.ads.UnityAds"]
    apk.get_providers.return_value = []
    findings: list = []
    patches: list = []

    check_ads(apk, findings, patches)

    assert "Unity Ads" in findings[0]["details"]


def test_multiple_networks_detected():
    apk = MagicMock()
    apk.get_activities.return_value = [
        "com.google.android.gms.ads.AdActivity",
        "com.facebook.ads.AdView",
        "com.applovin.sdk.AdActivity",
    ]
    apk.get_providers.return_value = []
    findings: list = []
    patches: list = []

    check_ads(apk, findings, patches)

    assert len(findings[0]["details"]) >= 3


def test_provider_detected():
    apk = MagicMock()
    apk.get_activities.return_value = []
    apk.get_providers.return_value = [
        "com.google.android.gms.ads.MobileAdsInitProvider",
    ]
    findings: list = []
    patches: list = []

    check_ads(apk, findings, patches)

    assert findings[0]["type"] == "ads"


def test_no_duplicate_network():
    """2 activity cùng AdMob → chỉ list 1 lần."""
    apk = MagicMock()
    apk.get_activities.return_value = [
        "com.google.android.gms.ads.AdActivity",
        "com.google.android.gms.ads.purchase.InAppPurchaseActivity",
    ]
    apk.get_providers.return_value = []
    findings: list = []
    patches: list = []

    check_ads(apk, findings, patches)

    # AdMob chỉ xuất hiện 1 lần
    assert findings[0]["details"].count("AdMob") == 1


def test_apk_get_activities_raises():
    apk = MagicMock()
    apk.get_activities.side_effect = Exception("manifest broken")
    apk.get_providers.return_value = []
    findings: list = []
    patches: list = []

    check_ads(apk, findings, patches)

    assert findings[0]["type"] == "no_ads"


def test_apk_get_providers_raises():
    apk = MagicMock()
    apk.get_activities.return_value = []
    apk.get_providers.side_effect = Exception("providers broken")
    findings: list = []
    patches: list = []

    check_ads(apk, findings, patches)

    assert findings[0]["type"] == "no_ads"


def test_all_networks_from_activities():
    """Test tất cả network keys trong _AD_NETWORKS."""
    apk = MagicMock()
    apk.get_activities.return_value = [
        "com.google.android.gms.ads.AdActivity",   # AdMob
        "com.facebook.ads.Ad",                     # Facebook
        "com.unity3d.ads.Ads",                     # Unity
        "com.applovin.sdk.AppLovinAd",             # AppLovin
        "com.ironsource.mobile.IronSource",        # IronSource
        "com.vungle.warren.Vungle",                # Vungle
        "com.chartboost.sdk.Chartboost",           # Chartboost
        "com.adcolony.sdk.AdColony",               # AdColony
        "com.mopub.mobileads.MoPubView",           # MoPub
        "com.inmobi.ads.InMobiAd",                 # InMobi
        "com.startapp.android.publish.StartApp",   # StartApp
    ]
    apk.get_providers.return_value = []
    findings: list = []
    patches: list = []

    check_ads(apk, findings, patches)

    # Phải detect ít nhất 8+ networks
    assert len(findings[0]["details"]) >= 8