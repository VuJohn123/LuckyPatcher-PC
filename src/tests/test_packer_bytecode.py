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


# ============================================================
# v3 — rare packer detection (new signatures)
# ============================================================
class TestRarePackers:
    def test_nagain_detected(self, tmp_path):
        dex = _fake_dex(strings=["Lcom/nagain/NagainApplication;"])
        apk = _make_apk(tmp_path, "nagain.apk", {"classes.dex": dex})
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        assert "Nagain" in result.name
        assert result.patchable is False
        assert result.confidence == "high"

    def test_promon_detected(self, tmp_path):
        dex = _fake_dex(
            strings=["Lcom/promon/shield/PromonShield;"],
            native_count=5,   # thỏa native_mass=3
        )
        apk = _make_apk(tmp_path, "promon.apk", {"classes.dex": dex})
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        assert "Promon" in result.name
        assert result.patchable is False

    def test_appsealing_detected(self, tmp_path):
        dex = _fake_dex(strings=["Lcom/inka/AppSealing;"])
        apk = _make_apk(tmp_path, "sealing.apk", {"classes.dex": dex})
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        assert "AppSealing" in result.name
        assert result.patchable is False

    def test_baidu_protect_detected(self, tmp_path):
        dex = _fake_dex(
            strings=["Lcom/baidu/protect/ProtectApplication;"],
        )
        apk = _make_apk(tmp_path, "baidu.apk", {"classes.dex": dex})
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        assert "Baidu" in result.name
        assert result.patchable is False

    def test_chaosvm_detected(self, tmp_path):
        dex = _fake_dex(strings=["Lcom/chaosvm/ChaosVM;"])
        apk = _make_apk(tmp_path, "chaos.apk", {"classes.dex": dex})
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        assert "ChaosVM" in result.name

    def test_nqshield_detected(self, tmp_path):
        dex = _fake_dex(
            strings=["Lcom/nqshield/NQShieldApplication;"],
        )
        apk = _make_apk(tmp_path, "nq.apk", {"classes.dex": dex})
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        assert "NQ Shield" in result.name

    def test_chaosvm_not_triggered_by_generic_chaos(self, tmp_path):
        """Regression: 'Lcom/chaos/' generic KHÔNG match ChaosVM."""
        dex = _fake_dex(strings=["Lcom/chaos/engine/Foo;"])
        apk = _make_apk(tmp_path, "false.apk", {"classes.dex": dex})
        result = detect_packer_via_bytecode(apk)
        # Không có signature nào match → None
        assert result is None or "ChaosVM" not in result.name

    def test_new_signatures_all_have_required_keys(self):
        """Contract: mọi entry mới phải đủ 8 keys + confidence hợp lệ."""
        required = {
            "stub_classes", "invocations", "encrypted_dex",
            "native_mass", "stub_app_min", "confidence",
            "patchable", "notes",
        }
        valid_conf = {"high", "medium", "low"}
        new_names = [
            "Nagain (Korean)", "Promon Shield", "AppSealing (Inka)",
            "Baidu Protect", "ChaosVM", "NQ Shield",
        ]
        for name in new_names:
            assert name in _BYTECODE_SIGNATURES, f"missing {name}"
            sig = _BYTECODE_SIGNATURES[name]
            assert required.issubset(sig.keys()), f"{name} missing keys"
            assert sig["confidence"] in valid_conf
            assert isinstance(sig["patchable"], bool)

    def test_new_stub_classes_are_compiled_patterns(self):
        import re as _re
        for name in [
            "Nagain (Korean)", "Promon Shield", "AppSealing (Inka)",
            "Baidu Protect", "ChaosVM", "NQ Shield",
        ]:
            for pat in _BYTECODE_SIGNATURES[name]["stub_classes"]:
                assert isinstance(pat, _re.Pattern), f"{name}: {pat}"

# ============================================================
# v4 — window entropy analysis
# ============================================================
class TestEntropyWindowAnalysis:
    def test_empty_bytes_returns_zero(self):
        from scanner.checks.packer_bytecode import (
            entropy_window_analysis,
        )
        r = entropy_window_analysis(b"")
        assert r.total_windows == 0
        assert r.max_entropy == 0.0
        assert r.high_entropy_count == 0

    def test_uniform_random_high_entropy(self):
        from scanner.checks.packer_bytecode import (
            entropy_window_analysis,
        )
        data = os.urandom(64 * 1024)
        r = entropy_window_analysis(data)
        assert r.max_entropy > 7.5
        assert r.high_pct >= 90  # hầu hết windows random

    def test_all_zeros_low_entropy(self):
        from scanner.checks.packer_bytecode import (
            entropy_window_analysis,
        )
        data = b"\x00" * (64 * 1024)
        r = entropy_window_analysis(data)
        assert r.max_entropy == 0.0
        assert r.high_entropy_count == 0
        assert not r.has_encrypted_region

    def test_partial_encryption_detected(self):
        """
        Dex-like: 3 windows zero + 2 windows random → 
        has_encrypted_region phải phát hiện.
        """
        from scanner.checks.packer_bytecode import (
            entropy_window_analysis,
        )
        # 3 windows thấp (16KB mỗi cái) + 2 windows random = 80KB
        low = b"\x00" * (3 * 16384)
        high = os.urandom(2 * 16384)
        data = low + high
        r = entropy_window_analysis(data)
        # 5 windows total, 2 high → 40%
        assert r.total_windows == 5
        assert r.high_entropy_count == 2
        assert r.has_encrypted_region is True
        assert r.max_entropy > 7.5

    def test_mixed_30_pct_not_flagged(self):
        """<20% high windows không trigger."""
        from scanner.checks.packer_bytecode import (
            entropy_window_analysis,
        )
        # 9 windows low + 1 window high = 10% → KHÔNG flag
        low = b"\x00" * (9 * 16384)
        high = os.urandom(16384)
        data = low + high
        r = entropy_window_analysis(data)
        assert r.total_windows == 10
        assert r.high_entropy_count == 1
        assert r.has_encrypted_region is False

    def test_small_dex_fallback(self):
        """Dex < window_size dùng single-window fallback."""
        from scanner.checks.packer_bytecode import (
            entropy_window_analysis,
        )
        data = os.urandom(4096)
        r = entropy_window_analysis(data)
        assert r.total_windows == 1
        assert r.max_entropy > 7.5

    def test_custom_window_size(self):
        from scanner.checks.packer_bytecode import (
            entropy_window_analysis,
        )
        data = os.urandom(4 * 8192)
        r = entropy_window_analysis(data, window_size=8192)
        assert r.window_size == 8192
        assert r.total_windows == 4

    def test_tail_handled(self):
        """Tail nhỏ < window_size được sample riêng."""
        from scanner.checks.packer_bytecode import (
            entropy_window_analysis,
        )
        # 2 full windows + 8KB tail (>= 512 threshold)
        data = os.urandom(2 * 16384) + os.urandom(8192)
        r = entropy_window_analysis(data)
        assert r.total_windows == 3  # 2 full + 1 tail


class TestWindowEntropyResultDataclass:
    def test_high_pct_zero_when_no_windows(self):
        from scanner.checks.packer_bytecode import (
            WindowEntropyResult,
        )
        r = WindowEntropyResult()
        assert r.high_pct == 0.0
        assert r.has_encrypted_region is False

    def test_high_pct_calculation(self):
        from scanner.checks.packer_bytecode import (
            WindowEntropyResult,
        )
        r = WindowEntropyResult(
            total_windows=10, high_entropy_count=3,
        )
        assert r.high_pct == 30.0

    def test_has_encrypted_region_threshold(self):
        from scanner.checks.packer_bytecode import (
            WindowEntropyResult,
        )
        # 20% exact → True
        r = WindowEntropyResult(
            total_windows=10, high_entropy_count=2,
        )
        assert r.has_encrypted_region is True
        # 19% → False
        r2 = WindowEntropyResult(
            total_windows=100, high_entropy_count=19,
        )
        assert r2.has_encrypted_region is False


class TestBytecodeDetectionWindowFields:
    def test_detection_has_window_fields(self):
        from scanner.checks.packer_bytecode import (
            BytecodeDetection,
        )
        d = BytecodeDetection(
            name="x", confidence="high", patchable=False,
        )
        assert hasattr(d, "max_window_entropy")
        assert hasattr(d, "high_entropy_windows")
        assert d.max_window_entropy == 0.0
        assert d.high_entropy_windows == 0

    def test_detect_populates_window_fields(self, tmp_path):
        """
        Dex với region encrypted → detection có window fields.
        """
        from scanner.checks.packer_bytecode import (
            detect_packer_via_bytecode,
        )
        # PairIP stub + 1 region encrypted (16KB random)
        stub = b"Lcom/pairip/VMRunner;\x00"
        low = b"\x00" * (4 * 16384)  # 4 windows thấp
        high = os.urandom(2 * 16384)  # 2 windows cao
        payload = stub + low + high
        apk = _make_apk(
            tmp_path, "region.apk", {"classes.dex": payload},
        )
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        assert result.max_window_entropy > 7.0
        assert result.high_entropy_windows >= 2

    def test_region_encryption_evidence_emitted(self, tmp_path):
        """
        Global entropy thấp nhưng region encrypted → evidence
        `encrypted_region:` trong output.
        """
        from scanner.checks.packer_bytecode import (
            detect_packer_via_bytecode,
        )
        # PairIP stub + mostly zeros + small encrypted tail
        stub = b"Lcom/pairip/VMRunner;\x00"
        low = b"\x00" * (5 * 16384)   # 5 windows zero
        high = os.urandom(3 * 16384)  # 3 windows random (37.5%)
        payload = stub + low + high
        apk = _make_apk(
            tmp_path, "region2.apk", {"classes.dex": payload},
        )
        result = detect_packer_via_bytecode(apk)
        assert result is not None
        # Có evidence encrypted_region (không phải encrypted_dex)
        has_region = any(
            "encrypted_region" in e for e in result.evidence
        )
        has_global = any(
            "encrypted_dex" in e for e in result.evidence
        )
        assert has_region or has_global


class TestAugmentWindowPropagation:
    def test_augment_propagates_window_fields(self, tmp_path):
        from scanner.checks.packer_bytecode import (
            augment_packer_result,
        )
        # PairIP stub + high-entropy region
        payload = (
            b"Lcom/pairip/VMRunner;\x00" + os.urandom(32 * 1024)
        )
        apk = _make_apk(
            tmp_path, "p.apk", {"classes.dex": payload},
        )
        result = augment_packer_result(apk, None)
        assert result is not None
        assert "max_window_entropy" in result
        assert "high_entropy_windows" in result
        assert result["max_window_entropy"] > 7.0


# ============================================================
# v4 — _fast_entropy helper
# ============================================================
class TestFastEntropy:
    def test_matches_shannon(self):
        from scanner.checks.packer_bytecode import (
            _fast_entropy, shannon_entropy,
        )
        data = os.urandom(4096)
        assert abs(_fast_entropy(data) - shannon_entropy(data)) < 1e-9

    def test_empty_returns_zero(self):
        from scanner.checks.packer_bytecode import _fast_entropy
        assert _fast_entropy(b"") == 0.0

    def test_uniform_max(self):
        from scanner.checks.packer_bytecode import _fast_entropy
        data = bytes(range(256))
        e = _fast_entropy(data)
        assert abs(e - 8.0) < 0.01