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
# Names that only appear in an actual root check. `hasrootcause` is
# deliberately absent: it is Throwable.getCause()'s sibling in the JDK,
# not a root probe. Kotlin's `FilePathComponents.isRooted` is filtered by
# `_ROOT_OWNER_DENYLIST` below.
_ROOT_METHOD_EXACT: tuple[str, ...] = (
    "ismagiskpresent",
    "checkmagisk",
    "checksupersu",
    "checksuperuser",
    "isrooted",
    "isdevicerooted",
    "isrootpresent",
    "detectroot",
    "hasrooted",
    "rootbeer",
)

_ROOT_METHOD_PREFIXES: tuple[str, ...] = ("checkroot",)

_ROOT_STRING_MARKERS: tuple[str, ...] = (
    "com.scottyab.rootbeer",
    "com.topjohnwu.magisk",
    "com.noshufou.android.su",
    "eu.chainfire.supersu",
    "com.stericson.roottools",
    "com.thirdparty.root",
    "com.devadvance.root",
    "com.koushikdutta.superuser",
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

# Root-manager package names only appear when something actively looks for
# root apps, so they are strong evidence on their own.
_ROOT_STRING_STRONG: tuple[str, ...] = (
    "com.scottyab.rootbeer",
    "com.topjohnwu.magisk",
    "com.noshufou.android.su",
    "eu.chainfire.supersu",
    "com.stericson.roottools",
    "com.thirdparty.root",
    "com.devadvance.root",
    "com.koushikdutta.superuser",
)

# Owner classes that define a root-ish method name but are not root checks.
# Kotlin's `FilePathComponents` asks whether a path *has a root component*.
_ROOT_OWNER_DENYLIST: tuple[str, ...] = (
    "Lkotlin/io/FilePathComponents;",
    "Lkotlin/io/FilesKt;",
    "Lkotlin/io/FilesKt__FilePathComponentsKt;",
)

# Third-party SDKs that probe for root incidentally (ad fraud checks, crash
# telemetry, bidding device info). A hit owned only by these is not the app
# checking for root, so it must not be reported as an alarming finding.
_ROOT_SDK_PREFIXES: tuple[tuple[str, str], ...] = (
    ("Lcom/gameanalytics/", "GameAnalytics"),
    ("Lcom/google/firebase/", "Firebase/Crashlytics"),
    ("Lcom/google/android/gms/", "Google Play services"),
    ("Lcom/google/android/recaptcha/", "reCAPTCHA"),
    ("Lcom/unity3d/", "Unity Ads"),
    ("Lgatewayprotocol/", "Unity Ads bidding"),
    ("Lio/bidmachine/", "BidMachine"),
    ("Lcom/applovin/", "AppLovin"),
    ("Lcom/facebook/", "Facebook SDK"),
    ("Lcom/adjust/", "Adjust"),
    ("Lcom/mbridge/", "Mintegral"),
    ("Lcom/ironsource/", "IronSource"),
    ("Lcom/vungle/", "Vungle"),
    ("Lcom/bytedance/", "ByteDance/Pangle"),
    ("Lcom/appsflyer/", "AppsFlyer"),
    ("Lcom/singular/", "Singular"),
    ("Lcom/onesignal/", "OneSignal"),
    ("Lcom/amplitude/", "Amplitude"),
    ("Lcom/mixpanel/", "Mixpanel"),
    ("Lcom/braze/", "Braze"),
    ("Lcom/clevertap/", "CleverTap"),
    ("Lio/sentry/", "Sentry"),
    ("Lcom/sentry/", "Sentry"),
    ("Lkotlin/", "Kotlin stdlib"),
    ("Lkotlinx/", "Kotlin libraries"),
)


# ============================================================
# ROOT DETECTION PATTERNS (legacy blob matcher)
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

# Same needles, exposed for the shared DexIndex.
LP_STRING_MARKERS: tuple[str, ...] = _LP_PATTERNS


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
def _sdk_label(owner: str) -> str | None:
    """Return the SDK name owning `owner`, or None for app/first-party code."""
    for prefix, label in _ROOT_SDK_PREFIXES:
        if owner.startswith(prefix):
            return label
    return None


def _root_hits_from_index(index) -> dict:
    """Owner-aware root evidence from a :class:`DexIndex`.

    Returns:
        {
          "app": [labels],      # first-party / unknown-owner probes
          "sdk": {sdk: [labels]},
          "weak_strings": [...],  # su paths, test-keys, generic words
        }
    """
    denylist = set(_ROOT_OWNER_DENYLIST)
    app_hits: list[str] = []
    sdk_hits: dict[str, list[str]] = {}
    seen: set[str] = set()

    def record(method: str, owners: set[str]) -> None:
        for owner in sorted(owners - denylist):
            short = owner.rsplit("/", 1)[-1].rstrip(";")
            label = f"{short}.{index.display_name(method)}"
            if label in seen:
                continue
            seen.add(label)
            sdk = _sdk_label(owner)
            if sdk is None:
                app_hits.append(label)
            else:
                sdk_hits.setdefault(sdk, []).append(label)

    for method in _ROOT_METHOD_EXACT:
        record(method, index.owners_of(method))

    for prefix in _ROOT_METHOD_PREFIXES:
        for mname, owners in index.method_owners.items():
            if mname.startswith(prefix):
                record(mname, owners)

    strong: list[str] = [
        m for m in _ROOT_STRING_STRONG if index.has_string(m)
    ]
    weak: list[str] = [
        m for m in _ROOT_STRING_MARKERS
        if m not in _ROOT_STRING_STRONG and index.has_string(m)
    ]

    return {
        "app": app_hits + strong,
        "sdk": sdk_hits,
        "weak_strings": weak,
    }


def check_root_detection(
    get_all_dex_bytes,
    findings: list[dict],
    all_names: list[str] | None = None,
    index=None,
) -> None:
    """Detect root detection. LUÔN append 1 finding."""
    if findings is None:
        return

    app_hits: list[str] = []
    sdk_hits: dict[str, list[str]] = {}
    weak_strings: list[str] = []

    try:
        if index is not None:
            evidence = _root_hits_from_index(index)
            app_hits = evidence["app"]
            sdk_hits = evidence["sdk"]
            weak_strings = evidence["weak_strings"]
        else:
            if all_names is None:
                all_names = _extract_dex_names(get_all_dex_bytes)
            # Legacy blob path has no owner information, so every match is
            # treated as app-level (conservative).
            app_hits = _match_patterns(all_names, _ROOT_PATTERNS)
    except Exception as e:
        logger.warning("check_root_detection failed: %s", e)
        app_hits = []

    # First-party evidence wins; SDK-only evidence is informational.
    if app_hits:
        matched_display = ", ".join(app_hits[:3])
        findings.append({
            "type": "root_detection",
            "color": "red",
            "title": "Root Detection",
            "description": (
                f"Yes — app code checks for root "
                f"(matched: {matched_display})"
            ),
            "details": list(app_hits),
            "action": None,
        })
        return

    if sdk_hits or weak_strings:
        sdk_names = sorted(sdk_hits)
        detail: list[str] = []
        for sdk in sdk_names:
            detail.extend(sdk_hits[sdk])
        detail.extend(weak_strings)
        if sdk_names:
            summary = (
                f"No — app code does not check root; only bundled SDKs "
                f"probe for it ({', '.join(sdk_names)})"
            )
        else:
            summary = (
                "No — app code does not check root; only incidental "
                "root-related strings were found"
            )
        findings.append({
            "type": "root_detection",
            "color": None,
            "title": "Root Detection",
            "description": summary,
            "details": detail,
            "action": None,
        })
        return

    findings.append({
        "type": "root_detection",
        "color": None,
        "title": "Root Detection",
        "description": "No root detection detected",
        "details": [],
        "action": None,
    })


# ============================================================
# PUBLIC — LP DETECTION
# ============================================================
def check_lp_detection(
    get_all_dex_bytes,
    findings: list[dict],
    all_names: list[str] | None = None,
    index=None,
) -> None:
    """Detect LP artifacts. LUÔN append 1 finding."""
    if findings is None:
        return

    try:
        if index is not None:
            hits = [
                index.string_hits[m.lower()] for m in _LP_PATTERNS
                if index.has_string(m)
            ]
        else:
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
