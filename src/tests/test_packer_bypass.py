"""Test patcher/packer_bypass.py — act on BypassStrategy."""
from __future__ import annotations

import os

from patcher.packer_bypass import PackerBypassPatcher

# ============================================================
# Helpers
# ============================================================
_MANIFEST_SHELL = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.app">
    <application
        android:name="com.pairip.application.Application"
        android:label="Test">
        <activity android:name=".MainActivity" />
    </application>
</manifest>
"""

_MANIFEST_NO_NAME = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.app">
    <application android:label="Test">
        <activity android:name=".MainActivity" />
    </application>
</manifest>
"""

_SHELL_SMALI = """.class public Lcom/pairip/application/Application;
.super Landroid/app/Application;


# direct methods
.method public constructor <init>()V
    .locals 0

    invoke-direct {p0}, Landroid/app/Application;-><init>()V

    return-void
.end method

.method public onCreate()V
    .locals 3

    invoke-super {p0}, Landroid/app/Application;->onCreate()V

    const-string v0, "pairip"
    invoke-static {v0}, Lcom/pairip/VMRunner;->invoke(Ljava/lang/String;)V

    return-void
.end method
"""

_REAL_APP_SMALI = """.class public Lcom/example/app/RealApp;
.super Landroid/app/Application;


.method public onCreate()V
    .locals 0

    invoke-super {p0}, Landroid/app/Application;->onCreate()V

    return-void
.end method
"""


def _build_tree(tmp_path, manifest: str, smali: dict[str, str] | None = None):
    root = tmp_path / "decoded"
    root.mkdir()
    (root / "AndroidManifest.xml").write_text(manifest, encoding="utf-8")
    smali_root = root / "smali"
    smali_root.mkdir()
    for rel, content in (smali or {}).items():
        path = smali_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return str(root)


def _read(root: str, rel: str) -> str:
    with open(os.path.join(root, *rel.split("/")), encoding="utf-8") as f:
        return f.read()


# ============================================================
# Strategy dispatch
# ============================================================
class TestStrategyDispatch:
    def test_dex_plaintext_is_noop(self, tmp_path):
        root = _build_tree(tmp_path, _MANIFEST_SHELL)
        p = PackerBypassPatcher(root, strategy="dex_plaintext")
        assert p.patch() == 0

    def test_unpack_required_is_noop(self, tmp_path):
        root = _build_tree(tmp_path, _MANIFEST_SHELL)
        p = PackerBypassPatcher(root, strategy="unpack_required")
        assert p.patch() == 0
        assert _read(root, "AndroidManifest.xml") == _MANIFEST_SHELL

    def test_unknown_strategy_noop(self, tmp_path):
        root = _build_tree(tmp_path, _MANIFEST_SHELL)
        p = PackerBypassPatcher(root, strategy="does_not_exist")
        assert p.patch() == 0


# ============================================================
# SHELL_SWAP
# ============================================================
class TestShellSwap:
    def test_repoints_manifest_at_real_app(self, tmp_path):
        root = _build_tree(
            tmp_path,
            _MANIFEST_SHELL,
            {
                "com/pairip/application/Application.smali": _SHELL_SMALI,
                "com/example/app/RealApp.smali": _REAL_APP_SMALI,
            },
        )
        p = PackerBypassPatcher(root, strategy="shell_swap")
        assert p.patch() == 1
        manifest = _read(root, "AndroidManifest.xml")
        assert 'android:name="com.example.app.RealApp"' in manifest
        assert "com.pairip.application.Application" not in manifest

    def test_explicit_real_application(self, tmp_path):
        root = _build_tree(
            tmp_path,
            _MANIFEST_SHELL,
            {"com/pairip/application/Application.smali": _SHELL_SMALI},
        )
        p = PackerBypassPatcher(
            root, strategy="shell_swap",
            real_application="com.example.app.CustomApp",
        )
        assert p.patch() == 1
        manifest = _read(root, "AndroidManifest.xml")
        assert 'android:name="com.example.app.CustomApp"' in manifest

    def test_injects_name_when_application_has_none(self, tmp_path):
        root = _build_tree(
            tmp_path,
            _MANIFEST_NO_NAME,
            {"com/example/app/RealApp.smali": _REAL_APP_SMALI},
        )
        p = PackerBypassPatcher(
            root, strategy="shell_swap",
            real_application="com.example.app.RealApp",
        )
        assert p.patch() == 1
        manifest = _read(root, "AndroidManifest.xml")
        assert 'android:name="com.example.app.RealApp"' in manifest

    def test_no_real_app_falls_back_to_neutralize(self, tmp_path):
        root = _build_tree(
            tmp_path,
            _MANIFEST_SHELL,
            {"com/pairip/application/Application.smali": _SHELL_SMALI},
        )
        p = PackerBypassPatcher(root, strategy="shell_swap")
        # Only a shell Application exists → fallback neutralizes it.
        assert p.patch() == 1
        assert p.strategy == "stub_neutralize"
        smali = _read(
            root, "smali/com/pairip/application/Application.smali"
        )
        assert "VMRunner" not in smali

    def test_skips_shell_namespaces_when_choosing_real_app(self, tmp_path):
        other_shell = _SHELL_SMALI.replace(
            "com/pairip/application/Application", "com/tencent/StubApplication"
        ).replace("Lcom/pairip/VMRunner;", "Lcom/tencent/StubShell/X;")
        root = _build_tree(
            tmp_path,
            _MANIFEST_SHELL,
            {
                "com/pairip/application/Application.smali": _SHELL_SMALI,
                "com/tencent/StubApplication.smali": other_shell,
                "com/example/app/RealApp.smali": _REAL_APP_SMALI,
            },
        )
        p = PackerBypassPatcher(root, strategy="shell_swap")
        assert p.patch() == 1
        manifest = _read(root, "AndroidManifest.xml")
        assert "com.example.app.RealApp" in manifest

    def test_already_real_app_is_noop(self, tmp_path):
        manifest = _MANIFEST_SHELL.replace(
            "com.pairip.application.Application", "com.example.app.RealApp"
        )
        root = _build_tree(tmp_path, manifest)
        p = PackerBypassPatcher(
            root, strategy="shell_swap",
            shell_application="com.example.app.RealApp",
            real_application="com.example.app.RealApp",
        )
        assert p.patch() == 0

    def test_missing_manifest_returns_zero(self, tmp_path):
        root = tmp_path / "empty"
        root.mkdir()
        p = PackerBypassPatcher(str(root), strategy="shell_swap")
        assert p.patch() == 0


# ============================================================
# STUB_NEUTRALIZE
# ============================================================
class TestStubNeutralize:
    def test_neutralizes_lifecycle(self, tmp_path):
        root = _build_tree(
            tmp_path,
            _MANIFEST_SHELL,
            {"com/pairip/application/Application.smali": _SHELL_SMALI},
        )
        p = PackerBypassPatcher(root, strategy="stub_neutralize")
        assert p.patch() == 1
        smali = _read(
            root, "smali/com/pairip/application/Application.smali"
        )
        assert "VMRunner" not in smali
        assert "return-void" in smali
        # Constructor must survive.
        assert "constructor <init>" in smali

    def test_idempotent(self, tmp_path):
        root = _build_tree(
            tmp_path,
            _MANIFEST_SHELL,
            {"com/pairip/application/Application.smali": _SHELL_SMALI},
        )
        p = PackerBypassPatcher(root, strategy="stub_neutralize")
        assert p.patch() == 1
        first = _read(
            root, "smali/com/pairip/application/Application.smali"
        )
        p2 = PackerBypassPatcher(root, strategy="stub_neutralize")
        assert p2.patch() == 0
        second = _read(
            root, "smali/com/pairip/application/Application.smali"
        )
        assert first == second

    def test_missing_smali_returns_zero(self, tmp_path):
        root = _build_tree(tmp_path, _MANIFEST_SHELL)
        p = PackerBypassPatcher(root, strategy="stub_neutralize")
        assert p.patch() == 0

    def test_no_lifecycle_returns_zero(self, tmp_path):
        bare = _SHELL_SMALI.split(".method public onCreate")[0]
        root = _build_tree(
            tmp_path,
            _MANIFEST_SHELL,
            {"com/pairip/application/Application.smali": bare},
        )
        p = PackerBypassPatcher(root, strategy="stub_neutralize")
        assert p.patch() == 0

    def test_explicit_shell_application(self, tmp_path):
        manifest = _MANIFEST_SHELL.replace(
            "com.pairip.application.Application", "com.custom.Shell"
        )
        root = _build_tree(
            tmp_path,
            manifest,
            {"com/custom/Shell.smali": _SHELL_SMALI.replace(
                "com/pairip/application/Application", "com/custom/Shell"
            )},
        )
        p = PackerBypassPatcher(
            root, strategy="stub_neutralize",
            shell_application="com.custom.Shell",
        )
        assert p.patch() == 1


# ============================================================
# Manifest parsing helpers
# ============================================================
class TestManifestParsing:
    def test_manifest_application_extracts_name(self, tmp_path):
        root = _build_tree(tmp_path, _MANIFEST_SHELL)
        p = PackerBypassPatcher(root, strategy="dex_plaintext")
        assert (
            p._manifest_application(_MANIFEST_SHELL)
            == "com.pairip.application.Application"
        )

    def test_manifest_application_none_when_absent(self, tmp_path):
        root = _build_tree(tmp_path, _MANIFEST_NO_NAME)
        p = PackerBypassPatcher(root, strategy="dex_plaintext")
        assert p._manifest_application(_MANIFEST_NO_NAME) is None

    def test_manifest_application_empty_string(self, tmp_path):
        root = _build_tree(tmp_path, _MANIFEST_SHELL)
        p = PackerBypassPatcher(root, strategy="dex_plaintext")
        assert p._manifest_application("") is None
