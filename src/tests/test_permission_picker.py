"""Test permission_picker_dialog + env var bridge."""
from __future__ import annotations

import os
import zipfile

import pytest

from patcher.permission_changer import PermissionChanger


# ============================================================
# FIXTURES
# ============================================================
@pytest.fixture
def fake_manifest(tmp_path):
    """Tạo decompiled dir với manifest giả."""
    dec = tmp_path / "decompiled"
    dec.mkdir()
    manifest = dec / "AndroidManifest.xml"
    manifest.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<manifest>\n'
        '    <uses-permission android:name="android.permission.INTERNET"/>\n'
        '    <uses-permission android:name="android.permission.READ_SMS"/>\n'
        '    <uses-permission android:name="android.permission.SEND_SMS"/>\n'
        '    <uses-permission android:name="android.permission.CAMERA"/>\n'
        '    <uses-permission android:name="com.android.vending.BILLING"/>\n'
        '</manifest>\n'
    )
    return str(dec), str(manifest)


# ============================================================
# ENV VAR RESOLUTION
# ============================================================
class TestEnvVarResolution:
    def test_explicit_arg_wins(self, fake_manifest, monkeypatch):
        monkeypatch.setenv(
            "LP_PERMS_TO_REMOVE", "android.permission.CAMERA"
        )
        dec, _ = fake_manifest
        p = PermissionChanger(
            dec,
            permissions_to_remove=["android.permission.INTERNET"],
            log_callback=lambda *a: None,
        )
        assert p.permissions_to_remove == [
            "android.permission.INTERNET"
        ]

    def test_env_var_used_when_no_arg(
        self, fake_manifest, monkeypatch
    ):
        monkeypatch.setenv(
            "LP_PERMS_TO_REMOVE",
            "android.permission.CAMERA,android.permission.READ_SMS",
        )
        dec, _ = fake_manifest
        p = PermissionChanger(dec, log_callback=lambda *a: None)
        assert p.permissions_to_remove == [
            "android.permission.CAMERA",
            "android.permission.READ_SMS",
        ]

    def test_default_when_no_env_no_arg(
        self, fake_manifest, monkeypatch
    ):
        monkeypatch.delenv("LP_PERMS_TO_REMOVE", raising=False)
        dec, _ = fake_manifest
        p = PermissionChanger(dec, log_callback=lambda *a: None)
        assert p.permissions_to_remove == list(
            PermissionChanger.DEFAULT_REMOVE
        )

    def test_env_var_strips_whitespace(
        self, fake_manifest, monkeypatch
    ):
        monkeypatch.setenv(
            "LP_PERMS_TO_REMOVE",
            "  android.permission.CAMERA  ,  android.permission.READ_SMS ",
        )
        dec, _ = fake_manifest
        p = PermissionChanger(dec, log_callback=lambda *a: None)
        assert p.permissions_to_remove == [
            "android.permission.CAMERA",
            "android.permission.READ_SMS",
        ]

    def test_empty_env_falls_back_to_default(
        self, fake_manifest, monkeypatch
    ):
        monkeypatch.setenv("LP_PERMS_TO_REMOVE", "   ")
        dec, _ = fake_manifest
        p = PermissionChanger(dec, log_callback=lambda *a: None)
        assert p.permissions_to_remove == list(
            PermissionChanger.DEFAULT_REMOVE
        )


# ============================================================
# PATCH LOGIC
# ============================================================
class TestPatchLogic:
    def test_removes_selected_permissions(
        self, fake_manifest, monkeypatch
    ):
        monkeypatch.setenv(
            "LP_PERMS_TO_REMOVE",
            "android.permission.CAMERA,"
            "android.permission.READ_SMS",
        )
        dec, manifest = fake_manifest
        p = PermissionChanger(dec, log_callback=lambda *a: None)
        result = p.patch()
        assert result == 1

        content = open(manifest, encoding="utf-8").read()
        assert "android.permission.CAMERA" not in content
        assert "android.permission.READ_SMS" not in content
        assert "android.permission.INTERNET" in content
        assert "android.permission.SEND_SMS" in content

    def test_returns_zero_when_no_match(
        self, fake_manifest, monkeypatch
    ):
        monkeypatch.setenv(
            "LP_PERMS_TO_REMOVE",
            "android.permission.NONEXISTENT",
        )
        dec, _ = fake_manifest
        p = PermissionChanger(dec, log_callback=lambda *a: None)
        assert p.patch() == 0

    def test_case_insensitive_match(
        self, fake_manifest, monkeypatch
    ):
        monkeypatch.setenv(
            "LP_PERMS_TO_REMOVE",
            "ANDROID.PERMISSION.CAMERA",
        )
        dec, manifest = fake_manifest
        p = PermissionChanger(dec, log_callback=lambda *a: None)
        p.patch()
        content = open(manifest, encoding="utf-8").read()
        assert "android.permission.CAMERA" not in content


# ============================================================
# PERMISSION DATABASE
# ============================================================
class TestPermissionDatabase:
    def test_db_not_empty(self):
        from ui.permission_picker_dialog import _PERMISSION_DB
        assert len(_PERMISSION_DB) > 40

    def test_db_entries_shape(self):
        from ui.permission_picker_dialog import _PERMISSION_DB
        for name, entry in _PERMISSION_DB.items():
            assert isinstance(entry, tuple)
            assert len(entry) == 3
            emoji, cat, desc = entry
            assert cat in (
                "dangerous", "normal", "signature", "special",
            )
            assert isinstance(desc, str) and len(desc) > 3

    def test_common_permissions_have_description(self):
        from ui.permission_picker_dialog import _PERMISSION_DB
        must_have = [
            "INTERNET", "CAMERA", "READ_SMS", "SEND_SMS",
            "ACCESS_FINE_LOCATION", "READ_CONTACTS",
            "WRITE_EXTERNAL_STORAGE", "BILLING",
        ]
        for name in must_have:
            assert name in _PERMISSION_DB, f"{name} missing from DB"