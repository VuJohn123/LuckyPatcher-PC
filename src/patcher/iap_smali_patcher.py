"""
Chuyển hướng Intent billing sang proxy package.

v5 (2026):
  - Mở rộng target actions: Google v3, Amazon, Samsung, Huawei, Yandex.
  - Thêm path_hints cho store-specific SDKs.
  - Bypass FileContentCache khi ĐỌC (perf).
"""
from __future__ import annotations

import logging
import os
import re

from core.progress import Progress
from core.smali_utils import get_all_smali_files

logger = logging.getLogger(__name__)

# Billing actions để redirect
TARGET_ACTIONS = [
    "com.android.vending.billing.InAppBillingService.BIND",
    "com.android.vending.billing.InAppBillingService.LOCK",
    "com.android.vending.billing.InAppBillingService.LUCK",
    "com.amazon.device.iap.billingclient.api.Billing.AIDL",
    "com.sec.android.iap.service.iapService",
    "com.huawei.hms.iap.IAP",
]

TARGET_PACKAGES = [
    "com.android.vending",
    "com.amazon.venezia",
    "com.sec.android.iap",
    "com.huawei.hms",
    "com.yandex.store",
]

# LP parity — proxy package
PROXY_PACKAGE = "com.chelpus.lackypatch"

_PATH_HINTS = (
    "billing", "vending", "inappbilling", "iinappbilling",
    "billingclient", "purchase", "iap", "store", "payment",
    "amazon", "venezia", "samsung", "huawei", "yandex",
)

_FULL_SCAN = os.environ.get("LP_IAP_FULL_SCAN", "").strip().lower() in (
    "1", "true", "yes", "on"
)
_SKIP_PATH_LEN = 250


def _path_might_contain_billing(filepath: str) -> bool:
    fp = filepath.replace("\\", "/").lower()
    return any(h in fp for h in _PATH_HINTS)


# Precompile regex cho từng action + package
_ACTION_RES = [
    re.compile(r'const-string\s+(\S+),\s*"' + re.escape(a) + r'"')
    for a in TARGET_ACTIONS
]
_PKG_CONST_RES = [
    re.compile(r'const-string\s+(\S+),\s*"' + re.escape(p) + r'"')
    for p in TARGET_PACKAGES
]
_SETPKG_RES = [
    re.compile(
        r'(invoke-virtual\s+\{.*?\},\s+'
        r'Landroid/content/Intent;->setPackage\()"'
        + re.escape(p) + r'"'
    )
    for p in TARGET_PACKAGES
]


class IAPSmaliPatcher:
    def __init__(self, decompiled_path: str, log_callback=print):
        self.decompiled_path = decompiled_path
        self.log = log_callback
        self._cache = self._try_get_cache()

    def _try_get_cache(self):
        try:
            from core.pipeline_executor import get_file_cache
            return get_file_cache()
        except Exception:
            return None

    def _read_direct(self, filepath: str) -> str:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _write_file(self, filepath: str, content: str) -> None:
        if self._cache is not None:
            try:
                self._cache.write(filepath, content)
                return
            except Exception:
                pass
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    def _patch_files(self, files: list[str], label: str) -> tuple[int, int]:
        patched = 0
        matched = 0
        prog = Progress(
            len(files), label=f"IAPSmali/{label}",
            log_callback=self.log, step_pct=10,
        )
        for filepath in files:
            if len(filepath) > _SKIP_PATH_LEN:
                prog.update()
                continue
            try:
                content = self._read_direct(filepath)
            except OSError:
                prog.update()
                continue

            if not any(a in content for a in TARGET_ACTIONS) \
               and not any(p in content for p in TARGET_PACKAGES):
                prog.update()
                continue

            matched += 1
            original = content

            for action_re, action in zip(_ACTION_RES, TARGET_ACTIONS):
                content = action_re.sub(
                    rf'const-string \1, "{action}.PROXY"', content,
                )
            for pkg_re in _PKG_CONST_RES:
                content = pkg_re.sub(
                    rf'const-string \1, "{PROXY_PACKAGE}"', content,
                )
            for setpkg_re in _SETPKG_RES:
                content = setpkg_re.sub(
                    rf'\1"{PROXY_PACKAGE}"', content,
                )

            if content != original:
                try:
                    self._write_file(filepath, content)
                    patched += 1
                except OSError as e:
                    logger.warning("write failed %s: %s", filepath, e)
            prog.update()
        prog.close()
        self.log(
            f"[*] [IAPSmaliPatcher] ({label}) "
            f"scanned={len(files)} matched={matched} patched={patched}"
        )
        return patched, len(files)

    def patch_billing_calls(
        self,
        proxy_host: str = "localhost",
        proxy_port: int = 8888,
    ) -> int:
        self.log(
            f"[*] [IAPSmaliPatcher] Starting "
            f"(proxy={PROXY_PACKAGE})"
        )
        all_files = list(get_all_smali_files(self.decompiled_path))
        total = len(all_files)

        if _FULL_SCAN:
            self.log(f"[*] [IAPSmaliPatcher] FULL scan ({total} files)")
            patched, _ = self._patch_files(all_files, "FULL")
            self.log(f"[✔] [IAPSmaliPatcher] Patched {patched} files")
            return patched

        candidates = [f for f in all_files if _path_might_contain_billing(f)]
        self.log(
            f"[*] [IAPSmaliPatcher] PREFILTER "
            f"({len(candidates)}/{total})"
        )
        patched, _ = self._patch_files(candidates, "PREFILTER")

        if patched == 0 and len(candidates) < total:
            remaining = [
                f for f in all_files
                if f not in set(candidates)
            ]
            self.log(
                f"[i] [IAPSmaliPatcher] PREFILTER 0 → "
                f"FULL fallback on {len(remaining)} remaining files"
            )
            patched2, _ = self._patch_files(remaining, "FULL-FALLBACK")
            patched += patched2

        self.log(f"[✔] [IAPSmaliPatcher] Patched {patched} files")
        return patched

    def patch(self) -> int:
        return self.patch_billing_calls()