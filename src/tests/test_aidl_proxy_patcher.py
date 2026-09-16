"""Test AIDL proxy injection."""
import os
import tempfile

from patcher.aidl_proxy_patcher import AIDLProxyPatcher


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_patch_no_source_does_not_crash():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "smali"))
        manifest = os.path.join(tmp, "AndroidManifest.xml")
        _write(manifest, "<manifest><application></application></manifest>")
        patcher = AIDLProxyPatcher(
            tmp, proxy_source_dir="/nonexistent",
            log_callback=lambda *_: None,
        )
        patcher.patch()  # không crash


def test_patch_injects_manifest():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "smali"))
        manifest = os.path.join(tmp, "AndroidManifest.xml")
        _write(manifest, "<manifest><application></application></manifest>")
        patcher = AIDLProxyPatcher(
            tmp, proxy_source_dir="/nonexistent",
            log_callback=lambda *_: None,
        )
        patcher.patch()
        with open(manifest) as f:
            content = f.read()
        assert "IInAppBillingServiceProxy" in content


def test_patch_with_proxy_source():
    with tempfile.TemporaryDirectory() as tmp:
        # Tạo proxy source
        proxy_src = os.path.join(tmp, "_proxy_src")
        proxy_smali = os.path.join(
            proxy_src, "com", "android", "vending", "billing"
        )
        os.makedirs(proxy_smali)
        with open(os.path.join(proxy_smali, "Proxy.smali"), "w") as f:
            f.write(".class public LProxy;\n")

        # Tạo decompiled
        decomp = os.path.join(tmp, "decompiled")
        os.makedirs(os.path.join(decomp, "smali"))
        _write(
            os.path.join(decomp, "AndroidManifest.xml"),
            "<manifest><application></application></manifest>",
        )

        patcher = AIDLProxyPatcher(
            decomp, proxy_source_dir=proxy_src,
            log_callback=lambda *_: None,
        )
        count = patcher.patch()
        assert count >= 1
        # Proxy file được copy
        copied = os.path.join(
            decomp, "smali", "com", "android", "vending", "billing",
            "Proxy.smali",
        )
        assert os.path.exists(copied)


def test_patch_already_injected():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "smali"))
        manifest = os.path.join(tmp, "AndroidManifest.xml")
        _write(
            manifest,
            "<manifest><application>"
            '<service android:name="com.android.vending.billing.'
            'IInAppBillingServiceProxy" />'
            "</application></manifest>",
        )
        patcher = AIDLProxyPatcher(
            tmp, proxy_source_dir="/nonexistent",
            log_callback=lambda *_: None,
        )
        patcher.patch()
        with open(manifest) as f:
            content = f.read()
        # Chỉ 1 lần khai báo
        assert content.count("IInAppBillingServiceProxy") == 1


def test_patch_manifest_missing_app_tag():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "smali"))
        manifest = os.path.join(tmp, "AndroidManifest.xml")
        _write(manifest, "<manifest></manifest>")
        patcher = AIDLProxyPatcher(
            tmp, proxy_source_dir="/nonexistent",
            log_callback=lambda *_: None,
        )
        # Không có </application> → không inject, không crash
        patcher.patch()