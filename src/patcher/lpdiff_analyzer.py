"""So sánh 2 file smali → sinh custom patch pattern có mask operand."""
from __future__ import annotations

import logging
import re
import zipfile
import os
import tempfile
import shutil

logger = logging.getLogger(__name__)


class LPDiffAnalyzer:
    def __init__(self, original_smali: str, patched_smali: str):
        self.orig = original_smali
        self.patched = patched_smali

    def generate_pattern(self, mask_operands: bool = True) -> str:
        with open(self.orig, "r", encoding="utf-8", errors="ignore") as f:
            orig_lines = f.readlines()
        with open(self.patched, "r", encoding="utf-8", errors="ignore") as f:
            patched_lines = f.readlines()

        orig_insts = self._extract_instructions(orig_lines)
        patch_insts = self._extract_instructions(patched_lines)

        lines: list[str] = []
        i = j = 0
        while i < len(orig_insts) and j < len(patch_insts):
            if orig_insts[i] == patch_insts[j]:
                i += 1
                j += 1
                continue
            orig_block = orig_insts[i:i + 5]
            patch_block = patch_insts[j:j + 5]
            pattern = self._block_to_pattern(orig_block, mask_operands)
            replacement = "\n".join(patch_block)
            lines.append(f"{pattern} -> {replacement}")
            i += len(orig_block)
            j += len(patch_block)

        return "\n".join(lines)

    def _extract_instructions(self, lines: list[str]) -> list[str]:
        out = []
        for line in lines:
            s = line.strip()
            if s and not s.startswith(".") and not s.startswith("#") and ":" not in s:
                out.append(s)
        return out

    def _block_to_pattern(self, block: list[str], mask: bool) -> str:
        parts = []
        for inst in block:
            if mask:
                masked = re.sub(r"\bv\d+\b", r"v\\d+", inst)
                masked = re.sub(r"\bp\d+\b", r"p\\d+", masked)
                masked = re.sub(r":\w+", r":\\w+", masked)
                masked = re.sub(r'"(.*?)"', r'"\\w*"', masked)
                parts.append(re.escape(masked)
                             .replace(r"\{\.\*\?\}", r"{.*?}")
                             .replace(r"\(\.\*\)", r"(.*)"))
            else:
                parts.append(re.escape(inst))
        return "\n".join(parts)

    def save_lpzip(self, output_zip: str, target_filename: str = "classes.dex") -> str:
        tmp = tempfile.mkdtemp()
        try:
            txt = os.path.join(tmp, "patch.txt")
            with open(txt, "w", encoding="utf-8") as f:
                f.write(f"[{target_filename}]\n{self.generate_pattern()}")
            with zipfile.ZipFile(output_zip, "w") as z:
                z.write(txt, arcname="patch.txt")
            return output_zip
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def patch(self) -> int:
        return 0