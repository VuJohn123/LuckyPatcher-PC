"""Test root + LP detection."""
from unittest.mock import MagicMock, patch

from scanner.checks.security_check import (
    check_lp_detection,
    check_root_detection,
)


def _make_dex_with_methods(method_names: list[str]) -> MagicMock:
    """DEX với 1 class chứa nhiều method."""
    cls = MagicMock()
    cls.get_name.return_value = "Lcom/example/Test;"
    methods = []
    for mn in method_names:
        m = MagicMock()
        m.get_name.return_value = mn
        methods.append(m)
    cls.get_methods.return_value = methods
    dex = MagicMock()
    dex.get_classes.return_value = [cls]
    return dex


def _make_dex_with_classes(class_names: list[str]) -> MagicMock:
    dex = MagicMock()
    classes = []
    for cn in class_names:
        c = MagicMock()
        c.get_name.return_value = cn
        classes.append(c)
    dex.get_classes.return_value = classes
    return dex


# ============================================================
# Root detection
# ============================================================
def test_root_no_detection():
    findings: list = []
    with patch(
        "scanner.checks.security_check.DEX",
        return_value=_make_dex_with_methods(["onCreate", "onClick"]),
    ):
        check_root_detection(
            lambda: [("classes.dex", b"x")], findings,
        )

    assert len(findings) == 1
    assert findings[0]["type"] == "root_detection"
    assert "No" in findings[0]["description"]
    assert findings[0]["color"] is None


def test_root_yes_magisk_method():
    findings: list = []
    with patch(
        "scanner.checks.security_check.DEX",
        return_value=_make_dex_with_methods(["isMagiskPresent"]),
    ):
        check_root_detection(
            lambda: [("classes.dex", b"x")], findings,
        )

    assert len(findings) == 1
    assert findings[0]["color"] == "red"
    assert "Yes" in findings[0]["description"]
    assert "isMagiskPresent" in findings[0]["description"]


def test_root_yes_supersu():
    findings: list = []
    with patch(
        "scanner.checks.security_check.DEX",
        return_value=_make_dex_with_methods(["checkSuperSU"]),
    ):
        check_root_detection(
            lambda: [("classes.dex", b"x")], findings,
        )

    assert findings[0]["color"] == "red"


def test_root_yes_checkroot_case_insensitive():
    findings: list = []
    with patch(
        "scanner.checks.security_check.DEX",
        return_value=_make_dex_with_methods(["CHECKROOT"]),
    ):
        check_root_detection(
            lambda: [("classes.dex", b"x")], findings,
        )

    assert findings[0]["color"] == "red"


def test_root_parse_error_graceful():
    findings: list = []
    with patch(
        "scanner.checks.security_check.DEX",
        side_effect=Exception("dex broken"),
    ):
        check_root_detection(
            lambda: [("classes.dex", b"x")], findings,
        )

    assert findings[0]["type"] == "root_detection"
    assert "No" in findings[0]["description"]


def test_root_empty_dex_list():
    findings: list = []
    check_root_detection(lambda: [], findings)

    assert findings[0]["type"] == "root_detection"
    assert "No" in findings[0]["description"]


# ============================================================
# Root attribution — SDK vs app code
# ============================================================
def _index_with_owners(owners_by_method: dict, strings=()):
    from scanner.dex_index import DexIndex

    classes = sorted({
        c for owners in owners_by_method.values() for c in owners
    })
    hits = {s.lower(): s for s in strings}
    return DexIndex(
        classes=classes,
        classes_lower=[c.lower() for c in classes],
        method_owners={
            m.lower(): set(o) for m, o in owners_by_method.items()
        },
        method_display={m.lower(): m for m in owners_by_method},
        string_hits=hits,
    )


def test_root_sdk_only_probe_is_not_an_alarm():
    """GameAnalytics probe không được báo là app tự check root."""
    findings: list = []
    index = _index_with_owners({
        "isDeviceRooted": {"Lcom/gameanalytics/sdk/GAPlatform;"},
        "checkRootMethod1": {"Lcom/gameanalytics/sdk/GAPlatform;"},
    })
    check_root_detection(lambda: [], findings, index=index)

    assert findings[0]["type"] == "root_detection"
    assert findings[0]["color"] is None
    assert "does not check root" in findings[0]["description"]
    assert "GameAnalytics" in findings[0]["description"]
    assert "GAPlatform.isDeviceRooted" in findings[0]["details"]


def test_root_app_owned_probe_is_an_alarm():
    """Class của chính app → vẫn báo đỏ."""
    findings: list = []
    index = _index_with_owners({
        "isRooted": {"Lnet/mobigame/artemis/AntiCheat;"},
    })
    check_root_detection(lambda: [], findings, index=index)

    assert findings[0]["color"] == "red"
    assert "AntiCheat.isRooted" in findings[0]["description"]


def test_root_kotlin_path_helper_is_ignored():
    """Kotlin FilePathComponents.isRooted không phải root check."""
    findings: list = []
    index = _index_with_owners({
        "isRooted": {"Lkotlin/io/FilePathComponents;"},
    })
    check_root_detection(lambda: [], findings, index=index)

    assert findings[0]["color"] is None
    assert "No root detection detected" in findings[0]["description"]


def test_root_weak_strings_do_not_raise_alarm():
    """su path / test-keys đơn lẻ → informational, không đỏ."""
    findings: list = []
    index = _index_with_owners({}, strings=("/system/bin/su", "test-keys"))
    check_root_detection(lambda: [], findings, index=index)

    assert findings[0]["color"] is None
    assert "/system/bin/su" in findings[0]["details"]


def test_root_magisk_package_is_an_alarm():
    """Tên package root-manager là bằng chứng mạnh."""
    findings: list = []
    index = _index_with_owners({}, strings=("com.topjohnwu.magisk",))
    check_root_detection(lambda: [], findings, index=index)

    assert findings[0]["color"] == "red"


# ============================================================
# LP detection
# ============================================================
def test_lp_no_detection():
    findings: list = []
    with patch(
        "scanner.checks.security_check.DEX",
        return_value=_make_dex_with_classes(["Lcom/example/App;"]),
    ):
        check_lp_detection(
            lambda: [("classes.dex", b"x")], findings,
        )

    assert len(findings) == 1
    assert findings[0]["type"] == "lp_detection"
    assert "No" in findings[0]["description"]


def test_lp_yes_luckypatcher():
    findings: list = []
    with patch(
        "scanner.checks.security_check.DEX",
        return_value=_make_dex_with_classes([
            "Lcom/example/LuckyPatcherDetector;",
        ]),
    ):
        check_lp_detection(
            lambda: [("classes.dex", b"x")], findings,
        )

    assert findings[0]["color"] == "red"
    assert "Yes" in findings[0]["description"]


def test_lp_yes_com_chelpu():
    findings: list = []
    with patch(
        "scanner.checks.security_check.DEX",
        return_value=_make_dex_with_classes([
            "Lcom/chelpus/utils/Utils;",
        ]),
    ):
        check_lp_detection(
            lambda: [("classes.dex", b"x")], findings,
        )

    assert findings[0]["color"] == "red"


def test_lp_parse_error_graceful():
    findings: list = []
    with patch(
        "scanner.checks.security_check.DEX",
        side_effect=Exception("dex broken"),
    ):
        check_lp_detection(
            lambda: [("classes.dex", b"x")], findings,
        )

    assert findings[0]["type"] == "lp_detection"
    assert "No" in findings[0]["description"]
