"""Test signature_integrity_patcher v4 — anti-tamper extended."""
from __future__ import annotations

import pytest

from patcher.signature_integrity_patcher import (
    SignatureIntegrityPatcher,
    _INTEGRITY_METHOD_ACTIONS,
    _KEYWORDS,
)


def _write(tmp_path, name: str, content: str) -> str:
    p = tmp_path / "smali" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return str(p)


@pytest.fixture
def patcher(tmp_path):
    (tmp_path / "smali").mkdir(exist_ok=True)
    return SignatureIntegrityPatcher(
        str(tmp_path), log_callback=lambda *a: None,
    )


class TestConstants:
    def test_keywords_nonempty(self):
        assert len(_KEYWORDS) > 10

    def test_actions_nonempty(self):
        assert len(_INTEGRITY_METHOD_ACTIONS) > 20

    def test_actions_tuple_shape(self):
        for item in _INTEGRITY_METHOD_ACTIONS:
            assert isinstance(item, tuple)
            assert len(item) == 2
            assert item[1] in ("return_true", "return_false")


class TestIntegrityMethods:
    def test_check_integrity_returns_true(self, patcher, tmp_path):
        _write(
            tmp_path, "Checker.smali",
            '.method public checkIntegrity()Z\n'
            '    .registers 2\n'
            '    const/4 v0, 0x0\n'
            '    return v0\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Checker.smali").read_text()
        assert "const/4 v0, 0x1" in content

    def test_verify_crc_returns_true(self, patcher, tmp_path):
        _write(
            tmp_path, "CRC.smali",
            '.method public verifyCRC()Z\n'
            '    .registers 2\n'
            '    const/4 v0, 0x0\n'
            '    return v0\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "CRC.smali").read_text()
        assert "const/4 v0, 0x1" in content

    def test_check_tamper_returns_false(self, patcher, tmp_path):
        _write(
            tmp_path, "Tamper.smali",
            '.method public checkTamper()Z\n'
            '    .registers 2\n'
            '    const/4 v0, 0x1\n'
            '    return v0\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Tamper.smali").read_text()
        # Tamper should return FALSE (app is not tampered)
        assert "const/4 v0, 0x0" in content


class TestRootDetection:
    def test_is_rooted_returns_false(self, patcher, tmp_path):
        _write(
            tmp_path, "Root.smali",
            '.method public isRooted()Z\n'
            '    .registers 2\n'
            '    const/4 v0, 0x1\n'
            '    return v0\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Root.smali").read_text()
        assert "const/4 v0, 0x0" in content

    def test_check_root_returns_false(self, patcher, tmp_path):
        _write(
            tmp_path, "CheckRoot.smali",
            '.method public checkRoot()Z\n'
            '    .registers 2\n'
            '    const/4 v0, 0x1\n'
            '    return v0\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "CheckRoot.smali").read_text()
        assert "const/4 v0, 0x0" in content


class TestEmulatorDetection:
    def test_is_emulator_returns_false(self, patcher, tmp_path):
        _write(
            tmp_path, "Emu.smali",
            '.method public isEmulator()Z\n'
            '    .registers 2\n'
            '    const/4 v0, 0x1\n'
            '    return v0\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Emu.smali").read_text()
        assert "const/4 v0, 0x0" in content


class TestDebugDetection:
    def test_is_debuggable_returns_false(self, patcher, tmp_path):
        _write(
            tmp_path, "Dbg.smali",
            '.method public isDebuggable()Z\n'
            '    .registers 2\n'
            '    const/4 v0, 0x1\n'
            '    return v0\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Dbg.smali").read_text()
        assert "const/4 v0, 0x0" in content

    def test_is_debug_returns_false(self, patcher, tmp_path):
        _write(
            tmp_path, "Debug.smali",
            '.method public isDebug()Z\n'
            '    .registers 2\n'
            '    const/4 v0, 0x1\n'
            '    return v0\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Debug.smali").read_text()
        assert "const/4 v0, 0x0" in content


class TestFridaDetection:
    def test_detect_frida_returns_false(self, patcher, tmp_path):
        _write(
            tmp_path, "Frida.smali",
            '.method public detectFrida()Z\n'
            '    .registers 2\n'
            '    const/4 v0, 0x1\n'
            '    return v0\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Frida.smali").read_text()
        assert "const/4 v0, 0x0" in content

    def test_is_hooked_returns_false(self, patcher, tmp_path):
        _write(
            tmp_path, "Hooked.smali",
            '.method public isHooked()Z\n'
            '    .registers 2\n'
            '    const/4 v0, 0x1\n'
            '    return v0\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Hooked.smali").read_text()
        assert "const/4 v0, 0x0" in content


class TestSafetyNet:
    def test_safetynet_returns_true(self, patcher, tmp_path):
        _write(
            tmp_path, "SN.smali",
            '.method public safetynetCheck()Z\n'
            '    .registers 2\n'
            '    const/4 v0, 0x0\n'
            '    return v0\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "SN.smali").read_text()
        assert "const/4 v0, 0x1" in content


class TestSkipUnrelated:
    def test_unrelated_method_unchanged(self, patcher, tmp_path):
        _write(
            tmp_path, "Unrelated.smali",
            '.method public randomFunction()Z\n'
            '    .registers 2\n'
            '    const/4 v0, 0x0\n'
            '    return v0\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Unrelated.smali").read_text()
        assert "const/4 v0, 0x0" in content  # unchanged

    def test_annotation_skipped(self, patcher, tmp_path):
        _write(
            tmp_path, "Annotated.smali",
            '.method public checkIntegrity()Z\n'
            '    .registers 2\n'
            '    .annotation runtime Ljava/lang/Override;\n'
            '    .end annotation\n'
            '    const/4 v0, 0x0\n'
            '    return v0\n'
            '.end method\n'
        )
        # Should not crash
        patcher.patch()


class TestClassifier:
    def test_classify_integrity(self, patcher):
        assert patcher._classify_method("checkintegrity") == "return_true"

    def test_classify_root(self, patcher):
        assert patcher._classify_method("isrooted") == "return_false"

    def test_classify_unknown(self, patcher):
        assert patcher._classify_method("randomfunc") is None


class TestIntegration:
    def test_patch_returns_int(self, patcher):
        assert isinstance(patcher.patch(), int)

    def test_empty_dir(self, tmp_path):
        (tmp_path / "smali").mkdir()
        p = SignatureIntegrityPatcher(
            str(tmp_path), log_callback=lambda *a: None,
        )
        assert p.patch() == 0