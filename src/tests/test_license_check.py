"""Test license detection — LVL, LicenseValidator, manifest fallback."""
from unittest.mock import MagicMock, patch

from scanner.checks.license_check import check_license


def _make_class(name: str, methods: list[str] | None = None) -> MagicMock:
    cls = MagicMock()
    cls.get_name.return_value = name
    mocks = []
    for m in (methods or []):
        mm = MagicMock()
        mm.get_name.return_value = m
        mocks.append(mm)
    cls.get_methods.return_value = mocks
    return cls


def _make_dex(classes: list) -> MagicMock:
    dex = MagicMock()
    dex.get_classes.return_value = classes
    return dex


# ============================================================
# DEX scan path
# ============================================================
def test_no_license_finding():
    """Không có class license → finding 'no_license'."""
    apk = MagicMock()
    apk.get_activities.return_value = []
    dex = _make_dex([_make_class("Lcom/example/MainActivity;")])
    findings: list = []
    patches: list = []

    with patch(
        "scanner.checks.license_check.DEX", return_value=dex
    ):
        check_license(
            apk, "/tmp/x.apk", lambda: [("classes.dex", b"x")],
            findings, patches,
        )

    assert len(findings) == 1
    assert findings[0]["type"] == "no_license"
    assert patches == []


def test_lvl_class_triggers_license_finding():
    """Class có 'license' trong tên → finding 'license'."""
    apk = MagicMock()
    dex = _make_dex([
        _make_class("Lcom/android/vending/licensing/LicenseValidator;",
                    ["allow", "verify"]),
    ])
    findings: list = []
    patches: list = []

    with patch(
        "scanner.checks.license_check.DEX", return_value=dex
    ):
        check_license(
            apk, "/tmp/x.apk", lambda: [("classes.dex", b"x")],
            findings, patches,
        )

    assert len(findings) == 1
    assert findings[0]["type"] == "license"
    assert findings[0]["color"] == "green"
    assert "license" in patches


def test_blacklist_offline_license_helper_skipped():
    """ExoPlayer OfflineLicenseHelper bị skip (blacklist)."""
    apk = MagicMock()
    apk.get_activities.return_value = []
    dex = _make_dex([
        _make_class("Lcom/google/android/exoplayer2/drm/OfflineLicenseHelper;"),
    ])
    findings: list = []
    patches: list = []

    with patch(
        "scanner.checks.license_check.DEX", return_value=dex
    ):
        check_license(
            apk, "/tmp/x.apk", lambda: [("classes.dex", b"x")],
            findings, patches,
        )

    # Không match license → fallback manifest → không tìm thấy → "no_license"
    assert len(findings) == 1
    assert findings[0]["type"] == "no_license"


def test_lvl_case_insensitive():
    """LVL match case-insensitive: 'LVL', 'Lvl', 'lvl'."""
    apk = MagicMock()
    dex = _make_dex([
        _make_class("Lcom/example/lvl/LvlCheck;"),
    ])
    findings: list = []
    patches: list = []

    with patch(
        "scanner.checks.license_check.DEX", return_value=dex
    ):
        check_license(
            apk, "/tmp/x.apk", lambda: [("classes.dex", b"x")],
            findings, patches,
        )

    assert findings[0]["type"] == "license"


def test_dex_parse_error_graceful():
    """DEX parse fail → skip, không crash."""
    apk = MagicMock()
    apk.get_activities.return_value = []
    findings: list = []
    patches: list = []

    with patch(
        "scanner.checks.license_check.DEX",
        side_effect=Exception("dex parse fail"),
    ):
        check_license(
            apk, "/tmp/x.apk", lambda: [("classes.dex", b"x")],
            findings, patches,
        )

    assert findings[0]["type"] == "no_license"


def test_multiple_dex_files():
    """Dex đầu không có license, dex 2 có → tìm thấy."""
    apk = MagicMock()
    dex_clean = _make_dex([_make_class("Lcom/x/App;")])
    dex_license = _make_dex([_make_class("Lcom/license/Check;")])
    findings: list = []
    patches: list = []

    def _dex_factory(data):
        # Trả về dex khác nhau dựa vào data
        return dex_license if data == b"dex2" else dex_clean

    with patch(
        "scanner.checks.license_check.DEX", side_effect=_dex_factory
    ):
        check_license(
            apk, "/tmp/x.apk",
            lambda: [("classes.dex", b"dex1"), ("classes2.dex", b"dex2")],
            findings, patches,
        )

    assert findings[0]["type"] == "license"


# ============================================================
# Manifest fallback
# ============================================================
def test_manifest_fallback_license_activity():
    """Không có dex license nhưng activity có 'license'."""
    apk = MagicMock()
    apk.get_activities.return_value = [
        "com.example.LicenseActivity",
        "com.example.MainActivity",
    ]
    dex = _make_dex([_make_class("Lcom/x/Main;")])
    findings: list = []
    patches: list = []

    with patch(
        "scanner.checks.license_check.DEX", return_value=dex
    ):
        check_license(
            apk, "/tmp/x.apk", lambda: [("classes.dex", b"x")],
            findings, patches,
        )

    assert findings[0]["type"] == "license"
    assert "Activity" in findings[0]["description"]


def test_manifest_exoplayer_activity_skipped():
    """Activity có 'license' + 'exoplayer' → skip (DRM, không phải LVL)."""
    apk = MagicMock()
    apk.get_activities.return_value = [
        "com.google.android.exoplayer2.drm.license.DrmActivity",
    ]
    dex = _make_dex([_make_class("Lcom/x/Main;")])
    findings: list = []
    patches: list = []

    with patch(
        "scanner.checks.license_check.DEX", return_value=dex
    ):
        check_license(
            apk, "/tmp/x.apk", lambda: [("classes.dex", b"x")],
            findings, patches,
        )

    # Activity bị skip vì 'exoplayer'
    assert findings[0]["type"] == "no_license"


def test_apk_get_activities_raises():
    """apk.get_activities lỗi → fallback qua dex, không crash."""
    apk = MagicMock()
    apk.get_activities.side_effect = Exception("manifest parse fail")
    dex = _make_dex([_make_class("Lcom/x/Main;")])
    findings: list = []
    patches: list = []

    with patch(
        "scanner.checks.license_check.DEX", return_value=dex
    ):
        check_license(
            apk, "/tmp/x.apk", lambda: [("classes.dex", b"x")],
            findings, patches,
        )

    assert findings[0]["type"] == "no_license"