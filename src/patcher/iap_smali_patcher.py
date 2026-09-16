"""
Chuyển hướng Intent billing sang proxy package.
"""
from __future__ import annotations

import logging
import os
import re

from core.smali_utils import get_all_smali_files

logger = logging.getLogger(__name__)

TARGET_ACTION = "com.android.vending.billing.InAppBillingService.BIND"
TARGET_PACKAGE = "com.android.vending"
PROXY_PACKAGE = "com.android.vending.billing"


class IAPSmaliPatcher:
    def __init__(self, decompiled_path: str, log_callback=print):
        self.decompiled_path = decompiled_path
        self.log = log_callback

    def patch_billing_calls(self, proxy_host: str = "localhost",
                            proxy_port: int = 8888) -> int:
        self.log("[*] [IAPSmaliPatcher] Redirecting billing intents...")
        patched = 0

        # Regex thay thế
        action_re = re.compile(
            r'const-string\s+(\S+),\s*"' + re.escape(TARGET_ACTION) + r'"'
        )
        pkg_const_re = re.compile(
            r'const-string\s+(\S+),\s*"' + re.escape(TARGET_PACKAGE) + r'"'
        )
        setpkg_re = re.compile(
            r'(invoke-virtual\s+\{.*?\},\s+'
            r'Landroid/content/Intent;->setPackage\()"'
            + re.escape(TARGET_PACKAGE) + r'"'
        )

        for filepath in get_all_smali_files(self.decompiled_path):
            if len(filepath) > 250:
                continue
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except OSError:
                continue

            if TARGET_ACTION not in content and TARGET_PACKAGE not in content:
                continue

            original = content

            # 1. Đổi intent action
            content = action_re.sub(
                rf'const-string \1, "{TARGET_ACTION}.PROXY"',
                content,
            )
            # 2. Đổi const-string package
            content = pkg_const_re.sub(
                rf'const-string \1, "{PROXY_PACKAGE}"',
                content,
            )
            # 3. Đổi setPackage
            content = setpkg_re.sub(
                rf'\1"{PROXY_PACKAGE}"',
                content,
            )

            if content != original:
                try:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                    patched += 1
                except OSError as e:
                    logger.warning("write failed %s: %s", filepath, e)

        self.log(f"[*] [IAPSmaliPatcher] Patched {patched} files")
        return patched

    def patch(self) -> int:
        return self.patch_billing_calls()