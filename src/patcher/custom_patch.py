"""
Custom patch parser + applier — hỗ trợ .txt và .lpzip.

v4 (LP parity + extended mask):
  - Mask syntax mở rộng:
      **       → `\\S+`  (một operand không space)
      *        → `[^,}\\s]+`  (một operand, không vượt dấu phẩy/ngoặc)
      ?        → `\\S*`  (zero hoặc một operand)
      <reg>    → `[vp]\\d+`  (bất kỳ register nào)
      <label>  → `:\\w+`  (bất kỳ label)
      <any>    → `.*?`  (bất kỳ - non-greedy)
  - Support LP pattern format: `**` đầu pattern = wildcard prefix.
  - ReDoS-safe qua core.regex_safe.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import zipfile

from core.regex_safe import safe_sub, is_safe_pattern, safe_search
from core.smali_utils import get_all_smali_files

logger = logging.getLogger(__name__)

_MAX_CONTENT_MB = 50
_MAX_PATH_LEN = 250


# ============================================================
# MASK SYNTAX
# ============================================================
_MASK_MAP = (
    # Order matters — longest markers first
    ("**", r"\S+"),         # one non-space token
    ("<reg>", r"[vp]\d+"),  # v0..v31, p0..p31
    ("<label>", r":\w+"),   # :cond_0, :goto_1, etc.
    ("<any>", r".*?"),      # any non-greedy
    ("*", r"[^,}\s]+"),     # one token, no comma/brace/space
    ("?", r"\S*"),          # zero or one token
)


def _has_mask(pattern: str) -> bool:
    return any(m in pattern for m, _ in _MASK_MAP)


def _apply_mask(pattern: str) -> str:
    """
    Convert LP mask syntax → regex.

    Escapes literal chars first, then replaces markers (which after
    escape are still recognizable because we scan for marker text
    BEFORE escaping — must do it carefully).

    Approach:
      1. Split pattern by markers, keeping order.
      2. Escape literal segments.
      3. Join with regex fragments.
    """
    # Find all marker positions
    markers = []
    i = 0
    while i < len(pattern):
        matched = False
        for marker, regex in _MASK_MAP:
            if pattern.startswith(marker, i):
                markers.append((i, marker, regex))
                i += len(marker)
                matched = True
                break
        if not matched:
            i += 1

    if not markers:
        return re.escape(pattern)

    # Build escaped chunks + regex chunks
    parts: list[str] = []
    last_end = 0
    for pos, marker, regex in markers:
        if pos > last_end:
            parts.append(re.escape(pattern[last_end:pos]))
        parts.append(regex)
        last_end = pos + len(marker)
    if last_end < len(pattern):
        parts.append(re.escape(pattern[last_end:]))

    return "".join(parts)


# ============================================================
# PARSER
# ============================================================
class CustomPatchParser:
    def __init__(self, patch_file_path: str):
        self.path = patch_file_path

    def parse(self) -> list[dict]:
        if self.path.endswith(".lpzip"):
            return self._parse_lpzip()
        return self._parse_txt()

    def _parse_txt(self) -> list[dict]:
        instructions: list[dict] = []
        current_target = None
        current_ops: list[dict] = []

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError as e:
            logger.error("Không đọc được patch: %s", e)
            return []

        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("[") and "]" in line:
                if current_target:
                    instructions.append({
                        "target_file": current_target,
                        "operations": current_ops,
                    })
                current_target = line[1:line.index("]")].strip()
                current_ops = []
                rest = line[line.index("]") + 1:].strip()
                if "->" in rest:
                    pat, rep = rest.split("->", 1)
                    current_ops.append(self._make_op(pat, rep))
            elif "->" in line:
                pat, rep = line.split("->", 1)
                current_ops.append(self._make_op(pat, rep))

        if current_target:
            instructions.append({
                "target_file": current_target,
                "operations": current_ops,
            })

        return instructions

    def _make_op(self, pattern: str, replacement: str) -> dict:
        pattern = pattern.strip()
        replacement = replacement.strip()
        return {
            "type": "replace",
            "pattern": pattern,
            "replacement": replacement,
            "masked": _has_mask(pattern),
        }

    def _parse_lpzip(self) -> list[dict]:
        tmpdir = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(self.path, "r") as z:
                txts = [n for n in z.namelist() if n.endswith(".txt")]
                if not txts:
                    return []
                content = z.read(txts[0]).decode(
                    "utf-8", errors="ignore"
                )
            tmp_txt = os.path.join(tmpdir, "patch.txt")
            with open(tmp_txt, "w", encoding="utf-8") as f:
                f.write(content)
            self.path = tmp_txt
            return self._parse_txt()
        except (zipfile.BadZipFile, OSError) as e:
            logger.error("lpzip parse failed: %s", e)
            return []
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# APPLIER
# ============================================================
class CustomPatchApplier:
    def __init__(self, decompiled_path: str, log_callback=print,
                 file_cache=None):
        self.decompiled_path = decompiled_path
        self.log = log_callback
        self.file_cache = file_cache

    def _read(self, path: str) -> str:
        if self.file_cache:
            return self.file_cache.read(path)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _write(self, path: str, content: str) -> None:
        if self.file_cache:
            self.file_cache.write(path, content)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

    def apply(self, instructions: list[dict]) -> int:
        patched = 0
        rejected = 0
        masked_used = 0
        max_bytes = _MAX_CONTENT_MB * 1024 * 1024

        for instr in instructions:
            target = instr.get("target_file", "")
            matched = self._find_files(target)
            if not matched:
                self.log(f"[!] [CustomPatch] Không tìm thấy: {target}")
                continue

            for path in matched:
                try:
                    size = os.path.getsize(path)
                    if size > max_bytes:
                        continue
                except OSError:
                    continue

                content = self._read(path)
                original = content

                for op in instr.get("operations", []):
                    if op.get("type") != "replace":
                        continue

                    pattern = op.get("pattern", "")
                    replacement = op.get("replacement", "")
                    masked = op.get("masked", False)

                    if not pattern:
                        continue

                    if masked:
                        pattern = _apply_mask(pattern)
                        masked_used += 1

                    new_content, ok = safe_sub(
                        pattern, replacement, content,
                        flags=re.DOTALL,
                        log_callback=self.log,
                    )
                    if not ok:
                        rejected += 1
                        continue
                    content = new_content

                if content != original:
                    self._write(path, content)
                    patched += 1

        if rejected:
            self.log(
                f"[i] [CustomPatch] {rejected} pattern(s) rejected"
            )
        if masked_used:
            self.log(
                f"[i] [CustomPatch] Used mask in {masked_used} ops"
            )
        return patched

    def _find_files(self, pattern: str) -> list[str]:
        if not is_safe_pattern(pattern)[0]:
            self.log(
                "[!] [CustomPatch] target pattern rejected"
            )
            return []

        matched = []
        try:
            for filepath in get_all_smali_files(self.decompiled_path):
                if len(filepath) > _MAX_PATH_LEN:
                    continue
                rel = os.path.relpath(filepath, self.decompiled_path)
                if safe_search(pattern, rel):
                    matched.append(filepath)
        except Exception as e:
            logger.warning("find_files failed: %s", e)
        return matched

    def patch(self) -> int:
        patch_file = os.environ.get("LP_CUSTOM_PATCH")
        if not patch_file or not os.path.exists(patch_file):
            return 0
        instructions = CustomPatchParser(patch_file).parse()
        return self.apply(instructions)