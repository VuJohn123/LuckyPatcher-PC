"""Ad remover — xóa ad activities khỏi AndroidManifest."""
from __future__ import annotations
import os
import re
from patcher.base import BasePatcher

class AdRemover(BasePatcher):
    def __init__(self, decompiled_path, log_callback=print, file_cache=None):
        super().__init__(decompiled_path, log_callback, file_cache)
        self.manifest_path = os.path.join(
            decompiled_path, "AndroidManifest.xml"
        )

    def _remove_components(self, names, tag) -> bool:
        try:
            content = self._read(self.manifest_path)
        except OSError:
            return False
        original = content
        for n in names:
            pat = (rf'<{tag}[^>]*android:name="'
                   + re.escape(n) + r'"[^/]*/?>')
            content = re.sub(pat, "", content, flags=re.DOTALL)
        if content != original:
            self._write(self.manifest_path, content)
            return True
        return False

    def remove_activities(self, ad_activities) -> bool:
        return self._remove_components(ad_activities, "activity")

    def remove_receivers(self, ad_receivers) -> bool:
        return self._remove_components(ad_receivers, "receiver")

    def patch(self) -> int:
        return 0