"""Test CustomPatchDownloader — mock network."""
from unittest.mock import MagicMock, patch

import requests

from patcher.custom_patch_downloader import CustomPatchDownloader


def test_init_creates_dir(tmp_path):
    dl = CustomPatchDownloader(
        download_dir=str(tmp_path / "patches"),
        log_callback=lambda *_: None,
    )
    import os
    assert os.path.isdir(dl.download_dir)


def test_download_success(tmp_path):
    dl = CustomPatchDownloader(
        download_dir=str(tmp_path),
        log_callback=lambda *_: None,
    )
    with patch.object(dl.session, "head") as mock_head, \
         patch.object(dl.session, "get") as mock_get:
        # Mock HEAD response
        mock_head_resp = MagicMock()
        mock_head_resp.status_code = 200
        mock_head_resp.headers = {"content-length": "100"}
        mock_head.return_value = mock_head_resp

        # Mock GET response
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = b"data1data2"
        mock_get.return_value = mock_resp

        result = dl.download_patch("test.lpzip")
        assert result is not None


def test_download_timeout(tmp_path):
    dl = CustomPatchDownloader(
        download_dir=str(tmp_path),
        log_callback=lambda *_: None,
    )
    with patch.object(dl.session, "get") as mock_get:
        mock_get.side_effect = requests.Timeout("timeout")
        result = dl.download_patch("test.lpzip")
        assert result is None


def test_download_http_error(tmp_path):
    dl = CustomPatchDownloader(
        download_dir=str(tmp_path),
        log_callback=lambda *_: None,
    )
    with patch.object(dl.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("404")
        mock_get.return_value = mock_resp
        result = dl.download_patch("test.lpzip")
        assert result is None
