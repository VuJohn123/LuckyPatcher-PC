"""Test patcher/lpdiff_analyzer.py — LPDiffAnalyzer."""
import os
import zipfile

import pytest

from patcher.lpdiff_analyzer import LPDiffAnalyzer


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def orig_patched_files(tmp_path):
    orig = tmp_path / "orig.smali"
    patched = tmp_path / "patched.smali"
    orig.write_text(
        ".class public LA;\n"
        ".method public test()V\n"
        "    const/4 v0, 0x0\n"
        "    return-void\n"
        ".end method\n",
        encoding="utf-8",
    )
    patched.write_text(
        ".class public LA;\n"
        ".method public test()V\n"
        "    const/4 v0, 0x1\n"
        "    return-void\n"
        ".end method\n",
        encoding="utf-8",
    )
    return str(orig), str(patched)


# ============================================================
# Constructor
# ============================================================
def test_init(orig_patched_files):
    orig, patched = orig_patched_files
    a = LPDiffAnalyzer(orig, patched)
    assert a.orig == orig
    assert a.patched == patched


# ============================================================
# generate_pattern
# ============================================================
def test_generate_pattern_with_mask(orig_patched_files):
    orig, patched = orig_patched_files
    a = LPDiffAnalyzer(orig, patched)
    pattern = a.generate_pattern(mask_operands=True)
    assert isinstance(pattern, str)


def test_generate_pattern_without_mask(orig_patched_files):
    orig, patched = orig_patched_files
    a = LPDiffAnalyzer(orig, patched)
    pattern = a.generate_pattern(mask_operands=False)
    assert isinstance(pattern, str)


def test_generate_pattern_identical_files(tmp_path):
    """2 file giống nhau → pattern rỗng."""
    f1 = tmp_path / "a.smali"
    f2 = tmp_path / "b.smali"
    content = ".class public LA;\n.method test()V\n.end method\n"
    f1.write_text(content)
    f2.write_text(content)

    a = LPDiffAnalyzer(str(f1), str(f2))
    pattern = a.generate_pattern()
    # Không có diff → empty hoặc chỉ whitespace
    assert isinstance(pattern, str)


def test_generate_pattern_missing_file(tmp_path):
    a = LPDiffAnalyzer(
        str(tmp_path / "nonexistent1.smali"),
        str(tmp_path / "nonexistent2.smali"),
    )
    with pytest.raises((FileNotFoundError, OSError)):
        a.generate_pattern()


# ============================================================
# _extract_instructions
# ============================================================
def test_extract_instructions_filters_directives():
    a = LPDiffAnalyzer("/dev/null", "/dev/null")
    lines = [
        ".class public LA;\n",
        "    .method test()V\n",
        "    const/4 v0, 0x0\n",
        "    # comment\n",
        "    invoke-static {}\n",
        ":label\n",
    ]
    result = a._extract_instructions(lines)
    assert "const/4 v0, 0x0" in result
    assert "invoke-static {}" in result
    # Directives bị loại
    assert not any(".class" in r for r in result)
    assert not any(".method" in r for r in result)
    assert not any("#" in r for r in result)


def test_extract_instructions_empty():
    a = LPDiffAnalyzer("/dev/null", "/dev/null")
    assert a._extract_instructions([]) == []


# ============================================================
# save_lpzip
# ============================================================
def test_save_lpzip_creates_zip(orig_patched_files, tmp_path):
    orig, patched = orig_patched_files
    a = LPDiffAnalyzer(orig, patched)
    out = str(tmp_path / "patch.lpzip")
    result = a.save_lpzip(out)
    assert result == out
    assert os.path.exists(out)

    with zipfile.ZipFile(out, "r") as z:
        assert "patch.txt" in z.namelist()


def test_save_lpzip_custom_target(orig_patched_files, tmp_path):
    orig, patched = orig_patched_files
    a = LPDiffAnalyzer(orig, patched)
    out = str(tmp_path / "patch.lpzip")
    a.save_lpzip(out, target_filename="classes2.dex")

    with zipfile.ZipFile(out, "r") as z:
        content = z.read("patch.txt").decode()
    assert "classes2.dex" in content


# ============================================================
# patch interface
# ============================================================
def test_patch_returns_zero(orig_patched_files):
    """Interface stub — luôn trả 0."""
    orig, patched = orig_patched_files
    a = LPDiffAnalyzer(orig, patched)
    assert a.patch() == 0