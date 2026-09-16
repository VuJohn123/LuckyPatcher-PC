"""Test GitHub updater — mock requests."""
from unittest.mock import MagicMock, patch

import pytest

from core.github_updater import (
    CURRENT_VERSION,
    GitHubUpdater,
    UpdateInfo,
    _is_newer,
    _parse_version,
)


# ---------- version parsing ----------
def test_parse_version_simple():
    """3-part version được pad thành 4-tuple để so sánh."""
    assert _parse_version("4.1.2") == (4, 1, 2, 0)


def test_parse_version_with_suffix():
    """Suffix không phải digit bị strip: '4.1.2-beta' → (4, 1, 2, 0)."""
    assert _parse_version("4.1.2-beta") == (4, 1, 2, 0)


def test_parse_version_empty():
    """Empty → toàn bộ zero 4-tuple."""
    assert _parse_version("") == (0, 0, 0, 0)


def test_parse_version_two_parts():
    """'4.1' → pad về (4, 1, 0, 0)."""
    assert _parse_version("4.1") == (4, 1, 0, 0)


def test_parse_version_4_parts():
    """'4.1.2.3' → giữ nguyên."""
    assert _parse_version("4.1.2.3") == (4, 1, 2, 3)


def test_parse_version_caps_at_4():
    """'4.1.2.3.4.5' → cap 4 phần."""
    assert _parse_version("4.1.2.3.4.5") == (4, 1, 2, 3)


def test_is_newer_true():
    assert _is_newer("4.1.0", "4.0.0")


def test_is_newer_false():
    assert not _is_newer("4.0.0", "4.0.0")


def test_is_newer_same_major():
    assert _is_newer("4.0.1", "4.0.0")


def test_is_newer_with_suffix():
    """4.1.2-beta > 4.1.1 (pad → 4-tuple)."""
    assert _is_newer("4.1.2-beta", "4.1.1")


# ---------- UpdateInfo ----------
def test_update_info_to_html():
    info = UpdateInfo(
        version="4.1.0",
        release_date="2026-10-01",
        changelog=["Fix A", "Add B"],
        download_url="https://example.com",
    )
    html = info.to_html()
    assert "4.1.0" in html
    assert "Fix A" in html


# ---------- check_sync ----------
def test_check_sync_no_update():
    updater = GitHubUpdater(current_version="4.0.0")
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"version": "4.0.0"}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp
        assert updater.check_sync() is None


def test_check_sync_has_update():
    updater = GitHubUpdater(current_version="4.0.0")
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "version": "4.1.0",
            "release_date": "2026-10-01",
            "changelog": ["Fix X"],
            "download_url": "https://example.com",
        }
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp
        info = updater.check_sync()
        assert info is not None
        assert info.version == "4.1.0"
        assert "Fix X" in info.changelog


def test_check_sync_network_error_returns_none():
    updater = GitHubUpdater()
    with patch("requests.get", side_effect=Exception("network fail")):
        assert updater.check_sync() is None


def test_check_sync_missing_version():
    updater = GitHubUpdater()
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp
        assert updater.check_sync() is None


# ---------- check_async ----------
def test_check_async_calls_callback():
    import time
    results = []

    def callback(info):
        results.append(info)

    updater = GitHubUpdater(current_version="4.0.0")
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"version": "4.0.0"}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp
        updater.check_async(callback)

        # Đợi callback chạy (tối đa 2s)
        deadline = time.time() + 2
        while not results and time.time() < deadline:
            time.sleep(0.05)

    assert len(results) == 1