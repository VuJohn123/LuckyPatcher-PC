"""Test core/xposed_generator.py — Xposed module code generator."""
from __future__ import annotations

import os

import pytest

from core.xposed_generator import (
    _HOOK_CLASS_NAMES,
    _INNER_CLASS_TEMPLATES,
    _XPOSED_INIT_PACKAGE,
    XposedModuleConfig,
    XposedModuleGenerator,
    generate_xposed_module,
)


# ============================================================
# Config
# ============================================================
class TestConfig:
    def test_defaults(self):
        cfg = XposedModuleConfig()
        assert cfg.package_name == "com.lppc.xposed.generated"
        assert cfg.min_xposed_version == 82
        assert cfg.hooks == []

    def test_hooks_list_independent(self):
        a = XposedModuleConfig()
        b = XposedModuleConfig()
        a.hooks.append("iap")
        assert b.hooks == []


# ============================================================
# Generator — basic
# ============================================================
class TestGeneratorBasic:
    def test_generates_full_structure(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(
            package_name="com.test.module",
            target_package="com.example.app",
            hooks=["iap", "license"],
        )
        result = gen.generate(cfg, str(tmp_path / "out"))

        assert result.is_valid is True
        assert "iap" in result.hooks_generated
        assert "license" in result.hooks_generated

        out = tmp_path / "out"
        assert (out / "AndroidManifest.xml").exists()
        assert (out / "assets" / "xposed_init").exists()
        assert (
            out / "smali" / "com" / "lppc" / "xposed" / "hooks"
            / "XposedEntry.smali"
        ).exists()
        assert (
            out / "smali" / "com" / "lppc" / "xposed" / "hooks"
            / "IAPHook.smali"
        ).exists()
        assert (
            out / "smali" / "com" / "lppc" / "xposed" / "hooks"
            / "LicenseHook.smali"
        ).exists()
        assert (out / "README.md").exists()

    def test_default_hooks_when_empty(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=[])
        result = gen.generate(cfg, str(tmp_path / "out"))
        assert "iap" in result.hooks_generated

    def test_invalid_hooks_filtered(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["bogus", "iap"])
        result = gen.generate(cfg, str(tmp_path / "out"))
        assert "iap" in result.hooks_generated
        assert "bogus" not in result.hooks_generated

    def test_signature_hook(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["signature"])
        result = gen.generate(cfg, str(tmp_path / "out"))
        assert "signature" in result.hooks_generated
        assert (
            tmp_path / "out" / "smali" / "com" / "lppc" / "xposed"
            / "hooks" / "SignatureHook.smali"
        ).exists()


# ============================================================
# Inner classes ($1 extends XC_MethodHook)
# ============================================================
class TestInnerClasses:
    def test_inner_class_files_generated(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["iap", "license", "signature"])
        result = gen.generate(cfg, str(tmp_path / "out"))

        assert "IAPHook$1" in result.inner_classes_generated
        assert "LicenseHook$1" in result.inner_classes_generated
        assert "SignatureHook$1" in result.inner_classes_generated

        hooks_dir = (
            tmp_path / "out" / "smali" / "com" / "lppc"
            / "xposed" / "hooks"
        )
        assert (hooks_dir / "IAPHook$1.smali").exists()
        assert (hooks_dir / "LicenseHook$1.smali").exists()
        assert (hooks_dir / "SignatureHook$1.smali").exists()

    def test_inner_class_extends_xc_method_hook(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["iap"])
        gen.generate(cfg, str(tmp_path / "out"))

        inner = (
            tmp_path / "out" / "smali" / "com" / "lppc"
            / "xposed" / "hooks" / "IAPHook$1.smali"
        ).read_text()
        assert ".super Lde/robv/android/xposed/XC_MethodHook;" in inner
        assert "afterHookedMethod" in inner

    def test_license_inner_suppresses_dontallow(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["license"])
        gen.generate(cfg, str(tmp_path / "out"))

        inner = (
            tmp_path / "out" / "smali" / "com" / "lppc"
            / "xposed" / "hooks" / "LicenseHook$1.smali"
        ).read_text()
        assert "beforeHookedMethod" in inner
        assert "setResult" in inner
        assert "dontAllow" not in inner  # inner doesn't reference dontAllow

    def test_license_hook_hooks_dontallow(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["license"])
        gen.generate(cfg, str(tmp_path / "out"))

        hook = (
            tmp_path / "out" / "smali" / "com" / "lppc"
            / "xposed" / "hooks" / "LicenseHook.smali"
        ).read_text()
        assert '"dontAllow"' in hook

    def test_inner_class_templates_cover_all_hooks(self):
        for hook in XposedModuleGenerator.SUPPORTED_HOOKS:
            assert hook in _INNER_CLASS_TEMPLATES


# ============================================================
# Manifest
# ============================================================
class TestManifest:
    def test_manifest_has_required_metadata(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(
            package_name="com.test.module",
            target_package="com.example.app",
            hooks=["iap"],
        )
        gen.generate(cfg, str(tmp_path / "out"))

        manifest = (tmp_path / "out" / "AndroidManifest.xml").read_text()
        assert 'package="com.test.module"' in manifest
        assert 'android:name="xposedmodule"' in manifest
        assert 'android:value="true"' in manifest
        assert 'android:name="xposedminversion"' in manifest
        assert 'android:name="xposedscope"' in manifest


# ============================================================
# xposed_init
# ============================================================
class TestXposedInit:
    def test_xposed_init_correct_package(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["iap"])
        gen.generate(cfg, str(tmp_path / "out"))

        init_path = tmp_path / "out" / "assets" / "xposed_init"
        content = init_path.read_text().strip()
        assert content == _XPOSED_INIT_PACKAGE


# ============================================================
# Scope
# ============================================================
class TestScope:
    def test_scope_has_target_package(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(
            target_package="com.example.app",
            hooks=["iap"],
        )
        gen.generate(cfg, str(tmp_path / "out"))

        arrays = (
            tmp_path / "out" / "res" / "values" / "arrays.xml"
        ).read_text()
        assert "<item>com.example.app</item>" in arrays

    def test_scope_android_when_no_target(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(target_package="", hooks=["iap"])
        gen.generate(cfg, str(tmp_path / "out"))

        arrays = (
            tmp_path / "out" / "res" / "values" / "arrays.xml"
        ).read_text()
        assert "<item>android</item>" in arrays


# ============================================================
# Entry — init calls
# ============================================================
class TestEntryInitCalls:
    def test_entry_references_hooks(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["iap", "license"])
        gen.generate(cfg, str(tmp_path / "out"))

        entry = (
            tmp_path / "out" / "smali" / "com" / "lppc" / "xposed"
            / "hooks" / "XposedEntry.smali"
        ).read_text()
        assert "IAPHook;->init" in entry
        assert "LicenseHook;->init" in entry

    def test_entry_uses_correct_class_names_not_capitalize(self, tmp_path):
        """Regression: 'iap'.capitalize() → 'Iap' (bug), phải là 'IAP'."""
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["iap"])
        gen.generate(cfg, str(tmp_path / "out"))

        entry = (
            tmp_path / "out" / "smali" / "com" / "lppc" / "xposed"
            / "hooks" / "XposedEntry.smali"
        ).read_text()
        assert "IAPHook;->init" in entry
        assert "IapHook;->init" not in entry

    def test_entry_uses_classloader_register(self, tmp_path):
        """Entry phải truyền v0 (classLoader) vào init, không phải p1."""
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(
            target_package="com.example.app",
            hooks=["iap"],
        )
        gen.generate(cfg, str(tmp_path / "out"))

        entry = (
            tmp_path / "out" / "smali" / "com" / "lppc" / "xposed"
            / "hooks" / "XposedEntry.smali"
        ).read_text()
        assert "invoke-static {v0}" in entry
        assert "invoke-static {v2}" not in entry

    def test_entry_has_target_check_when_target_set(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(
            target_package="com.example.app",
            hooks=["iap"],
        )
        gen.generate(cfg, str(tmp_path / "out"))

        entry = (
            tmp_path / "out" / "smali" / "com" / "lppc" / "xposed"
            / "hooks" / "XposedEntry.smali"
        ).read_text()
        assert "com.example.app" in entry
        assert ":cond_skip" in entry

    def test_entry_no_target_check_when_empty(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(target_package="", hooks=["iap"])
        gen.generate(cfg, str(tmp_path / "out"))

        entry = (
            tmp_path / "out" / "smali" / "com" / "lppc" / "xposed"
            / "hooks" / "XposedEntry.smali"
        ).read_text()
        assert ":cond_skip" not in entry


# ============================================================
# README
# ============================================================
class TestReadme:
    def test_readme_lists_hooks(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(
            target_package="com.example.app",
            hooks=["iap", "signature"],
        )
        gen.generate(cfg, str(tmp_path / "out"))

        readme = (tmp_path / "out" / "README.md").read_text()
        assert "com.example.app" in readme
        assert "iap" in readme
        assert "signature" in readme

    def test_readme_lists_inner_classes(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["iap", "license"])
        gen.generate(cfg, str(tmp_path / "out"))

        readme = (tmp_path / "out" / "README.md").read_text()
        assert "IAPHook$1" in readme
        assert "LicenseHook$1" in readme


# ============================================================
# High-level entry
# ============================================================
class TestGenerateXposedModule:
    def test_high_level_helper(self, tmp_path):
        result = generate_xposed_module(
            target_package="com.example.app",
            patch_modes=["iap", "license"],
            output_dir=str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        assert result is not None
        assert result.is_valid is True
        assert "iap" in result.hooks_generated
        assert "license" in result.hooks_generated
        assert "IAPHook$1" in result.inner_classes_generated
        assert "LicenseHook$1" in result.inner_classes_generated

    def test_high_level_default_iap(self, tmp_path):
        result = generate_xposed_module(
            target_package="com.example.app",
            patch_modes=[],
            output_dir=str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        assert result is not None
        assert "iap" in result.hooks_generated


# ============================================================
# Error handling
# ============================================================
class TestErrorHandling:
    def test_handles_io_error(self, tmp_path, monkeypatch):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["iap"])

        def _fail_makedirs(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(os, "makedirs", _fail_makedirs)
        result = gen.generate(cfg, str(tmp_path / "out"))
        assert result.is_valid is False
        assert len(result.errors) > 0


# ============================================================
# Constants sanity
# ============================================================
class TestConstants:
    def test_hook_class_names_correct(self):
        assert _HOOK_CLASS_NAMES["iap"] == "IAPHook"
        assert _HOOK_CLASS_NAMES["license"] == "LicenseHook"
        assert _HOOK_CLASS_NAMES["signature"] == "SignatureHook"

    def test_no_capitalize_bug(self):
        """Regression: 'iap'.capitalize() == 'Iap' (sai)."""
        assert "iap".capitalize() == "Iap"
        assert _HOOK_CLASS_NAMES["iap"] != "iap".capitalize() + "Hook"


# ============================================================
# v1.4 — signature spoof inner template (LP parity)
# ============================================================
class TestSignatureSpoof:
    """Verify `after_signature_spoof` template clears PackageInfo.signatures."""

    def test_signature_hook_uses_spoof_for_getpackageinfo(self, tmp_path):
        """getPackageInfo = target index 1 → SignatureHook$1 dùng spoof template."""
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["signature"])
        gen.generate(cfg, str(tmp_path / "out"))

        inner = (
            tmp_path / "out" / "smali" / "com" / "lppc"
            / "xposed" / "hooks" / "SignatureHook$1.smali"
        ).read_text()
        assert "afterHookedMethod" in inner
        assert "PackageInfo" in inner
        assert "signatures" in inner
        # Phải KHÁC generic after template (không log "hooked")
        assert "__METHOD__ hooked" not in inner

    def test_signature_spoof_clears_signatures_field(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["signature"])
        gen.generate(cfg, str(tmp_path / "out"))

        inner = (
            tmp_path / "out" / "smali" / "com" / "lppc"
            / "xposed" / "hooks" / "SignatureHook$1.smali"
        ).read_text()
        # iput-object null → PackageInfo.signatures
        assert "iput-object" in inner
        assert "Landroid/content/pm/PackageInfo;->signatures:" in inner

    def test_after_signature_spoof_template_registered(self):
        from core.xposed_generator import _INNER_TEMPLATES
        assert "after_signature_spoof" in _INNER_TEMPLATES

    def test_generic_after_template_still_works(self, tmp_path):
        """Regression: install hook $0 vẫn dùng generic `after` template."""
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["install"])
        gen.generate(cfg, str(tmp_path / "out"))

        inner = (
            tmp_path / "out" / "smali" / "com" / "lppc"
            / "xposed" / "hooks" / "InstallHook$0.smali"
        ).read_text()
        assert "afterHookedMethod" in inner
        assert "LP-PC-InstallHook" in inner

    def test_signature_spoof_does_not_break_other_hooks(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["signature", "iap", "license"])
        result = gen.generate(cfg, str(tmp_path / "out"))
        assert result.is_valid is True
        assert "signature" in result.hooks_generated
        assert "iap" in result.hooks_generated
        assert "license" in result.hooks_generated