"""
Nhúng AIDL proxy service vào APK.

LP parity (v2):
  - Fix manifest permission sai (BIND_GET_INSTALL_PACKAGES không áp dụng).
  - Service dùng `com.chelpus.lackypatch` namespace? Không — service chạy
    trong app, chỉ redirect intent target. Service class giữ
    `com.android.vending.billing.IInAppBillingServiceProxy` để tránh
    check package name của app.
  - Idempotent: skip nếu service đã tồn tại.
  - Không copy nếu proxy source dir trống (graceful).
"""
from __future__ import annotations

import logging
import os
import shutil

logger = logging.getLogger(__name__)


# ---- Service declaration (FIX: bỏ permission sai) ----
SERVICE_DECL = """
        <service
            android:name="com.android.vending.billing.IInAppBillingServiceProxy"
            android:exported="true"
            android:enabled="true">
            <intent-filter>
                <action android:name="com.android.vending.billing.IInAppBillingService.BIND" />
            </intent-filter>
        </service>"""

# Marker để idempotent check
_SERVICE_MARKER = "IInAppBillingServiceProxy"


class AIDLProxyPatcher:
    def __init__(
        self,
        decompiled_path: str,
        proxy_source_dir: str | None = None,
        log_callback=print,
        file_cache=None,
    ):
        self.decompiled_path = decompiled_path
        self.log = log_callback
        self.file_cache = file_cache

        if proxy_source_dir is None:
            tools_dir = os.path.join(
                os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__)
                )),
                "tools",
            )
            proxy_source_dir = os.path.join(
                tools_dir, "proxy_service", "smali"
            )
        self.proxy_source = proxy_source_dir

    # ============================================================
    # SMALI TARGET
    # ============================================================
    def _find_smali_target(self) -> str:
        """Tìm smali dir đầu tiên (smali, smali_classes2, ...)."""
        for entry in sorted(os.listdir(self.decompiled_path)):
            full = os.path.join(self.decompiled_path, entry)
            if os.path.isdir(full) and entry.startswith("smali"):
                return full
        # Fallback: tạo smali mới
        target = os.path.join(self.decompiled_path, "smali")
        os.makedirs(target, exist_ok=True)
        return target

    def _copy_proxy_files(self) -> int:
        if not os.path.isdir(self.proxy_source):
            self.log(
                f"[i] [AIDLProxy] Proxy source trống: {self.proxy_source}"
            )
            return 0

        target = self._find_smali_target()
        count = 0
        for root, _dirs, files in os.walk(self.proxy_source):
            for f in files:
                src = os.path.join(root, f)
                rel = os.path.relpath(src, self.proxy_source)
                dest = os.path.join(target, rel)
                try:
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(src, dest)
                    count += 1
                except OSError as e:
                    logger.warning(
                        "Copy proxy file failed %s: %s", src, e
                    )
        return count

    # ============================================================
    # MANIFEST UPDATE
    # ============================================================
    def _read_manifest(self) -> str | None:
        manifest = os.path.join(
            self.decompiled_path, "AndroidManifest.xml"
        )
        try:
            if self.file_cache:
                return self.file_cache.read(manifest)
            with open(manifest, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None

    def _write_manifest(self, content: str) -> bool:
        manifest = os.path.join(
            self.decompiled_path, "AndroidManifest.xml"
        )
        try:
            if self.file_cache:
                self.file_cache.write(manifest, content)
            else:
                with open(manifest, "w", encoding="utf-8") as f:
                    f.write(content)
            return True
        except OSError as e:
            logger.warning("Write manifest failed: %s", e)
            return False

    def _update_manifest(self) -> bool:
        content = self._read_manifest()
        if content is None:
            return False

        # Idempotent check
        if _SERVICE_MARKER in content:
            self.log("[i] [AIDLProxy] Service đã tồn tại — skip")
            return False

        if "</application>" not in content:
            self.log("[!] [AIDLProxy] Manifest thiếu </application>")
            return False

        content = content.replace(
            "</application>",
            SERVICE_DECL + "\n    </application>",
        )
        return self._write_manifest(content)

    # ============================================================
    # PATCH
    # ============================================================
    def patch(self) -> int:
        self.log("[*] [AIDLProxy] Injecting proxy service...")
        copied = self._copy_proxy_files()
        if copied:
            self.log(f"[+] [AIDLProxy] Copied {copied} proxy smali files")

        injected = self._update_manifest()
        if injected:
            self.log("[+] [AIDLProxy] Service declaration added to manifest")
            return copied + 1

        return copied