"""
Packer precision fusion — structural index + entropy windows + bytecode score.

The primary signature table (`packer_check.py`) answers "which packer is
this?" from cheap signals (manifest application class, native libs, asset
names, dex prefixes). The bytecode table (`packer_bytecode.py`) answers the
same question from raw dex patterns, but only runs when the primary tier
found nothing.

Neither answers the question that actually decides whether a patch will do
anything: **is the application dex readable?**

A packer can be present in two very different shapes:

  * **Shell only** — the packer stub is bundled (e.g. PairIP's integrity
    check, or a Legu shell left behind after an unpack), but the real
    classes are still plaintext in `classes*.dex`. Normal patches work.
  * **Encrypted** — the real dex is an encrypted blob decrypted at runtime
    by native code. Static patches match 0 files and fail silently.

`assess_packability()` fuses three signals to tell those apart:

  1. Structural index — how many classes belong to the app's own package,
     and what class density the dex shows per megabyte.
  2. Entropy windows — whether large contiguous dex regions are
     high-entropy (a strong encrypted-payload signal).
  3. Bytecode signature score — how strongly the stub classes/invocations
     match a known packer.

The result is a `PackabilityAssessment` carrying a refined `patchable`
flag, a confidence, a human-readable rationale, and a recommended
`BypassStrategy` that the patcher layer can act on.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================
# STRATEGY
# ============================================================
class BypassStrategy(Enum):
    """What the patcher layer should do with a packed APK."""

    # Dex is readable — treat as a normal APK and patch away.
    DEX_PLAINTEXT = "dex_plaintext"

    # The packer stub is present but the real Application class is also
    # readable. Repoint the manifest at the real Application and drop the
    # shell entry point.
    SHELL_SWAP = "shell_swap"

    # Shell entry cannot be swapped (no readable Application), but the stub
    # entry class can be neutralized to a no-op so control falls through to
    # the plaintext code paths.
    STUB_NEUTRALIZE = "stub_neutralize"

    # Real dex is encrypted; no static bypass is possible. Requires an
    # external unpacker or a runtime dumper.
    UNPACK_REQUIRED = "unpack_required"


# ============================================================
# ASSESSMENT
# ============================================================
@dataclass
class PackabilityAssessment:
    """Fused verdict on whether an APK can be statically patched."""

    packer_name: str = ""
    patchable: bool = False
    confidence: str = "low"
    strategy: BypassStrategy = BypassStrategy.UNPACK_REQUIRED
    rationale: str = ""
    evidence: list[str] = field(default_factory=list)

    # Structural signals
    class_count: int = 0
    own_package_classes: int = 0
    dex_megabytes: float = 0.0
    class_density: float = 0.0  # classes per MB of dex

    # Entropy signals
    max_window_entropy: float = 0.0
    high_entropy_pct: float = 0.0

    # Bytecode score
    bytecode_score: int = 0

    def to_dict(self) -> dict:
        return {
            "packer_name": self.packer_name,
            "patchable": self.patchable,
            "confidence": self.confidence,
            "strategy": self.strategy.value,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "class_count": self.class_count,
            "own_package_classes": self.own_package_classes,
            "dex_megabytes": round(self.dex_megabytes, 2),
            "class_density": round(self.class_density, 1),
            "max_window_entropy": round(self.max_window_entropy, 2),
            "high_entropy_pct": round(self.high_entropy_pct, 1),
            "bytecode_score": self.bytecode_score,
        }


# ============================================================
# THRESHOLDS
# ============================================================
# A plaintext app dex carries its own package classes and packs a healthy
# number of descriptors per megabyte. An encrypted payload shows almost
# none of either.
_OWN_PKG_MIN_CLASSES = 5
_CLASS_DENSITY_MIN = 120.0     # descriptors per MB of dex
_ENTROPY_HIGH_PCT_MAX = 20.0   # >= this % of high-entropy windows → suspect
_WINDOW_ENTROPY_MIN = 7.5

# Bytecode score above which the stub is considered "strongly present".
_STRONG_BYTECODE_SCORE = 4

# Packers whose licence/DRM enforcement lives in native code. Their dex can
# be perfectly readable while license patches still match nothing, so the
# verdict stays "patchable" but carries an explicit caveat.
_NATIVE_ENFORCEMENT = {
    "pairip",
    "dexprotector",
    "promon",
    "liapp",
    "arxan",
    "appsealing",
}

# Cap the number of entropy windows analysed per dex by the fusion layer.
# Sampling stays evenly spaced across the whole dex, so coverage is kept
# while cost becomes independent of dex size. 150 windows (~2.4 MB sampled)
# keeps the high-entropy percentage within 0.2 pp of a full sweep.
_FUSION_MAX_WINDOWS = 150


def _package_class_prefix(package: str | None) -> str | None:
    if not package:
        return None
    pkg = package.strip().replace(".", "/")
    if not pkg:
        return None
    return "L" + pkg + "/"


def _is_native_enforced(packer_name: str | None) -> bool:
    if not packer_name:
        return False
    lowered = packer_name.lower()
    return any(token in lowered for token in _NATIVE_ENFORCEMENT)


# ============================================================
# STRUCTURAL SIGNAL
# ============================================================
def structural_signal(
    index,
    package: str | None,
    dex_bytes_total: int,
) -> tuple[int, int, float, float]:
    """
    Return (class_count, own_package_classes, dex_megabytes, density).

    `index` is a :class:`scanner.dex_index.DexIndex` (may be None).
    """
    class_count = len(getattr(index, "classes", []) or [])
    own = 0
    prefix = _package_class_prefix(package)
    if prefix and class_count:
        prefix_lower = prefix.lower()
        own = sum(
            1
            for cl in getattr(index, "classes_lower", []) or []
            if cl.startswith(prefix_lower)
        )
    mb = (dex_bytes_total / (1024 * 1024)) if dex_bytes_total else 0.0
    density = (class_count / mb) if mb > 0 else 0.0
    return class_count, own, mb, density


# ============================================================
# ENTROPY SIGNAL
# ============================================================
def entropy_signal(dex_entries: list[tuple[str, bytes]]) -> tuple[float, float]:
    """
    Return (max_window_entropy, high_entropy_pct) aggregated over all dex.

    Degrades to (0.0, 0.0) if the bytecode module is unavailable.
    """
    try:
        from scanner.checks.packer_bytecode import entropy_window_analysis
    except ImportError:  # pragma: no cover - defensive
        return 0.0, 0.0

    max_entropy = 0.0
    high = 0
    total = 0
    for _name, raw in dex_entries:
        if not raw:
            continue
        try:
            result = entropy_window_analysis(
                raw, max_windows=_FUSION_MAX_WINDOWS
            )
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("Entropy window failed: %s", e)
            continue
        max_entropy = max(max_entropy, result.max_entropy)
        high += result.high_entropy_count
        total += result.total_windows
    pct = (100.0 * high / total) if total else 0.0
    return max_entropy, pct


# ============================================================
# BYTECODE SIGNAL
# ============================================================
def bytecode_signal(
    apk_path: str,
    packer_name: str | None = None,
    index=None,
    dex_entries: list[tuple[str, bytes]] | None = None,
    entropy_bad: bool = False,
) -> tuple[int, list[str]]:
    """
    Return (score, evidence) for the bytecode signature table.

    When `index` is provided the score is computed from the shared
    structural index plus the already-read dex bytes, so no zip is
    reopened and no 60 MB regex sweep is repeated. Without an index it
    falls back to the full `detect_packer_via_bytecode` pass.

    When `packer_name` is given, only that signature is scored; otherwise
    the strongest match is returned.
    """
    try:
        from scanner.checks.packer_bytecode import (
            _BYTECODE_SIGNATURES,
            detect_packer_via_bytecode,
        )
    except ImportError:  # pragma: no cover - defensive
        return 0, []

    if index is not None:
        blob = "\n".join(getattr(index, "classes", []) or [])
        sig = (
            _match_signature_name(packer_name, _BYTECODE_SIGNATURES)
            if packer_name
            else None
        )
        if sig is not None:
            return _score_signature_from_blob(
                sig, blob, dex_entries, entropy_bad
            )
        best_score = 0
        best_evidence: list[str] = []
        for candidate in _BYTECODE_SIGNATURES.values():
            score, evidence = _score_signature_from_blob(
                candidate, blob, dex_entries, entropy_bad
            )
            if score > best_score:
                best_score = score
                best_evidence = evidence
        return best_score, best_evidence

    try:
        detection = detect_packer_via_bytecode(apk_path)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("Bytecode signal failed: %s", e)
        return 0, []

    if detection is None:
        return 0, []

    if packer_name:
        sig = _match_signature_name(packer_name, _BYTECODE_SIGNATURES)
        if sig is not None:
            return _score_signature(sig, detection.evidence)

    return len(detection.evidence), list(detection.evidence)


def _match_signature_name(name: str, table: dict) -> dict | None:
    """Fuzzy-match a signature table key from a display name."""
    if name in table:
        return table[name]
    lowered = name.lower()
    for key, sig in table.items():
        key_lower = key.lower()
        if key_lower in lowered or lowered in key_lower:
            return sig
    # Try the first token, e.g. "PairIP (Google Play)" -> "pairip"
    token = lowered.split("(")[0].strip().split()[0] if lowered else ""
    if token:
        for key, sig in table.items():
            if key.lower().startswith(token):
                return sig
    return None


def _score_signature_from_blob(
    sig: dict,
    blob: str,
    dex_entries: list[tuple[str, bytes]] | None,
    entropy_bad: bool,
) -> tuple[int, list[str]]:
    """Score a signature against a class-descriptor blob (no zip I/O)."""
    score = 0
    evidence: list[str] = []

    for pat in sig.get("stub_classes", ()):
        if pat.search(blob):
            evidence.append(f"stub_class:{pat.pattern}")
            score += 3

    for pat in sig.get("invocations", ()):
        if pat.search(blob):
            evidence.append(f"invocation:{pat.pattern}")
            score += 2

    if sig.get("encrypted_dex") and entropy_bad:
        evidence.append("encrypted_region:dex")
        score += 2

    native_req = sig.get("native_mass")
    if native_req and dex_entries:
        try:
            from scanner.checks.packer_bytecode import (
                _count_native_methods_raw,
            )
        except ImportError:  # pragma: no cover - defensive
            _count_native_methods_raw = None  # type: ignore[assignment]
        if _count_native_methods_raw is not None:
            total = sum(
                _count_native_methods_raw(raw)
                for _n, raw in dex_entries
                if raw
            )
            if total >= native_req:
                evidence.append(f"native_mass:{total}>={native_req}")
                score += 1

    return score, evidence


def _score_signature(sig: dict, evidence: list[str]) -> tuple[int, list[str]]:
    """Recompute a signature score from already-collected evidence."""
    score = 0
    matched: list[str] = []
    for pat in sig.get("stub_classes", ()):
        if any(pat.pattern in e for e in evidence):
            score += 3
            matched.append(f"stub_class:{pat.pattern}")
    for pat in sig.get("invocations", ()):
        if any(pat.pattern in e for e in evidence):
            score += 2
            matched.append(f"invocation:{pat.pattern}")
    if sig.get("encrypted_dex") and any(
        e.startswith(("encrypted_dex", "encrypted_region")) for e in evidence
    ):
        score += 2
        matched.append("encrypted_dex_signal")
    native_req = sig.get("native_mass")
    if native_req:
        for e in evidence:
            if e.startswith("native_mass"):
                score += 1
                matched.append(e)
                break
    return score, matched


# ============================================================
# FUSION
# ============================================================
def assess_packability(
    apk_path: str,
    packer_name: str | None,
    index=None,
    package: str | None = None,
    dex_entries: list[tuple[str, bytes]] | None = None,
) -> PackabilityAssessment:
    """
    Fuse structural, entropy and bytecode signals into a verdict.

    Args:
        apk_path: Path to the APK (used by the bytecode signal).
        packer_name: Primary packer display name (or None when clean).
        index: Shared :class:`DexIndex` (optional).
        package: Manifest package name (optional).
        dex_entries: ``[(name, bytes), ...]`` (optional; read from the APK
            when omitted).
    """
    assessment = PackabilityAssessment(packer_name=packer_name or "")

    if not packer_name:
        assessment.patchable = True
        assessment.confidence = "high"
        assessment.strategy = BypassStrategy.DEX_PLAINTEXT
        assessment.rationale = "No packer detected."
        return assessment

    # --- dex bytes ---
    if dex_entries is None:
        try:
            from scanner.checks.packer_bytecode import _read_dex_entries
            dex_entries = _read_dex_entries(apk_path)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("Dex read failed: %s", e)
            dex_entries = []
    dex_entries = dex_entries or []
    dex_total = sum(len(raw) for _n, raw in dex_entries if raw)

    # --- 1. structural ---
    class_count, own, mb, density = structural_signal(index, package, dex_total)
    assessment.class_count = class_count
    assessment.own_package_classes = own
    assessment.dex_megabytes = mb
    assessment.class_density = density

    # --- 2. entropy ---
    max_entropy, high_pct = entropy_signal(dex_entries)
    assessment.max_window_entropy = max_entropy
    assessment.high_entropy_pct = high_pct

    # A single hot window is common in any APK (compressed assets, native
    # blobs), so it never counts as encryption on its own. Only a sustained
    # high-entropy region does.
    region_encrypted = high_pct >= _ENTROPY_HIGH_PCT_MAX

    # --- 3. bytecode ---
    score, bc_evidence = bytecode_signal(
        apk_path, packer_name, index=index,
        dex_entries=dex_entries, entropy_bad=region_encrypted,
    )
    assessment.bytecode_score = score
    assessment.evidence.extend(bc_evidence)

    # --- fuse ---
    own_ok = own >= _OWN_PKG_MIN_CLASSES
    density_ok = density >= _CLASS_DENSITY_MIN

    assessment.evidence.extend([
        f"classes={class_count}",
        f"own_pkg_classes={own}",
        f"density={density:.1f}/MB",
        f"max_window_entropy={max_entropy:.2f}",
        f"high_entropy_pct={high_pct:.1f}",
        f"bytecode_score={score}",
    ])

    # Case A — the app's own classes are present and readable. The packer
    # stub may still be bundled but it is not hiding the code.
    if own_ok and density_ok and not (region_encrypted and high_pct >= 40.0):
        assessment.patchable = True
        assessment.confidence = "high" if own >= 20 else "medium"
        assessment.strategy = BypassStrategy.DEX_PLAINTEXT
        assessment.rationale = (
            f"{packer_name} shell present but {own} app-package classes are "
            f"readable (density {density:.0f}/MB) — static patches apply."
        )
        if _is_native_enforced(packer_name):
            assessment.rationale += (
                " Licence checks may still run in native code, so a "
                "license patch can match 0 files."
            )
        return assessment

    # Case B — own classes readable but sparse; a shell swap may be needed.
    if own_ok and not region_encrypted:
        assessment.patchable = True
        assessment.confidence = "medium"
        assessment.strategy = BypassStrategy.SHELL_SWAP
        assessment.rationale = (
            f"{packer_name} stub found; {own} app classes readable but dex is "
            f"sparse ({density:.0f}/MB) — swap the shell Application first."
        )
        return assessment

    # Case C — stub strongly present, dex not obviously encrypted, but no
    # own classes. Neutralizing the stub may reveal plaintext code paths.
    if score >= _STRONG_BYTECODE_SCORE and not region_encrypted:
        assessment.patchable = True
        assessment.confidence = "low"
        assessment.strategy = BypassStrategy.STUB_NEUTRALIZE
        assessment.rationale = (
            f"{packer_name} stub strongly matched (score {score}) with no "
            f"encrypted regions — neutralize the stub entry as a best effort."
        )
        return assessment

    # Case D — encrypted payload. No static bypass.
    assessment.patchable = False
    assessment.confidence = "high" if region_encrypted else "medium"
    assessment.strategy = BypassStrategy.UNPACK_REQUIRED
    if region_encrypted:
        assessment.rationale = (
            f"{packer_name} dex payload is encrypted "
            f"({high_pct:.0f}% high-entropy windows, max "
            f"{max_entropy:.2f}) — requires an external unpacker."
        )
    else:
        assessment.rationale = (
            f"{packer_name} detected but no readable app classes "
            f"(classes={class_count}, own={own}) — likely encrypted."
        )
    return assessment


def assess_from_apk_path(
    apk_path: str,
    packer_name: str | None,
    package: str | None = None,
) -> PackabilityAssessment:
    """Convenience wrapper that builds a temporary DexIndex."""
    index = None
    dex_entries: list[tuple[str, bytes]] = []
    try:
        from scanner.checks.packer_bytecode import _read_dex_entries
        dex_entries = _read_dex_entries(apk_path)
    except Exception:  # pragma: no cover - defensive
        dex_entries = []

    if dex_entries:
        try:
            from scanner.dex_index import build_dex_index
            index = build_dex_index(
                [(n, b) for n, b in dex_entries if b and len(b) >= 1024]
            )
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("Index build failed: %s", e)

    return assess_packability(
        apk_path, packer_name, index=index, package=package,
        dex_entries=dex_entries,
    )


__all__ = [
    "BypassStrategy",
    "PackabilityAssessment",
    "assess_from_apk_path",
    "assess_packability",
    "bytecode_signal",
    "entropy_signal",
    "structural_signal",
]
