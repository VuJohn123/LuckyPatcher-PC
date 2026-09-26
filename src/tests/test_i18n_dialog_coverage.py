"""
i18n coverage test — verify mọi dialog key tồn tại trong vi/en.

Sẽ fail nếu có key dialog.* được gọi trong code nhưng thiếu trong JSON.
Không cần chạy GUI, chỉ load i18n và check dictionary.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_I18N_DIR = _REPO_ROOT / "assets" / "i18n"


def _load(lang: str) -> dict:
    path = _I18N_DIR / f"{lang}.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _flatten_keys(d: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for k, v in d.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys |= _flatten_keys(v, full)
        else:
            keys.add(full)
    return keys


_REQUIRED_KEYS = [
    # Dialog common
    "dialog.common.ok",
    "dialog.common.cancel",
    "dialog.common.close",
    "dialog.common.error",
    "dialog.common.warning_title",
    "dialog.common.continue",
    "dialog.common.stop",
    # Resign
    "dialog.resign.title",
    "dialog.resign.header",
    "dialog.resign.key_group",
    "dialog.resign.pkg_group",
    "dialog.resign.pkg_label",
    "dialog.resign.btn_ok",
    "dialog.resign.key.testkey",
    "dialog.resign.key.platform",
    "dialog.resign.key.media",
    "dialog.resign.key.shared",
    "dialog.resign.desc.testkey",
    "dialog.resign.desc.platform",
    "dialog.resign.desc.media",
    "dialog.resign.desc.shared",
    # Clone
    "dialog.clone.title",
    "dialog.clone.header",
    "dialog.clone.orig_pkg",
    "dialog.clone.new_pkg",
    "dialog.clone.new_name",
    "dialog.clone.hint",
    "dialog.clone.btn_ok",
    "dialog.clone.suffix_pkg",
    "dialog.clone.suffix_name",
    "dialog.clone.warn_empty_pkg",
    "dialog.clone.warn_regex_pkg",
    "dialog.clone.warn_same_pkg",
    # Patch config
    "dialog.patch_config.title",
    "dialog.patch_config.btn_ok",
    "dialog.patch_config.btn_cancel",
    # Wizard
    "dialog.wizard.title",
    "dialog.wizard.header",
    "dialog.wizard.btn_ok",
    "dialog.wizard.btn_cancel",
    "dialog.wizard.opt.iap_dex",
    "dialog.wizard.opt.ads_full_offline",
    "dialog.wizard.opt.license_extreme",
    "dialog.wizard.opt.multi_full",
]


class TestI18nCoverage:
    def test_vi_has_all_required_keys(self):
        keys = _flatten_keys(_load("vi"))
        missing = [k for k in _REQUIRED_KEYS if k not in keys]
        assert not missing, f"vi.json missing: {missing}"

    def test_en_has_all_required_keys(self):
        keys = _flatten_keys(_load("en"))
        missing = [k for k in _REQUIRED_KEYS if k not in keys]
        assert not missing, f"en.json missing: {missing}"

    def test_vi_en_have_same_key_set(self):
        """Ensure vi/en không drift."""
        vi_keys = _flatten_keys(_load("vi"))
        en_keys = _flatten_keys(_load("en"))
        only_vi = vi_keys - en_keys
        only_en = en_keys - vi_keys
        assert not only_vi, f"vi-only keys: {sorted(only_vi)}"
        assert not only_en, f"en-only keys: {sorted(only_en)}"

    def test_all_dialog_keys_are_strings(self):
        for lang in ("vi", "en"):
            data = _load(lang)
            for k in _REQUIRED_KEYS:
                # walk nested
                cur = data
                for part in k.split("."):
                    cur = cur[part]
                assert isinstance(cur, str), (
                    f"{lang}:{k} is not str: {type(cur)}"
                )


class TestI18nRuntime:
    def test_t_returns_dialog_strings(self):
        from core.i18n import set_language, t
        set_language("vi")
        assert t("dialog.resign.title") == "Ký lại APK"
        assert t("dialog.clone.btn_ok") == "Clone"
        set_language("en")
        assert t("dialog.resign.title") == "Resign APK"
        assert t("dialog.clone.btn_ok") == "Clone"
        # Restore
        set_language("vi")

    def test_t_format_placeholder(self):
        from core.i18n import set_language, t
        set_language("vi")
        out = t("dialog.clone.header", name="MyApp")
        assert "MyApp" in out
        set_language("vi")

    def test_t_patch_config_title(self):
        from core.i18n import set_language, t
        set_language("vi")
        out = t("dialog.patch_config.title", name="License")
        assert "License" in out
        set_language("vi")