"""
Vá trực tiếp bytecode Smali liên quan đến InApp Billing.
Hỗ trợ Google Play Billing, Unity IAP, Unreal IAP.
"""
from __future__ import annotations

import logging
import re
import random
import string

from core.smali_utils import (
    REGEX_IAP_BILLING_METHOD,
    get_all_smali_files,
)

logger = logging.getLogger(__name__)

TARGET_METHODS = [
    # Google Play Billing
    "launchBillingFlow", "getBuyIntent", "queryPurchases", "querySkuDetails",
    "isBillingSupported", "consumePurchase", "getPurchases",
    # Unity IAP
    "UnityPurchasing", "InitiatePurchase", "PurchaseProduct",
    "ProcessPurchase", "ConfirmPurchase", "FinishTransaction",
    # Unreal IAP
    "InAppPurchase", "MakePurchase", "CompletePurchase",
    # Wrapper phổ biến
    "startPurchase", "buyProduct", "makePurchase", "doPayment",
    "requestPurchase", "processPurchase", "sendPurchase",
    "startPayment", "doBilling", "executePayment",
    "onPurchase", "onBuy", "onPayment", "onCheckout",
]


class IAPDexPatcher:
    def __init__(self, decompiled_path: str, log_callback=print, file_cache=None):
        self.decompiled_path = decompiled_path
        self.log = log_callback
        self.file_cache = file_cache
        self.session_id = "".join(random.choices(string.ascii_lowercase, k=8))

    def _read(self, path: str) -> str:
        if self.file_cache:
            return self.file_cache.read(path)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _write(self, path: str, content: str) -> None:
        if self.file_cache:
            self.file_cache.write(path, content)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

    def patch(self) -> int:
        return self.patch_with_report()["total_patched"]

    def patch_with_report(self) -> dict:
        self.log("[*] [IAPDexPatcher] Starting smart silent patch...")
        report = {"patterns": {}, "total_patched": 0}
        patched_files = 0
        skipped = 0

        for filepath in get_all_smali_files(self.decompiled_path):
            if len(filepath) > 250:
                skipped += 1
                continue

            try:
                content = self._read(filepath)
            except (OSError, IOError):
                skipped += 1
                continue

            # Pre-filter
            if not any(m in content for m in TARGET_METHODS):
                continue

            original = content
            for match in REGEX_IAP_BILLING_METHOD.finditer(content):
                full = match.group(0)
                method_sig = match.group(1)
                return_type = match.group(2)

                if not any(m.lower() in method_sig.lower() for m in TARGET_METHODS):
                    continue

                if return_type == "V":
                    replacement = self._void_method(full.split("\n")[0])
                else:
                    replacement = self._bundle_method(full.split("\n")[0])

                content = content.replace(full, replacement)
                report["patterns"][method_sig] = True

            if content != original:
                try:
                    self._write(filepath, content)
                    patched_files += 1
                    self.log(f"[+] [IAPDexPatcher] {filepath.split('/')[-1].split(chr(92))[-1]}")
                except (OSError, IOError):
                    skipped += 1

        report["total_patched"] = patched_files
        self.log(f"[*] [IAPDexPatcher] Patched: {patched_files}, skipped: {skipped}")
        return report

    def _void_method(self, header: str) -> str:
        v = f"v{random.randint(1, 15)}"
        lbl = f":cond_{self.session_id[:4]}"
        return (
            f"{header}\n"
            "    .locals 1\n"
            f"    const/4 {v}, 0x0\n"
            f"    if-eqz {v}, {lbl}\n"
            f"    {lbl}\n"
            "    return-void\n"
            ".end method"
        )

    def _bundle_method(self, header: str) -> str:
        v_resp = f"v{random.randint(0, 9)}"
        v_key = f"v{random.randint(0, 9)}"
        v_val = f"v{random.randint(0, 9)}"
        lbl = f":skip_{self.session_id[:6]}"
        return (
            f"{header}\n"
            "    .locals 3\n"
            f"    new-instance {v_resp}, Landroid/os/Bundle;\n"
            f"    invoke-direct {{{v_resp}}}, Landroid/os/Bundle;-><init>()V\n"
            f'    const-string {v_key}, "RESPONSE_CODE"\n'
            f"    const/4 {v_val}, 0x0\n"
            f"    invoke-virtual {{{v_resp}, {v_key}, {v_val}}}, "
            f"Landroid/os/Bundle;->putInt(Ljava/lang/String;I)V\n"
            f"    goto {lbl}\n"
            f"    {lbl}\n"
            f"    return-object {v_resp}\n"
            ".end method"
        )