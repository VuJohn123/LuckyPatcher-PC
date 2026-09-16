"""Test SmartPatternPatcher — base class cho pattern-based patchers."""
import os
import tempfile
from unittest.mock import patch

from patcher.smart_pattern_patcher import SmartPatternPatcher


def _w(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_apply_string_replacement():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _w(smali, ".class public LA;\nconst v0, 0x0\n")

        patcher = SmartPatternPatcher(tmp, log_callback=lambda *_: None)
        count = patcher.apply_patterns([
            {"search": r"const v0, 0x0", "replace": "const v0, 0x1"}
        ])
        assert count >= 1
        with open(smali) as f:
            assert "const v0, 0x1" in f.read()


def test_apply_callable_replace():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _w(smali, ".class public LA;\n.method foo()V\n.end method\n")

        def replacer(m):
            return m.group(0).replace("foo", "bar")

        patcher = SmartPatternPatcher(tmp, log_callback=lambda *_: None)
        count = patcher.apply_patterns([
            {"search": r"foo", "replace": replacer}
        ])
        assert count >= 1
        with open(smali) as f:
            assert "bar" in f.read()


def test_target_methods_filter():
    with tempfile.TemporaryDirectory() as tmp:
        a = os.path.join(tmp, "smali", "A.smali")
        b = os.path.join(tmp, "smali", "B.smali")
        _w(a, "TARGET_STRING content")
        _w(b, "OTHER content")

        patcher = SmartPatternPatcher(tmp, log_callback=lambda *_: None)
        count = patcher.apply_patterns(
            [{"search": r"content", "replace": "modified"}],
            target_methods=["TARGET_STRING"],
        )
        # Chỉ file A được sửa
        assert count == 1
        with open(a) as f:
            assert "modified" in f.read()
        with open(b) as f:
            assert "modified" not in f.read()


def test_no_match_returns_zero():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _w(smali, "nothing here")
        patcher = SmartPatternPatcher(tmp, log_callback=lambda *_: None)
        assert patcher.apply_patterns([
            {"search": r"xyz_not_present", "replace": "x"}
        ]) == 0


def test_skip_long_path():
    """File path > 250 ký tự phải bị skip.

    Windows giới hạn CreateDirectoryW ~247 ký tự (sớm hơn MAX_PATH 260),
    nên không thể tạo file thật để test. Mock get_all_smali_files để
    trả về path dài → verify logic length-check của patcher.
    """
    with tempfile.TemporaryDirectory() as tmp:
        long_path = os.path.join(
            tmp, "smali",
            *[("x" * 40) for _ in range(7)],
            "A.smali",
        )
        assert len(long_path) > 250, f"Path chưa đủ dài: {len(long_path)}"

        with patch(
            "patcher.smart_pattern_patcher.get_all_smali_files",
            return_value=[long_path],
        ):
            patcher = SmartPatternPatcher(tmp, log_callback=lambda *_: None)
            assert patcher.apply_patterns([
                {"search": r"content", "replace": "x"}
            ]) == 0


def test_invalid_regex_does_not_crash():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _w(smali, "content")
        patcher = SmartPatternPatcher(tmp, log_callback=lambda *_: None)
        # Regex invalid → không crash
        count = patcher.apply_patterns([
            {"search": r"[invalid(", "replace": "x"}
        ])
        assert count == 0


def test_empty_patterns():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _w(smali, "content")
        patcher = SmartPatternPatcher(tmp, log_callback=lambda *_: None)
        assert patcher.apply_patterns([]) == 0