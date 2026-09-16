"""
Custom patch parser + applier — hỗ trợ .txt và .lpzip.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import zipfile

from core.smali_utils import get_all_smali_files

logger = logging.getLogger(__name__)


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
                    current_ops.append({
                        "type": "replace",
                        "pattern": pat.strip(),
                        "replacement": rep.strip(),
                    })
            elif "->" in line:
                pat, rep = line.split("->", 1)
                current_ops.append({
                    "type": "replace",
                    "pattern": pat.strip(),
                    "replacement": rep.strip(),
                })

        if current_target:
            instructions.append({
                "target_file": current_target,
                "operations": current_ops,
            })

        return instructions

    def _parse_lpzip(self) -> list[dict]:
        tmpdir = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(self.path, "r") as z:
                txts = [n for n in z.namelist() if n.endswith(".txt")]
                if not txts:
                    return []
                content = z.read(txts[0]).decode("utf-8", errors="ignore")
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


class CustomPatchApplier:
    def __init__(self, decompiled_path: str, log_callback=print, file_cache=None):
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
        for instr in instructions:
            target = instr.get("target_file", "")
            matched = self._find_files(target)
            if not matched:
                self.log(f"[!] [CustomPatch] Không tìm thấy: {target}")
                continue

            for path in matched:
                content = self._read(path)
                original = content
                for op in instr.get("operations", []):
                    if op.get("type") != "replace":
                        continue
                    try:
                        content = re.sub(
                            op["pattern"], op["replacement"],
                            content, flags=re.DOTALL,
                        )
                    except re.error as e:
                        logger.warning("Regex lỗi: %s", e)
                if content != original:
                    self._write(path, content)
                    patched += 1

        return patched

    def _find_files(self, pattern: str) -> list[str]:
        matched = []
        for filepath in get_all_smali_files(self.decompiled_path):
            rel = os.path.relpath(filepath, self.decompiled_path)
            try:
                if re.search(pattern, rel):
                    matched.append(filepath)
            except re.error:
                continue
        return matched

    def patch(self) -> int:
        """Interface tương thích lazy_loader."""
        patch_file = os.environ.get("LP_CUSTOM_PATCH")
        if not patch_file or not os.path.exists(patch_file):
            return 0
        instructions = CustomPatchParser(patch_file).parse()
        return self.apply(instructions)