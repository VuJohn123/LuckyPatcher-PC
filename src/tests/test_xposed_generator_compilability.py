"""Compilability regression tests — catch smali label conflicts.

Background: smali.jar requires UNIQUE labels per method. Multi-target hooks
(e.g. IAPHook with 4 targets) concatenate N bodies into a single `init`
method. If templates hard-code labels like `:try_start_0`, smali fails.
"""
from __future__ import annotations

import re

import pytest

from core.xposed_generator import (
    _HOOK_CLASS_NAMES,
    XposedModuleConfig,
    XposedModuleGenerator,
)

# Label definition: line = optional ws + ":" + identifier + optional ws
_LABEL_RE = re.compile(r"^\s*(:[a-zA-Z_]\w*)\s*$", re.MULTILINE)


def _extract_labels(smali_text: str) -> list[str]:
    return _LABEL_RE.findall(smali_text)


class TestSmaliLabelsUnique:
    @pytest.mark.parametrize("hook", ["iap", "license", "signature", "install"])
    def test_no_duplicate_labels_per_hook_class(self, tmp_path, hook):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=[hook])
        gen.generate(cfg, str(tmp_path / "out"))

        cls = _HOOK_CLASS_NAMES[hook]
        path = (
            tmp_path / "out" / "smali" / "com" / "lppc"
            / "xposed" / "hooks" / f"{cls}.smali"
        )
        labels = _extract_labels(path.read_text())
        dupes = {l for l in labels if labels.count(l) > 1}
        assert not dupes, (
            f"{hook}: duplicate labels would break smali.jar: "
            f"{sorted(dupes)}"
        )

    def test_all_hooks_together_no_duplicate_labels(self, tmp_path):
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(
            hooks=["iap", "license", "signature", "install"],
        )
        gen.generate(cfg, str(tmp_path / "out"))

        hooks_dir = (
            tmp_path / "out" / "smali" / "com" / "lppc" / "xposed" / "hooks"
        )
        for cls in _HOOK_CLASS_NAMES.values():
            path = hooks_dir / f"{cls}.smali"
            labels = _extract_labels(path.read_text())
            dupes = {l for l in labels if labels.count(l) > 1}
            assert not dupes, f"{cls}: {sorted(dupes)}"

    def test_try_start_labels_are_indexed(self, tmp_path):
        """Regression: check try_start_N exists per target, no bare try_start_0."""
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["iap"])  # 4 targets
        gen.generate(cfg, str(tmp_path / "out"))

        hook = (
            tmp_path / "out" / "smali" / "com" / "lppc"
            / "xposed" / "hooks" / "IAPHook.smali"
        ).read_text()
        labels = _extract_labels(hook)
        for idx in range(4):
            assert f":try_start_{idx}" in labels, f"missing try_start_{idx}"
            assert f":try_end_{idx}" in labels, f"missing try_end_{idx}"
            assert f":catch_{idx}" in labels, f"missing catch_{idx}"