"""
Vá bytecode Smali liên quan đến InApp Billing.
Hỗ trợ: Google Play Billing, Unity IAP, Unreal IAP, Facebook IAP.

Smart detection (3-tier):
  1. STRONG_IAP_METHODS — tên method không thể nhầm (launchBillingFlow, ...)
  2. Path hint            — path chứa billing/purchase/iap/store
  3. Class hint           — tên class chứa BillingHelper/IAPManager/...
  Blacklist: Analytics/Firebase/AdMob/... — bỏ qua trừ khi path cũng có billing
"""
from __future__ import annotations

import logging
import random
import re
import string

from core.smali_utils import (
    REGEX_IAP_BILLING_METHOD,
    get_all_smali_files,
)

logger = logging.getLogger(__name__)


# ============================================================
# TARGET METHOD NAMES — match lower-case
# ============================================================
TARGET_METHODS = [
    # Google Play Billing direct
    "launchBillingFlow", "getBuyIntent", "queryPurchases", "querySkuDetails",
    "isBillingSupported", "consumePurchase", "getPurchases",
    # Unity IAP
    "UnityPurchasing", "InitiatePurchase", "PurchaseProduct",
    "ProcessPurchase", "ConfirmPurchase", "FinishTransaction",
    "OnPurchaseFailed", "OnPurchaseSucceeded",
    # Unity IAP extensions
    "PurchaseProductInternal", "InitiatePurchaseInternal",
    # Unreal IAP
    "InAppPurchase", "MakePurchase", "CompletePurchase",
    # Wrapper phổ biến
    "startPurchase", "buyProduct", "makePurchase", "doPayment",
    "requestPurchase", "processPurchase", "sendPurchase",
    "startPayment", "doBilling", "executePayment",
    # Callback (yếu — cần strong signal khác)
    "onPurchase", "onBuy", "onPayment", "onCheckout",
    "onBillingComplete", "onBillingSuccess", "onPurchaseSuccess",
    # Facebook IAP
    "PurchaseWithProduct", "PurchaseAndRetrieve",
    # Adjust wrapper
    "onTrackedPurchase",
]


# ============================================================
# STRONG signals — tên method không thể nhầm với ads/analytics
# Chỉ cần 1 method khớp → coi file là IAP, không cần path/class hint
# ============================================================
STRONG_IAP_METHODS_LOWER = frozenset({
    "launchbillingflow",
    "initiatepurchase", "purchaseproduct", "purchaseproductinternal",
    "initiatepurchaseinternal",
    "getbuyintent", "querypurchases", "queryskudetails",
    "isbillingsupported", "consumepurchase", "getpurchases",
    "inapppurchase", "makepurchase", "completepurchase",
    "startpurchase", "buyproduct",
    "purchasewithproduct", "purchaseandretrieve",
})


# Class names gợi ý là IAP wrapper
WRAPPER_CLASS_HINTS_LOWER = frozenset({
    "billinghelper", "billingmanager", "billingclient",
    "purchasemanager", "iapmanager", "iaphelper",
    "purchaseservice", "storemanager", "unitypurchasing",
    "istorelistener", "iextensionprovider",
    "billingprocessor", "inappbillingprocessor",
})


# Class names ưu tiên tránh patch sai
BLACKLIST_CLASS_HINTS_LOWER = frozenset({
    "analytics", "tracker", "admob", "appmeasurement",
    "firebase", "crashlytics", "adjusttracker",
})


class IAPDexPatcher:
    def __init__(self, decompiled_path: str, log_callback=print, file_cache=None):
        self.decompiled_path = decompiled_path
        self.log = log_callback
        self.file_cache = file_cache
        self.session_id = "".join(
            random.choices(string.ascii_lowercase, k=8)
        )

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

    # ============================================================
    # SMART DETECTION — 3-tier
    # ============================================================
    def _is_iap_class(self, filepath: str, content: str) -> bool:
        """
        Quyết định file có nên patch không.

        Logic:
          1. Nếu path chứa blacklist hint VÀ không có billing/purchase/iap/store
             → skip (tránh patch Analytics tracker)
          2. Nếu path chứa billing/purchase/iap/store → OK
          3. Nếu class name chứa wrapper hint → OK
          4. Nếu content chứa STRONG_IAP_METHODS → OK (fallback cho test/minified)
          5. Còn lại → skip
        """
        path_lower = filepath.lower()

        # Tier 0: blacklist guard
        has_blacklist = any(
            bl in path_lower for bl in BLACKLIST_CLASS_HINTS_LOWER
        )
        has_iap_path_hint = any(
            k in path_lower
            for k in ("billing", "purchase", "iap", "storemanager")
        )
        if has_blacklist and not has_iap_path_hint:
            return False

        # Tier 1: path hint
        if has_iap_path_hint:
            return True

        # Tier 2: class header hint
        header_match = re.search(r"\.class\s+[^\n]*\s(L\S+);", content)
        if header_match:
            class_name = header_match.group(1).lower()
            for hint in WRAPPER_CLASS_HINTS_LOWER:
                if hint in class_name:
                    return True

        # Tier 3: strong method hint (minified / obfuscated paths)
        content_lower = content.lower()
        for strong in STRONG_IAP_METHODS_LOWER:
            if strong in content_lower:
                return True

        return False

    # ============================================================
    # MAIN PATCH
    # ============================================================
    def patch(self) -> int:
        return self.patch_with_report()["total_patched"]

    def patch_with_report(self) -> dict:
        self.log("[*] [IAPDexPatcher] Starting smart silent patch...")
        report = {
            "patterns": {},
            "total_patched": 0,
            "skipped_files": 0,
            "scanned_files": 0,
        }
        patched_files = 0
        skipped = 0
        scanned = 0

        target_lower = [m.lower() for m in TARGET_METHODS]

        for filepath in get_all_smali_files(self.decompiled_path):
            if len(filepath) > 250:
                skipped += 1
                continue

            try:
                content = self._read(filepath)
            except (OSError, IOError):
                skipped += 1
                continue

            scanned += 1

            # Pre-filter: phải có target method
            if not any(m in content for m in TARGET_METHODS):
                continue

            # Smart class filter
            if not self._is_iap_class(filepath, content):
                continue

            original = content
            for match in REGEX_IAP_BILLING_METHOD.finditer(content):
                full = match.group(0)
                method_sig = match.group(1)
                return_type = match.group(2)

                # Match theo lower-case
                if not any(
                    m in method_sig.lower() for m in target_lower
                ):
                    continue

                if return_type == "V":
                    replacement = self._void_method(
                        full.split("\n")[0]
                    )
                else:
                    replacement = self._bundle_method(
                        full.split("\n")[0]
                    )

                content = content.replace(full, replacement)
                report["patterns"][method_sig] = True

            if content != original:
                try:
                    self._write(filepath, content)
                    patched_files += 1
                    short = filepath.split("/")[-1].split(chr(92))[-1]
                    self.log(f"[+] [IAPDexPatcher] {short}")
                except (OSError, IOError):
                    skipped += 1

        report["total_patched"] = patched_files
        report["skipped_files"] = skipped
        report["scanned_files"] = scanned
        self.log(
            f"[*] [IAPDexPatcher] Patched: {patched_files}, "
            f"scanned: {scanned}, skipped: {skipped}"
        )
        return report

    # ============================================================
    # REPLACEMENT BUILDERS
    # ============================================================
    def _void_method(self, header: str) -> str:
        """Void method → no-op return."""
        return (
            f"{header}\n"
            "    .locals 0\n"
            "    return-void\n"
            ".end method"
        )

    def _bundle_method(self, header: str) -> str:
        """
        Bundle-returning method → trả về Bundle có RESPONSE_CODE=0
        và INAPP_PURCHASE_DATA_LIST rỗng (đúng format Google Play Billing).
        """
        return (
            f"{header}\n"
            "    .locals 3\n"
            "    new-instance v0, Landroid/os/Bundle;\n"
            "    invoke-direct {v0}, Landroid/os/Bundle;-><init>()V\n"
            '    const-string v1, "RESPONSE_CODE"\n'
            "    const/4 v2, 0x0\n"
            "    invoke-virtual {v0, v1, v2}, "
            "Landroid/os/Bundle;->putInt(Ljava/lang/String;I)V\n"
            '    const-string v1, "INAPP_PURCHASE_DATA_LIST"\n'
            "    invoke-virtual {v0, v1, v2}, "
            "Landroid/os/Bundle;->putInt(Ljava/lang/String;I)V\n"
            "    return-object v0\n"
            ".end method"
        )