"""Phân tích sâu APK — trả về findings chi tiết.

v9 (2026):
  - FIX: cache restore path không set `self.packer_info`.
    → Reconstruct từ findings[type=='packer'] (không đổi API cache).
  - Cache version-aware (v9 bump invalidate cache cũ).

v8:
  - FAST path: ASCII regex cho security/license/iap/packer scan
    (~0.3s/dex) thay vì androguard DEX() (~5-8s/dex).
  - Shared `dex_names` cho root + LP.
  - Timing logs để debug performance.
"""
from __future__ import annotations

import logging
import time
import zipfile
from pathlib import Path

from androguard.core.apk import APK

from core.smali_utils import APKCache
from patcher.watermarker import Watermarker
from scanner.checks.license_check import check_license
from scanner.checks.ads_check import check_ads
from scanner.checks.iap_check import check_iap
from scanner.checks.packer_check import check_packer_with_fallback
from scanner.checks.security_check import (
    check_root_detection,
    check_lp_detection,
    _extract_dex_names,
)

logger = logging.getLogger(__name__)


# ============================================================
# CACHE VERSION
# ============================================================
# Bump khi thay đổi logic detection → tự động invalidate cache cũ.
#
# Lịch sử:
#   v1 — base
#   v2 — fix root detection strict patterns
#   v3 — fix root detection confidence scoring
#   v4 — share dex strings cache (perf, đã revert)
#   v5 — security check iterate classes+methods (fix test contract)
#   v6 — fast path strings + share dex_names
#   v7 — ASCII regex fast path cho security_check
#   v8 — ASCII regex cho license/iap/packer (final perf fix)
#   v9 — fix cache path restore packer_info (reconstruct từ findings)
# Dòng ~50
_ANALYZER_CACHE_VERSION = 10   # was 9


class AppDeepAnalyzer:
    """Phân tích sâu APK — phát hiện license/ads/iap/root/LP/packer."""

    def __init__(self, apk_path: str, patches_dir: str | None = None):
        self.apk_path = apk_path
        self.apk = APK(apk_path)
        self.patches_dir = patches_dir or str(
            Path(apk_path).parent.parent / "patches"
        )
        self.findings: list[dict] = []
        self.available_patches: list[str] = []
        self._cache = APKCache()
        self.packer_info: dict | None = None

    # ============================================================
    # PUBLIC — MAIN
    # ============================================================
    def analyze(self, force_reanalyze: bool = False) -> list[dict]:
        # Cache lookup with version
        if not force_reanalyze:
            cached = self._cache.get_cached_analysis(
                self.apk_path,
                min_version=_ANALYZER_CACHE_VERSION,
            )
            if cached:
                self.findings = cached.get("findings", [])
                self.available_patches = [
                    f["action"] for f in self.findings
                    if f.get("action")
                ]
                # FIX v9: restore packer_info từ findings (cache không
                # lưu attribute riêng). Nếu không có finding 'packer'
                # → None (khớp với full scan path khi clean).
                self.packer_info = self._reconstruct_packer_info(
                    self.findings
                )
                return self.findings

        t0 = time.monotonic()

        self._check_watermark()

        # Packer check trước license/iap
        t_packer = time.monotonic()
        self.packer_info = check_packer_with_fallback(
            self.apk, self.apk_path, self._get_all_dex_bytes,
            self.findings, self.available_patches,
        )
        logger.debug(
            "[analyzer] packer: %.2fs", time.monotonic() - t_packer,
        )

        t_lic = time.monotonic()
        check_license(
            self.apk, self.apk_path, self._get_all_dex_bytes,
            self.findings, self.available_patches,
        )
        logger.debug(
            "[analyzer] license: %.2fs", time.monotonic() - t_lic,
        )

        t_ads = time.monotonic()
        check_ads(self.apk, self.findings, self.available_patches)
        logger.debug(
            "[analyzer] ads: %.2fs", time.monotonic() - t_ads,
        )

        t_iap = time.monotonic()
        check_iap(
            self.apk, self._get_all_dex_bytes,
            self.findings, self.available_patches,
        )
        logger.debug(
            "[analyzer] iap: %.2fs", time.monotonic() - t_iap,
        )

        t_misc = time.monotonic()
        self._check_custom_patch()
        self._check_system_app()
        self._check_dangerous_permissions()
        self._count_components()
        logger.debug(
            "[analyzer] misc: %.2fs", time.monotonic() - t_misc,
        )

        # === Security checks — share dex_names ===
        t_sec = time.monotonic()
        dex_names = _extract_dex_names(self._get_all_dex_bytes)
        logger.info(
            "[analyzer] Extracted %d names in %.2fs",
            len(dex_names), time.monotonic() - t_sec,
        )

        t_root = time.monotonic()
        check_root_detection(
            self._get_all_dex_bytes, self.findings,
            all_names=dex_names,
        )
        logger.info(
            "[analyzer] Root check: %.3fs",
            time.monotonic() - t_root,
        )

        t_lp = time.monotonic()
        check_lp_detection(
            self._get_all_dex_bytes, self.findings,
            all_names=dex_names,
        )
        logger.info(
            "[analyzer] LP check: %.3fs", time.monotonic() - t_lp,
        )

        logger.info(
            "[analyzer] Total analyze: %.2fs", time.monotonic() - t0,
        )

        # Save cache
        try:
            self._cache.save_analysis(
                self.apk_path, self.findings,
                self.get_summary(), self.get_colors(),
                version=_ANALYZER_CACHE_VERSION,
            )
        except Exception as e:
            logger.debug("Cache save failed: %s", e)

        return self.findings

    # ============================================================
    # INTERNAL — cache packer reconstruction
    # ============================================================
    @staticmethod
    def _reconstruct_packer_info(
        findings: list[dict],
    ) -> dict | None:
        """
        Rebuild `packer_info` dict từ finding type=='packer'.

        Dùng cho cache restore path — cache lưu findings (đủ data),
        nhưng không lưu attribute `packer_info` riêng.

        Shape khớp với `check_packer_with_fallback` trả về:
            {name, confidence, patchable, evidence}

        Return None nếu không có finding 'packer' (APK clean).
        """
        for f in findings:
            if f.get("type") != "packer":
                continue

            title = f.get("title", "") or ""
            # check_packer format: "Packed: <name>"
            name = title
            if name.startswith("Packed: "):
                name = name[len("Packed: "):].strip()

            details = f.get("details", []) or []
            confidence = "unknown"
            evidence: list[str] = []
            for d in details:
                if isinstance(d, str) and d.startswith("Confidence: "):
                    confidence = d.split(": ", 1)[1].strip()
                elif isinstance(d, str) and d.startswith(
                    "Source: "
                ):
                    # Bytecode fallback marker — không phải evidence
                    continue
                else:
                    evidence.append(d)

            # Color mapping khớp với packer_check.py:
            #   yellow → patchable=True (obfuscator)
            #   red    → patchable=False (hard packer)
            patchable = f.get("color") == "yellow"

            return {
                "name": name,
                "confidence": confidence,
                "patchable": patchable,
                "evidence": evidence,
            }

        # Không có finding 'packer' → APK clean (khớp full scan path)
        return None

    # ============================================================
    # PUBLIC — summary / colors
    # ============================================================
    def get_colors(self) -> list[str]:
        return list({
            f["color"] for f in self.findings if f.get("color")
        }) or ["white"]

    def get_summary(self) -> dict:
        try:
            package = self.apk.get_package()
        except Exception:
            package = ""
        try:
            app_name = self.apk.get_app_name()
        except Exception:
            app_name = (
                Path(self.apk_path).stem if self.apk_path else "Unknown"
            )
        try:
            version = self.apk.get_androidversion_name()
        except Exception:
            version = ""
        try:
            size = Path(self.apk_path).stat().st_size
        except Exception:
            size = 0
        return {
            "app_name": app_name,
            "package": package,
            "version": version,
            "apk_path": self.apk_path,
            "size": size,
        }

    # ============================================================
    # INTERNAL — dex bytes
    # ============================================================
    def _get_all_dex_bytes(self) -> list[tuple[str, bytes]]:
        """Read dex bytes from APK. Graceful on corrupt zip."""
        dex_list: list[tuple[str, bytes]] = []
        try:
            with zipfile.ZipFile(self.apk_path, "r") as z:
                for name in z.namelist():
                    if not name.endswith(".dex"):
                        continue
                    try:
                        data = z.read(name)
                        if len(data) >= 2:
                            dex_list.append((name, data))
                    except Exception:
                        continue
        except Exception as e:
            logger.debug("Không mở được APK: %s", e)
        return dex_list

    # ============================================================
    # INTERNAL — individual checks
    # ============================================================
    def _check_watermark(self) -> None:
        marker = Watermarker.check_watermark(self.apk_path)
        if not marker:
            return
        import time as tm
        self.findings.append({
            "type": "watermark",
            "color": None,
            "title": "LP-PC Suite Patched",
            "description": (
                f"Đã vá vào "
                f"{tm.strftime('%Y-%m-%d %H:%M', tm.localtime(marker['timestamp']))}"
            ),
            "details": marker.get("patches", []),
            "action": None,
        })

    def _check_custom_patch(self) -> None:
        patch_files: list[str] = []
        try:
            p = Path(self.patches_dir)
            if p.exists():
                for f in p.iterdir():
                    if f.suffix in (".txt", ".lpzip"):
                        patch_files.append(f.name)
        except Exception:
            pass
        if patch_files:
            self.findings.append({
                "type": "custom_patch",
                "color": "yellow",
                "title": "Custom Patch Available",
                "description": f"{len(patch_files)} patch(es) found",
                "details": patch_files,
                "action": "apply_custom_patch",
            })
            self.available_patches.append("custom")
        else:
            self.findings.append({
                "type": "no_custom_patch",
                "color": None,
                "title": "Custom Patch",
                "description": "Not available",
                "details": [],
                "action": None,
            })

    def _check_system_app(self) -> None:
        try:
            pkg = self.apk.get_package()
        except Exception:
            return
        if not pkg.startswith(("com.android.", "com.google.android.")):
            return
        try:
            recvs = self.apk.get_receivers()
            has_boot = any("BOOT_COMPLETED" in str(r) for r in recvs)
        except Exception:
            has_boot = False
        if has_boot:
            self.findings.append({
                "type": "system_boot",
                "color": "purple",
                "title": "System Startup App",
                "description": "Starts at boot time",
                "details": [],
                "action": None,
            })
        else:
            self.findings.append({
                "type": "system",
                "color": "orange",
                "title": "System Application",
                "description": "Pre-installed system app",
                "details": [],
                "action": None,
            })

    def _check_dangerous_permissions(self) -> None:
        dangerous = (
            "android.permission.READ_SMS",
            "android.permission.SEND_SMS",
            "android.permission.RECEIVE_SMS",
            "android.permission.READ_CONTACTS",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.CAMERA",
            "android.permission.RECORD_AUDIO",
            "android.permission.READ_PHONE_STATE",
            "android.permission.CALL_PHONE",
            "android.permission.WRITE_EXTERNAL_STORAGE",
            "android.permission.READ_EXTERNAL_STORAGE",
        )
        try:
            found = [
                p.split(".")[-1]
                for p in self.apk.get_permissions()
                if p in dangerous
            ]
        except Exception:
            found = []
        if found:
            self.findings.append({
                "type": "permissions",
                "color": None,
                "title": "Dangerous Permissions",
                "description": f"{len(found)} dangerous permission(s)",
                "details": found,
                "action": "manage_permissions",
            })

    def _count_components(self) -> None:
        try:
            acts = len(self.apk.get_activities())
            srv = len(self.apk.get_services())
            recv = len(self.apk.get_receivers())
            prov = len(self.apk.get_providers())
        except Exception:
            return
        self.findings.append({
            "type": "components",
            "color": None,
            "title": "App Components",
            "description": (
                f"Activities: {acts}, Services: {srv}, "
                f"Receivers: {recv}, Providers: {prov}"
            ),
            "details": [],
            "action": None,
        })