"""
E2E test — chạy AppDeepAnalyzer trên APK thật (Test.apk).

Skip nếu Test.apk không tồn tại hoặc < 1 MB.

Mục đích:
  - Verify full stack: manifest parse + dex scan + packer detect +
    security check + classifier.
  - Confirm PairIP detection hoạt động end-to-end trên real APK.

Không assert exact values (APK có thể đổi) — chỉ assert shape +
nội dung tối thiểu.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEST_APK = _REPO_ROOT / "Test.apk"

pytestmark = pytest.mark.skipif(
    not _TEST_APK.exists() or _TEST_APK.stat().st_size < 1024 * 1024,
    reason="Test.apk missing or < 1 MB",
)


# ============================================================
# Full analyzer E2E
# ============================================================
class TestAnalyzerE2E:
    def test_analyze_returns_findings_and_summary(self):
        from scanner.analyzer import AppDeepAnalyzer

        analyzer = AppDeepAnalyzer(str(_TEST_APK))
        findings = analyzer.analyze(force_reanalyze=True)

        assert isinstance(findings, list)
        assert len(findings) > 0

        summary = analyzer.get_summary()
        assert isinstance(summary, dict)
        assert summary.get("package"), "package name missing"
        assert isinstance(summary.get("app_name"), str)

    def test_summary_has_real_package(self):
        from scanner.analyzer import AppDeepAnalyzer

        analyzer = AppDeepAnalyzer(str(_TEST_APK))
        analyzer.analyze(force_reanalyze=True)
        summary = analyzer.get_summary()

        pkg = summary.get("package", "")
        assert "." in pkg, f"Invalid package: {pkg}"

    def test_findings_have_required_shape(self):
        from scanner.analyzer import AppDeepAnalyzer

        analyzer = AppDeepAnalyzer(str(_TEST_APK))
        findings = analyzer.analyze(force_reanalyze=True)

        for f in findings:
            assert "type" in f, f"Finding missing 'type': {f}"
            assert "title" in f, f"Finding missing 'title': {f}"
            assert "color" in f

    def test_colors_returned(self):
        from scanner.analyzer import AppDeepAnalyzer

        analyzer = AppDeepAnalyzer(str(_TEST_APK))
        analyzer.analyze(force_reanalyze=True)
        colors = analyzer.get_colors()

        assert isinstance(colors, list)
        assert len(colors) >= 1
        valid = {
            "green", "blue", "yellow", "purple",
            "orange", "red", "white",
        }
        for c in colors:
            assert c in valid, f"Unknown color: {c}"


# ============================================================
# Packer detection specific
# ============================================================
class TestPackerE2E:
    def test_pairip_detected_in_test_apk(self):
        """
        Test.apk là PairIP-protected. Verify detection end-to-end.
        """
        from scanner.analyzer import AppDeepAnalyzer

        analyzer = AppDeepAnalyzer(str(_TEST_APK))
        analyzer.analyze(force_reanalyze=True)

        packer = getattr(analyzer, "packer_info", None)
        assert packer is not None, "packer_info missing"
        assert isinstance(packer, dict)
        assert "PairIP" in packer.get("name", ""), (
            f"Expected PairIP, got {packer}"
        )
        assert packer.get("patchable") is False

    def test_packer_finding_in_findings_list(self):
        from scanner.analyzer import AppDeepAnalyzer

        analyzer = AppDeepAnalyzer(str(_TEST_APK))
        findings = analyzer.analyze(force_reanalyze=True)

        packer_findings = [
            f for f in findings if f.get("type") == "packer"
        ]
        assert packer_findings, "No packer finding emitted"
        assert "PairIP" in packer_findings[0].get("title", "")


# ============================================================
# Cache round-trip — relative comparison (robust trên mọi machine)
# ============================================================
class TestAnalyzerCacheE2E:
    def test_second_analyze_is_significantly_faster(self):
        """
        Cache hit phải nhanh hơn full scan ít nhất 5× (thực tế ~50-100×).
        Relative threshold tránh flaky test trên máy chậm.

        Note: full scan trên Test.apk mất ~60-180s; cache hit ~1s.
        """
        import time
        from scanner.analyzer import AppDeepAnalyzer

        # 1) Full scan (force)
        a1 = AppDeepAnalyzer(str(_TEST_APK))
        t0 = time.monotonic()
        a1.analyze(force_reanalyze=True)
        full_scan_dt = time.monotonic() - t0
        assert full_scan_dt > 5.0, (
            f"Full scan quá nhanh ({full_scan_dt:.2f}s) — "
            f"có thể cache bị stale, test invalid"
        )

        # 2) Cache hit (no force)
        a2 = AppDeepAnalyzer(str(_TEST_APK))
        t0 = time.monotonic()
        a2.analyze(force_reanalyze=False)
        cached_dt = time.monotonic() - t0

        speedup = full_scan_dt / max(cached_dt, 0.001)
        assert speedup >= 5.0, (
            f"Cache không hiệu quả: full={full_scan_dt:.2f}s, "
            f"cached={cached_dt:.2f}s, speedup={speedup:.1f}× "
            f"(expected ≥5×)"
        )

    def test_cache_returns_same_packer_result(self):
        """Cache hit phải trả cùng packer_info như full scan."""
        from scanner.analyzer import AppDeepAnalyzer

        a1 = AppDeepAnalyzer(str(_TEST_APK))
        a1.analyze(force_reanalyze=True)
        full_packer = getattr(a1, "packer_info", None)

        a2 = AppDeepAnalyzer(str(_TEST_APK))
        a2.analyze(force_reanalyze=False)
        cached_packer = getattr(a2, "packer_info", None)

        assert full_packer is not None
        assert cached_packer is not None
        assert full_packer.get("name") == cached_packer.get("name")
        assert full_packer.get("patchable") == cached_packer.get("patchable")


# ============================================================
# Security check E2E
# ============================================================
class TestSecurityE2E:
    def test_root_detection_finding_present(self):
        from scanner.analyzer import AppDeepAnalyzer

        analyzer = AppDeepAnalyzer(str(_TEST_APK))
        findings = analyzer.analyze(force_reanalyze=True)

        root_findings = [
            f for f in findings if f.get("type") == "root_detection"
        ]
        assert root_findings, "No root_detection finding"

    def test_lp_detection_finding_present(self):
        from scanner.analyzer import AppDeepAnalyzer

        analyzer = AppDeepAnalyzer(str(_TEST_APK))
        findings = analyzer.analyze(force_reanalyze=True)

        lp_findings = [
            f for f in findings if f.get("type") == "lp_detection"
        ]
        assert lp_findings, "No lp_detection finding"