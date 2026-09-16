"""Test ads blocklist patcher."""
import os
import tempfile

from patcher.ads_blocklist import AdsBlocklistPatcher


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def test_remove_ad_urls():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            '.class public LA;\n'
            '    const-string v0, "https://googleads.g.doubleclick.net/x"\n'
        ))
        patcher = AdsBlocklistPatcher(tmp)
        count = patcher.remove_ad_urls_from_smali()
        assert count >= 1
        with open(smali) as f:
            assert "doubleclick.net" not in f.read()


def test_make_ads_offline():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            '.class public LA;\n'
            '.method public static isOnline()Z\n'
            '    .locals 1\n'
            '    const/4 v0, 0x1\n'
            '    return v0\n'
            '.end method\n'
        ))
        patcher = AdsBlocklistPatcher(tmp)
        count = patcher.make_ads_offline()
        assert count == 1