"""Test IAP smali patcher — không cần thật sự chạy billing."""
import os
import tempfile

from patcher.iap_smali_patcher import IAPSmaliPatcher


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_patch_redirects_intent_action():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            '.class public LA;\n'
            '.method public static x()V\n'
            '    const-string v0, "com.android.vending.billing.InAppBillingService.BIND"\n'
            '.end method\n'
        ))
        patcher = IAPSmaliPatcher(tmp)
        patcher.patch_billing_calls()
        with open(smali) as f:
            content = f.read()
        assert ".PROXY" in content


def test_no_patch_when_no_billing():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, ".class public LA;\n")
        patcher = IAPSmaliPatcher(tmp)
        assert patcher.patch_billing_calls() == 0