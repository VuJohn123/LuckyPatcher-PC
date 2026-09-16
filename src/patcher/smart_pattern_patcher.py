"""Base class cho các patcher dùng pattern cấu trúc."""
from __future__ import annotations

import logging
import os
import re

from core.smali_utils import get_all_smali_files

logger = logging.getLogger(__name__)


class SmartPatternPatcher:
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

    def apply_patterns(self, patterns: list[dict],
                       target_methods: list[str] | None = None) -> int:
        total = 0
        for filepath in get_all_smali_files(self.decompiled_path):
            if len(filepath) > 250:
                continue
            try:
                content = self._read(filepath)
            except OSError:
                continue

            if target_methods and not any(m in content for m in target_methods):
                continue

            original = content
            for p in patterns:
                search = p.get("search")
                replace = p.get("replace")
                if not search:
                    continue
                try:
                    if callable(replace):
                        new_content = re.sub(search, replace, content,
                                             flags=re.DOTALL)
                        if new_content != content:
                            total += 1
                            content = new_content
                    else:
                        new_content, n = re.subn(search, replace, content,
                                                  flags=re.DOTALL)
                        if n > 0:
                            content = new_content
                            total += n
                except re.error as e:
                    logger.warning("Pattern error in %s: %s", filepath, e)

            if content != original:
                try:
                    self._write(filepath, content)
                except OSError as e:
                    logger.warning("Write failed %s: %s", filepath, e)

        self.log(f"[*] [SmartPattern] Total replacements: {total}")
        return total