"""
Security check — phát hiện root detection + LP detection trong APK.

v7 (2026):
  - PERFORMANCE: fast ASCII regex trên dex bytes cho real APK
    (~300-800ms / 9 dex thay vì ~135s với androguard DEX()).
  - FALLBACK: androguard DEX cho test mock (bytes < 1KB).
  - Env `LP_ANDROGUARD_LOG=1` để bật log androguard khi cần debug.
  - LUÔN append finding (clean hoặc detected).
  - Preserve original case trong description.
"""
from __future__ import annotations

import logging
import os
import re

# Silence androguard loguru — CHỈ khi user không set LP_ANDROGUARD_LOG
if os.environ.get("LP_ANDROGUARD_LOG", "").strip().lower() not in (
    "1", "true", "yes", "on"
):
    try:
        from loguru import logger as _loguru
        _loguru.disable("androguard")
    except ImportError:
        pass
    except Exception:
        pass

from androguard.core.dex import DEX

logger = logging.getLogger(__name__)


# ============================================================
# ASCII STRING PATTERN (fast path)
# ============================================================
_ASCII_RUN_RE = re.compile(rb"[\x20-\x7e]{4,}")
_FAST_THRESHOLD = 1024


# ============================================================
# ROOT DETECTION PATTERNS
# ============================================================
_ROOT_PATTERNS: tuple[str, ...] = (
    "com.scottyab.rootbeer",
    "com.topjohnwu.magisk",
    "com.noshufou.android.su",
    "eu.chainfire.supersu",
    "com.stericson.roottools",
    "com.thirdparty.root",
    "com.devadvance.root",
    "com.koushikdutta.superuser",
    "ismagiskpresent",
    "checkmagisk",
    "checksupersu",
    "checksuperuser",
    "checkroot",
    "isrooted",
    "isdevicerooted",
    "isrootpresent",
    "detectroot",
    "hasroot",
    "rootbeer",
    "magisk",
    "supersu",
    "superuser",
    "busybox",
    "/system/xbin/su",
    "/system/bin/su",
    "/sbin/su",
    "/su/bin/su",
    "/data/local/xbin/su",
    "/data/local/bin/su",
    "test-keys",
)


_LP_PATTERNS: tuple[str, ...] = (
    "com.chelpus.lackypatch",
    "com.chelpus.luckypatcher",
    "com.dimonvideo.luckypatcher",
    "com.forpda.lp",
    "com/chelpus/",
    "lucky patcher",
    "luckypatcher",
    "chelpus",
    "suspatcher",
    "uret patcher",
)


# ============================================================
# HELPERS
# ============================================================
def _is_real_list(obj) -> bool:
    """Check obj là list/tuple thật, không phải MagicMock."""
    return isinstance(obj, (list, tuple))


def _extract_ascii_strings(dex_bytes: bytes) -> list[str]:
    """FAST: Extract printable ASCII runs từ raw dex bytes."""
    try:
        return [
            m.decode("latin-1", errors="ignore")
            for m in _ASCII_RUN_RE.findall(dex_bytes)
        ]
    except Exception as e:
        logger.debug("ASCII extract failed: %s", e)
        return []


def _extract_via_dex(dex_bytes: bytes) -> list[str]:
    """SLOW fallback: parse dex structure qua androguard. Cho test mock."""
    names: list[str] = []
    try:
        dex = DEX(dex_bytes)
    except Exception as e:
        logger.debug("DEX parse failed: %s", e)
        return names

    try:
        strings = dex.get_strings()
        if _is_real_list(strings) and strings:
            for s in strings:
                try:
                    names.append(str(s))
                except Exception:
                    continue
            return names
    except Exception as e:
        logger.debug("get_strings failed: %s", e)

    try:
        classes = dex.get_classes()
    except Exception:
        return names
    if not _is_real_list(classes):
        return names

    for cls in classes:
        try:
            cname = cls.get_name()
            if cname:
                names.append(str(cname))
        except Exception:
            continue

        try:
            methods = cls.get_methods()
        except Exception:
            methods = []
        if not _is_real_list(methods):
            continue

        for m in methods:
            try:
                mname = m.get_name()
                if mname:
                    names.append(str(mname))
            except Exception:
                continue

    return names


def _extract_dex_names(get_all_dex_bytes) -> list[str]:
    """Extract names từ dex — fast ASCII regex cho real, DEX cho test."""
    names: list[str] = []
    if get_all_dex_bytes is None:
        return names

    try:
        for _dex_name, dex_bytes in get_all_dex_bytes():
            if not dex_bytes:
                continue

            if len(dex_bytes) < _FAST_THRESHOLD:
                names.extend(_extract_via_dex(dex_bytes))
            else:
                names.extend(_extract_ascii_strings(dex_bytes))
    except Exception as e:
        logger.warning("Extract dex names failed: %s", e)
    return names


def _match_patterns(
    names: list[str], patterns: tuple[str, ...],
) -> list[str]:
    """Return ORIGINAL matched names (preserve case) cho mỗi pattern."""
    if not names:
        return []

    blob_lower = "\n".join(names).lower()
    hits: list[str] = []
    seen_patterns: set[str] = set()

    for p in patterns:
        pl = p.lower()
        if pl in seen_patterns:
            continue
        if pl not in blob_lower:
            continue
        seen_patterns.add(pl)

        matched_original = None
        for name in names:
            if pl in name.lower():
                matched_original = name
                break

        hits.append(matched_original or p)
    return hits


# ============================================================
# PUBLIC — ROOT DETECTION
# ============================================================
def check_root_detection(
    get_all_dex_bytes,
    findings: list[dict],
    all_names: list[str] | None = None,
) -> None:
    """Detect root detection. LUÔN append 1 finding."""
    if findings is None:
        return

    try:
        if all_names is None:
            all_names = _extract_dex_names(get_all_dex_bytes)
        hits = _match_patterns(all_names, _ROOT_PATTERNS)
    except Exception as e:
        logger.warning("check_root_detection failed: %s", e)
        hits = []

    if not hits:
        findings.append({
            "type": "root_detection",
            "color": None,
            "title": "Root Detection",
            "description": "No root detection detected",
            "details": [],
            "action": None,
        })
        return

    matched_display = ", ".join(hits[:3])
    findings.append({
        "type": "root_detection",
        "color": "red",
        "title": "Root Detection",
        "description": (
            f"Yes — App may detect root access "
            f"(matched: {matched_display})"
        ),
        "details": list(hits),
        "action": None,
    })


# ============================================================
# PUBLIC — LP DETECTION
# ============================================================
def check_lp_detection(
    get_all_dex_bytes,
    findings: list[dict],
    all_names: list[str] | None = None,
) -> None:
    """Detect LP artifacts. LUÔN append 1 finding."""
    if findings is None:
        return

    try:
        if all_names is None:
            all_names = _extract_dex_names(get_all_dex_bytes)
        hits = _match_patterns(all_names, _LP_PATTERNS)
    except Exception as e:
        logger.warning("check_lp_detection failed: %s", e)
        hits = []

    if not hits:
        findings.append({
            "type": "lp_detection",
            "color": None,
            "title": "Lucky Patcher Detection",
            "description": "No LP artifacts detected",
            "details": [],
            "action": None,
        })
        return

    matched_display = ", ".join(hits[:3])
    findings.append({
        "type": "lp_detection",
        "color": "red",
        "title": "Lucky Patcher Detected",
        "description": (
            f"Yes — APK này là Lucky Patcher hoặc clone LP "
            f"(matched: {matched_display})"
        ),
        "details": list(hits),
        "action": None,
    })