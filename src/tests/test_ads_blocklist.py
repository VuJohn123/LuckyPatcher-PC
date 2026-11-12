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


def test_remove_ad_urls_multiple_domains_single_pass():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            '.class public LA;\n'
            '    const-string v0, "https://googlesyndication.com/a"\n'
            '    const-string v1, "https://applovin.com/b"\n'
            '    const-string v2, "https://example.com/keep"\n'
        ))
        patcher = AdsBlocklistPatcher(tmp)
        assert patcher.remove_ad_urls_from_smali() == 1
        with open(smali) as f:
            content = f.read()
        assert "googlesyndication.com" not in content
        assert "applovin.com" not in content
        assert '"https://example.com/keep"' in content
        assert content.count('"http://127.0.0.1"') == 2


def test_remove_ad_strings_exact_literals():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            '.class public LA;\n'
            '    const-string v0, "doubleclick.net"\n'
            '    const-string v1, "example.com"\n'
        ))
        patcher = AdsBlocklistPatcher(tmp)
        assert patcher.remove_ad_strings() == 1
        with open(smali) as f:
            content = f.read()
        assert '"doubleclick.net"' not in content
        assert '"example.com"' in content


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
