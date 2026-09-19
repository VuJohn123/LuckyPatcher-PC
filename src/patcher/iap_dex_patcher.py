"""
Vá bytecode Smali liên quan đến InApp Billing.
Hỗ trợ: Google Play Billing (v1-v7), Unity IAP, Unreal IAP, Facebook IAP,
        Amazon IAP, Samsung IAP, Huawei IAP.

v3 (2026):
  - Mở rộng TARGET_METHODS: +50 method patterns.
  - Strong hints mở rộng cho obfuscated paths.
  - Class hints thêm billing library v6-v7.
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
    # === Google Play Billing v1-v3 ===
    "launchBillingFlow", "getBuyIntent", "getBuyIntentToReplaceSkus",
    "queryPurchases", "querySkuDetails", "queryInventory",
    "isBillingSupported", "consumePurchase", "getPurchases",
    "getSkuDetails", "consumeAsync",
    # === Google Play Billing v4-v5 ===
    "queryProductDetails", "queryProductDetailsAsync",
    "acknowledgePurchase", "acknowledgePurchaseAsync",
    "launchPriceConfirmationFlow",
    # === Google Play Billing v6-v7 ===
    "setObfuscatedAccountId", "setObfuscatedProfileId",
    "enablePendingPurchases", "startConnection",
    "endConnection",
    # === Unity IAP ===
    "UnityPurchasing", "InitiatePurchase", "PurchaseProduct",
    "ProcessPurchase", "ConfirmPurchase", "FinishTransaction",
    "OnPurchaseFailed", "OnPurchaseSucceeded",
    "PurchaseProductInternal", "InitiatePurchaseInternal",
    "FetchAdditionalProducts", "CrossPlatformValidator",
    # === Unity IAP extensions ===
    "IRegisterListener", "IDetailedStoreListener",
    # === Unreal IAP ===
    "InAppPurchase", "MakePurchase", "CompletePurchase",
    "QueryOwnedProducts", "QueryProductInfo",
    # === Wrapper phổ biến ===
    "startPurchase", "buyProduct", "makePurchase", "doPayment",
    "requestPurchase", "processPurchase", "sendPurchase",
    "startPayment", "doBilling", "executePayment",
    "buyItem", "purchaseItem", "acquireItem", "unlockItem",
    "purchaseCoins", "buyCoins", "buyGems", "buyPremium",
    "upgradeToPro", "unlockFullVersion", "buyFullVersion",
    # === Callback ===
    "onPurchase", "onBuy", "onPayment", "onCheckout",
    "onBillingComplete", "onBillingSuccess", "onPurchaseSuccess",
    "onPurchaseError", "onBillingError",
    "onActivityResult",     # billing v1-v3 callback
    "onServiceConnected",   # billing v1-v3 bind
    "onProductDetailsResponse", "onPurchasesUpdated",
    "onBillingSetupFinished", "onBillingServiceDisconnected",
    # === Local validation ===
    "verifyPurchase", "verifySignature", "verifyReceipt",
    "verifySku", "validatePurchase",
    "checkPurchase", "checkReceipt",
    # === Facebook IAP ===
    "PurchaseWithProduct", "PurchaseAndRetrieve",
    # === Adjust wrapper ===
    "onTrackedPurchase",
    # === Store-specific ===
    "samsungPurchase", "amazonPurchase", "huaweiPurchase",
    "yandexPurchase",
]


STRONG_IAP_METHODS_LOWER = frozenset({
    "launchbillingflow",
    "initiatepurchase", "purchaseproduct", "purchaseproductinternal",
    "initiatepurchaseinternal",
    "getbuyintent", "querypurchases", "queryskudetails",
    "queryproductdetails", "queryproductdetailsasync",
    "isbillingsupported", "consumepurchase", "consumeasync",
    "getpurchases", "getskudetails",
    "inapppurchase", "makepurchase", "completepurchase",
    "startpurchase", "buyproduct",
    "purchasewithproduct", "purchaseandretrieve",
    "acknowledgepurchase", "acknowledgepurchaseasync",
    "onpurchasesupdated", "onbillingsetupfinished",
    "onproductdetailsresponse",
    "buyitem", "purchaseitem", "acquireitem", "unlockitem",
    "purchasecoins", "buycoins", "buygems",
    "upgradetopro", "unlockfullversion", "buyfullversion",
})


WRAPPER_CLASS_HINTS_LOWER = frozenset({
    "billinghelper", "billingmanager", "billingclient",
    "purchasemanager", "iapmanager", "iaphelper",
    "purchaseservice", "storemanager", "unitypurchasing",
    "istorelistener", "iextensionprovider",
    "billingprocessor", "inappbillingprocessor",
    "playbilling", "googleplaybilling",
    "iabhelper", "iappurchasemanager",
    "storekit", "storefront",
    "paymentmanager", "paymenthelper",
})


BLACKLIST_CLASS_HINTS_LOWER = frozenset({
    "analytics", "tracker", "admob", "appmeasurement",
    "firebase", "crashlytics", "adjusttracker",
    "facebookads", "appsflyer", "segment",
})


class IAPDexPatcher:
    def __init__(self, decompiled_path: str, log_callback=print,
                 file_cache=None):
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

    def _is_iap_class(self, filepath: str, content: str) -> bool:
        path_lower = filepath.lower()

        has_blacklist = any(
            bl in path_lower for bl in BLACKLIST_CLASS_HINTS_LOWER
        )
        has_iap_path_hint = any(
            k in path_lower
            for k in ("billing", "purchase", "iap", "storemanager",
                      "payment", "store")
        )
        if has_blacklist and not has_iap_path_hint:
            return False

        if has_iap_path_hint:
            return True

        header_match = re.search(r"\.class\s+[^\n]*\s(L\S+);", content)
        if header_match:
            class_name = header_match.group(1).lower()
            for hint in WRAPPER_CLASS_HINTS_LOWER:
                if hint in class_name:
                    return True

        content_lower = content.lower()
        for strong in STRONG_IAP_METHODS_LOWER:
            if strong in content_lower:
                return True

        return False

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

            if not any(m in content for m in TARGET_METHODS):
                continue

            if not self._is_iap_class(filepath, content):
                continue

            original = content
            for match in REGEX_IAP_BILLING_METHOD.finditer(content):
                full = match.group(0)
                method_sig = match.group(1)
                return_type = match.group(2)

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

    def _void_method(self, header: str) -> str:
        return (
            f"{header}\n"
            "    .locals 0\n"
            "    return-void\n"
            ".end method"
        )

    def _bundle_method(self, header: str) -> str:
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