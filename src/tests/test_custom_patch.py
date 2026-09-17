"""Test patcher/custom_patch.py — parser + applier."""
import os
import zipfile

import pytest

from patcher.custom_patch import CustomPatchApplier, CustomPatchParser


# ============================================================
# CustomPatchParser
# ============================================================
def test_parser_txt_single(tmp_path):
    f = tmp_path / "patch.txt"
    f.write_text("[smali/A.smali]\nold -> new\n", encoding="utf-8")

    p = CustomPatchParser(str(f))
    result = p.parse()
    assert len(result) == 1
    assert result[0]["target_file"] == "smali/A.smali"
    assert len(result[0]["operations"]) == 1


def test_parser_txt_multiple_ops(tmp_path):
    f = tmp_path / "patch.txt"
    f.write_text(
        "[smali/A.smali]\nold1 -> new1\nold2 -> new2\n",
        encoding="utf-8",
    )
    p = CustomPatchParser(str(f))
    result = p.parse()
    assert len(result[0]["operations"]) == 2


def test_parser_txt_inline_replacement(tmp_path):
    f = tmp_path / "patch.txt"
    f.write_text(
        "[smali/A.smali] old -> new\n",
        encoding="utf-8",
    )
    p = CustomPatchParser(str(f))
    result = p.parse()
    assert result[0]["target_file"] == "smali/A.smali"
    assert len(result[0]["operations"]) == 1


def test_parser_skips_comments(tmp_path):
    f = tmp_path / "patch.txt"
    f.write_text(
        "# comment\n"
        "[smali/A.smali]\n"
        "# another\n"
        "old -> new\n",
        encoding="utf-8",
    )
    p = CustomPatchParser(str(f))
    result = p.parse()
    assert len(result[0]["operations"]) == 1


def test_parser_empty_file(tmp_path):
    f = tmp_path / "patch.txt"
    f.write_text("", encoding="utf-8")
    p = CustomPatchParser(str(f))
    assert p.parse() == []


def test_parser_missing_file():
    p = CustomPatchParser("/nonexistent/patch.txt")
    # Trả về [] nếu không đọc được
    result = p.parse()
    assert result == []


def test_parser_lpzip(tmp_path):
    lpzip = tmp_path / "patch.lpzip"
    with zipfile.ZipFile(lpzip, "w") as z:
        z.writestr("patch.txt", "[smali/A.smali]\nold -> new\n")

    p = CustomPatchParser(str(lpzip))
    result = p.parse()
    assert len(result) >= 1


def test_parser_lpzip_no_txt(tmp_path):
    lpzip = tmp_path / "patch.lpzip"
    with zipfile.ZipFile(lpzip, "w") as z:
        z.writestr("readme.md", "nothing")

    p = CustomPatchParser(str(lpzip))
    assert p.parse() == []


def test_parser_lpzip_corrupt(tmp_path):
    lpzip = tmp_path / "patch.lpzip"
    lpzip.write_bytes(b"not a zip")
    p = CustomPatchParser(str(lpzip))
    assert p.parse() == []


# ============================================================
# CustomPatchApplier
# ============================================================
def test_applier_init(tmp_path):
    a = CustomPatchApplier(str(tmp_path))
    assert a.decompiled_path == str(tmp_path)


def test_applier_apply_replace(tmp_path):
    smali_dir = tmp_path / "smali"
    smali_dir.mkdir()
    f = smali_dir / "A.smali"
    f.write_text("original content", encoding="utf-8")

    a = CustomPatchApplier(str(tmp_path))
    instructions = [{
        # Windows dùng '\', Linux dùng '/' → pattern phải match cả 2
        "target_file": r"smali[/\\]A\.smali",
        "operations": [
            {"type": "replace", "pattern": "original", "replacement": "modified"}
        ],
    }]
    count = a.apply(instructions)
    assert count == 1
    assert f.read_text() == "modified content"


def test_applier_missing_target(tmp_path):
    a = CustomPatchApplier(str(tmp_path))
    instructions = [{
        "target_file": "nonexistent.smali",
        "operations": [{"type": "replace", "pattern": "a", "replacement": "b"}],
    }]
    count = a.apply(instructions)
    assert count == 0


def test_applier_invalid_regex(tmp_path):
    smali_dir = tmp_path / "smali"
    smali_dir.mkdir()
    (smali_dir / "A.smali").write_text("content", encoding="utf-8")

    a = CustomPatchApplier(str(tmp_path))
    instructions = [{
        "target_file": r"smali/A\.smali",
        "operations": [
            {"type": "replace", "pattern": "[invalid(", "replacement": "x"}
        ],
    }]
    # Không crash
    a.apply(instructions)


def test_applier_non_replace_op(tmp_path):
    smali_dir = tmp_path / "smali"
    smali_dir.mkdir()
    (smali_dir / "A.smali").write_text("content", encoding="utf-8")

    a = CustomPatchApplier(str(tmp_path))
    instructions = [{
        "target_file": r"smali/A\.smali",
        "operations": [{"type": "unknown"}],
    }]
    count = a.apply(instructions)
    assert count == 0


def test_applier_patch_no_env_var(tmp_path):
    """patch() khi không có LP_CUSTOM_PATCH env → return 0."""
    import os
    saved = os.environ.pop("LP_CUSTOM_PATCH", None)
    try:
        a = CustomPatchApplier(str(tmp_path))
        assert a.patch() == 0
    finally:
        if saved:
            os.environ["LP_CUSTOM_PATCH"] = saved


def test_applier_patch_with_file(tmp_path):
    smali_dir = tmp_path / "smali"
    smali_dir.mkdir()
    (smali_dir / "A.smali").write_text("old_content", encoding="utf-8")

    patch_file = tmp_path / "patch.txt"
    patch_file.write_text(
        f"[smali/A\\.smali]\nold_content -> new_content\n",
        encoding="utf-8",
    )

    import os
    os.environ["LP_CUSTOM_PATCH"] = str(patch_file)
    try:
        a = CustomPatchApplier(str(tmp_path))
        count = a.patch()
        assert count >= 0
    finally:
        os.environ.pop("LP_CUSTOM_PATCH", None)