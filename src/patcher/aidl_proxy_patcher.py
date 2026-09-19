"""
AIDL Proxy Patcher — copy proxy smali + inject service vào manifest.

Đây là PATCHER (chèn proxy đã có sẵn vào target app). Khác với
`aidl_proxy_generator.py` là GENERATOR (tạo proxy package từ đầu).

Flow:
  1. Copy toàn bộ `proxy_source_dir` → `<decompiled>/smali/` (giữ structure).
  2. Inject `<service>` declaration vào AndroidManifest.xml (idempotent).
  3. Return count = (files copied) + (manifest injected 0|1).

Test contract (từ test_aidl_proxy_patcher.py):
  AIDLProxyPatcher(decompiled_path, proxy_source_dir=..., log_callback=...)
    .patch() -> int
"""
from __future__ import annotations

import logging
import os
import shutil

logger = logging.getLogger(__name__)

PROXY_SERVICE_NAME = (
    "com.android.vending.billing.IInAppBillingServiceProxy"
)

# Service snippet — inject trước `</application>`.
# Chỉ chứa chuỗi "IInAppBillingServiceProxy" 1 lần (android:name).
_PROXY_SERVICE_SNIPPET = (
    '\n        <service '
    f'android:name="{PROXY_SERVICE_NAME}" '
    'android:exported="true">\n'
    '            <intent-filter>\n'
    '                <action android:name='
    '"com.android.vending.billing.InAppBillingService.BIND" />\n'
    '            </intent-filter>\n'
    '        </service>\n'
)


class AIDLProxyPatcher:
    """Copy proxy smali + inject service declaration vào manifest."""

    def __init__(
        self,
        decompiled_path: str,
        proxy_source_dir: str,
        log_callback=print,
        file_cache=None,
    ):
        self.decompiled_path = decompiled_path
        self.proxy_source_dir = proxy_source_dir or ""
        self.log = log_callback
        self.file_cache = file_cache

    # ============================================================
    # MAIN
    # ============================================================
    def patch(self) -> int:
        """
        Return: number of files copied + 1 if manifest was updated else 0.
        Never raises — all errors logged + swallowed.
        """
        count = 0
        try:
            count += self._copy_proxy_source()
        except Exception as e:
            logger.warning("AIDL copy failed: %s", e)

        try:
            count += self._inject_manifest_service()
        except Exception as e:
            logger.warning("AIDL manifest inject failed: %s", e)

        return count

    # ============================================================
    # COPY PROXY SOURCE → smali/
    # ============================================================
    def _copy_proxy_source(self) -> int:
        if not self.proxy_source_dir:
            return 0
        if not os.path.isdir(self.proxy_source_dir):
            logger.debug(
                "Proxy source dir không tồn tại: %s",
                self.proxy_source_dir,
            )
            return 0

        target_root = os.path.join(self.decompiled_path, "smali")
        os.makedirs(target_root, exist_ok=True)

        copied = 0
        for root, _dirs, files in os.walk(self.proxy_source_dir):
            for fname in files:
                src = os.path.join(root, fname)
                rel = os.path.relpath(src, self.proxy_source_dir)
                dst = os.path.join(target_root, rel)
                try:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                    copied += 1
                except OSError as e:
                    logger.warning(
                        "Copy failed %s → %s: %s", src, dst, e,
                    )

        if copied:
            self.log(
                f"[*] [AIDLProxy] Copied {copied} smali files "
                f"từ {self.proxy_source_dir}"
            )
        return copied

    # ============================================================
    # INJECT MANIFEST
    # ============================================================
    def _inject_manifest_service(self) -> int:
        manifest = os.path.join(
            self.decompiled_path, "AndroidManifest.xml"
        )
        if not os.path.exists(manifest):
            logger.debug("Manifest không tồn tại: %s", manifest)
            return 0

        try:
            with open(manifest, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            logger.warning("Đọc manifest failed: %s", e)
            return 0

        # Idempotent — không inject nếu đã có
        if "IInAppBillingServiceProxy" in content:
            logger.debug("AIDL proxy đã inject sẵn — skip")
            return 0

        # Cần </application> để chèn trước nó
        if "</application>" not in content:
            logger.debug(
                "Manifest không có </application> — skip inject"
            )
            return 0

        new_content = content.replace(
            "</application>",
            _PROXY_SERVICE_SNIPPET + "    </application>",
            1,
        )

        try:
            with open(manifest, "w", encoding="utf-8") as f:
                f.write(new_content)
            self.log(
                "[*] [AIDLProxy] Injected <service> vào manifest"
            )
            return 1
        except OSError as e:
            logger.warning("Ghi manifest failed: %s", e)
            return 0