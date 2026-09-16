"""Test APK downloader — mock network."""
from unittest.mock import MagicMock, patch

import pytest

from core.apk_downloader import APKDownloader


def test_init_creates_download_dir(tmp_path):
    d = APKDownloader(download_dir=str(tmp_path / "dl"))
    import os
    assert os.path.isdir(d.download_dir)


def test_google_play_info_missing_lib():
    d = APKDownloader(download_dir="/tmp/x")
    with patch.dict("sys.modules", {"google_play_scraper": None}):
        with patch("builtins.__import__", side_effect=ImportError):
            result = d.get_google_play_app_info("com.x")
            assert result is None


@patch("core.apk_downloader.requests.Session")
def test_download_timeout_returns_none(mock_session):
    session = MagicMock()
    mock_session.return_value = session
    session.get.side_effect = Exception("timeout")
    d = APKDownloader(download_dir="/tmp/x")
    d.session = session
    # Patch specific
    import requests
    session.get.side_effect = requests.Timeout("timeout")
    result = d.download_from_direct_url("https://x.com/a.apk")
    assert result is None


def test_extract_filename_from_url():
    d = APKDownloader(download_dir="/tmp/x")
    resp = MagicMock()
    resp.headers = {}
    name = d._filename("https://example.com/path/app.apk", resp)
    assert name == "app.apk"