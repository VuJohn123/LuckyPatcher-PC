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
    with patch.object(dl.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.iter_content.return_value = [b"data1", b"data2"]
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