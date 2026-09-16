"""Test URL validation + filename sanitization."""
import pytest

from core.apk_downloader import (
    APKDownloader,
    UnsafeDownloadError,
    _validate_url,
)


# ---------- _validate_url ----------
def test_valid_https():
    assert _validate_url("https://example.com/app.apk")


def test_valid_http():
    assert _validate_url("http://example.com/app.apk")


def test_rejects_file_scheme():
    with pytest.raises(UnsafeDownloadError):
        _validate_url("file:///etc/passwd")


def test_rejects_ftp_scheme():
    with pytest.raises(UnsafeDownloadError):
        _validate_url("ftp://example.com/x")


def test_rejects_gopher():
    with pytest.raises(UnsafeDownloadError):
        _validate_url("gopher://example.com")


def test_rejects_localhost():
    with pytest.raises(UnsafeDownloadError):
        _validate_url("http://localhost:8080/x")


def test_rejects_loopback_ip():
    with pytest.raises(UnsafeDownloadError):
        _validate_url("http://127.0.0.1/x")


def test_rejects_metadata_endpoint():
    with pytest.raises(UnsafeDownloadError):
        _validate_url("http://169.254.169.254/latest/meta-data")


def test_rejects_private_ip():
    with pytest.raises(UnsafeDownloadError):
        _validate_url("http://192.168.1.1/x")


def test_rejects_empty():
    with pytest.raises(UnsafeDownloadError):
        _validate_url("")


def test_rejects_no_host():
    with pytest.raises(UnsafeDownloadError):
        _validate_url("http:///x")


# ---------- filename sanitization ----------
def test_sanitize_filename_strips_path():
    assert APKDownloader._sanitize_filename("../../etc/passwd") == "passwd"


def test_sanitize_filename_backslash():
    assert APKDownloader._sanitize_filename("..\\..\\windows\\x.apk") == "x.apk"


def test_sanitize_filename_special_chars():
    result = APKDownloader._sanitize_filename("app<>|.apk")
    assert "<" not in result
    assert "|" not in result


def test_sanitize_filename_empty():
    assert APKDownloader._sanitize_filename("") == "download.apk"


def test_sanitize_filename_too_long():
    long_name = "a" * 500 + ".apk"
    result = APKDownloader._sanitize_filename(long_name)
    assert len(result) <= 200