"""Kết hợp nhiều mode patch — orchestrate tuần tự."""
from __future__ import annotations

import logging

from core.lazy_loader import get_patcher_class

logger = logging.getLogger(__name__)


class MultiPatchCombiner:
    def __init__(self, decompiled_path: str, log_callback=print, file_cache=None):
        self.decompiled_path = decompiled_path
        self.log = log_callback
        self.file_cache = file_cache

    def apply_patches(self, modes: list[str]) -> dict:
        result = {"success": [], "failed": []}
        for mode in modes:
            cls = get_patcher_class(mode)
            if cls is None:
                result["failed"].append(mode)
                continue
            try:
                patcher = cls(self.decompiled_path,
                              log_callback=self.log,
                              file_cache=self.file_cache)
                if hasattr(patcher, "patch"):
                    patcher.patch()
                result["success"].append(mode)
            except Exception as e:
                logger.warning("Mode %s failed: %s", mode, e)
                result["failed"].append(mode)
        return result