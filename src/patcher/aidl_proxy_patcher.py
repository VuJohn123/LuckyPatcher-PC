"""Nhúng AIDL proxy service vào APK."""
from __future__ import annotations

import logging
import os
import shutil

logger = logging.getLogger(__name__)

SERVICE_DECL = """
        <service android:name="com.android.vending.billing.IInAppBillingServiceProxy"
                 android:exported="true"
                 android:permission="android.permission.BIND_GET_INSTALL_PACKAGES">
            <intent-filter>
                <action android:name="com.android.vending.billing.IInAppBillingService.BIND" />
            </intent-filter>
        </service>"""


class AIDLProxyPatcher:
    def __init__(self, decompiled_path: str, proxy_source_dir: str | None = None,
                 log_callback=print, file_cache=None):
        self.decompiled_path = decompiled_path
        self.log = log_callback
        self.file_cache = file_cache
        if proxy_source_dir is None:
            tools_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "tools",
            )
            proxy_source_dir = os.path.join(tools_dir, "proxy_service", "smali")
        self.proxy_source = proxy_source_dir

    def _find_smali_target(self) -> str:
        for entry in os.listdir(self.decompiled_path):
            full = os.path.join(self.decompiled_path, entry)
            if os.path.isdir(full) and entry.startswith("smali"):
                return full
        target = os.path.join(self.decompiled_path, "smali")
        os.makedirs(target, exist_ok=True)
        return target

    def _copy_proxy_files(self) -> int:
        if not os.path.isdir(self.proxy_source):
            self.log(f"[!] Proxy source không tồn tại: {self.proxy_source}")
            return 0

        target = self._find_smali_target()
        count = 0
        for root, _, files in os.walk(self.proxy_source):
            for f in files:
                src = os.path.join(root, f)
                rel = os.path.relpath(src, self.proxy_source)
                dest = os.path.join(target, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src, dest)
                count += 1
        return count

    def _update_manifest(self) -> bool:
        manifest = os.path.join(self.decompiled_path, "AndroidManifest.xml")
        try:
            if self.file_cache:
                content = self.file_cache.read(manifest)
            else:
                with open(manifest, "r", encoding="utf-8") as f:
                    content = f.read()
        except OSError:
            return False

        if "IInAppBillingServiceProxy" in content:
            return False
        if "</application>" not in content:
            return False

        content = content.replace(
            "</application>",
            SERVICE_DECL + "\n</application>",
        )
        try:
            if self.file_cache:
                self.file_cache.write(manifest, content)
            else:
                with open(manifest, "w", encoding="utf-8") as f:
                    f.write(content)
            return True
        except OSError:
            return False

    def patch(self) -> int:
        self.log("[*] [AIDLProxy] Injecting proxy service...")
        copied = self._copy_proxy_files()
        self.log(f"[+] Copied {copied} proxy smali files")
        if self._update_manifest():
            self.log("[+] Service declaration added to manifest")
            return copied + 1
        return copied