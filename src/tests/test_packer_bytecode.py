"""Test scanner/checks/packer_bytecode.py — bytecode packer detection."""
from __future__ import annotations

import os
import zipfile

import pytest

from scanner.checks.packer_bytecode import (
    _BYTECODE_SIGNATURES,
    _ENCRYPTED_ENTROPY_MIN,
    _STUB_APP_MAX_LINES,
    BytecodeDetection,
    augment_packer_result,
    detect_encrypted_dex,
    detect_packer_via_bytecode,
    detect_stub_application,
    shannon_entropy,
    unique_byte_count,
)


# ============================================================
# Helpers — build fake APK
# ============================================================
def _make_apk(tmp_path, name: str, dex_payloads: dict[str, bytes]):
    """dex_payloads: {entry_name: raw_bytes}."""
    apk = tmp_path / name
    with zipfile.ZipFile(apk, "w") as z:
        for entry_name, raw in dex_payloads.items():
            z.writestr(entry_name, raw)
    return str(apk)


def _fake_dex(strings: list[str] | None = None,
              native_count: int = 0,
              padding: int = 0) -> bytes:
    """
    Build fake dex bytes chứa class descriptors + native methods.
    Không phải dex hợp lệ — chỉ raw bytes cho regex.
    """
    parts = []
    for s in strings or []:
        parts.append(s.encode("utf-8"))
        parts.append(b"\x00")
    for _ in range(native_count):
        parts.append(b".method public native foo()V")
    if padding:
        parts.append(os.urandom(padding))
    return b"".join(parts)


def _high_entropy_blob(size: int = 8192) -> bytes:
    """Random bytes → high Shannon entropy."""
    return os.urandom(size)


def _low_entropy_blob(size: int = 8192) -> bytes:
    """All zeros → entropy 0."""
    return b"\x00" * size


# ============================================================
# Shannon entropy
# ============================================================
class TestShannonEntropy:
    def test_empty_returns_zero(self):
        assert shannon_entropy(b"") == 0.0

    def test_single_byte_value_zero(self):
        assert shannon_entropy(b"\x00" * 100) == 0.0

    def test_uniform_max_entropy(self):
        # 256 distinct bytes, each once → max entropy = 8.0
        data = bytes(range(256))
        e = shannon_entropy(data)
        assert abs(e - 8.0) < 0.01

    def test_low_entropy_two_values(self):
        data = b"\x00\x01" * 1000
        e = shannon_entropy(data)
        assert abs(e - 1.0) < 0.01

    def test_random_data_high_entropy(self):
        data = os.urandom(4096)
        e = shannon_entropy(data)
        assert e > 7.5


# ============================================================
# Unique byte count
# ============================================================
class TestUniqueByteCount:
    def test_empty_zero(self):
        assert unique_byte_count(b"") == 0

    def test_all_zeros_one(self):
        assert unique_byte_count(b"\x00" * 100) == 1

    def test_all_256(self):
        assert unique_byte_count(bytes(range(256))) == 256

    def test_random_high(self):
        assert unique_byte_count(os.urandom(4096)) > 200


# ============================================================
# Encrypted DEX detection
# ============================================================
class TestEncryptedDex:
    def test_small_input_not_encrypted(self):
        enc, _, _ = detect_encrypted_dex(b"small")
        assert enc is False

    def test_low_entropy_not_encrypted(self):
        enc, _, _ = detect_encrypted_dex(_low_entropy_blob(8192))
        assert enc is False

    def test_high_entropy_encrypted(self):
        enc, entropy, unique = detect_encrypted_dex(_high_entropy_blob(16384))
        assert enc is True
        assert entropy >= _ENCRYPTED_ENTROPY_MIN
        assert unique >= 200

    def test_entropy_returned_even_when_not_encrypted(self):
        _, entropy, _ = detect_encrypted_dex(_low_entropy_blob(8192))
        assert entropy == 0.0


# ============================================================
# Stub Application detection
# ============================================================
class TestStubApplication:
    def test_full_sized_app_not_stub(self):
        smali = "\n".join(
            f"    # line {i}" for i in range(100)
        ) + "\n    invoke-static {}, Ljava/lang/System;->loadLibrary()V"
        is_stub, count, matched = detect_stub_application(smali)
        assert is_stub is False
        assert count > _STUB_APP_MAX_LINES

    def test_small_app_with_loadlibrary_is_stub(self):
        smali = (
            ".class public Lcom/x/App;\n"
            ".super Landroid/app/Application;\n"
            "    invoke-static {}, Ljava/lang/System;->loadLibrary()V\n"
        )
        is_stub, count, matched = detect_stub_application(smali)
        assert is_stub is True
        assert count <= _STUB_APP_MAX_LINES
        assert "loadLibrary" in matched

    def test_small_app_no_keywords_not_stub(self):
        smali = ".class public Lcom/x/App;\n.super Ljava/lang/Object;\n"
        is_stub, _, matched = detect_stub_application(smali)
        assert is_stub is False
        assert matched == []

    def test_empty_string_not_stub(self):
        is_stub, count, _ = detect_stub_application("")
        assert is_stub is False
        assert count == 0


# ============================================================
# Main detect — via bytecode
# ============================================================
class TestDetectViaBytecode:
    def test_missing_apk_returns_none(self, tmp_path):
        result = detect_packer_via_bytecode(str(tmp_path / "nope.apk"))
        assert result is None

    def test_empty_apk_returns_none(self, tmp_path):
        apk = _make_apk(tmp_path, "empty.apk", {})
        assert detect_packer_via_bytecode(apk) is None

    def test_no_dex_returns_none(self, tmp_path):
        apk = _make_apk(tmp_path, "nodx.apk",
                        {"resources.arsc": b"blob"})
        assert detect_packer_via_bytecode(apk) is None

    def test_clean_dex_returns_none(self, tmp_path):
        dex = _fake_dex(strings=["Lcom/example/Foo;",
                                 "Lcom/example/Bar;"])
        apk = _make_apk(tmp_path, "clean.apk", {"classes.dex": dex})
        assert detect_packer_via_bytecode(apk) is None

    def test_tencent_detected(self, tmp_path):
        dex = _fake_dex(
            strings=["Lcom/tencent/StubShell/StubApp;"],
        )
        apk = _make_apk(tmp_path, "tx.apk", {"classes.dex": dex})
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        assert "Tencent" in result.name
        assert result.patchable is False

    def test_qihoo_360_detected(self, tmp_path):
        dex = _fake_dex(strings=["Lcom/stub/StubApp;"])
        apk = _make_apk(tmp_path, "360.apk", {"classes.dex": dex})
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        assert "360" in result.name

    def test_bangcle_detected(self, tmp_path):
        dex = _fake_dex(
            strings=["Lcom/bangcle/andJNI/JNIWrapper;"],
        )
        apk = _make_apk(tmp_path, "bangcle.apk", {"classes.dex": dex})
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        assert "Bangcle" in result.name

    def test_ijiami_detected(self, tmp_path):
        dex = _fake_dex(strings=["Lcom/shell/SuperApplication;"])
        apk = _make_apk(tmp_path, "ijiami.apk", {"classes.dex": dex})
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        assert "Ijiami" in result.name

    def test_pairip_detected(self, tmp_path):
        dex = _fake_dex(
            strings=["Lcom/pairip/VMRunner;",
                     "Lcom/pairip/application/Application;"],
        )
        apk = _make_apk(tmp_path, "pairip.apk", {"classes.dex": dex})
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        assert "PairIP" in result.name
        assert result.patchable is False
        assert result.confidence == "high"

    def test_evidence_populated(self, tmp_path):
        dex = _fake_dex(strings=["Lcom/pairip/VMRunner;"])
        apk = _make_apk(tmp_path, "pairip.apk", {"classes.dex": dex})
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        assert len(result.evidence) > 0
        assert any("stub_class" in e for e in result.evidence)

    def test_strongest_wins(self, tmp_path):
        """PairIP + Tencent → strongest score wins."""
        dex = _fake_dex(strings=[
            "Lcom/tencent/StubShell/StubApp;",     # +3
            "Lcom/pairip/VMRunner;",               # +3 (PairIP)
            "Lcom/pairip/application/Application;",  # +3 more (PairIP)
        ])
        apk = _make_apk(tmp_path, "multi.apk", {"classes.dex": dex})
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        assert "PairIP" in result.name

    def test_multi_dex_aggregate(self, tmp_path):
        """Evidence across multiple dex files."""
        dex1 = _fake_dex(strings=["Lcom/pairip/VMRunner;"])
        dex2 = _fake_dex(
            strings=["Lcom/pairip/application/Application;"],
        )
        apk = _make_apk(tmp_path, "multi.apk", {
            "classes.dex": dex1,
            "classes2.dex": dex2,
        })
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        assert "PairIP" in result.name

    def test_encrypted_dex_signal(self, tmp_path):
        """High-entropy dex + stub class → stronger signal."""
        payload = (
            b"Lcom/pairip/VMRunner;\x00"
            + os.urandom(16384)
        )
        apk = _make_apk(tmp_path, "enc.apk", {"classes.dex": payload})
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        assert result.entropy > 7.0
        assert any("encrypted_dex" in e for e in result.evidence)

    def test_native_mass_signal(self, tmp_path):
        """Arxan requires ≥5 native methods."""
        dex = _fake_dex(
            strings=["Lcom/arxan/Foo;"],
            native_count=10,
        )
        apk = _make_apk(tmp_path, "arxan.apk", {"classes.dex": dex})
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        assert "Arxan" in result.name
        assert result.native_count >= 5

    def test_custom_signatures_override(self, tmp_path):
        dex = _fake_dex(strings=["Lcom/custom/Stub;"])
        apk = _make_apk(tmp_path, "custom.apk", {"classes.dex": dex})

        import re
        custom = {
            "CustomPacker": {
                "stub_classes": [re.compile(r"Lcom/custom/Stub;")],
                "invocations": [],
                "encrypted_dex": False,
                "native_mass": None,
                "stub_app_min": None,
                "confidence": "high",
                "patchable": False,
                "notes": "test",
            },
        }
        result = detect_packer_via_bytecode(apk, signatures=custom)
        assert result is not None
        assert result.name == "CustomPacker"


# ============================================================
# augment_packer_result
# ============================================================
class TestAugment:
    def test_primary_wins_when_not_none(self, tmp_path):
        primary = {
            "name": "PrimaryPacker",
            "confidence": "high",
            "patchable": False,
        }
        result = augment_packer_result(str(tmp_path / "x.apk"), primary)
        assert result is primary

    def test_fallback_used_when_primary_none(self, tmp_path):
        dex = _fake_dex(strings=["Lcom/pairip/VMRunner;"])
        apk = _make_apk(tmp_path, "p.apk", {"classes.dex": dex})
        result = augment_packer_result(apk, None)
        assert result is not None
        assert "PairIP" in result["name"]
        assert result["source"] == "bytecode"

    def test_no_detection_returns_none(self, tmp_path):
        dex = _fake_dex(strings=["Lcom/example/Foo;"])
        apk = _make_apk(tmp_path, "c.apk", {"classes.dex": dex})
        result = augment_packer_result(apk, None)
        assert result is None

    def test_missing_apk_returns_none(self, tmp_path):
        result = augment_packer_result(str(tmp_path / "nope.apk"), None)
        assert result is None


# ============================================================
# Signature table integrity
# ============================================================
class TestSignatureTable:
    def test_all_entries_have_required_keys(self):
        required = {"stub_classes", "invocations", "confidence",
                    "patchable", "notes"}
        for name, sig in _BYTECODE_SIGNATURES.items():
            assert required.issubset(sig.keys()), f"{name} missing keys"

    def test_confidence_values_valid(self):
        valid = {"high", "medium", "low"}
        for sig in _BYTECODE_SIGNATURES.values():
            assert sig["confidence"] in valid

    def test_patchable_is_bool(self):
        for sig in _BYTECODE_SIGNATURES.values():
            assert isinstance(sig["patchable"], bool)

    def test_stub_classes_are_compiled_patterns(self):
        import re
        for sig in _BYTECODE_SIGNATURES.values():
            for pat in sig["stub_classes"]:
                assert isinstance(pat, re.Pattern)


# ============================================================
# Error handling
# ============================================================
class TestErrorHandling:
    def test_corrupt_zip_graceful(self, tmp_path):
        bad = tmp_path / "bad.apk"
        bad.write_bytes(b"not a zip")
        result = detect_packer_via_bytecode(str(bad))
        assert result is None

    def test_bad_dex_entry_skipped(self, tmp_path):
        """Nếu 1 dex lỗi, các dex khác vẫn được scan."""
        apk = tmp_path / "mixed.apk"
        with zipfile.ZipFile(apk, "w") as z:
            z.writestr("classes.dex", _fake_dex(
                strings=["Lcom/pairip/VMRunner;"]
            ))
            z.writestr("classes2.dex", b"corrupt-dex")
        result = detect_packer_via_bytecode(str(apk))
        assert result is not None
        assert "PairIP" in result.name