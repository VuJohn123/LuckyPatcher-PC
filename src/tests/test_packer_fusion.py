"""Test scanner/checks/packer_fusion.py — precision fusion verdicts."""
from __future__ import annotations

import zipfile

from scanner.checks.packer_fusion import (
    BypassStrategy,
    PackabilityAssessment,
    _match_signature_name,
    assess_packability,
    bytecode_signal,
    entropy_signal,
    structural_signal,
)
from scanner.dex_index import DexIndex


# ============================================================
# Helpers
# ============================================================
def _make_apk(tmp_path, name: str, dex_payload: bytes | None = None):
    apk = tmp_path / name
    with zipfile.ZipFile(apk, "w") as z:
        if dex_payload is not None:
            z.writestr("classes.dex", dex_payload)
    return str(apk)


def _fake_dex(classes: list[str], padding: int = 0) -> bytes:
    """Fake dex bytes chứa class descriptors + optional padding."""
    blob = b"".join(
        b"L" + c.replace(".", "/").encode() + b";" for c in classes
    )
    return b"dex\n035\x00" + blob + b"\x00" * padding


def _index(*classes: str) -> DexIndex:
    lowered = [c.lower() for c in classes]
    return DexIndex(classes=list(classes), classes_lower=lowered)


def _own_classes(package: str, count: int) -> list[str]:
    prefix = "L" + package.replace(".", "/") + "/"
    return [f"{prefix}Class{i};" for i in range(count)]


# ============================================================
# structural_signal
# ============================================================
class TestStructuralSignal:
    def test_none_index(self):
        cc, own, mb, density = structural_signal(None, "com.x", 1024 * 1024)
        assert cc == 0
        assert own == 0
        assert mb == 1.0
        assert density == 0.0

    def test_counts_own_package(self):
        classes = _own_classes("com.example", 7) + ["Lcom/other/Foo;"]
        idx = _index(*classes)
        cc, own, _mb, _d = structural_signal(idx, "com.example", 1024 * 1024)
        assert cc == 8
        assert own == 7

    def test_package_with_dots_maps_to_slashes(self):
        idx = _index("Lcom/deep/pkg/A;", "Lcom/deep/pkg/B;")
        _cc, own, _mb, _d = structural_signal(idx, "com.deep.pkg", 1024)
        assert own == 2

    def test_prefix_is_boundary_aware(self):
        # `com.example2` must not count as `com.example`.
        idx = _index("Lcom/example2/A;", "Lcom/example/A;")
        _cc, own, _mb, _d = structural_signal(idx, "com.example", 1024)
        assert own == 1

    def test_no_package_no_own(self):
        idx = _index(*_own_classes("com.example", 5))
        cc, own, _mb, _d = structural_signal(idx, None, 1024)
        assert cc == 5
        assert own == 0

    def test_density_math(self):
        idx = _index(*[f"La/C{i};" for i in range(200)])
        _cc, _own, mb, density = structural_signal(idx, None, 2 * 1024 * 1024)
        assert mb == 2.0
        assert density == 100.0

    def test_zero_bytes_no_div_by_zero(self):
        idx = _index("La/B;")
        _cc, _own, mb, density = structural_signal(idx, None, 0)
        assert mb == 0.0
        assert density == 0.0


# ============================================================
# entropy_signal
# ============================================================
class TestEntropySignal:
    def test_empty_entries(self):
        assert entropy_signal([]) == (0.0, 0.0)

    def test_low_entropy_plain_dex(self):
        # Highly compressible payload → entropy well below 7.5.
        raw = b"A" * 65536
        max_e, pct = entropy_signal([("classes.dex", raw)])
        assert max_e < 7.5
        assert pct == 0.0

    def test_high_entropy_random_dex(self):
        import os
        raw = os.urandom(65536)
        max_e, pct = entropy_signal([("classes.dex", raw)])
        assert max_e >= 7.5
        assert pct >= 20.0

    def test_mixed_uses_max_and_ratio(self):
        import os
        plain = b"\x00" * 32768
        random = os.urandom(32768)
        max_e, pct = entropy_signal([
            ("classes.dex", plain),
            ("classes2.dex", random),
        ])
        assert max_e >= 7.5
        assert 0.0 < pct < 100.0

    def test_skips_empty_payloads(self):
        assert entropy_signal([("classes.dex", b"")]) == (0.0, 0.0)


# ============================================================
# bytecode_signal
# ============================================================
class TestBytecodeSignal:
    def test_index_path_scores_stub_class(self, tmp_path):
        apk = _make_apk(tmp_path, "a.apk", _fake_dex(["com.pairip.application.Application"]))
        idx = _index("Lcom/pairip/application/Application;")
        score, evidence = bytecode_signal(
            apk, "PairIP (Google Play)", index=idx, dex_entries=[]
        )
        assert score >= 3
        assert any(e.startswith("stub_class:") for e in evidence)

    def test_index_path_no_match(self, tmp_path):
        apk = _make_apk(tmp_path, "a.apk", _fake_dex(["com.example.App"]))
        idx = _index("Lcom/example/App;")
        score, evidence = bytecode_signal(
            apk, "PairIP (Google Play)", index=idx, dex_entries=[]
        )
        assert score == 0
        assert evidence == []

    def test_encrypted_signal_added_when_bad(self, tmp_path):
        apk = _make_apk(tmp_path, "a.apk", _fake_dex(["com.pairip.VMRunner"]))
        idx = _index("Lcom/pairip/VMRunner;")
        score_bad, ev_bad = bytecode_signal(
            apk, "PairIP (Google Play)", index=idx, dex_entries=[],
            entropy_bad=True,
        )
        score_ok, _ev_ok = bytecode_signal(
            apk, "PairIP (Google Play)", index=idx, dex_entries=[],
            entropy_bad=False,
        )
        assert score_bad == score_ok + 2
        assert any(e.startswith("encrypted_region") for e in ev_bad)

    def test_missing_apk_without_index_returns_zero(self, tmp_path):
        missing = str(tmp_path / "nope.apk")
        assert bytecode_signal(missing, "PairIP (Google Play)") == (0, [])


# ============================================================
# _match_signature_name
# ============================================================
class TestMatchSignatureName:
    def test_exact(self):
        from scanner.checks.packer_bytecode import _BYTECODE_SIGNATURES
        sig = _match_signature_name("PairIP (Google Play)", _BYTECODE_SIGNATURES)
        assert sig is not None
        assert sig is _BYTECODE_SIGNATURES["PairIP (Google Play)"]

    def test_token_prefix(self):
        from scanner.checks.packer_bytecode import _BYTECODE_SIGNATURES
        sig = _match_signature_name("PairIP", _BYTECODE_SIGNATURES)
        assert sig is not None

    def test_unknown_returns_none(self):
        assert _match_signature_name("Totally Unknown Packer", {}) is None


# ============================================================
# assess_packability — case matrix
# ============================================================
class TestAssessNoPacker:
    def test_clean_apk_is_plaintext(self, tmp_path):
        apk = _make_apk(tmp_path, "a.apk", _fake_dex(["com.example.App"]))
        a = assess_packability(apk, None)
        assert a.patchable is True
        assert a.strategy is BypassStrategy.DEX_PLAINTEXT
        assert a.confidence == "high"


class TestAssessCaseA:
    def test_readable_app_dex_is_plaintext(self, tmp_path):
        pkg = "com.example"
        classes = _own_classes(pkg, 30) + ["Lcom/pairip/application/Application;"]
        idx = _index(*classes)
        dex = _fake_dex(classes, padding=200_000)
        apk = _make_apk(tmp_path, "a.apk", dex)

        a = assess_packability(
            apk, "PairIP (Google Play)", index=idx, package=pkg,
            dex_entries=[("classes.dex", dex)],
        )
        assert a.patchable is True
        assert a.strategy is BypassStrategy.DEX_PLAINTEXT
        assert a.confidence == "high"
        assert a.own_package_classes == 30

    def test_medium_confidence_below_20_classes(self, tmp_path):
        pkg = "com.example"
        classes = _own_classes(pkg, 8)
        idx = _index(*classes)
        dex = _fake_dex(classes, padding=10_000)
        apk = _make_apk(tmp_path, "a.apk", dex)

        a = assess_packability(
            apk, "PairIP", index=idx, package=pkg,
            dex_entries=[("classes.dex", dex)],
        )
        assert a.patchable is True
        assert a.confidence == "medium"

    def test_native_enforcement_caveat_in_rationale(self, tmp_path):
        pkg = "com.example"
        classes = _own_classes(pkg, 30)
        idx = _index(*classes)
        dex = _fake_dex(classes, padding=200_000)
        apk = _make_apk(tmp_path, "a.apk", dex)

        a = assess_packability(
            apk, "PairIP (Google Play)", index=idx, package=pkg,
            dex_entries=[("classes.dex", dex)],
        )
        assert "native code" in a.rationale

    def test_no_caveat_for_non_native_packer(self, tmp_path):
        pkg = "com.example"
        classes = _own_classes(pkg, 30)
        idx = _index(*classes)
        dex = _fake_dex(classes, padding=200_000)
        apk = _make_apk(tmp_path, "a.apk", dex)

        a = assess_packability(
            apk, "DexGuard (Guardsquare)", index=idx, package=pkg,
            dex_entries=[("classes.dex", dex)],
        )
        assert "native code" not in a.rationale


class TestAssessCaseB:
    def test_sparse_dex_needs_shell_swap(self, tmp_path):
        pkg = "com.example"
        # 8 own classes over 1 MB of dex → density 8/MB, below the 120 floor.
        classes = _own_classes(pkg, 8)
        idx = _index(*classes)
        dex = _fake_dex(classes, padding=1024 * 1024)
        apk = _make_apk(tmp_path, "a.apk", dex)

        a = assess_packability(
            apk, "Tencent Legu", index=idx, package=pkg,
            dex_entries=[("classes.dex", dex)],
        )
        assert a.patchable is True
        assert a.strategy is BypassStrategy.SHELL_SWAP
        assert a.confidence == "medium"


class TestAssessCaseC:
    def test_strong_stub_no_own_classes_neutralize(self, tmp_path):
        # Stub classes strongly matched, no own-package classes, low entropy.
        classes = [
            "Lcom/pairip/VMRunner;",
            "Lcom/pairip/StartupLauncher;",
        ]
        idx = _index(*classes)
        dex = _fake_dex(classes, padding=50_000)
        apk = _make_apk(tmp_path, "a.apk", dex)

        a = assess_packability(
            apk, "PairIP (Google Play)", index=idx, package="com.example",
            dex_entries=[("classes.dex", dex)],
        )
        assert a.patchable is True
        assert a.strategy is BypassStrategy.STUB_NEUTRALIZE
        assert a.confidence == "low"
        assert a.bytecode_score >= 4


class TestAssessCaseD:
    def test_encrypted_payload_requires_unpack(self, tmp_path):
        import os
        # Random dex → high entropy region, no readable classes.
        dex = os.urandom(200_000)
        apk = _make_apk(tmp_path, "a.apk", dex)

        a = assess_packability(
            apk, "Tencent Legu", index=None, package="com.example",
            dex_entries=[("classes.dex", dex)],
        )
        assert a.patchable is False
        assert a.strategy is BypassStrategy.UNPACK_REQUIRED
        assert a.confidence == "high"
        assert "encrypted" in a.rationale.lower()

    def test_no_classes_no_entropy_still_unpack(self, tmp_path):
        # Plain but empty payload → no own classes, no entropy signal.
        dex = _fake_dex([], padding=50_000)
        apk = _make_apk(tmp_path, "a.apk", dex)

        a = assess_packability(
            apk, "Promon Shield", index=_index(), package="com.example",
            dex_entries=[("classes.dex", dex)],
        )
        assert a.patchable is False
        assert a.strategy is BypassStrategy.UNPACK_REQUIRED
        assert a.confidence == "medium"

    def test_without_package_readable_dex_still_unpack(self, tmp_path):
        # Regression for Test.apk behaviour: no package → own classes 0.
        classes = _own_classes("com.example", 30)
        idx = _index(*classes)
        dex = _fake_dex(classes, padding=200_000)
        apk = _make_apk(tmp_path, "a.apk", dex)

        a = assess_packability(
            apk, "PairIP (Google Play)", index=idx, package=None,
            dex_entries=[("classes.dex", dex)],
        )
        assert a.patchable is False
        assert a.strategy is BypassStrategy.UNPACK_REQUIRED


# ============================================================
# PackabilityAssessment serialisation
# ============================================================
class TestAssessmentSerialisation:
    def test_to_dict_shape(self):
        a = PackabilityAssessment(
            packer_name="X",
            patchable=True,
            confidence="high",
            strategy=BypassStrategy.DEX_PLAINTEXT,
            rationale="ok",
            class_count=10,
            own_package_classes=7,
            dex_megabytes=2.0,
            class_density=5.0,
            max_window_entropy=7.25,
            high_entropy_pct=12.34,
            bytecode_score=5,
        )
        d = a.to_dict()
        assert d["strategy"] == "dex_plaintext"
        assert d["class_density"] == 5.0
        assert d["max_window_entropy"] == 7.25
        assert d["high_entropy_pct"] == 12.3
        assert d["bytecode_score"] == 5

    def test_strategy_values(self):
        assert BypassStrategy.DEX_PLAINTEXT.value == "dex_plaintext"
        assert BypassStrategy.SHELL_SWAP.value == "shell_swap"
        assert BypassStrategy.STUB_NEUTRALIZE.value == "stub_neutralize"
        assert BypassStrategy.UNPACK_REQUIRED.value == "unpack_required"


# ============================================================
# Entropy window sampling
# ============================================================
class TestWindowSampling:
    def test_max_windows_bounds_work(self):
        import os

        from scanner.checks.packer_bytecode import entropy_window_analysis

        raw = os.urandom(1024 * 1024)
        full = entropy_window_analysis(raw)
        sampled = entropy_window_analysis(raw, max_windows=20)
        assert sampled.total_windows <= 20
        assert sampled.total_windows < full.total_windows

    def test_max_windows_none_analyses_all(self):
        from scanner.checks.packer_bytecode import entropy_window_analysis

        raw = b"B" * (64 * 1024)
        result = entropy_window_analysis(raw, max_windows=None)
        assert result.total_windows == 4

    def test_tail_included_in_sampling(self):
        from scanner.checks.packer_bytecode import entropy_window_analysis

        # 2.5 windows → 2 full + 1 tail.
        raw = b"C" * (2 * 16384 + 1024)
        result = entropy_window_analysis(raw)
        assert result.total_windows == 3
