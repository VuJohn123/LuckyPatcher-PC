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