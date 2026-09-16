"""Test APKSigner — chỉ test logic không cần tool."""
import pytest

from core.sign_with_key import APKSigner


def test_invalid_key_type():
    signer = APKSigner(tools_dir="/tmp/tools")
    with pytest.raises(ValueError):
        signer.sign_apk("/tmp/x.apk", key_type="unknown")


def test_missing_apk():
    signer = APKSigner(tools_dir="/tmp/tools")
    with pytest.raises(FileNotFoundError):
        signer.sign_apk("/nonexistent.apk", key_type="testkey")


def test_key_alias_map():
    assert "testkey" in APKSigner.KEY_ALIASES
    assert "platform" in APKSigner.KEY_ALIASES