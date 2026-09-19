"""Test check_packer_with_fallback + _replace_no_packer_finding.

Tier 1-4 của `check_packer` đã có test trong test_packer_check.py.
File này cover wrapper + bytecode fallback integration.
"""
from __future__ import annotations

import zipfile
from unittest.mock import MagicMock

import pytest

from scanner.checks.packer_check import (
    _replace_no_packer_finding,
    check_packer_with_fallback,
)


# ============================================================
# Helpers
# ============================================================
def _make_apk(tmp_path, name: str, dex_payload: bytes | None = None,
              native_lib: str | None = None):
    """Build fake APK với dex và/hoặc native lib."""
    apk = tmp_path / name
    with zipfile.ZipFile(apk, "w") as z:
        if dex_payload is not None:
            z.writestr("classes.dex", dex_payload)
        if native_lib:
            z.writestr(f"lib/arm64-v8a/{native_lib}", b"FAKE_SO")
    return str(apk)


def _fake_dex(*strings: str) -> bytes:
    """Fake dex bytes chứa class descriptors."""
    parts = []
    for s in strings:
        parts.append(s.encode("utf-8"))
        parts.append(b"\x00")
    return b"".join(parts)


def _mock_apk(
    app_class: str | None = None,
    files: list[str] | None = None,
) -> MagicMock:
    """Mock androguard APK object cho `check_packer`."""
    apk = MagicMock()
    files = files or []
    apk.get_files.return_value = files

    if app_class:
        # Mock manifest với application android:name
        import xml.etree.ElementTree as ET
        root = ET.fromstring(
            f'<manifest><application '
            f'xmlns:android="http://schemas.android.com/apk/res/android" '
            f'android:name="{app_class}"/></manifest>'
        )
        xml_mock = MagicMock()
        xml_mock.findall.side_effect = lambda tag: root.findall(tag)
        apk.get_android_manifest_xml.return_value = xml_mock
        apk.get_android_manifest_axml.return_value.get_xml.return_value = (
            ET.tostring(root)
        )
    else:
        apk.get_android_manifest_axml.return_value.get_xml.return_value = (
            b"<manifest/>"
        )
    return apk


def _no_dex() -> list:
    return []


# ============================================================
# check_packer_with_fallback — primary tier wins
# ============================================================
class TestWrapperPrimaryWins:
    def test_primary_pairip_via_native_lib(self, tmp_path):
        """Primary detect PairIP qua libpairipcore.so → return ngay."""
        apk_path = _make_apk(
            tmp_path, "p.apk",
            dex_payload=_fake_dex("Lcom/example/Foo;"),
            native_lib="libpairipcore.so",
        )
        mock_apk = _mock_apk(
            files=["lib/arm64-v8a/libpairipcore.so", "classes.dex"]
        )
        findings: list[dict] = []

        result = check_packer_with_fallback(
            mock_apk, apk_path, _no_dex, findings, [],
        )

        assert result is not None
        assert "PairIP" in result["name"]
        # Finding phải là `packer`, không phải `no_packer`
        assert any(f["type"] == "packer" for f in findings)
        assert not any(f["type"] == "no_packer" for f in findings)

    def test_primary_returns_packer_finding(self, tmp_path):
        apk_path = _make_apk(
            tmp_path, "p.apk",
            native_lib="libjiagu.so",
        )
        mock_apk = _mock_apk(
            files=["lib/arm64-v8a/libjiagu.so"]
        )
        findings: list[dict] = []

        result = check_packer_with_fallback(
            mock_apk, apk_path, _no_dex, findings, [],
        )
        assert result is not None
        assert "360" in result["name"]


# ============================================================
# check_packer_with_fallback — bytecode fallback tier
# ============================================================
class TestWrapperBytecodeFallback:
    def test_bytecode_fallback_when_primary_none(self, tmp_path):
        """Primary không match, bytecode match PairIP."""
        apk_path = _make_apk(
            tmp_path, "p.apk",
            dex_payload=_fake_dex("Lcom/pairip/VMRunner;"),
        )
        mock_apk = _mock_apk(files=["classes.dex"])  # no app_class, no libs
        findings: list[dict] = []

        result = check_packer_with_fallback(
            mock_apk, apk_path, _no_dex, findings, [],
        )

        assert result is not None
        assert "PairIP" in result["name"]
        # Finding phải được REPLACE (no_packer → packer)
        assert not any(f["type"] == "no_packer" for f in findings)
        assert any(f["type"] == "packer" for f in findings)

    def test_bytecode_fallback_replaces_no_packer_finding(self, tmp_path):
        apk_path = _make_apk(
            tmp_path, "p.apk",
            dex_payload=_fake_dex("Lcom/tencent/StubShell/StubApp;"),
        )
        mock_apk = _mock_apk(files=["classes.dex"])
        findings: list[dict] = []

        check_packer_with_fallback(
            mock_apk, apk_path, _no_dex, findings, [],
        )

        # Should have replaced no_packer with packer
        types = [f["type"] for f in findings]
        assert "packer" in types
        assert "no_packer" not in types

    def test_no_detection_returns_none(self, tmp_path):
        """Không primary, không bytecode → None."""
        apk_path = _make_apk(
            tmp_path, "p.apk",
            dex_payload=_fake_dex("Lcom/example/Clean;"),
        )
        mock_apk = _mock_apk(files=["classes.dex"])
        findings: list[dict] = []

        result = check_packer_with_fallback(
            mock_apk, apk_path, _no_dex, findings, [],
        )
        assert result is None
        # no_packer finding vẫn còn (vì không replace)
        assert any(f["type"] == "no_packer" for f in findings)

    def test_missing_apk_returns_none(self, tmp_path):
        mock_apk = _mock_apk()
        findings: list[dict] = []

        result = check_packer_with_fallback(
            mock_apk, str(tmp_path / "nope.apk"),
            _no_dex, findings, [],
        )
        assert result is None


# ============================================================
# _replace_no_packer_finding — unit test trực tiếp
# ============================================================
class TestReplaceNoPackerFinding:
    def test_replaces_existing_no_packer(self):
        findings = [
            {"type": "no_packer", "color": None, "title": "Packer"},
            {"type": "other", "color": None},
        ]
        fallback = {
            "name": "PairIP",
            "confidence": "high",
            "patchable": False,
            "evidence": ["bytecode_class:Lcom/pairip/"],
        }

        _replace_no_packer_finding(findings, fallback, "/x.apk")

        assert len(findings) == 2
        assert findings[0]["type"] == "packer"
        assert findings[0]["color"] == "red"
        assert "PairIP" in findings[0]["title"]
        assert "bytecode fallback" in " ".join(findings[0]["details"])

    def test_appends_when_no_packer_not_found(self):
        findings = [{"type": "other", "color": None}]
        fallback = {
            "name": "Tencent",
            "confidence": "high",
            "patchable": False,
            "evidence": [],
        }

        _replace_no_packer_finding(findings, fallback, "/x.apk")

        assert len(findings) == 2
        assert findings[-1]["type"] == "packer"

    def test_patchable_true_color_yellow(self):
        findings = [{"type": "no_packer", "color": None}]
        fallback = {
            "name": "DexGuard",
            "confidence": "medium",
            "patchable": True,
            "evidence": [],
        }

        _replace_no_packer_finding(findings, fallback, "/x.apk")

        assert findings[0]["type"] == "packer"
        assert findings[0]["color"] == "yellow"
        # Description nói về obfuscation (không phải shell)
        assert "obfuscation" in findings[0]["description"].lower()

    def test_patchable_false_color_red(self):
        findings = [{"type": "no_packer", "color": None}]
        fallback = {
            "name": "360",
            "confidence": "high",
            "patchable": False,
            "evidence": [],
        }

        _replace_no_packer_finding(findings, fallback, "/x.apk")

        assert findings[0]["color"] == "red"
        assert "packed" in findings[0]["description"].lower()

    def test_empty_evidence_still_works(self):
        findings = [{"type": "no_packer", "color": None}]
        fallback = {
            "name": "X",
            "confidence": "low",
            "patchable": False,
            "evidence": [],
        }

        _replace_no_packer_finding(findings, fallback, "/x.apk")

        # Details phải có ít nhất Confidence + Source
        assert len(findings[0]["details"]) >= 2

    def test_empty_findings_appends(self):
        findings: list[dict] = []
        fallback = {
            "name": "X",
            "confidence": "low",
            "patchable": False,
            "evidence": [],
        }

        _replace_no_packer_finding(findings, fallback, "/x.apk")
        assert len(findings) == 1


# ============================================================
# Integration: bytecode tier crash safe
# ============================================================
class TestBytecodeCrashSafety:
    def test_bytecode_module_crash_is_isolated(
        self, tmp_path, monkeypatch
    ):
        """Nếu augment_packer_result crash → return None, không raise."""
        apk_path = _make_apk(
            tmp_path, "p.apk",
            dex_payload=_fake_dex("Lcom/example/Clean;"),
        )
        mock_apk = _mock_apk(files=["classes.dex"])
        findings: list[dict] = []

        import scanner.checks.packer_bytecode as pb

        def _boom(*a, **kw):
            raise RuntimeError("simulated crash")

        monkeypatch.setattr(pb, "augment_packer_result", _boom)

        result = check_packer_with_fallback(
            mock_apk, apk_path, _no_dex, findings, [],
        )
        assert result is None