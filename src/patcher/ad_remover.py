"""Ad remover — xóa ad activities khỏi AndroidManifest."""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)


class AdRemover:
    def __init__(self, decompiled_path: str, file_cache=None):
        self.manifest_path = os.path.join(decompiled_path, "AndroidManifest.xml")
        self.file_cache = file_cache

    def _read(self) -> str:
        if self.file_cache:
            return self.file_cache.read(self.manifest_path)
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            return f.read()

    def _write(self, content: str) -> None:
        if self.file_cache:
            self.file_cache.write(self.manifest_path, content)
        else:
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                f.write(content)

    def remove_activities(self, ad_activities: list[str]) -> bool:
        if not ad_activities:
            return False
        content = self._read()
        original = content
        for act in ad_activities:
            pattern = r'<activity[^>]*android:name="' + re.escape(act) + r'"[^/]*/?>'
            content = re.sub(pattern, "", content, flags=re.DOTALL)
        if content != original:
            self._write(content)
            return True
        return False

    def remove_receivers(self, ad_receivers: list[str]) -> bool:
        if not ad_receivers:
            return False
        content = self._read()
        original = content
        for recv in ad_receivers:
            pattern = r'<receiver[^>]*android:name="' + re.escape(recv) + r'"[^/]*/?>'
            content = re.sub(pattern, "", content, flags=re.DOTALL)
        if content != original:
            self._write(content)
            return True
        return False