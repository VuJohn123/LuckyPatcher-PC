"""Test hex_pattern_patcher — LP format parser + byte-level matcher."""
from __future__ import annotations

import os
import zipfile

import pytest

from patcher.hex_pattern_patcher import (
    HexOp,
    HexPatch,
    HexPatternPatcher,
    LPPatchParser,
    PatchResult,
    _apply_op,
    _find_pattern,
    _parse_hex_bytes,
    _parse_offset,
    apply_hex_patches,
)


# ============================================================
# HELPERS
# ============================================================
def _make_apk(tmp_path, entries: dict[str, bytes]):
    """Build fake APK with given entries."""
    apk = tmp_path / "test.apk"
    with zipfile.ZipFile(apk, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return str(apk)


def _make_patch(tmp_path, content: str) -> str:
    p = tmp_path / "patch.txt"
    p.write_text(content, encoding="utf-8")
    return str(p)


# ============================================================
# _parse_hex_bytes
# ============================================================
class TestParseHexBytes:
    def test_simple_bytes(self):
        vals, mask = _parse_hex_bytes("12 34 56")
        assert vals == [0x12, 0x34, 0x56]
        assert mask == set()

    def test_wildcard_star_star(self):
        vals, mask = _parse_hex_bytes("12 ** 56")
        assert vals == [0x12, None, 0x56]
        assert mask == {1}

    def test_wildcard_question(self):
        vals, mask = _parse_hex_bytes("12 ?? 56")
        assert vals == [0x12, None, 0x56]
        assert mask == {1}

    def test_uppercase(self):
        vals, _ = _parse_hex_bytes("AA BB CC")
        assert vals == [0xAA, 0xBB, 0xCC]

    def test_single_char_padded(self):
        vals, _ = _parse_hex_bytes("A B C")
        assert vals == [0x0A, 0x0B, 0x0C]

    def test_invalid_treated_as_wildcard(self):
        vals, mask = _parse_hex_bytes("12 ZZ 56")
        assert vals == [0x12, None, 0x56]
        assert mask == {1}

    def test_empty_string(self):
        vals, mask = _parse_hex_bytes("")
        assert vals == []
        assert mask == set()

    def test_extra_whitespace(self):
        vals, _ = _parse_hex_bytes("  12   34   56  ")
        assert vals == [0x12, 0x34, 0x56]


# ============================================================
# _parse_offset
# ============================================================
class TestParseOffset:
    def test_valid_hex(self):
        assert _parse_offset("003b50") == 0x3B50

    def test_uppercase_hex(self):
        assert _parse_offset("003B50") == 0x3B50

    def test_wildcard_returns_none(self):
        assert _parse_offset("003b5*") is None
        assert _parse_offset("003b5?") is None

    def test_empty_returns_none(self):
        assert _parse_offset("") is None

    def test_invalid_returns_none(self):
        assert _parse_offset("not_hex") is None


# ============================================================
# LPPatchParser
# ============================================================
class TestLPPatchParser:
    def test_single_op(self):
        text = (
            "[FILE_IN_APK]\n"
            '{"name":"classes.dex"}\n'
            '{"offset":"003b50"}\n'
            '{"original":"12 34 56"}\n'
            '{"replaced":"12 AA 56"}\n'
        )
        patches = LPPatchParser(text).parse()
        assert len(patches) == 1
        assert patches[0].name == "classes.dex"
        assert len(patches[0].ops) == 1
        op = patches[0].ops[0]
        assert op.original == [0x12, 0x34, 0x56]
        assert op.replaced == [0x12, 0xAA, 0x56]
        assert op.offset == 0x3B50

    def test_multiple_ops_same_file(self):
        text = (
            "[FILE_IN_APK]\n"
            '{"name":"classes.dex"}\n'
            '{"original":"12 34"}\n'
            '{"replaced":"12 AA"}\n'
            '{"original":"56 78"}\n'
            '{"replaced":"56 BB"}\n'
        )
        patches = LPPatchParser(text).parse()
        assert len(patches) == 1
        assert len(patches[0].ops) == 2

    def test_multiple_files(self):
        text = (
            "[FILE_IN_APK]\n"
            '{"name":"classes.dex"}\n'
            '{"original":"12 34"}\n'
            '{"replaced":"12 AA"}\n'
            "[FILE_IN_APK]\n"
            '{"name":"classes2.dex"}\n'
            '{"original":"56 78"}\n'
            '{"replaced":"56 BB"}\n'
        )
        patches = LPPatchParser(text).parse()
        assert len(patches) == 2
        assert patches[0].name == "classes.dex"
        assert patches[1].name == "classes2.dex"

    def test_original_typo_supported(self):
        """LP has typo 'orginal' — must still parse."""
        text = (
            "[FILE_IN_APK]\n"
            '{"name":"classes.dex"}\n'
            '{"orginal":"12 34"}\n'
            '{"replaced":"12 AA"}\n'
        )
        patches = LPPatchParser(text).parse()
        assert len(patches) == 1
        assert len(patches[0].ops) == 1

    def test_wildcard_in_original(self):
        text = (
            "[FILE_IN_APK]\n"
            '{"name":"classes.dex"}\n'
            '{"original":"12 ** 34"}\n'
            '{"replaced":"12 34 34"}\n'
        )
        patches = LPPatchParser(text).parse()
        op = patches[0].ops[0]
        assert op.original[1] is None
        assert 1 in op.original_mask

    def test_wildcard_in_replaced_keeps_original(self):
        text = (
            "[FILE_IN_APK]\n"
            '{"name":"classes.dex"}\n'
            '{"original":"12 34 56"}\n'
            '{"replaced":"12 ** 56"}\n'
        )
        patches = LPPatchParser(text).parse()
        op = patches[0].ops[0]
        assert op.replaced[1] is None
        assert 1 in op.replaced_mask

    def test_other_files_section_ignored(self):
        text = (
            "[OTHER FILES]\n"
            '{"name":"random.txt"}\n'
            "[FILE_IN_APK]\n"
            '{"name":"classes.dex"}\n'
            '{"original":"12 34"}\n'
            '{"replaced":"12 AA"}\n'
        )
        patches = LPPatchParser(text).parse()
        assert len(patches) == 1
        assert patches[0].name == "classes.dex"

    def test_comments_ignored(self):
        text = (
            "# comment line\n"
            "[FILE_IN_APK]\n"
            "# another\n"
            '{"name":"classes.dex"}\n'
            '{"original":"12 34"}\n'
            '{"replaced":"12 AA"}\n'
        )
        patches = LPPatchParser(text).parse()
        assert len(patches) == 1

    def test_empty_input(self):
        assert LPPatchParser("").parse() == []

    def test_mismatched_lengths_padded(self):
        """Original 3 bytes, replaced 2 bytes → pad to 3."""
        text = (
            "[FILE_IN_APK]\n"
            '{"name":"classes.dex"}\n'
            '{"original":"12 34 56"}\n'
            '{"replaced":"AA BB"}\n'
        )
        patches = LPPatchParser(text).parse()
        op = patches[0].ops[0]
        assert len(op.original) == 3
        assert len(op.replaced) == 3
        assert op.replaced[2] is None   # padded → keep original

    def test_offset_optional(self):
        text = (
            "[FILE_IN_APK]\n"
            '{"name":"classes.dex"}\n'
            '{"original":"12 34"}\n'
            '{"replaced":"12 AA"}\n'
        )
        patches = LPPatchParser(text).parse()
        assert patches[0].ops[0].offset is None


# ============================================================
# _find_pattern
# ============================================================
class TestFindPattern:
    def test_exact_match(self):
        data = b"\x00\x11\x22\x33\x44"
        assert _find_pattern(data, [0x22, 0x33]) == 2

    def test_no_match(self):
        data = b"\x00\x11\x22"
        assert _find_pattern(data, [0xFF]) == -1

    def test_start_offset(self):
        data = b"\x11\x22\x11\x22"
        # Start at 2 → find at position 2
        assert _find_pattern(data, [0x11, 0x22], start=2) == 2

    def test_wildcard_match(self):
        data = b"\x11\xAA\x22\x11\xBB\x22"
        # Match 0x11, ?, 0x22 → position 0
        assert _find_pattern(data, [0x11, None, 0x22]) == 0

    def test_wildcard_no_match(self):
        data = b"\x11\xAA\x33"
        assert _find_pattern(data, [0x11, None, 0x22]) == -1

    def test_all_wildcards(self):
        data = b"\x11\x22\x33"
        assert _find_pattern(data, [None, None]) == 0

    def test_empty_pattern(self):
        data = b"\x11"
        assert _find_pattern(data, []) == -1

    def test_pattern_longer_than_data(self):
        assert _find_pattern(b"\x11", [0x11, 0x22]) == -1

    def test_first_byte_wildcard(self):
        data = b"\xAA\x11\x22"
        # First is wildcard → search from first fixed byte
        assert _find_pattern(data, [None, 0x11, 0x22]) == 0


# ============================================================
# _apply_op
# ============================================================
class TestApplyOp:
    def test_simple_replace(self):
        data = b"\x11\x22\x33\x44"
        op = HexOp(
            original=[0x22, 0x33],
            original_mask=set(),
            replaced=[0xAA, 0xBB],
            replaced_mask=set(),
        )
        new, n = _apply_op(data, op)
        assert n == 2
        assert new == b"\x11\xAA\xBB\x44"

    def test_wildcard_keeps_original(self):
        data = b"\x11\x22\x33"
        op = HexOp(
            original=[0x11, 0x22, 0x33],
            original_mask=set(),
            replaced=[None, 0xAA, None],
            replaced_mask={0, 2},
        )
        new, n = _apply_op(data, op)
        assert n == 3
        assert new == b"\x11\xAA\x33"

    def test_not_found(self):
        data = b"\x11\x22"
        op = HexOp(
            original=[0xFF, 0xEE],
            original_mask=set(),
            replaced=[0xAA, 0xBB],
            replaced_mask=set(),
        )
        new, n = _apply_op(data, op)
        assert n == 0
        assert new == data

    def test_search_from_offset(self):
        data = b"\x11\x22\x33\x11\x22\x33"
        op = HexOp(
            original=[0x11, 0x22, 0x33],
            original_mask=set(),
            replaced=[0xFF, 0xEE, 0xDD],
            replaced_mask=set(),
        )
        new, n = _apply_op(data, op, search_from=1)
        assert n == 3
        # Should find second occurrence at index 3
        assert new == b"\x11\x22\x33\xFF\xEE\xDD"


# ============================================================
# HexPatternPatcher.patch_apk
# ============================================================
class TestHexPatternPatcher:
    def test_missing_patch_file(self, tmp_path):
        apk = _make_apk(tmp_path, {"classes.dex": b"\x11\x22"})
        patcher = HexPatternPatcher(log_callback=lambda *a: None)
        result = patcher.patch_apk(apk, str(tmp_path / "nope.txt"))
        assert isinstance(result, PatchResult)
        assert result.applied == 0
        assert len(result.errors) > 0

    def test_empty_patch_file(self, tmp_path):
        apk = _make_apk(tmp_path, {"classes.dex": b"\x11\x22"})
        pf = _make_patch(tmp_path, "")
        patcher = HexPatternPatcher(log_callback=lambda *a: None)
        result = patcher.patch_apk(apk, pf)
        assert result.applied == 0

    def test_apply_single_patch(self, tmp_path):
        data = b"\x11\x22\x33\x44\x55"
        apk = _make_apk(tmp_path, {"classes.dex": data})
        pf = _make_patch(
            tmp_path,
            '[FILE_IN_APK]\n'
            '{"name":"classes.dex"}\n'
            '{"original":"22 33"}\n'
            '{"replaced":"AA BB"}\n',
        )
        patcher = HexPatternPatcher(log_callback=lambda *a: None)
        result = patcher.patch_apk(apk, pf)
        assert result.applied == 1
        assert result.total_ops == 1

        # Verify patched
        with zipfile.ZipFile(apk) as z:
            patched = z.read("classes.dex")
        assert patched == b"\x11\xAA\xBB\x44\x55"

    def test_multiple_ops(self, tmp_path):
        data = b"\x11\x22\x33\x44\x55\x66"
        apk = _make_apk(tmp_path, {"classes.dex": data})
        pf = _make_patch(
            tmp_path,
            '[FILE_IN_APK]\n'
            '{"name":"classes.dex"}\n'
            '{"original":"22 33"}\n'
            '{"replaced":"AA BB"}\n'
            '{"original":"55 66"}\n'
            '{"replaced":"CC DD"}\n',
        )
        patcher = HexPatternPatcher(log_callback=lambda *a: None)
        result = patcher.patch_apk(apk, pf)
        assert result.applied == 2

        with zipfile.ZipFile(apk) as z:
            patched = z.read("classes.dex")
        assert patched == b"\x11\xAA\xBB\x44\xCC\xDD"

    def test_entry_not_found(self, tmp_path):
        apk = _make_apk(tmp_path, {"classes.dex": b"\x11"})
        pf = _make_patch(
            tmp_path,
            '[FILE_IN_APK]\n'
            '{"name":"classes99.dex"}\n'
            '{"original":"11"}\n'
            '{"replaced":"22"}\n',
        )
        patcher = HexPatternPatcher(log_callback=lambda *a: None)
        result = patcher.patch_apk(apk, pf)
        assert result.applied == 0

    def test_pattern_not_found_skips(self, tmp_path):
        apk = _make_apk(tmp_path, {"classes.dex": b"\x11\x22"})
        pf = _make_patch(
            tmp_path,
            '[FILE_IN_APK]\n'
            '{"name":"classes.dex"}\n'
            '{"original":"FF FF"}\n'
            '{"replaced":"EE EE"}\n',
        )
        patcher = HexPatternPatcher(log_callback=lambda *a: None)
        result = patcher.patch_apk(apk, pf)
        assert result.applied == 0

    def test_wildcard_in_original(self, tmp_path):
        data = b"\x11\xAA\x33"
        apk = _make_apk(tmp_path, {"classes.dex": data})
        pf = _make_patch(
            tmp_path,
            '[FILE_IN_APK]\n'
            '{"name":"classes.dex"}\n'
            '{"original":"11 ** 33"}\n'
            '{"replaced":"11 BB 33"}\n',
        )
        patcher = HexPatternPatcher(log_callback=lambda *a: None)
        result = patcher.patch_apk(apk, pf)
        assert result.applied == 1

        with zipfile.ZipFile(apk) as z:
            patched = z.read("classes.dex")
        assert patched == b"\x11\xBB\x33"

    def test_wildcard_in_replaced(self, tmp_path):
        data = b"\x11\xAA\x33"
        apk = _make_apk(tmp_path, {"classes.dex": data})
        pf = _make_patch(
            tmp_path,
            '[FILE_IN_APK]\n'
            '{"name":"classes.dex"}\n'
            '{"original":"11 AA 33"}\n'
            '{"replaced":"11 ** 33"}\n',
        )
        patcher = HexPatternPatcher(log_callback=lambda *a: None)
        result = patcher.patch_apk(apk, pf)
        assert result.applied == 1

        with zipfile.ZipFile(apk) as z:
            patched = z.read("classes.dex")
        # Wildcard in replaced → keep original (0xAA)
        assert patched == b"\x11\xAA\x33"

    def test_multiple_entries(self, tmp_path):
        apk = _make_apk(tmp_path, {
            "classes.dex": b"\x11\x22",
            "classes2.dex": b"\xAA\xBB",
        })
        pf = _make_patch(
            tmp_path,
            '[FILE_IN_APK]\n'
            '{"name":"classes.dex"}\n'
            '{"original":"11 22"}\n'
            '{"replaced":"FF FF"}\n'
            '[FILE_IN_APK]\n'
            '{"name":"classes2.dex"}\n'
            '{"original":"AA BB"}\n'
            '{"replaced":"EE EE"}\n',
        )
        patcher = HexPatternPatcher(log_callback=lambda *a: None)
        result = patcher.patch_apk(apk, pf)
        assert result.applied == 2

        with zipfile.ZipFile(apk) as z:
            assert z.read("classes.dex") == b"\xFF\xFF"
            assert z.read("classes2.dex") == b"\xEE\xEE"

    def test_preserves_other_entries(self, tmp_path):
        apk = _make_apk(tmp_path, {
            "classes.dex": b"\x11",
            "AndroidManifest.xml": b"<manifest/>",
            "resources.arsc": b"fake",
        })
        pf = _make_patch(
            tmp_path,
            '[FILE_IN_APK]\n'
            '{"name":"classes.dex"}\n'
            '{"original":"11"}\n'
            '{"replaced":"22"}\n',
        )
        patcher = HexPatternPatcher(log_callback=lambda *a: None)
        patcher.patch_apk(apk, pf)

        with zipfile.ZipFile(apk) as z:
            names = z.namelist()
            assert "AndroidManifest.xml" in names
            assert "resources.arsc" in names

    def test_corrupted_apk(self, tmp_path):
        bad = tmp_path / "bad.apk"
        bad.write_bytes(b"not a zip")
        pf = _make_patch(
            tmp_path,
            '[FILE_IN_APK]\n'
            '{"name":"classes.dex"}\n'
            '{"original":"11"}\n'
            '{"replaced":"22"}\n',
        )
        patcher = HexPatternPatcher(log_callback=lambda *a: None)
        result = patcher.patch_apk(str(bad), pf)
        assert result.applied == 0
        assert len(result.errors) > 0


# ============================================================
# Module-level convenience
# ============================================================
class TestApplyHexPatches:
    def test_convenience_function(self, tmp_path):
        apk = _make_apk(tmp_path, {"classes.dex": b"\x11\x22"})
        pf = _make_patch(
            tmp_path,
            '[FILE_IN_APK]\n'
            '{"name":"classes.dex"}\n'
            '{"original":"11 22"}\n'
            '{"replaced":"AA BB"}\n',
        )
        result = apply_hex_patches(apk, pf, log_callback=lambda *a: None)
        assert result.applied == 1

    def test_parse_patch_file_helper(self, tmp_path):
        pf = _make_patch(
            tmp_path,
            '[FILE_IN_APK]\n'
            '{"name":"classes.dex"}\n'
            '{"original":"11"}\n'
            '{"replaced":"22"}\n',
        )
        patches = HexPatternPatcher.parse_patch_file(pf)
        assert len(patches) == 1
        assert patches[0].name == "classes.dex"


# ============================================================
# HexPatch / HexOp dataclass
# ============================================================
class TestDataclasses:
    def test_hex_op_length(self):
        op = HexOp(
            original=[0x11, 0x22, 0x33],
            original_mask=set(),
            replaced=[0xAA, 0xBB, 0xCC],
            replaced_mask=set(),
        )
        assert op.length == 3

    def test_hex_patch_defaults(self):
        p = HexPatch(name="classes.dex")
        assert p.name == "classes.dex"
        assert p.ops == []

    def test_patch_result_defaults(self):
        r = PatchResult()
        assert r.applied == 0
        assert r.errors == []