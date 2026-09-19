"""
Smart pattern patcher — base class cho patcher dùng pattern cấu trúc.

v2: ReDoS-safe dùng core.regex_safe.
    Giữ `get_all_smali_files` import ở module level để test có thể mock.
"""
from __future__ import annotations

import logging

from core.regex_safe import safe_sub
from core.smali_utils import get_all_smali_files  # noqa: F401  (test mock target)
from patcher.base import BasePatcher

logger = logging.getLogger(__name__)


class SmartPatternPatcher(BasePatcher):
    def apply_patterns(
        self,
        patterns: list[dict],
        target_methods: list[str] | None = None,
    ) -> int:
        """
        patterns: [{"search": <regex>, "replace": <str|callable>}]
        """
        if not patterns:
            return 0

        prefilter = tuple(target_methods) if target_methods else ()

        import re as _re

        def _transform(content: str, filepath: str) -> str | None:
            original = content
            for p in patterns:
                search = p.get("search")
                replace = p.get("replace")
                if not search:
                    continue
                new, ok = safe_sub(
                    search, replace, content,
                    flags=_re.DOTALL,
                    log_callback=self.log,
                )
                if ok:
                    content = new
            return content if content != original else None

        return self.patch_files(
            _transform,
            prefilter_keywords=prefilter,
            label="SmartPattern",
        )

    def patch(self) -> int:
        return 0