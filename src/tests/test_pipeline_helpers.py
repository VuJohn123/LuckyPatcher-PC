"""Test pipeline helpers — normalize_input, setup_logging."""
import os
import tempfile
from unittest.mock import patch

import pytest

from core.pipeline_helpers import normalize_input, setup_logging


# ============================================================
# setup_logging
# ============================================================
def test_setup_logging_creates_logger(tmp_path):
    config = {"logging": {
        "level": "DEBUG",
        "file": str(tmp_path / "test.log"),
        "max_bytes": 1024,
        "backup_count": 1,
    }}
    logger = setup_logging(config)
    assert logger.name == "lp_pc_suite"


def test_setup_logging_idempotent(tmp_path):
    config = {"logging": {"level": "INFO", "file": str(tmp_path / "a.log")}}
    logger1 = setup_logging(config)
    logger2 = setup_logging(config)
    assert logger1 is logger2


def test_setup_logging_invalid_path_fallback(tmp_path):
    """Path không tạo được → fallback basicConfig, không crash."""
    config = {"logging": {
        "level": "INFO",
        "file": "/invalid\x00path/log.log",
    }}
    logger = setup_logging(config)
    assert logger is not None


# ============================================================
# normalize_input — validation
# ============================================================
def test_normalize_input_rejects_empty():
    with pytest.raises(ValueError, match="rỗng"):
        normalize_input("", {}, lambda *_: None)


def test_normalize_input_rejects_nonexistent():
    with pytest.raises(ValueError, match="không tồn tại"):
        normalize_input("/nonexistent/file.apk", {}, lambda *_: None)


def test_normalize_input_unsupported_extension(tmp_path):
    f = tmp_path / "test.xyz"
    f.write_bytes(b"fake")
    with pytest.raises(ValueError, match="Không hỗ trợ"):
        normalize_input(str(f), {}, lambda *_: None)


# ============================================================
# normalize_input — .apk passthrough
# ============================================================
def test_normalize_input_apk_passthrough(tmp_path):
    apk = tmp_path / "test.apk"
    apk.write_bytes(b"fake-apk")
    logs = []
    result = normalize_input(str(apk), {}, logs.append)
    assert result == str(apk)
    assert any("bỏ qua conversion" in l for l in logs)


# ============================================================
# normalize_input — .xapk
# ============================================================
def test_normalize_input_xapk_converts(tmp_path):
    xapk = tmp_path / "test.xapk"
    xapk.write_bytes(b"fake-xapk")
    config = {"conversion": {"auto_convert_xapk": True}}
    converted_path = str(tmp_path / "converted.apk")

    with patch(
        "core.xapk_converter.convert_xapk_to_apk",
        return_value=converted_path,
    ):
        result = normalize_input(str(xapk), config, lambda *_: None)
        assert result == converted_path


def test_normalize_input_xapk_disabled_raises(tmp_path):
    xapk = tmp_path / "test.xapk"
    xapk.write_bytes(b"fake")
    config = {"conversion": {"auto_convert_xapk": False}}

    with pytest.raises(ValueError, match="auto_convert_xapk"):
        normalize_input(str(xapk), config, lambda *_: None)


def test_normalize_input_xapk_conversion_error(tmp_path):
    xapk = tmp_path / "test.xapk"
    xapk.write_bytes(b"fake")
    config = {"conversion": {"auto_convert_xapk": True}}

    from core.xapk_converter import XAPKConversionError
    with patch(
        "core.xapk_converter.convert_xapk_to_apk",
        side_effect=XAPKConversionError("bad zip"),
    ):
        with pytest.raises(ValueError, match="thất bại"):
            normalize_input(str(xapk), config, lambda *_: None)


# ============================================================
# normalize_input — .apks
# ============================================================
def test_normalize_input_apks_converts(tmp_path):
    apks = tmp_path / "test.apks"
    apks.write_bytes(b"fake-apks")
    config = {"conversion": {"auto_convert_apks": True}}
    converted_path = str(tmp_path / "converted.apk")

    with patch(
        "core.apks_converter.convert_apks_to_apk",
        return_value=converted_path,
    ):
        result = normalize_input(str(apks), config, lambda *_: None)
        assert result == converted_path


def test_normalize_input_apks_disabled_raises(tmp_path):
    apks = tmp_path / "test.apks"
    apks.write_bytes(b"fake")
    config = {"conversion": {"auto_convert_apks": False}}

    with pytest.raises(ValueError, match="auto_convert_apks"):
        normalize_input(str(apks), config, lambda *_: None)


def test_normalize_input_apks_conversion_error(tmp_path):
    apks = tmp_path / "test.apks"
    apks.write_bytes(b"fake")
    config = {"conversion": {"auto_convert_apks": True}}

    from core.apks_converter import APKSConversionError
    with patch(
        "core.apks_converter.convert_apks_to_apk",
        side_effect=APKSConversionError("bad format"),
    ):
        with pytest.raises(ValueError, match="thất bại"):
            normalize_input(str(apks), config, lambda *_: None)


# ============================================================
# normalize_input — folder
# ============================================================
def test_normalize_input_folder_empty(tmp_path):
    config = {"conversion": {"allow_split_apk": True}}
    with pytest.raises(ValueError, match="không chứa"):
        normalize_input(str(tmp_path), config, lambda *_: None)


def test_normalize_input_folder_disabled(tmp_path):
    config = {"conversion": {"allow_split_apk": False}}
    with pytest.raises(ValueError, match="allow_split_apk"):
        normalize_input(str(tmp_path), config, lambda *_: None)


def test_normalize_input_folder_merges(tmp_path):
    """
    Folder chứa .apk → merge.
    LƯU Ý: normalize_input() tạo merged.apk ở PARENT của folder
    (os.path.dirname(path)), không phải bên trong folder.
    """
    (tmp_path / "base.apk").write_bytes(b"fake")
    config = {"conversion": {"allow_split_apk": True}}

    # Expected: merged.apk nằm cạnh folder, không phải trong folder
    expected = os.path.join(
        os.path.dirname(str(tmp_path)), "merged.apk"
    )

    with patch("core.apk_utils.merge_split_apks") as mock_merge:
        result = normalize_input(str(tmp_path), config, lambda *_: None)
        assert result == expected
        # Verify merge_split_apks được gọi với đúng args
        mock_merge.assert_called_once()
        call_args = mock_merge.call_args
        assert call_args[0][0] == str(tmp_path)
        assert call_args[0][1] == expected