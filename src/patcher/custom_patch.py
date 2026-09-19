"""
Custom patch parser + applier — hỗ trợ .txt và .lpzip.

v3 (LP parity):
  - Hỗ trợ `**` mask operand — pattern survive qua app updates.
    Ví dụ: `const/4 v0, **` → match mọi giá trị immediate.
  - ReDoS-safe dùng core.regex_safe.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import zipfile

from core.regex_safe import safe_sub, is_safe_pattern
from core.smali_utils import get_all_smali_files

logger = logging.getLogger(__name__)

_MAX_CONTENT_MB = 50
_MAX_PATH_LEN = 250


# ============================================================
# MASK PARSER (** → regex wildcard)
# ============================================================
def _apply_mask(pattern: str) -> str:
    """
    Convert LP mask syntax sang regex:
      - `**` → `\\S+` (một operand bất kỳ, không space)
      - Literal đã escape để tránh regex injection từ user input.
    """
    # Escape phần literal, sau đó replace `\*\*` (escape của **)
    escaped = re.escape(pattern)
    # re.escape('**') → '\\*\\*'
    escaped = escaped.replace(r"\*\*", r"\S+")
    return escaped


def _has_mask(pattern: str) -> bool:
    return "**" in pattern


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

                    # Mask transform
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
                f"[i] [CustomPatch] Used ** mask in {masked_used} ops"
            )
        return patched

    def _find_files(self, pattern: str) -> list[str]:
        if not is_safe_pattern(pattern)[0]:
            self.log(
                f"[!] [CustomPatch] target pattern rejected"
            )
            return []

        matched = []
        try:
            from core.regex_safe import safe_search
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