"""Test scanner/checks/packer_check.py — APK packer detection."""
from unittest.mock import MagicMock, patch

import pytest

from scanner.checks.packer_check import (
    _asset_names,
    _get_application_class,
    _get_zip_entries,
    _native_lib_names,
    _scan_dex_prefixes,
    check_packer,
    _PACKER_SIGNATURES,
)


# ============================================================
# HELPERS
# ============================================================
def _make_apk(files=None, app_class=None):
    """Mock APK object with optional manifest + files."""
    apk = MagicMock()
    apk.get_files.return_value = files or []

    if app_class:
        app_elem = MagicMock()
        app_elem.get.return_value = app_class
        xml_root = MagicMock()
        xml_root.findall.return_value = [app_elem]
        apk.get_android_manifest_axml.side_effect = Exception("no axml")
        apk.get_android_manifest_xml.return_value = xml_root
    else:
        apk.get_android_manifest_axml.side_effect = Exception("no axml")
        apk.get_android_manifest_xml.side_effect = Exception("no xml")

    return apk


def _make_dex(classes: list[str]):
    """Mock DEX with class names."""
    dex = MagicMock()
    cls_mocks = []
    for cname in classes:
        c = MagicMock()
        c.get_name.return_value = cname
        cls_mocks.append(c)
    dex.get_classes.return_value = cls_mocks
    return dex


def _empty_dex_gen():
    return iter([])


def _dex_gen(classes: list[str]):
    def _g():
        yield ("classes.dex", b"fake")
    return _g


# ============================================================
# Low-level helpers
# ============================================================
class TestNativeLibNames:
    def test_extracts_so_basenames(self):
        entries = {
            "lib/arm64-v8a/libpairipcore.so",
            "lib/armeabi-v7a/libpairipcore.so",
            "lib/x86/libfoo.so",
        }
        assert _native_lib_names(entries) == {
            "libpairipcore.so", "libfoo.so",
        }

    def test_ignores_non_lib_entries(self):
        entries = {
            "classes.dex", "AndroidManifest.xml",
            "lib/arm64-v8a/libfoo.so",
        }
        assert _native_lib_names(entries) == {"libfoo.so"}

    def test_ignores_non_so(self):
        entries = {
            "lib/arm64-v8a/libfoo.so.txt",
            "lib/arm64-v8a/readme.md",
        }
        assert _native_lib_names(entries) == set()

    def test_empty_entries(self):
        assert _native_lib_names(set()) == set()


class TestAssetNames:
    def test_strips_assets_prefix(self):
        entries = {"assets/foo.dat", "assets/sub/bar.txt"}
        assert _asset_names(entries) == {"foo.dat", "sub/bar.txt"}

    def test_no_assets(self):
        assert _asset_names({"classes.dex"}) == set()

    def test_empty(self):
        assert _asset_names(set()) == set()


class TestGetZipEntries:
    def test_returns_set(self):
        apk = MagicMock()
        apk.get_files.return_value = ["a", "b", "c"]
        assert _get_zip_entries(apk) == {"a", "b", "c"}

    def test_empty_files(self):
        apk = MagicMock()
        apk.get_files.return_value = []
        assert _get_zip_entries(apk) == set()

    def test_exception_returns_empty(self):
        apk = MagicMock()
        apk.get_files.side_effect = Exception("bad")
        assert _get_zip_entries(apk) == set()


class TestGetApplicationClass:
    def test_extracts_from_xml(self):
        apk = _make_apk(app_class="com.example.App")
        assert _get_application_class(apk) == "com.example.App"

    def test_strips_leading_dot(self):
        apk = _make_apk(app_class=".App")
        assert _get_application_class(apk) == "App"

    def test_returns_none_when_no_app(self):
        apk = _make_apk()
        assert _get_application_class(apk) is None


class TestScanDexPrefixes:
    def test_finds_prefix(self):
        def gen():
            yield ("classes.dex", b"x")
        with patch(
            "scanner.checks.packer_check.DEX",
            return_value=_make_dex([
                "Lcom/other/Foo;",
                "Lcom/pairip/application/Application;",
            ]),
        ):
            result = _scan_dex_prefixes(
                gen, ["Lcom/pairip/application/"]
            )
        assert result == "Lcom/pairip/application/Application;"

    def test_no_match(self):
        def gen():
            yield ("classes.dex", b"x")
        with patch(
            "scanner.checks.packer_check.DEX",
            return_value=_make_dex(["Lcom/other/Foo;"]),
        ):
            result = _scan_dex_prefixes(gen, ["Lcom/pairip/"])
        assert result is None

    def test_dex_parse_fail_graceful(self):
        def gen():
            yield ("classes.dex", b"x")
        with patch(
            "scanner.checks.packer_check.DEX",
            side_effect=Exception("bad"),
        ):
            result = _scan_dex_prefixes(gen, ["Lcom/pairip/"])
        assert result is None


# ============================================================
# check_packer — detect via native libs (fast path)
# ============================================================
class TestPackerViaNativeLib:
    def test_pairip_detected(self):
        apk = _make_apk(files=["lib/arm64-v8a/libpairipcore.so"])
        findings: list = []
        patches: list = []

        info = check_packer(apk, "/x.apk", _empty_dex_gen, findings, patches)

        assert info is not None
        assert "PairIP" in info["name"]
        assert info["confidence"] == "high"
        assert info["patchable"] is False
        assert len(findings) == 1
        assert findings[0]["type"] == "packer"
        assert findings[0]["color"] == "red"

    def test_360_jiagu_detected(self):
        apk = _make_apk(files=["lib/armeabi-v7a/libjiagu.so"])
        findings: list = []
        patches: list = []

        info = check_packer(apk, "/x.apk", _empty_dex_gen, findings, patches)

        assert info is not None
        assert "360" in info["name"]
        assert findings[0]["color"] == "red"

    def test_tencent_detected(self):
        apk = _make_apk(files=["lib/arm64-v8a/libshell.so"])
        findings: list = []
        patches: list = []

        info = check_packer(apk, "/x.apk", _empty_dex_gen, findings, patches)
        assert info is not None
        assert "Tencent" in info["name"]


# ============================================================
# check_packer — detect via application class
# ============================================================
class TestPackerViaAppClass:
    def test_pairip_via_app_class(self):
        apk = _make_apk(app_class="com.pairip.application.Application")
        findings: list = []
        patches: list = []

        info = check_packer(apk, "/x.apk", _empty_dex_gen, findings, patches)

        assert info is not None
        assert "PairIP" in info["name"]
        # Evidence chứa app class
        assert any("Application" in e for e in info["evidence"])

    def test_no_packer_when_clean(self):
        apk = _make_apk(app_class="com.example.CleanApp")
        findings: list = []
        patches: list = []

        info = check_packer(apk, "/x.apk", _empty_dex_gen, findings, patches)

        assert info is None
        assert len(findings) == 1
        assert findings[0]["type"] == "no_packer"
        assert findings[0]["color"] is None


# ============================================================
# check_packer — detect via assets
# ============================================================
class TestPackerViaAssets:
    def test_bangcle_via_asset(self):
        apk = _make_apk(files=["assets/classes.jar"])
        findings: list = []
        patches: list = []

        info = check_packer(apk, "/x.apk", _empty_dex_gen, findings, patches)
        assert info is not None
        assert "Bangcle" in info["name"]

    def test_ijiami_via_asset(self):
        apk = _make_apk(files=["assets/ijiami.dat"])
        findings: list = []
        patches: list = []

        info = check_packer(apk, "/x.apk", _empty_dex_gen, findings, patches)
        assert info is not None
        assert "IJiami" in info["name"]


# ============================================================
# check_packer — detect via DEX scan (fallback)
# ============================================================
class TestPackerViaDex:
    def test_pairip_via_dex(self):
        apk = _make_apk()  # no libs, no app class
        findings: list = []
        patches: list = []

        def dex_gen():
            yield ("classes.dex", b"x")

        with patch(
            "scanner.checks.packer_check.DEX",
            return_value=_make_dex([
                "Lcom/pairip/VMRunner;",
            ]),
        ):
            info = check_packer(
                apk, "/x.apk", dex_gen, findings, patches
            )

        assert info is not None
        assert "PairIP" in info["name"]
        assert any("DEX" in e for e in info["evidence"])


# ============================================================
# Confidence sorting
# ============================================================
class TestConfidenceSorting:
    def test_high_confidence_wins_over_medium(self):
        # Files match both PairIP (high) and DexGuard (medium)
        apk = _make_apk(files=[
            "lib/arm64-v8a/libpairipcore.so",
            "assets/DexGuard",
        ])
        findings: list = []
        patches: list = []

        info = check_packer(apk, "/x.apk", _empty_dex_gen, findings, patches)

        assert info is not None
        assert "PairIP" in info["name"]
        assert info["confidence"] == "high"
        # Other signatures mentioned in details
        assert any(
            "Other signatures" in d
            for d in findings[0]["details"]
        )


# ============================================================
# DexGuard is patchable (obfuscator, not hard packer)
# ============================================================
class TestPatchable:
    def test_dexguard_patchable(self):
        apk = _make_apk(files=["assets/DexGuard"])
        findings: list = []
        patches: list = []

        info = check_packer(apk, "/x.apk", _empty_dex_gen, findings, patches)

        assert info is not None
        assert info["patchable"] is True
        # Patchable → yellow
        assert findings[0]["color"] == "yellow"

    def test_pairip_not_patchable(self):
        apk = _make_apk(files=["lib/arm64-v8a/libpairipcore.so"])
        findings: list = []
        patches: list = []

        info = check_packer(apk, "/x.apk", _empty_dex_gen, findings, patches)

        assert info is not None
        assert info["patchable"] is False
        assert findings[0]["color"] == "red"


# ============================================================
# Signature table integrity
# ============================================================
class TestSignatureTable:
    def test_all_signatures_have_required_keys(self):
        for name, sig in _PACKER_SIGNATURES.items():
            for key in ("confidence", "patchable",
                        "app_classes", "dex_prefixes",
                        "native_libs", "assets"):
                assert key in sig, f"{name} missing {key}"

    def test_confidence_values_valid(self):
        for name, sig in _PACKER_SIGNATURES.items():
            assert sig["confidence"] in ("high", "medium", "low"), \
                f"{name} has invalid confidence"

    def test_patchable_is_bool(self):
        for name, sig in _PACKER_SIGNATURES.items():
            assert isinstance(sig["patchable"], bool), \
                f"{name} patchable not bool"