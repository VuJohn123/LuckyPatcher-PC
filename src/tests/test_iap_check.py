"""Test IAP detection — BILLING permission + BillingClient class."""
from unittest.mock import MagicMock, patch

from scanner.checks.iap_check import check_iap


def _make_dex(class_names: list[str]) -> MagicMock:
    dex = MagicMock()
    classes = []
    for cn in class_names:
        c = MagicMock()
        c.get_name.return_value = cn
        classes.append(c)
    dex.get_classes.return_value = classes
    return dex


def test_no_iap_finding():
    apk = MagicMock()
    apk.get_permissions.return_value = []
    findings: list = []
    patches: list = []

    with patch(
        "scanner.checks.iap_check.DEX",
        return_value=_make_dex(["Lcom/x/App;"]),
    ):
        check_iap(
            apk, lambda: [("classes.dex", b"x")],
            findings, patches,
        )

    assert findings[0]["type"] == "no_iap"


def test_billing_permission_triggers_iap():
    apk = MagicMock()
    apk.get_permissions.return_value = ["com.android.vending.BILLING"]
    findings: list = []
    patches: list = []

    check_iap(apk, lambda: [], findings, patches)

    assert findings[0]["type"] == "iap"
    assert findings[0]["color"] == "green"
    assert "iap" in patches
    # Phải return sớm — không scan dex
    assert "BILLING" in findings[0]["description"]


def test_billing_client_class_in_dex():
    apk = MagicMock()
    apk.get_permissions.return_value = []
    findings: list = []
    patches: list = []

    with patch(
        "scanner.checks.iap_check.DEX",
        return_value=_make_dex([
            "Lcom/android/billingclient/api/BillingClient;",
        ]),
    ):
        check_iap(
            apk, lambda: [("classes.dex", b"x")],
            findings, patches,
        )

    assert findings[0]["type"] == "iap"
    assert "BillingClient" in findings[0]["description"]


def test_iinapp_billing_service_detected():
    apk = MagicMock()
    apk.get_permissions.return_value = []
    findings: list = []
    patches: list = []

    with patch(
        "scanner.checks.iap_check.DEX",
        return_value=_make_dex([
            "Lcom/android/vending/billing/IInAppBillingService;",
        ]),
    ):
        check_iap(
            apk, lambda: [("classes.dex", b"x")],
            findings, patches,
        )

    assert findings[0]["type"] == "iap"
    assert "IInAppBillingService" in findings[0]["description"]


def test_apk_get_permissions_raises():
    apk = MagicMock()
    apk.get_permissions.side_effect = Exception("manifest broken")
    findings: list = []
    patches: list = []

    with patch(
        "scanner.checks.iap_check.DEX",
        return_value=_make_dex([]),
    ):
        check_iap(
            apk, lambda: [("classes.dex", b"x")],
            findings, patches,
        )

    assert findings[0]["type"] == "no_iap"


def test_dex_parse_error_graceful():
    apk = MagicMock()
    apk.get_permissions.return_value = []
    findings: list = []
    patches: list = []

    with patch(
        "scanner.checks.iap_check.DEX",
        side_effect=Exception("parse error"),
    ):
        check_iap(
            apk, lambda: [("classes.dex", b"x")],
            findings, patches,
        )

    assert findings[0]["type"] == "no_iap"


def test_already_in_available_patches_no_duplicate():
    """Nếu 'iap' đã có trong available_patches → không thêm lại."""
    apk = MagicMock()
    apk.get_permissions.return_value = ["com.android.vending.BILLING"]
    findings: list = []
    patches: list = ["iap"]  # đã có sẵn

    check_iap(apk, lambda: [], findings, patches)

    assert patches.count("iap") == 1