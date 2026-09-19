"""Thay đổi permissions trong AndroidManifest."""
from __future__ import annotations

import os
import re

from patcher.base import BasePatcher


class PermissionChanger(BasePatcher):
    DEFAULT_REMOVE = (
        "android.permission.READ_SMS",
        "android.permission.SEND_SMS",
        "android.permission.RECEIVE_SMS",
        "android.permission.READ_CONTACTS",
    )

    def __init__(
        self,
        decompiled_path: str,
        permissions_to_remove=None,
        log_callback=print,
        file_cache=None,
    ):
        super().__init__(decompiled_path, log_callback, file_cache)
        self.manifest_path = os.path.join(
            decompiled_path, "AndroidManifest.xml"
        )
        self.permissions_to_remove = (
            permissions_to_remove or list(self.DEFAULT_REMOVE)
        )

    def remove_permissions(self) -> bool:
        """Backward-compat: return True nếu có ít nhất 1 permission bị xóa."""
        try:
            content = self._read(self.manifest_path)
        except OSError:
            return False

        original = content
        for perm in self.permissions_to_remove:
            pat = (
                r'<uses-permission\s+android:name="'
                + re.escape(perm) + r'"\s*/?>'
            )
            content = re.sub(pat, "", content, flags=re.IGNORECASE)

        if content != original:
            self._write(self.manifest_path, content)
            return True
        return False

    def patch(self) -> int:
        return 1 if self.remove_permissions() else 0