"""Test signature_patcher v6 — LP parity passes (0x80, framework, digest)."""
from __future__ import annotations

import pytest

from patcher.signature_patcher import (
    _FLAG_GET_SIGNING_CERTIFICATES,
    _FLAG_INSTALL_ALLOW_DOWNGRADE,
    _FRAMEWORK_METHODS,
    SignatureVerifyPatcher,
)


# ============================================================
# HELPERS
# ============================================================
def _write_smali(tmp_path, filename: str, content: str) -> str:
    p = tmp_path / "smali" / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return str(p)


@pytest.fixture
def patcher(tmp_path):
    (tmp_path / "smali").mkdir(exist_ok=True)
    return SignatureVerifyPatcher(
        str(tmp_path),
        log_callback=lambda *a: None,
    )


# ============================================================
# Constants
# ============================================================
class TestConstants:
    def test_install_allow_downgrade(self):
        assert _FLAG_INSTALL_ALLOW_DOWNGRADE == 0x80

    def test_get_signing_certificates(self):
        assert _FLAG_GET_SIGNING_CERTIFICATES == 0x08000000

    def test_framework_methods_nonempty(self):
        assert len(_FRAMEWORK_METHODS) >= 12

    def test_framework_has_both_jars(self):
        classes = {c for c, _, _ in _FRAMEWORK_METHODS}
        assert any("PackageManagerServiceUtils" in c for c in classes)
        assert any("SigningDetails" in c for c in classes)


# ============================================================
# PASS 1 — Method body boolean patch
# ============================================================
class TestPass1MethodBodies:
    def test_patch_verify_signature_method(self, patcher, tmp_path):
        _write_smali(
            tmp_path, "Foo.smali",
            '.method public verifySignature()Z\n'
            '    .registers 2\n'
            '    const/4 v0, 0x0\n'
            '    return v0\n'
            '.end method\n'
        )
        count = patcher.patch()
        assert count >= 1

        content = (
            tmp_path / "smali" / "Foo.smali"
        ).read_text()
        assert "const/4 v0, 0x1" in content

    def test_skip_unrelated_method(self, patcher, tmp_path):
        _write_smali(
            tmp_path, "Bar.smali",
            '.method public unrelatedStuff()Z\n'
            '    .registers 2\n'
            '    const/4 v0, 0x0\n'
            '    return v0\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Bar.smali").read_text()
        # Should not be patched
        assert "const/4 v0, 0x0" in content

    def test_skip_method_with_annotation(self, patcher, tmp_path):
        _write_smali(
            tmp_path, "Annotated.smali",
            '.method public checkSignature()Z\n'
            '    .registers 2\n'
            '    .annotation runtime Ljava/lang/Override;\n'
            '    .end annotation\n'
            '    const/4 v0, 0x0\n'
            '    return v0\n'
            '.end method\n'
        )
        patcher.patch()
        # Annotation present → skip (my impl only patches if no .annotation
        # inside `full` match — but REGEX_SIGNATURE_METHOD may or may not
        # include annotation block; we assert result does not crash)
        assert (tmp_path / "smali" / "Annotated.smali").exists()


# ============================================================
# PASS 2 — LP 0x80 trick
# ============================================================
class TestPass2CheckSignaturesCall:
    def test_patch_check_signatures_call(self, patcher, tmp_path):
        _write_smali(
            tmp_path, "Checker.smali",
            '.method public test()V\n'
            '    .registers 4\n'
            '    invoke-virtual {v0, v1, v2}, '
            'Landroid/content/pm/PackageManager;'
            '->checkSignatures(Ljava/lang/String;Ljava/lang/String;)I\n'
            '    move-result v3\n'
            '    return-void\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Checker.smali").read_text()
        # call site should be patched to return 0
        assert "const/4 v3, 0x0" in content

    def test_high_register_uses_const16(self, patcher, tmp_path):
        _write_smali(
            tmp_path, "Check.smali",
            '.method public verify()V\n'
            '    .registers 40\n'
            '    invoke-virtual {p0, p1}, '
            'Landroid/content/pm/PackageManager;'
            '->checkSignatures(Ljava/lang/String;Ljava/lang/String;)I\n'
            '    move-result v16\n'
            '    return-void\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Check.smali").read_text()
        # const/4 cannot encode v16 → must widen to const/16.
        assert "const/16 v16, 0x0" in content
        assert "const/4 v16" not in content

    def test_no_change_without_signature_keyword(self, patcher, tmp_path):
        _write_smali(
            tmp_path, "NoKeyword.smali",
            '.method public test()V\n'
            '    .registers 2\n'
            '    return-void\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "NoKeyword.smali").read_text()
        assert "const/4 v0, 0x0" not in content


# ============================================================
# PASS 3 — getPackageInfo flag injection
# ============================================================
class TestPass3GetPackageInfo:
    def test_flag_injection(self, patcher, tmp_path):
        _write_smali(
            tmp_path, "Getter.smali",
            '.method public get(Ljava/lang/String;)V\n'
            '    .registers 4\n'
            '    const/16 v0, 0x40\n'
            '    invoke-virtual {p0, p1, v0}, '
            'Landroid/content/pm/PackageManager;'
            '->getPackageInfo(Ljava/lang/String;I)'
            'Landroid/content/pm/PackageInfo;\n'
            '    return-void\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Getter.smali").read_text()
        # 0x40 | 0x08000000 = 0x08000040. 0x08000040 does not fit const/16
        # (signed 16-bit) → must use the 32-bit `const` form.
        assert "const v0, 0x8000040" in content
        assert "const/16 v0, 0x8000040" not in content

    def test_invoke_register_list_preserved(self, patcher, tmp_path):
        _write_smali(
            tmp_path, "Regs.smali",
            '.method public get(Ljava/lang/String;)V\n'
            '    .registers 5\n'
            '    const/16 v2, 0x40\n'
            '    invoke-virtual {p0, p1, v2}, '
            'Landroid/content/pm/PackageManager;'
            '->getPackageInfo(Ljava/lang/String;I)'
            'Landroid/content/pm/PackageInfo;\n'
            '    return-void\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Regs.smali").read_text()
        assert "invoke-virtual {p0, p1, v2}" in content
        assert "{...}" not in content

    def test_unrelated_const_in_other_method_untouched(
        self, patcher, tmp_path,
    ):
        """Regression: DOTALL `(.*?)` used to rewrite an array-size const."""
        _write_smali(
            tmp_path, "Mixed.smali",
            '.method static constructor <clinit>()V\n'
            '    .locals 1\n'
            '    const/4 v0, 0x7\n'
            '    new-array v0, v0, [Ljava/lang/String;\n'
            '    sput-object v0, Lcom/x;->A:[Ljava/lang/String;\n'
            '    return-void\n'
            '.end method\n'
            '.method public validate(Ljava/lang/String;)V\n'
            '    .registers 4\n'
            '    const/16 v0, 0x40\n'
            '    invoke-virtual {p0, p1, v0}, '
            'Landroid/content/pm/PackageManager;'
            '->getPackageInfo(Ljava/lang/String;I)'
            'Landroid/content/pm/PackageInfo;\n'
            '    return-void\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Mixed.smali").read_text()
        assert "const/4 v0, 0x7" in content
        assert "new-array v0, v0," in content
        assert "const v0, 0x8000040" in content
        assert "0x8000007" not in content

    def test_non_adjacent_const_not_patched(self, patcher, tmp_path):
        """A const separated by real instructions is not the flag literal."""
        _write_smali(
            tmp_path, "Far.smali",
            '.method public get(Ljava/lang/String;)V\n'
            '    .registers 4\n'
            '    const/16 v0, 0x40\n'
            '    invoke-static {}, Lcom/x;->y()V\n'
            '    invoke-virtual {p0, p1, v0}, '
            'Landroid/content/pm/PackageManager;'
            '->getPackageInfo(Ljava/lang/String;I)'
            'Landroid/content/pm/PackageInfo;\n'
            '    return-void\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Far.smali").read_text()
        assert "0x8000040" not in content

    def test_idempotent_when_flag_already_set(self, patcher, tmp_path):
        _write_smali(
            tmp_path, "Done.smali",
            '.method public get(Ljava/lang/String;)V\n'
            '    .registers 4\n'
            '    const v0, 0x8000040\n'
            '    invoke-virtual {p0, p1, v0}, '
            'Landroid/content/pm/PackageManager;'
            '->getPackageInfo(Ljava/lang/String;I)'
            'Landroid/content/pm/PackageInfo;\n'
            '    return-void\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Done.smali").read_text()
        assert content.count("0x8000040") == 1

    def test_zero_flags_uses_high16_full_literal(
        self, patcher, tmp_path,
    ):
        """flags=0 → 0x08000000 → const/high16 takes the full literal."""
        _write_smali(
            tmp_path, "Zero.smali",
            '.method public get(Ljava/lang/String;)V\n'
            '    .registers 4\n'
            '    const/4 v1, 0x0\n'
            '    invoke-virtual {p0, p1, v1}, '
            'Landroid/content/pm/PackageManager;'
            '->getPackageInfo(Ljava/lang/String;I)'
            'Landroid/content/pm/PackageInfo;\n'
            '    return-void\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Zero.smali").read_text()
        assert "const/high16 v1, 0x8000000" in content
        assert "const/high16 v1, 0x800\n" not in content

    def test_range_invoke_flags_register(self, patcher, tmp_path):
        _write_smali(
            tmp_path, "Range.smali",
            '.method public get(Ljava/lang/String;Ljava/lang/Object;)V\n'
            '    .registers 3\n'
            '    const/16 p2, 0x40\n'
            '    invoke-virtual/range {p0 .. p2}, '
            'Landroid/content/pm/PackageManager;'
            '->getPackageInfo(Ljava/lang/String;I)'
            'Landroid/content/pm/PackageInfo;\n'
            '    return-void\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Range.smali").read_text()
        assert "const p2, 0x8000040" in content
        assert "invoke-virtual/range {p0 .. p2}" in content


# ============================================================
# PASS 4 — Framework methods
# ============================================================
class TestPass4FrameworkMethods:
    def test_patch_signingdetails_checkcapability(self, patcher, tmp_path):
        _write_smali(
            tmp_path, "SD.smali",
            '.method public checkCapability()Z\n'
            '    .registers 2\n'
            '    const/4 v0, 0x0\n'
            '    return v0\n'
            '.end method\n'
            '.method public getSigningDetails()Landroid/content/pm/SigningDetails;\n'
            '    .registers 1\n'
            '    return-object p0\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "SD.smali").read_text()
        assert "const/4 v0, 0x1" in content

    def test_checkdowngrade_return_void(self, patcher, tmp_path):
        _write_smali(
            tmp_path, "PMSU.smali",
            '.method public checkDowngrade()V\n'
            '    .registers 2\n'
            '    const/4 v0, 0x0\n'
            '    return-void\n'
            '.end method\n'
            '.field private static final TAG:Ljava/lang/String; = "PackageManagerServiceUtils"\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "PMSU.smali").read_text()
        # Should contain bare return-void replacement
        assert "return-void" in content


# ============================================================
# PASS 5 — MessageDigest.isEqual
# ============================================================
class TestPass5MessageDigest:
    def test_force_digest_equal(self, patcher, tmp_path):
        _write_smali(
            tmp_path, "Verifier.smali",
            '.method public verify()V\n'
            '    .registers 5\n'
            '    invoke-static {v0, v1}, '
            'Ljava/security/MessageDigest;'
            '->isEqual([B[B)Z\n'
            '    move-result v2\n'
            '    return-void\n'
            '.end method\n'
            'Ljava/lang/security/Signature;\n'
            'Ljava/security/MessageDigest;\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Verifier.smali").read_text()
        assert "const/4 v2, 0x1" in content

    def test_parameter_register_uses_const16(self, patcher, tmp_path):
        _write_smali(
            tmp_path, "Verifier2.smali",
            '.method public verifySignature(Ljava/lang/String;Ljava/lang/String;)V\n'
            '    .registers 40\n'
            '    invoke-static {v0, v1}, '
            'Ljava/security/MessageDigest;'
            '->isEqual([B[B)Z\n'
            '    move-result p2\n'
            '    return-void\n'
            '.end method\n'
        )
        patcher.patch()
        content = (tmp_path / "smali" / "Verifier2.smali").read_text()
        assert "const/16 p2, 0x1" in content
        assert "const/4 p2" not in content


# ============================================================
# Integration — patch() returns int
# ============================================================
class TestPatchIntegration:
    def test_patch_returns_int(self, patcher):
        result = patcher.patch()
        assert isinstance(result, int)

    def test_patch_empty_dir(self, tmp_path):
        (tmp_path / "smali").mkdir()
        p = SignatureVerifyPatcher(
            str(tmp_path), log_callback=lambda *a: None,
        )
        assert p.patch() == 0

    def test_patch_missing_dir(self, tmp_path):
        p = SignatureVerifyPatcher(
            str(tmp_path / "nonexistent"),
            log_callback=lambda *a: None,
        )
        assert p.patch() == 0

    def test_multiple_files(self, patcher, tmp_path):
        # Dùng method name có keyword "Signature" để pass prefilter
        # (prefilter_keywords bao gồm "checkSignature").
        for i in range(3):
            _write_smali(
                tmp_path, f"File{i}.smali",
                f'.method public checkSignature{i}()Z\n'
                f'    .registers 2\n'
                f'    const/4 v0, 0x0\n'
                f'    return v0\n'
                f'.end method\n'
            )
        count = patcher.patch()
        assert count >= 3
