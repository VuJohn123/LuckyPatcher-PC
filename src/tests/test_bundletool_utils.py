"""Test bundletool wrapper — không có jar → None."""
from core.bundletool_utils import aab_to_apk


def test_missing_bundletool_returns_none(tmp_path):
    aab = tmp_path / "x.aab"
    aab.write_bytes(b"not-aab")
    result = aab_to_apk(str(aab), log_callback=lambda *_: None)
    # tools/bundletool.jar không tồn tại → None
    assert result is None