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


class _MemoryCache:
    def __init__(self, root):
        self.root = root
        self.written = {}

    def read(self, path):
        if path in self.written:
            return self.written[path]
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()

    def write(self, path, content):
        self.written[path] = content


def test_accepts_file_cache_and_writes_through_it():
    """Regression: proxy mode passes file_cache=... to this constructor."""
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            '.class public LA;\n'
            '.method public static x()V\n'
            '    const-string v0, "com.android.vending.billing.InAppBillingService.BIND"\n'
            '.end method\n'
        ))
        cache = _MemoryCache(tmp)
        patcher = IAPSmaliPatcher(tmp, file_cache=cache)
        patcher.patch_billing_calls()
        assert any(".PROXY" in c for c in cache.written.values())
        with open(smali, encoding="utf-8") as f:
            assert ".PROXY" not in f.read()


def test_no_patch_when_no_billing():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, ".class public LA;\n")
        patcher = IAPSmaliPatcher(tmp)
        assert patcher.patch_billing_calls() == 0
