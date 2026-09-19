"""Test core/apk_downloader.py — SSRF-safe downloader."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from core.apk_downloader import (
    ALLOWED_SCHEMES,
    APKDownloader,
    BLOCKED_HOSTS,
    MAX_DOWNLOAD_SIZE,
    UnsafeDownloadError,
    _validate_url,
)


# ============================================================
# _validate_url — SECURITY GATE
# ============================================================
class TestValidateUrl:
    # ---- Valid ----
    def test_valid_https(self):
        url = "https://example.com/app.apk"
        assert _validate_url(url) == url

    def test_valid_http(self):
        url = "http://example.com/app.apk"
        assert _validate_url(url) == url

    def test_valid_with_query_string(self):
        url = "https://cdn.example.com/dl?id=123&token=abc"
        assert _validate_url(url) == url

    def test_valid_public_ip(self):
        url = "https://8.8.8.8/app.apk"
        assert _validate_url(url) == url

    def test_strips_whitespace(self):
        url = "  https://example.com/app.apk  "
        assert _validate_url(url) == "https://example.com/app.apk"

    # ---- Invalid: scheme ----
    def test_rejects_file_scheme(self):
        with pytest.raises(UnsafeDownloadError, match="Scheme"):
            _validate_url("file:///etc/passwd")

    def test_rejects_ftp_scheme(self):
        with pytest.raises(UnsafeDownloadError, match="Scheme"):
            _validate_url("ftp://example.com/file")

    def test_rejects_gopher_scheme(self):
        with pytest.raises(UnsafeDownloadError, match="Scheme"):
            _validate_url("gopher://example.com/")

    def test_rejects_no_scheme(self):
        with pytest.raises(UnsafeDownloadError, match="Scheme"):
            _validate_url("example.com/app.apk")

    # ---- Invalid: empty / None ----
    def test_rejects_empty(self):
        with pytest.raises(UnsafeDownloadError, match="rỗng"):
            _validate_url("")

    def test_rejects_none(self):
        with pytest.raises(UnsafeDownloadError, match="rỗng"):
            _validate_url(None)

    def test_rejects_non_string(self):
        with pytest.raises(UnsafeDownloadError, match="rỗng"):
            _validate_url(12345)

    # ---- Invalid: no host ----
    def test_rejects_no_host(self):
        with pytest.raises(UnsafeDownloadError, match="thiếu host"):
            _validate_url("https:///path")

    # ---- Invalid: blocked host ----
    def test_rejects_localhost(self):
        with pytest.raises(UnsafeDownloadError, match="Host bị chặn"):
            _validate_url("http://localhost/app.apk")

    def test_rejects_localhost_uppercase(self):
        with pytest.raises(UnsafeDownloadError, match="Host bị chặn"):
            _validate_url("http://LOCALHOST/app.apk")

    def test_rejects_loopback_ipv4(self):
        with pytest.raises(UnsafeDownloadError, match="Host bị chặn"):
            _validate_url("http://127.0.0.1/app.apk")

    def test_rejects_zero_ip(self):
        with pytest.raises(UnsafeDownloadError, match="Host bị chặn"):
            _validate_url("http://0.0.0.0/app.apk")

    def test_rejects_metadata_endpoint(self):
        with pytest.raises(UnsafeDownloadError, match="Host bị chặn"):
            _validate_url("http://169.254.169.254/latest/meta-data/")

    def test_rejects_ipv6_loopback(self):
        with pytest.raises(UnsafeDownloadError, match="Host bị chặn"):
            _validate_url("http://[::1]/app.apk")

    # ---- Invalid: private IP ----
    def test_rejects_private_ip_class_a(self):
        with pytest.raises(UnsafeDownloadError, match="nội bộ"):
            _validate_url("http://10.0.0.1/app.apk")

    def test_rejects_private_ip_class_b(self):
        with pytest.raises(UnsafeDownloadError, match="nội bộ"):
            _validate_url("http://172.16.0.1/app.apk")

    def test_rejects_private_ip_class_c(self):
        with pytest.raises(UnsafeDownloadError, match="nội bộ"):
            _validate_url("http://192.168.1.1/app.apk")

    def test_rejects_link_local(self):
        with pytest.raises(UnsafeDownloadError, match="nội bộ"):
            _validate_url("http://169.254.1.1/app.apk")


# ============================================================
# Constants
# ============================================================
class TestConstants:
    def test_allowed_schemes(self):
        assert "http" in ALLOWED_SCHEMES
        assert "https" in ALLOWED_SCHEMES
        assert "file" not in ALLOWED_SCHEMES

    def test_blocked_hosts_contains_metadata(self):
        assert "169.254.169.254" in BLOCKED_HOSTS
        assert "localhost" in BLOCKED_HOSTS

    def test_max_size_reasonable(self):
        assert 100 * 1024 * 1024 <= MAX_DOWNLOAD_SIZE <= 2 * 1024**3


# ============================================================
# __init__
# ============================================================
class TestConstructor:
    def test_creates_download_dir(self, tmp_path):
        d = tmp_path / "downloads"
        APKDownloader(download_dir=str(d), log_callback=lambda *a: None)
        assert d.exists()

    def test_session_has_retries(self, tmp_path):
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        assert dl.session is not None
        # Headers set
        assert "User-Agent" in dl.session.headers

    def test_session_max_redirects_set(self, tmp_path):
        """v2 fix: session.max_redirects phải được set (không dùng kwarg)."""
        from core.apk_downloader import MAX_REDIRECTS
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        assert dl.session.max_redirects == MAX_REDIRECTS

    def test_config_overrides(self, tmp_path):
        cfg = {
            "network": {
                "connect_timeout": 5,
                "read_timeout": 20,
                "max_download_size": 100 * 1024 * 1024,
            }
        }
        dl = APKDownloader(
            download_dir=str(tmp_path),
            log_callback=lambda *a: None,
            config=cfg,
        )
        assert dl.timeout == (5, 20)
        assert dl.max_size == 100 * 1024 * 1024


# ============================================================
# _out_path
# ============================================================
class TestOutPath:
    def test_out_path_sanitizes_package(self, tmp_path):
        """
        Path traversal: ../ bị strip. Kết quả nằm trong download_dir
        với basename an toàn (không có path separator).
        """
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        path = dl._out_path("../../evil", "apkpure")

        # Basename không chứa separator
        basename = os.path.basename(path)
        assert "/" not in basename
        assert "\\" not in basename

        # Path nằm trong download_dir
        assert os.path.dirname(path) == str(tmp_path)

        # "evil" vẫn còn trong filename (chỉ strip traversal markers)
        assert "evil" in basename

    def test_out_path_has_source_suffix(self, tmp_path):
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        path = dl._out_path("com.example.app", "apkpure")
        assert path.endswith("_apkpure.apk")


# ============================================================
# _sanitize_filename
# ============================================================
class TestSanitizeFilename:
    def test_normal(self):
        assert APKDownloader._sanitize_filename("app.apk") == "app.apk"

    def test_strips_path(self):
        assert APKDownloader._sanitize_filename(
            "/etc/passwd"
        ) == "passwd"

    def test_strips_windows_path(self):
        assert APKDownloader._sanitize_filename(
            "C:\\Windows\\System32\\evil.apk"
        ) == "evil.apk"

    def test_backslash_path(self):
        result = APKDownloader._sanitize_filename(
            "..\\..\\etc\\passwd"
        )
        assert ".." not in result or result == "passwd"
        assert result == "passwd"

    def test_special_chars_replaced(self):
        result = APKDownloader._sanitize_filename("app@#$%.apk")
        assert "@" not in result
        assert result.endswith(".apk")

    def test_empty_returns_default(self):
        assert APKDownloader._sanitize_filename("") == "download.apk"

    def test_only_special_returns_non_empty(self):
        result = APKDownloader._sanitize_filename("/@#$%")
        assert result  # Không rỗng

    def test_too_long_truncated(self):
        long_name = "a" * 500 + ".apk"
        result = APKDownloader._sanitize_filename(long_name)
        assert len(result) <= 200


# ============================================================
# _download — happy path + size limit
# ============================================================
def _mock_response(headers=None, chunks=None, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.headers = headers or {}
    resp.raise_for_status.return_value = None
    resp.iter_content.return_value = iter(chunks or [])
    return resp


class TestDownload:
    def test_success(self, tmp_path):
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        resp = _mock_response(
            headers={"content-length": "10"},
            chunks=[b"hello", b"world"],
        )
        dl.session = MagicMock()
        dl.session.get.return_value = resp

        out = tmp_path / "app.apk"
        result = dl._download("https://example.com/app.apk", str(out))

        assert result == str(out)
        assert out.read_bytes() == b"helloworld"

    def test_rejected_unsafe_url(self, tmp_path):
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        result = dl._download("file:///etc/passwd", None)
        assert result is None

    def test_content_length_too_large(self, tmp_path):
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        dl.max_size = 1024  # 1 KB
        resp = _mock_response(headers={"content-length": "9999999"})
        dl.session = MagicMock()
        dl.session.get.return_value = resp

        result = dl._download("https://example.com/big.apk", None)
        assert result is None

    def test_streamed_size_exceeds_limit(self, tmp_path):
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        dl.max_size = 100  # 100 bytes
        resp = _mock_response(
            headers={},
            chunks=[b"x" * 50, b"y" * 100],  # 150 bytes total
        )
        dl.session = MagicMock()
        dl.session.get.return_value = resp

        out = tmp_path / "big.apk"
        result = dl._download("https://example.com/big.apk", str(out))

        assert result is None
        assert not out.exists()  # File removed on overflow

    def test_timeout_returns_none(self, tmp_path):
        import requests
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        dl.session = MagicMock()
        dl.session.get.side_effect = requests.Timeout("timed out")

        result = dl._download("https://example.com/app.apk", None)
        assert result is None

    def test_network_error_returns_none(self, tmp_path):
        import requests
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        dl.session = MagicMock()
        dl.session.get.side_effect = requests.RequestException("boom")

        result = dl._download("https://example.com/app.apk", None)
        assert result is None

    def test_http_error_returns_none(self, tmp_path):
        import requests
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        resp = MagicMock()
        resp.raise_for_status.side_effect = requests.HTTPError("404")
        dl.session = MagicMock()
        dl.session.get.return_value = resp

        result = dl._download("https://example.com/app.apk", None)
        assert result is None


# ============================================================
# _filename — Content-Disposition parsing
# ============================================================
class TestFilename:
    def test_from_content_disposition(self, tmp_path):
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        resp = MagicMock()
        resp.headers = {
            "Content-Disposition": 'attachment; filename="real.apk"'
        }
        result = dl._filename("https://example.com/download", resp)
        assert result == "real.apk"

    def test_from_content_disposition_star(self, tmp_path):
        """RFC 5987: filename*=UTF-8''my%20app.apk → my_app.apk."""
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        resp = MagicMock()
        resp.headers = {
            "Content-Disposition":
                "attachment; filename*=UTF-8''my%20app.apk"
        }
        result = dl._filename("https://example.com/download", resp)
        assert "my" in result
        assert "app" in result
        # %20 → space → sanitize thành _
        assert " " not in result
        assert result.endswith(".apk")

    def test_star_takes_precedence_over_legacy(self, tmp_path):
        """Nếu cả 2 có → ưu tiên filename*= (RFC 5987)."""
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        resp = MagicMock()
        resp.headers = {
            "Content-Disposition":
                'attachment; filename="legacy.apk"; '
                "filename*=UTF-8''preferred.apk"
        }
        result = dl._filename("https://example.com/download", resp)
        assert result == "preferred.apk"

    def test_from_url_path(self, tmp_path):
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        resp = MagicMock()
        resp.headers = {}
        result = dl._filename("https://example.com/path/app-name.apk", resp)
        assert result == "app-name.apk"

    def test_no_filename_returns_default(self, tmp_path):
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        resp = MagicMock()
        resp.headers = {}
        result = dl._filename("https://example.com/", resp)
        assert result == "downloaded.apk"

    def test_url_encoded_path_decoded(self, tmp_path):
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        resp = MagicMock()
        resp.headers = {}
        result = dl._filename(
            "https://example.com/my%20app.apk", resp
        )
        assert "my" in result
        assert "app" in result

    def test_content_disposition_malformed(self, tmp_path):
        """Content-Disposition có filename*= nhưng malformed → fallback URL."""
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        resp = MagicMock()
        resp.headers = {
            "Content-Disposition": "attachment; filename*="
        }
        result = dl._filename(
            "https://example.com/fallback.apk", resp
        )
        assert result == "fallback.apk"


# ============================================================
# Google Play info
# ============================================================
class TestGooglePlayInfo:
    def test_missing_lib_returns_none(self, tmp_path):
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        with patch("builtins.__import__",
                   side_effect=ImportError("no scraper")):
            result = dl.get_google_play_app_info("com.example.app")
        assert result is None

    def test_scraper_exception_returns_none(self, tmp_path):
        dl = APKDownloader(download_dir=str(tmp_path),
                           log_callback=lambda *a: None)
        mock_gp = MagicMock()
        mock_gp.app.side_effect = Exception("scraper boom")

        with patch.dict("sys.modules",
                        {"google_play_scraper": mock_gp}):
            result = dl.get_google_play_app_info("com.example.app")
        assert result is None