"""Test core/sign_with_key.py — AOSP key signing."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from core.sign_with_key import APKSigner


# ============================================================
# HELPERS
# ============================================================
def _make_tools_dir(tmp_path, keys=("platform",)):
    """Tạo tools/keys/<key>.pk8 + .x509.pem cho test."""
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    for k in keys:
        (keys_dir / f"{k}.pk8").write_bytes(b"fake-pk8")
        (keys_dir / f"{k}.x509.pem").write_text("fake-pem")
    return tmp_path


def _make_apk(tmp_path, name="app.apk"):
    apk = tmp_path / name
    apk.write_bytes(b"PK\x03\x04fake apk data")
    return apk


@pytest.fixture
def no_apksigner():
    """Disable apksigner discovery."""
    with patch.object(APKSigner, "_find_apksigner", return_value=None):
        yield


@pytest.fixture
def with_apksigner():
    """Enable fake apksigner."""
    with patch.object(APKSigner, "_find_apksigner",
                      return_value="/fake/apksigner"):
        yield


# ============================================================
# KEY_ALIASES
# ============================================================
class TestKeyAliases:
    def test_has_all_keys(self):
        for key in ("platform", "media", "shared", "testkey"):
            assert key in APKSigner.KEY_ALIASES

    def test_alias_values_match_keys(self):
        for k, v in APKSigner.KEY_ALIASES.items():
            assert k == v


# ============================================================
# _find_apksigner
# ============================================================
class TestFindApksigner:
    def test_from_path(self, tmp_path):
        with patch("core.sign_with_key.shutil.which",
                   side_effect=lambda n: "/fake/apksigner"
                   if "apksigner" in n else None):
            signer = APKSigner(str(tmp_path), log_callback=lambda *a: None)
        assert signer._apksigner == "/fake/apksigner"

    def test_from_android_home(self, tmp_path, monkeypatch):
        sdk = tmp_path / "sdk"
        bt = sdk / "build-tools" / "34.0.0"
        bt.mkdir(parents=True)
        (bt / "apksigner.bat").write_text("fake")
        monkeypatch.setenv("ANDROID_HOME", str(sdk))

        with patch("core.sign_with_key.shutil.which", return_value=None):
            signer = APKSigner(str(tmp_path), log_callback=lambda *a: None)
        assert signer._apksigner is not None
        assert "apksigner" in signer._apksigner

    def test_no_path_no_sdk_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANDROID_HOME", raising=False)
        monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
        with patch("core.sign_with_key.shutil.which", return_value=None):
            signer = APKSigner(str(tmp_path), log_callback=lambda *a: None)
        assert signer._apksigner is None

    def test_sdk_no_build_tools_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANDROID_HOME", str(tmp_path))
        with patch("core.sign_with_key.shutil.which", return_value=None):
            signer = APKSigner(str(tmp_path), log_callback=lambda *a: None)
        assert signer._apksigner is None


# ============================================================
# sign_apk — validation
# ============================================================
class TestSignApkValidation:
    def test_invalid_key_type(self, tmp_path, no_apksigner):
        signer = APKSigner(str(_make_tools_dir(tmp_path)),
                           log_callback=lambda *a: None)
        with pytest.raises(ValueError, match="Key type"):
            signer.sign_apk(str(_make_apk(tmp_path)), key_type="bogus")

    def test_missing_apk(self, tmp_path, no_apksigner):
        signer = APKSigner(str(_make_tools_dir(tmp_path)),
                           log_callback=lambda *a: None)
        with pytest.raises(FileNotFoundError):
            signer.sign_apk(str(tmp_path / "nope.apk"), key_type="platform")

    def test_missing_key_files(self, tmp_path, no_apksigner):
        # Không tạo keys
        tools = tmp_path
        (tools / "keys").mkdir()
        apk = _make_apk(tmp_path)
        signer = APKSigner(str(tools), log_callback=lambda *a: None)

        with pytest.raises(FileNotFoundError, match="key files"):
            signer.sign_apk(str(apk), key_type="platform")


# ============================================================
# sign_apk — apksigner path
# ============================================================
class TestSignApkWithApksigner:
    def test_success(self, tmp_path, with_apksigner):
        tools = _make_tools_dir(tmp_path, keys=("platform",))
        apk = _make_apk(tmp_path)
        signer = APKSigner(str(tools), log_callback=lambda *a: None)

        with patch.object(signer, "_pk8_to_p12", return_value="/tmp/k.p12"), \
             patch("core.sign_with_key.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            result = signer.sign_apk(str(apk), key_type="platform")

        assert result.endswith("_signed.apk")

    def test_apksigner_fail_falls_back_to_jarsigner(
        self, tmp_path, with_apksigner
    ):
        tools = _make_tools_dir(tmp_path, keys=("platform",))
        apk = _make_apk(tmp_path)
        signer = APKSigner(str(tools), log_callback=lambda *a: None)

        with patch.object(signer, "_pk8_to_p12", return_value="/tmp/k.p12"), \
             patch.object(signer, "_p12_to_jks", return_value="/tmp/k.jks"), \
             patch.object(signer, "_sign_with_apksigner",
                          side_effect=RuntimeError("apksigner boom")), \
             patch.object(signer, "_jarsigner",
                          return_value="/tmp/fallback_signed.apk") as mock_js:
            result = signer.sign_apk(str(apk), key_type="platform")

        assert "fallback" in result
        mock_js.assert_called_once()

    def test_no_apksigner_uses_jarsigner(self, tmp_path, no_apksigner):
        tools = _make_tools_dir(tmp_path, keys=("media",))
        apk = _make_apk(tmp_path)
        signer = APKSigner(str(tools), log_callback=lambda *a: None)

        with patch.object(signer, "_pk8_to_p12", return_value="/tmp/k.p12"), \
             patch.object(signer, "_p12_to_jks", return_value="/tmp/k.jks"), \
             patch.object(signer, "_jarsigner",
                          return_value="/tmp/signed.apk") as mock_js:
            result = signer.sign_apk(str(apk), key_type="media")

        assert result == "/tmp/signed.apk"
        mock_js.assert_called_once()


# ============================================================
# _sign_with_apksigner
# ============================================================
class TestSignWithApksigner:
    def test_subprocess_nonzero_rc_raises(self, tmp_path):
        signer = APKSigner(str(tmp_path), log_callback=lambda *a: None)
        signer._apksigner = "/fake/apksigner"

        with patch("core.sign_with_key.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="sign error"
            )
            with pytest.raises(RuntimeError, match="apksigner failed"):
                signer._sign_with_apksigner(
                    "/tmp/x.apk", "/tmp/k.p12", "platform",
                    lambda *a: None,
                )

    def test_success_returns_signed_path(self, tmp_path):
        signer = APKSigner(str(tmp_path), log_callback=lambda *a: None)
        signer._apksigner = "/fake/apksigner"

        with patch("core.sign_with_key.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            result = signer._sign_with_apksigner(
                "/tmp/orig.apk", "/tmp/k.p12", "platform",
                lambda *a: None,
            )

        assert result == "/tmp/orig_signed.apk"


# ============================================================
# _jarsigner
# ============================================================
class TestJarsigner:
    def test_calls_run(self, tmp_path):
        signer = APKSigner(str(tmp_path), log_callback=lambda *a: None)
        with patch.object(signer, "_run") as mock_run:
            result = signer._jarsigner(
                "/tmp/app.apk", "/tmp/k.jks", "platform",
                lambda *a: None,
            )
        assert result == "/tmp/app_signed.apk"
        mock_run.assert_called_once()


# ============================================================
# _run helper
# ============================================================
class TestRunHelper:
    def test_missing_command(self, tmp_path):
        signer = APKSigner(str(tmp_path), log_callback=lambda *a: None)
        with patch("core.sign_with_key.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="Không tìm thấy"):
                signer._run(["nonexistent_cmd", "arg"], lambda *a: None,
                            "test")

    def test_success(self, tmp_path):
        signer = APKSigner(str(tmp_path), log_callback=lambda *a: None)
        with patch("core.sign_with_key.shutil.which",
                   return_value="/fake/openssl"), \
             patch("core.sign_with_key.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            signer._run(["openssl", "pkcs12"], lambda *a: None, "openssl")

    def test_failure_rc_nonzero(self, tmp_path):
        signer = APKSigner(str(tmp_path), log_callback=lambda *a: None)
        with patch("core.sign_with_key.shutil.which",
                   return_value="/fake/openssl"), \
             patch("core.sign_with_key.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="openssl error"
            )
            with pytest.raises(RuntimeError, match="openssl failed"):
                signer._run(["openssl", "pkcs12"], lambda *a: None,
                            "openssl")