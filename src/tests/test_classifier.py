"""Test AppClassifier — quick scan colors."""
from unittest.mock import MagicMock, patch

from scanner.classifier import AppClassifier


# ============================================================
# Constructor
# ============================================================
def test_classifier_no_path():
    """Không có apk_path → apk=None → classify trả ['white']."""
    c = AppClassifier(None)
    assert c.apk is None
    assert c.classify() == ["white"]


# ============================================================
# classify with mocked APK
# ============================================================
def test_classify_clean_app():
    """App thường không license/ads/system → ['white']."""
    with patch("scanner.classifier.APK") as mock_apk_cls:
        mock_apk = MagicMock()
        mock_apk.get_activities.return_value = ["com.example.MainActivity"]
        mock_apk.get_package.return_value = "com.example.app"
        mock_apk_cls.return_value = mock_apk

        with patch.object(
            AppClassifier, "_has_license", return_value=False
        ):
            c = AppClassifier("/tmp/x.apk")
            assert c.classify() == ["white"]


def test_classify_license_only():
    with patch("scanner.classifier.APK"):
        with patch.object(
            AppClassifier, "_has_license", return_value=True
        ), patch.object(
            AppClassifier, "_has_ads", return_value=False
        ), patch.object(
            AppClassifier, "_is_system", return_value=False
        ):
            c = AppClassifier("/tmp/x.apk")
            assert c.classify() == ["green"]


def test_classify_ads_only():
    with patch("scanner.classifier.APK"):
        with patch.object(
            AppClassifier, "_has_license", return_value=False
        ), patch.object(
            AppClassifier, "_has_ads", return_value=True
        ), patch.object(
            AppClassifier, "_is_system", return_value=False
        ):
            c = AppClassifier("/tmp/x.apk")
            assert c.classify() == ["blue"]


def test_classify_system_only():
    with patch("scanner.classifier.APK"):
        with patch.object(
            AppClassifier, "_has_license", return_value=False
        ), patch.object(
            AppClassifier, "_has_ads", return_value=False
        ), patch.object(
            AppClassifier, "_is_system", return_value=True
        ):
            c = AppClassifier("/tmp/x.apk")
            assert c.classify() == ["purple"]


def test_classify_all_three():
    with patch("scanner.classifier.APK"):
        with patch.object(
            AppClassifier, "_has_license", return_value=True
        ), patch.object(
            AppClassifier, "_has_ads", return_value=True
        ), patch.object(
            AppClassifier, "_is_system", return_value=True
        ):
            c = AppClassifier("/tmp/x.apk")
            colors = c.classify()
            assert "green" in colors
            assert "blue" in colors
            assert "purple" in colors


# ============================================================
# _has_ads
# ============================================================
def test_has_ads_admob():
    with patch("scanner.classifier.APK") as mock_apk_cls:
        mock_apk = MagicMock()
        mock_apk.get_activities.return_value = [
            "com.google.android.gms.ads.AdActivity",
        ]
        mock_apk_cls.return_value = mock_apk
        c = AppClassifier("/tmp/x.apk")
        assert c._has_ads() is True


def test_has_ads_facebook():
    with patch("scanner.classifier.APK") as mock_apk_cls:
        mock_apk = MagicMock()
        mock_apk.get_activities.return_value = [
            "com.facebook.ads.InterstitialAd",
        ]
        mock_apk_cls.return_value = mock_apk
        c = AppClassifier("/tmp/x.apk")
        assert c._has_ads() is True


def test_has_ads_unity():
    with patch("scanner.classifier.APK") as mock_apk_cls:
        mock_apk = MagicMock()
        mock_apk.get_activities.return_value = [
            "com.unity3d.ads.UnityAds",
        ]
        mock_apk_cls.return_value = mock_apk
        c = AppClassifier("/tmp/x.apk")
        assert c._has_ads() is True


def test_has_ads_none():
    with patch("scanner.classifier.APK") as mock_apk_cls:
        mock_apk = MagicMock()
        mock_apk.get_activities.return_value = ["com.example.Main"]
        mock_apk_cls.return_value = mock_apk
        c = AppClassifier("/tmp/x.apk")
        assert c._has_ads() is False


def test_has_ads_exception_returns_false():
    with patch("scanner.classifier.APK") as mock_apk_cls:
        mock_apk = MagicMock()
        mock_apk.get_activities.side_effect = Exception("manifest broken")
        mock_apk_cls.return_value = mock_apk
        c = AppClassifier("/tmp/x.apk")
        assert c._has_ads() is False


# ============================================================
# _is_system
# ============================================================
def test_is_system_com_android():
    with patch("scanner.classifier.APK") as mock_apk_cls:
        mock_apk = MagicMock()
        mock_apk.get_package.return_value = "com.android.systemui"
        mock_apk_cls.return_value = mock_apk
        c = AppClassifier("/tmp/x.apk")
        assert c._is_system() is True


def test_is_system_google_android():
    with patch("scanner.classifier.APK") as mock_apk_cls:
        mock_apk = MagicMock()
        mock_apk.get_package.return_value = "com.google.android.gms"
        mock_apk_cls.return_value = mock_apk
        c = AppClassifier("/tmp/x.apk")
        assert c._is_system() is True


def test_is_system_regular():
    with patch("scanner.classifier.APK") as mock_apk_cls:
        mock_apk = MagicMock()
        mock_apk.get_package.return_value = "com.example.app"
        mock_apk_cls.return_value = mock_apk
        c = AppClassifier("/tmp/x.apk")
        assert c._is_system() is False


def test_is_system_exception():
    with patch("scanner.classifier.APK") as mock_apk_cls:
        mock_apk = MagicMock()
        mock_apk.get_package.side_effect = Exception("no package")
        mock_apk_cls.return_value = mock_apk
        c = AppClassifier("/tmp/x.apk")
        assert c._is_system() is False


# ============================================================
# _has_license (DEX)
# ============================================================
def test_has_license_offline_helper_skipped():
    """OfflineLicenseHelper phải bị skip, không tính là license."""
    import zipfile, io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("classes.dex", b"fake")
    fake_apk_bytes = buf.getvalue()

    with patch("scanner.classifier.APK") as mock_apk_cls:
        mock_apk = MagicMock()
        mock_apk_cls.return_value = mock_apk

        cls1 = MagicMock()
        cls1.get_name.return_value = (
            "Lcom/google/android/exoplayer2/drm/OfflineLicenseHelper;"
        )
        mock_dex = MagicMock()
        mock_dex.get_classes.return_value = [cls1]

        with patch("scanner.classifier.DEX", return_value=mock_dex), \
             patch("scanner.classifier.zipfile.ZipFile") as mock_zip:
            mock_zip.return_value.__enter__.return_value.namelist.return_value = ["classes.dex"]
            mock_zip.return_value.__enter__.return_value.read.return_value = fake_apk_bytes
            c = AppClassifier("/tmp/x.apk")
            # _has_license: OfflineLicenseHelper bị skip → return False
            result = c._has_license()
            assert result is False


def test_has_license_none_dex():
    """Không tìm thấy dex → return False."""
    with patch("scanner.classifier.APK") as mock_apk_cls:
        mock_apk_cls.return_value = MagicMock()
        with patch.object(
            AppClassifier, "_get_dex_bytes", return_value=None
        ):
            c = AppClassifier("/tmp/x.apk")
            assert c._has_license() is False