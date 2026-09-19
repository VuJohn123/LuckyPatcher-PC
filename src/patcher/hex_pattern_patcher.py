"""
Hex Pattern Patcher — LP-format byte-level pattern matching.

Implements LP custom patch format:
    [FILE_IN_APK]
    {"name":"classes.dex"}
    {"offset":"003b50"}
    {"original":"12 34 ** 56"}
    {"replaced":"12 AA ** 56"}

Wildcards:
  - `**` hoặc `??` trong `original` → match bất kỳ byte
  - `**` trong `replaced` → giữ nguyên byte gốc
  - `offset` optional — nếu có, search từ offset; nếu không, full scan
  - Offset có thể chứa `*` → hex wildcard (vd `003b5*`)

Ưu điểm so với regex text:
  - Survives app updates (operand changes được mask)
  - Không cần decompile — patch trực tiếp dex bytes
  - Nhanh hơn 50-100x (không parse smali text)

Format sections:
    [FILE_IN_APK]    — file nằm trong APK (dex, .so, assets)
    [OTHER FILES]    — file ngoài (chưa support — log warning)

References:
  - Sbenny custom patch format
  - Mobimart hex patch format
  - LP-DeCodes lpdiff analyzer
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================
# DATA MODEL
# ============================================================
@dataclass
class HexOp:
    """One hex patch operation."""
    original: list[int | None]     # None = wildcard
    original_mask: set[int]        # positions where pattern is wildcard
    replaced: list[int | None]     # None = keep original byte
    replaced_mask: set[int]        # positions to keep original
    offset: int | None = None      # hint offset if provided

    @property
    def length(self) -> int:
        return len(self.original)


@dataclass
class HexPatch:
    """All ops for 1 file inside APK."""
    name: str                       # e.g., "classes.dex"
    ops: list[HexOp] = field(default_factory=list)


@dataclass
class PatchResult:
    """Summary of applied patch."""
    total_files: int = 0
    total_ops: int = 0
    applied: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


# ============================================================
# PARSER — LP FORMAT
# ============================================================
_JSON_LINE_RE = re.compile(
    r'\{\s*"([\w_]+)"\s*:\s*"([^"]*)"\s*\}'
)

_FILE_SECTION_RE = re.compile(r"^\s*\[(FILE_IN_APK|OTHER FILES)\]\s*$")


def _parse_hex_bytes(s: str) -> tuple[list[int | None], set[int]]:
    """
    Parse string "12 34 ** 56" → ([0x12, 0x34, None, 0x56], {2}).

    Supports:
      - 2-char hex bytes: "12", "AA", "ff"
      - Wildcard: "**" hoặc "??"
      - Single hex: "A" → treated as 0x0A (padding)
    """
    tokens = s.strip().split()
    values: list[int | None] = []
    masks: set[int] = set()

    for i, tok in enumerate(tokens):
        tok = tok.strip()
        if tok in ("**", "??"):
            values.append(None)
            masks.add(i)
            continue
        try:
            if len(tok) == 1:
                tok = tok.zfill(2)
            values.append(int(tok, 16))
        except ValueError:
            logger.debug("Invalid hex token '%s' — treat as wildcard", tok)
            values.append(None)
            masks.add(i)
    return values, masks


def _parse_offset(s: str) -> int | None:
    """Parse offset string. Return int or None if wildcard/invalid."""
    s = s.strip()
    if not s or "*" in s or "?" in s:
        return None
    try:
        return int(s, 16)
    except ValueError:
        return None


class LPPatchParser:
    """Parse LP-format custom patch file → list of HexPatch."""

    def __init__(self, patch_text: str):
        self.text = patch_text

    def parse(self) -> list[HexPatch]:
        patches: list[HexPatch] = []
        current: HexPatch | None = None
        current_section: str | None = None

        pending_offset: int | None = None
        pending_original: tuple[list[int | None], set[int]] | None = None

        for raw in self.text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            # Section header
            m = _FILE_SECTION_RE.match(line)
            if m:
                section = m.group(1)
                if section == "OTHER FILES":
                    if current and current.ops:
                        patches.append(current)
                    current = None
                    current_section = "OTHER"
                    continue
                # FILE_IN_APK
                if current and current.ops:
                    patches.append(current)
                current = None
                current_section = "APK"
                pending_offset = None
                pending_original = None
                continue

            if current_section == "OTHER":
                # Not supported — skip silently
                continue

            # JSON line
            jm = _JSON_LINE_RE.match(line)
            if not jm:
                continue
            key = jm.group(1).lower()
            val = jm.group(2)

            if key == "name":
                # New file target
                if current and current.ops:
                    patches.append(current)
                current = HexPatch(name=val)
                pending_offset = None
                pending_original = None
                continue

            if current is None:
                continue

            if key in ("offset", "orginal", "original"):
                if key == "offset":
                    pending_offset = _parse_offset(val)
                else:
                    pending_original = _parse_hex_bytes(val)
                continue

            if key == "replaced":
                if pending_original is None:
                    continue
                orig_vals, orig_mask = pending_original
                rep_vals, rep_mask = _parse_hex_bytes(val)

                # Normalize: aligned lengths
                max_len = max(len(orig_vals), len(rep_vals))
                orig_vals = orig_vals + [None] * (max_len - len(orig_vals))
                rep_vals = rep_vals + [None] * (max_len - len(rep_vals))

                # In "replaced", None = keep original byte
                op = HexOp(
                    original=orig_vals,
                    original_mask=orig_mask,
                    replaced=rep_vals,
                    replaced_mask={
                        i for i, v in enumerate(rep_vals) if v is None
                    },
                    offset=pending_offset,
                )
                current.ops.append(op)
                pending_offset = None
                pending_original = None
                continue

        if current and current.ops:
            patches.append(current)

        return patches


# ============================================================
# MATCHER — wildcard-aware byte search
# ============================================================
def _find_pattern(
    data: bytes,
    pattern: list[int | None],
    start: int = 0,
) -> int:
    """
    Return first index in `data` where `pattern` matches (None = wildcard).
    -1 if not found.

    Handles:
      - All-wildcard pattern: trả về `start` nếu đủ chỗ.
      - First byte wildcard: anchor vào first fixed byte nhưng vẫn
        iterate toàn bộ sliding window.
      - No-wildcard fast path: dùng bytes.find().
    """
    n = len(pattern)
    if n == 0 or n > len(data):
        return -1
    if start < 0:
        start = 0
    if start + n > len(data):
        return -1

    # Fast path: no wildcards → bytes.find()
    if all(p is not None for p in pattern):
        needle = bytes(p for p in pattern if p is not None)
        return data.find(needle, start)

    # Wildcard path — sliding window
    # first_fixed = -1 nếu toàn wildcard
    first_fixed = -1
    for i, p in enumerate(pattern):
        if p is not None:
            first_fixed = i
            break

    end = len(data) - n + 1
    i = start
    while i < end:
        # Quick check on first fixed byte (skip most positions)
        if first_fixed >= 0:
            if data[i + first_fixed] != pattern[first_fixed]:
                i += 1
                continue

        # Verify full pattern
        ok = True
        for j, p in enumerate(pattern):
            if p is None:
                continue
            if data[i + j] != p:
                ok = False
                break
        if ok:
            return i
        i += 1
    return -1


def _apply_op(data: bytes, op: HexOp, search_from: int = 0) -> tuple[bytes, int]:
    """
    Apply 1 op. Return (new_data, bytes_modified_or_0).

    Wildcards in `replaced` keep original byte.
    """
    idx = _find_pattern(data, op.original, start=search_from)
    if idx < 0:
        return data, 0

    # Build replacement bytes
    new_bytes = bytearray()
    for i, rep_val in enumerate(op.replaced):
        if rep_val is None:
            new_bytes.append(data[idx + i])
        else:
            new_bytes.append(rep_val)

    new_data = data[:idx] + bytes(new_bytes) + data[idx + len(op.original):]
    return new_data, len(op.original)


# ============================================================
# PATCHER
# ============================================================
class HexPatternPatcher:
    """
    Apply LP hex pattern patches trực tiếp vào APK (post-recompile).

    Flow:
      1. Read APK zip
      2. For each patch target (classes.dex, lib/*.so, ...):
         - Extract bytes
         - Apply all ops (byte-level with wildcards)
         - Replace in zip
      3. Rebuild APK to temp then atomic-replace
    """

    def __init__(self, log_callback=print):
        self.log = log_callback

    # ============================================================
    # PUBLIC
    # ============================================================
    def patch_apk(
        self,
        apk_path: str,
        patch_file: str,
    ) -> PatchResult:
        """
        Apply patches from `patch_file` to `apk_path` in-place.

        Returns PatchResult với counts.
        """
        result = PatchResult()

        # Read + parse
        try:
            with open(patch_file, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            result.errors.append(f"Cannot read patch file: {e}")
            self.log(f"[!] [HexPatcher] {e}")
            return result

        patches = LPPatchParser(text).parse()
        if not patches:
            self.log("[i] [HexPatcher] Không có patch nào để apply")
            return result

        result.total_files = len(patches)
        result.total_ops = sum(len(p.ops) for p in patches)

        self.log(
            f"[*] [HexPatcher] {result.total_files} file(s), "
            f"{result.total_ops} op(s)"
        )

        # Patch each file
        applied_total = 0
        for patch in patches:
            try:
                n = self._patch_file_in_apk(apk_path, patch)
                applied_total += n
            except Exception as e:
                logger.warning("HexPatch failed %s: %s", patch.name, e)
                result.errors.append(f"{patch.name}: {e}")

        result.applied = applied_total
        result.skipped = result.total_ops - applied_total

        self.log(
            f"[✔] [HexPatcher] Applied {applied_total}/"
            f"{result.total_ops} op(s)"
        )
        return result

    # ============================================================
    # INTERNAL
    # ============================================================
    def _patch_file_in_apk(
        self,
        apk_path: str,
        patch: HexPatch,
    ) -> int:
        """Patch one entry (by name) inside APK. Return ops applied."""
        # APK entries can use either / or \ as separator
        candidates = [
            patch.name,
            patch.name.replace("/", "\\"),
            patch.name.replace("\\", "/"),
        ]

        # Read APK into temp
        tmp = tempfile.mkdtemp(prefix="hexpatch_")
        try:
            tmp_apk = os.path.join(tmp, "out.apk")
            applied = 0

            with zipfile.ZipFile(apk_path, "r") as zin, \
                 zipfile.ZipFile(tmp_apk, "w", zipfile.ZIP_DEFLATED) as zout:
                found = False
                for info in zin.infolist():
                    data = zin.read(info.filename)
                    if not found and info.filename in candidates:
                        new_data, n = self._apply_all_ops(data, patch.ops)
                        if n > 0:
                            data = new_data
                            applied = n
                            found = True
                            self.log(
                                f"[+] [HexPatcher] {info.filename} — "
                                f"{n} op(s)"
                            )
                    zout.writestr(info, data)

            if not found:
                self.log(
                    f"[i] [HexPatcher] Không tìm thấy entry '{patch.name}'"
                )
                return 0

            # Atomic replace
            shutil.move(tmp_apk, apk_path)
            return applied

        except (zipfile.BadZipFile, OSError) as e:
            logger.warning("APK patch failed: %s", e)
            raise
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _apply_all_ops(
        self,
        data: bytes,
        ops: list[HexOp],
    ) -> tuple[bytes, int]:
        """Apply list of ops sequentially. Return (new_data, count)."""
        count = 0
        for op in ops:
            start = op.offset if op.offset is not None else 0
            new_data, n = _apply_op(data, op, search_from=start)
            if n > 0:
                data = new_data
                count += 1
        return data, count

    # ============================================================
    # UTILITY
    # ============================================================
    @staticmethod
    def parse_patch_file(patch_file: str) -> list[HexPatch]:
        """Public parse helper for tests / analyzer."""
        with open(patch_file, "r", encoding="utf-8") as f:
            text = f.read()
        return LPPatchParser(text).parse()


# ============================================================
# MODULE-LEVEL CONVENIENCE
# ============================================================
def apply_hex_patches(
    apk_path: str,
    patch_file: str,
    log_callback=print,
) -> PatchResult:
    """One-shot: apply LP hex patches to APK."""
    patcher = HexPatternPatcher(log_callback=log_callback)
    return patcher.patch_apk(apk_path, patch_file)