"""Test AdScanner — mock APK, không cần file thật."""
from unittest.mock import MagicMock, patch

from scanner.ad_scanner import AdScanner


def _make_scanner(activities, providers=None):
    with patch("scanner.ad_scanner.APK") as mock_apk:
        inst = MagicMock()
        inst.get_activities.return_value = activities
        inst.get_providers.return_value = providers or []
        mock_apk.return_value = inst
        return AdScanner("/dummy.apk"), inst


def test_no_ads_detected():
    scanner, _ = _make_scanner(["com.app.MainActivity"])
    acts, provs = scanner.scan_manifest()
    assert acts == []
    assert provs == []


def test_detect_admob():
    scanner, _ = _make_scanner(
        ["com.google.android.gms.ads.AdActivity", "com.app.MainActivity"]
    )
    acts, _ = scanner.scan_manifest()
    assert "com.google.android.gms.ads.AdActivity" in acts


def test_detect_facebook_ads():
    scanner, _ = _make_scanner(["com.facebook.ads.InterstitialAd"])
    acts, _ = scanner.scan_manifest()
    assert len(acts) == 1


def test_detect_unity_ads():
    scanner, _ = _make_scanner(["com.unity3d.ads.UnityAds"])
    acts, _ = scanner.scan_manifest()
    assert len(acts) == 1


def test_detect_multiple_networks():
    scanner, _ = _make_scanner([
        "com.google.android.gms.ads.AdActivity",
        "com.facebook.ads.AdActivity",
        "com.applovin.sdk.AdActivity",
    ])
    acts, _ = scanner.scan_manifest()
    assert len(acts) == 3


def test_detect_provider():
    scanner, _ = _make_scanner([], ["com.google.android.gms.ads.MobileAdsInitProvider"])
    _, provs = scanner.scan_manifest()
    assert len(provs) == 1


def test_apk_raises_returns_empty():
    with patch("scanner.ad_scanner.APK") as mock_apk:
        inst = MagicMock()
        inst.get_activities.side_effect = Exception("parse error")
        mock_apk.return_value = inst
        scanner = AdScanner("/dummy.apk")
        acts, provs = scanner.scan_manifest()
        assert acts == []