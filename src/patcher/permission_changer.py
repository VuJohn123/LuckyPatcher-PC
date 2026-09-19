"""Thay đổi permissions trong AndroidManifest.xml.

v2 (2026):
  - Hỗ trợ env var `LP_PERMS_TO_REMOVE` — UI picker truyền list
    permission qua env, không cần modify constructor call trong
    pipeline_executor.
  - Priority: explicit arg > env var > DEFAULT_REMOVE.
"""
from __future__ import annotations

import logging
import os
import re

from patcher.base import BasePatcher

logger = logging.getLogger(__name__)


class PermissionChanger(BasePatcher):
    # Fallback khi không có arg và không có env var
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
        self.permissions_to_remove = self._resolve_permissions(
            permissions_to_remove
        )

    def _resolve_permissions(self, explicit: list | None) -> list[str]:
        """
        Priority:
          1. explicit (từ code, test)
          2. env var `LP_PERMS_TO_REMOVE` (từ UI picker)
          3. DEFAULT_REMOVE
        """
        if explicit:
            return list(explicit)

        env_val = os.environ.get("LP_PERMS_TO_REMOVE", "").strip()
        if env_val:
            perms = [p.strip() for p in env_val.split(",") if p.strip()]
            if perms:
                logger.debug(
                    "PermissionChanger: dùng %d perm từ env var",
                    len(perms),
                )
                return perms

        return list(self.DEFAULT_REMOVE)

    # ============================================================
    # PATCH
    # ============================================================
    def remove_permissions(self) -> bool:
        try:
            content = self._read(self.manifest_path)
        except OSError:
            return False

        original = content
        removed = 0
        for perm in self.permissions_to_remove:
            pat = (
                r'<uses-permission\s+android:name="'
                + re.escape(perm) + r'"\s*/?>\s*\n?'
            )
            new_content, count = re.subn(
                pat, "", content, flags=re.IGNORECASE,
            )
            if count > 0:
                content = new_content
                removed += count

        if content != original:
            self._write(self.manifest_path, content)
            self.log(
                f"[✔] [PermissionChanger] Đã xóa {removed} permission"
            )
            return True
        return False

    def patch(self) -> int:
        return 1 if self.remove_permissions() else 0