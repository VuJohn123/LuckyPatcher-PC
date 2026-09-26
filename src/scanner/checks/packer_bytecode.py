"""
Bytecode-based packer detection — fallback cho packer hiếm.

Extends primary detection (native-lib / app-class / asset / dex-prefix)
với các kỹ thuật bytecode-level:

  1. Invocation patterns — scan dex method calls tới known stub classes.
  2. Encrypted DEX sections — entropy global + **window analysis** (v4).
  3. Native method mass.
  4. Stub Application class.
  5. Encrypted string markers.

v3 (2026) — 6 packer hiếm ngoài TQ:
  Nagain, Promon Shield, AppSealing (Inka), Baidu Protect, ChaosVM,
  NQ Shield.

v4 (2026) — entropy window analysis:
  - Sliding-window (non-overlap) Shannon entropy detect partial
    encryption (packer encrypt strings/code section, không cả dex).
  - BytecodeDetection adds `max_window_entropy` + `high_entropy_windows`.
  - Detection signal mới: dex có >20% windows encrypted nhưng global
    entropy thấp → vẫn flag packer.

References:
  - APKiD bytecode rules (RedNaga)
  - MobSF packer detection patterns
  - Freezdy413485/LP-DeCodes (LP 12.10.4 packer signatures)
"""
from __future__ import annotations

import logging
import math
import os
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================================
# SIGNATURE TABLE — bytecode-level
# ============================================================
# Mỗi entry:
#   stub_classes:   list[re.Pattern] — class names phải xuất hiện trong dex
#   invocations:    list[re.Pattern] — method refs đặc trưng
#   encrypted_dex:  bool — nếu True, entropy check bắt buộc fail
#   native_mass:    int | None — số native methods tối thiểu (nếu có)
#   stub_app_min:   int | None — Application class size tối đa (smali LOC)
#   confidence:     "high"|"medium"|"low"
#   patchable:      bool
#   notes:          str — mô tả ngắn
_BYTECODE_SIGNATURES: dict[str, dict] = {
    "PairIP (Google Play)": {
        "stub_classes": [
            re.compile(r"Lcom/pairip/[A-Z]\w+;"),
            re.compile(r"Lcom/pairip/VMRunner;"),
            re.compile(r"Lcom/pairip/application/Application;"),
        ],
        "invocations": [
            re.compile(r"Lcom/pairip/VMRunner;->invoke"),
            re.compile(r"Lcom/pairip/StartupLauncher;->"),
        ],
        "encrypted_dex": True,
        "native_mass": None,
        "stub_app_min": None,
        "confidence": "high",
        "patchable": False,
        "notes": "Google Play Integrity — VM-based dex encryption",
    },
    "Tencent Legu/StubShell": {
        "stub_classes": [
            re.compile(r"Lcom/tencent/StubShell/"),
            re.compile(r"Lcom/tencent/StubApplication;"),
            re.compile(r"Lcom/tencent/bugly/crashreport/CrashReport;"),
        ],
        "invocations": [
            re.compile(r"Lcom/tencent/StubShell/StubApp;->"),
            re.compile(r"Lcom/tencent/StubShell/TxAppEntry;->"),
        ],
        "encrypted_dex": True,
        "native_mass": None,
        "stub_app_min": None,
        "confidence": "high",
        "patchable": False,
        "notes": "Tencent Legu shell — native decrypt + reflection dispatch",
    },
    "360 Jiagu (Qihoo)": {
        "stub_classes": [
            re.compile(r"Lcom/qihoo/util/"),
            re.compile(r"Lcom/stub/StubApp;"),
            re.compile(r"Lcom/qihoo360/replugin/"),
        ],
        "invocations": [
            re.compile(r"Lcom/stub/StubApp;->"),
            re.compile(r"Lcom/qihoo/util/QHDialog;->"),
        ],
        "encrypted_dex": True,
        "native_mass": None,
        "stub_app_min": None,
        "confidence": "high",
        "patchable": False,
        "notes": "360 Jiagu — Qihoo 360 shell",
    },
    "Bangcle (SecNeo)": {
        "stub_classes": [
            re.compile(r"Lcom/bangcle/andJNI/"),
            re.compile(r"Lcom/secneo/apkwrapper/"),
            re.compile(r"Lcom/secneo/encrypt/"),
        ],
        "invocations": [
            re.compile(r"Lcom/bangcle/andJNI/JNIWrapper;->"),
            re.compile(r"Lcom/secneo/apkwrapper/ProxyApplication;->"),
        ],
        "encrypted_dex": True,
        "native_mass": None,
        "stub_app_min": None,
        "confidence": "high",
        "patchable": False,
        "notes": "Bangcle/SecNeo — JNI wrapper shell",
    },
    "Ijiami (Shell)": {
        "stub_classes": [
            re.compile(r"Lcom/shell/SuperApplication;"),
            re.compile(r"Lcom/shell/SuperApplication2;"),
            re.compile(r"Lcom/shell/StubApplication;"),
        ],
        "invocations": [
            re.compile(r"Lcom/shell/SuperApplication;->"),
            re.compile(r"Lcom/shell/NativeApplication;->"),
        ],
        "encrypted_dex": True,
        "native_mass": None,
        "stub_app_min": None,
        "confidence": "high",
        "patchable": False,
        "notes": "Ijiami — Chinese shell",
    },
    "DexGuard (Guardsquare)": {
        "stub_classes": [
            re.compile(r"Lcom/guardsquare/dexguard/runtime/"),
        ],
        "invocations": [
            re.compile(r"Lcom/guardsquare/dexguard/runtime/encryption/"),
            re.compile(r"Lcom/guardsquare/dexguard/runtime/StringDecryptor;"),
        ],
        "encrypted_dex": False,
        "native_mass": None,
        "stub_app_min": None,
        "confidence": "medium",
        "patchable": True,
        "notes": "DexGuard — string/control-flow obfuscation (không shell)",
    },
    "DexProtector (Licel)": {
        "stub_classes": [
            re.compile(r"Lcom/licel/dexprotector/"),
        ],
        "invocations": [
            re.compile(r"Lcom/licel/jni/NativeBridge;->"),
        ],
        "encrypted_dex": True,
        "native_mass": 3,
        "stub_app_min": None,
        "confidence": "high",
        "patchable": False,
        "notes": "DexProtector — native string/class encryption",
    },
    "LIAPP": {
        "stub_classes": [
            re.compile(r"Lcom/liapp/"),
            re.compile(r"Lkr/co/liapp/"),
        ],
        "invocations": [
            re.compile(r"Lcom/liapp/ObfuscationManager;->"),
        ],
        "encrypted_dex": True,
        "native_mass": None,
        "stub_app_min": None,
        "confidence": "medium",
        "patchable": False,
        "notes": "LIAPP — Korean shell/RASP",
    },
    "Virbox": {
        "stub_classes": [
            re.compile(r"Lcom/virbox/"),
            re.compile(r"Lcom/sense/"),
        ],
        "invocations": [
            re.compile(r"Lcom/virbox/protect/"),
        ],
        "encrypted_dex": True,
        "native_mass": None,
        "stub_app_min": None,
        "confidence": "medium",
        "patchable": False,
        "notes": "Virbox — Chinese VM protection",
    },
    "Arxan": {
        "stub_classes": [
            re.compile(r"Lcom/arxan/"),
        ],
        "invocations": [],
        "encrypted_dex": False,
        "native_mass": 5,
        "stub_app_min": None,
        "confidence": "medium",
        "patchable": True,
        "notes": "Arxan — native code protection (không shell dex)",
    },
    # ============================================================
    # v3 additions — packer hiếm / ngoài TQ
    # ============================================================
    "Nagain (Korean)": {
        "stub_classes": [
            re.compile(r"Lcom/nagain/"),
            re.compile(r"Lcom/nagacore/"),
            re.compile(r"Lcom/nagain/core/"),
        ],
        "invocations": [
            re.compile(r"Lcom/nagain/NagainApplication;->"),
            re.compile(r"Lcom/nagain/core/NagainCore;->"),
        ],
        "encrypted_dex": True,
        "native_mass": None,
        "stub_app_min": None,
        "confidence": "high",
        "patchable": False,
        "notes": "Nagain — Korean shell, native dex decrypt",
    },
    "Promon Shield": {
        "stub_classes": [
            re.compile(r"Lcom/promon/shield/"),
            re.compile(r"Lcom/promon/"),
        ],
        "invocations": [
            re.compile(r"Lcom/promon/shield/PromonShield;->"),
        ],
        "encrypted_dex": False,
        "native_mass": 3,
        "stub_app_min": None,
        "confidence": "high",
        "patchable": False,
        "notes": "Promon Shield — RASP, native VM (không shell dex)",
    },
    "AppSealing (Inka)": {
        "stub_classes": [
            re.compile(r"Lcom/inka/"),
            re.compile(r"Lcom/appsealing/"),
            re.compile(r"Lcom/inka/AppSealing;"),
        ],
        "invocations": [
            re.compile(r"Lcom/inka/AppSealing;->"),
            re.compile(r"Lcom/inka/InkaApplication;->"),
        ],
        "encrypted_dex": True,
        "native_mass": None,
        "stub_app_min": None,
        "confidence": "high",
        "patchable": False,
        "notes": "AppSealing (Inka) — Korean shell, native VM",
    },
    "Baidu Protect": {
        "stub_classes": [
            re.compile(r"Lcom/baidu/protect/"),
        ],
        "invocations": [
            re.compile(r"Lcom/baidu/protect/ProtectApplication;->"),
        ],
        "encrypted_dex": True,
        "native_mass": None,
        "stub_app_min": None,
        "confidence": "medium",
        "patchable": False,
        "notes": "Baidu Protect — Chinese shell (Baidu Security)",
    },
    "ChaosVM": {
        "stub_classes": [
            re.compile(r"Lcom/chaosvm/"),
        ],
        "invocations": [
            re.compile(r"Lcom/chaosvm/ChaosVM;->"),
        ],
        "encrypted_dex": True,
        "native_mass": None,
        "stub_app_min": None,
        "confidence": "medium",
        "patchable": False,
        "notes": "ChaosVM — VM-based dex protection",
    },
    "NQ Shield": {
        "stub_classes": [
            re.compile(r"Lcom/nqshield/"),
        ],
        "invocations": [
            re.compile(r"Lcom/nqshield/NQShieldApplication;->"),
        ],
        "encrypted_dex": True,
        "native_mass": None,
        "stub_app_min": None,
        "confidence": "medium",
        "patchable": False,
        "notes": "NQ Shield (NQ Mobile) — Korean/Chinese shell",
    },
}

# Entropy threshold cho encrypted dex detection (global)
_ENCRYPTED_ENTROPY_MIN = 7.5   # Shannon entropy (bits/byte), max = 8.0
_ENCRYPTED_UNIQUE_MIN = 200    # unique byte values
_ENCRYPTED_MIN_BYTES = 4096    # sample size tối thiểu

# Window analysis (v4) — non-overlapping windows detect partial encryption
_WINDOW_SIZE = 16384           # 16 KB per window
_WINDOW_SAMPLE_STRIDE = 4      # sample every Nth byte (4x faster)
_WINDOW_REGION_PCT_MIN = 20    # % high-entropy windows để flag region encrypted

# Stub app heuristic
_STUB_APP_MAX_LINES = 30
_STUB_APP_KEYWORDS = (
    "loadLibrary",
    "System->load",
    "getApplicationContext",
)


# ============================================================
# DATA CLASSES
# ============================================================
@dataclass
class BytecodeDetection:
    """Result của 1 lần detect qua bytecode."""
    name: str
    confidence: str
    patchable: bool
    evidence: list[str] = field(default_factory=list)
    entropy: float = 0.0
    native_count: int = 0
    notes: str = ""
    # v4 fields — window analysis
    max_window_entropy: float = 0.0
    high_entropy_windows: int = 0


@dataclass
class WindowEntropyResult:
    """Result của entropy window analysis trên 1 dex."""
    max_entropy: float = 0.0
    max_offset: int = 0
    high_entropy_count: int = 0
    total_windows: int = 0
    avg_entropy: float = 0.0
    window_size: int = _WINDOW_SIZE

    @property
    def high_pct(self) -> float:
        if not self.total_windows:
            return 0.0
        return 100.0 * self.high_entropy_count / self.total_windows

    @property
    def has_encrypted_region(self) -> bool:
        return self.high_pct >= _WINDOW_REGION_PCT_MIN


# ============================================================
# ENTROPY — Shannon
# ============================================================
def shannon_entropy(data: bytes) -> float:
    """Shannon entropy (bits/byte). Return 0.0 if empty."""
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    entropy = 0.0
    for c in counts:
        if c:
            p = c / n
            entropy -= p * math.log2(p)
    return entropy


def unique_byte_count(data: bytes) -> int:
    """Số byte values distinct trong `data` (0-256)."""
    return len(set(data))


def _fast_entropy(data: bytes) -> float:
    """
    Entropy via collections.Counter — nhanh hơn loop thuần
    (~5x trên 16KB).
    """
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    return -sum(
        (c / n) * math.log2(c / n) for c in counts.values()
    )


# ============================================================
# WINDOW ENTROPY ANALYSIS (v4)
# ============================================================
def entropy_window_analysis(
    dex_bytes: bytes,
    window_size: int = _WINDOW_SIZE,
    sample_stride: int = _WINDOW_SAMPLE_STRIDE,
    threshold: float = _ENCRYPTED_ENTROPY_MIN,
) -> WindowEntropyResult:
    """
    Sliding-window Shannon entropy detect partial encryption.

    Chia `dex_bytes` thành các window non-overlap 16KB, mỗi window
    sample every `sample_stride` byte rồi tính entropy. Trả về:
      - max_entropy + offset của window nguy hiểm nhất
      - high_entropy_count = số window ≥ threshold
      - avg_entropy

    Packer encrypt 1 section (vd strings section) → window entropy
    max sẽ cao dù global entropy thấp.

    Args:
        dex_bytes: raw bytes của 1 dex file
        window_size: kích thước 1 window (default 16KB)
        sample_stride: sample mỗi N byte để tăng tốc (default 4)
        threshold: entropy threshold để coi window là "encrypted"

    Returns:
        WindowEntropyResult
    """
    n = len(dex_bytes)
    if n == 0:
        return WindowEntropyResult(window_size=window_size)

    # Small dex → single window fallback
    if n < window_size:
        sample = dex_bytes[::max(1, sample_stride)]
        e = _fast_entropy(sample)
        return WindowEntropyResult(
            max_entropy=e,
            max_offset=0,
            high_entropy_count=1 if e >= threshold else 0,
            total_windows=1,
            avg_entropy=e,
            window_size=window_size,
        )

    max_e = 0.0
    max_off = 0
    high_count = 0
    total = 0
    sum_e = 0.0

    stride = max(1, sample_stride)
    for offset in range(0, n - window_size + 1, window_size):
        window = dex_bytes[offset:offset + window_size]
        # Sample để tăng tốc — random vẫn random
        sample = window[::stride]
        e = _fast_entropy(sample)
        total += 1
        sum_e += e
        if e > max_e:
            max_e = e
            max_off = offset
        if e >= threshold:
            high_count += 1

    # Tail (nếu còn dư < window_size, sample riêng)
    tail_start = total * window_size
    if tail_start < n:
        tail = dex_bytes[tail_start:]
        if len(tail) >= 512:  # bỏ qua tail quá nhỏ
            sample = tail[::stride]
            e = _fast_entropy(sample)
            total += 1
            sum_e += e
            if e > max_e:
                max_e = e
                max_off = tail_start
            if e >= threshold:
                high_count += 1

    return WindowEntropyResult(
        max_entropy=max_e,
        max_offset=max_off,
        high_entropy_count=high_count,
        total_windows=total,
        avg_entropy=(sum_e / total) if total else 0.0,
        window_size=window_size,
    )


# ============================================================
# DEX EXTRACTION
# ============================================================
def _read_dex_entries(apk_path: str) -> list[tuple[str, bytes]]:
    """Read .dex entries từ APK. Graceful on corrupt zip."""
    out: list[tuple[str, bytes]] = []
    try:
        with zipfile.ZipFile(apk_path, "r") as z:
            for name in z.namelist():
                if not name.endswith(".dex"):
                    continue
                try:
                    out.append((name, z.read(name)))
                except (zipfile.BadZipFile, OSError, RuntimeError) as e:
                    logger.debug("Skip dex %s: %s", name, e)
    except (zipfile.BadZipFile, OSError) as e:
        logger.warning("Cannot read APK %s: %s", apk_path, e)
    return out


# ============================================================
# STRING SCAN
# ============================================================
_CLASS_DESCRIPTOR_RE = re.compile(rb"L[\w/$]+;")


def _iter_strings(dex_bytes: bytes) -> list[str]:
    """Extract ASCII-ish class descriptors từ raw dex bytes."""
    results: list[str] = []
    for m in _CLASS_DESCRIPTOR_RE.finditer(dex_bytes):
        try:
            results.append(m.group(0).decode("utf-8", errors="ignore"))
        except Exception:
            continue
    return results


# ============================================================
# NATIVE METHOD COUNT
# ============================================================
_NATIVE_METHOD_RE = re.compile(
    rb"\.method\s+[^.\n]*\bnative\b[^.\n]*\(",
    re.MULTILINE,
)
_NATIVE_METHOD_SMALI_RE = re.compile(
    r"\.method\s+[^\n]*\bnative\b[^\n]*\(",
    re.MULTILINE,
)


def _count_native_methods_raw(dex_bytes: bytes) -> int:
    """Đếm native methods từ raw dex bytes (heuristic)."""
    return len(_NATIVE_METHOD_RE.findall(dex_bytes))


# ============================================================
# ENCRYPTED DEX DETECTION (global)
# ============================================================
def detect_encrypted_dex(dex_bytes: bytes) -> tuple[bool, float, int]:
    """
    Phát hiện dex có dấu hiệu bị encrypt (global).
    Return (is_encrypted, entropy, unique_bytes).
    Rule: entropy > 7.5 AND unique > 200 → encrypted.
    """
    if len(dex_bytes) < _ENCRYPTED_MIN_BYTES:
        return False, 0.0, 0
    sample = dex_bytes[:_ENCRYPTED_MIN_BYTES * 4]
    entropy = shannon_entropy(sample)
    unique = unique_byte_count(sample)
    is_encrypted = (
        entropy >= _ENCRYPTED_ENTROPY_MIN
        and unique >= _ENCRYPTED_UNIQUE_MIN
    )
    return is_encrypted, entropy, unique


def detect_encrypted_regions(dex_bytes: bytes) -> WindowEntropyResult:
    """
    Wrapper cho entropy_window_analysis — semantic alias cho case
    "detect partial encryption" trong dex.
    """
    return entropy_window_analysis(dex_bytes)


# ============================================================
# STUB APP DETECTION
# ============================================================
def detect_stub_application(
    smali_content: str,
) -> tuple[bool, int, list[str]]:
    """Detect Application class dạng stub (packer shell)."""
    lines = smali_content.splitlines()
    line_count = len(lines)
    matched = [kw for kw in _STUB_APP_KEYWORDS if kw in smali_content]
    is_stub = line_count <= _STUB_APP_MAX_LINES and bool(matched)
    return is_stub, line_count, matched


# ============================================================
# MAIN DETECTION
# ============================================================
def detect_packer_via_bytecode(
    apk_path: str,
    signatures: dict | None = None,
) -> BytecodeDetection | None:
    """
    Detect packer từ dex bytecode patterns.

    v4: thêm window entropy analysis. Dex có region encrypted
    (global entropy thấp nhưng >20% windows high) vẫn flag packer.
    """
    sigs = signatures if signatures is not None else _BYTECODE_SIGNATURES

    if not apk_path or not os.path.exists(apk_path):
        return None

    dex_entries = _read_dex_entries(apk_path)
    if not dex_entries:
        return None

    # Aggregate evidence across all dex files
    all_strings: list[str] = []
    total_native = 0
    encrypted_count = 0
    region_encrypted_count = 0
    max_entropy = 0.0
    max_window_entropy = 0.0
    total_high_windows = 0

    for _name, raw in dex_entries:
        strings = _iter_strings(raw)
        all_strings.extend(strings)

        total_native += _count_native_methods_raw(raw)

        # Global entropy check
        enc, entropy, _unique = detect_encrypted_dex(raw)
        if enc:
            encrypted_count += 1
        max_entropy = max(max_entropy, entropy)

        # v4: window analysis
        window = entropy_window_analysis(raw)
        if window.has_encrypted_region:
            region_encrypted_count += 1
        max_window_entropy = max(
            max_window_entropy, window.max_entropy
        )
        total_high_windows += window.high_entropy_count

    strings_blob = "\n".join(all_strings)

    # Match từng signature
    best: BytecodeDetection | None = None
    best_score = 0

    for name, sig in sigs.items():
        evidence: list[str] = []
        score = 0

        # --- Stub classes ---
        for pat in sig.get("stub_classes", ()):
            if pat.search(strings_blob):
                evidence.append(f"stub_class:{pat.pattern}")
                score += 3

        # --- Invocations ---
        for pat in sig.get("invocations", ()):
            if pat.search(strings_blob):
                evidence.append(f"invocation:{pat.pattern}")
                score += 2

        # --- Encrypted dex signal (nếu signature yêu cầu) ---
        if sig.get("encrypted_dex"):
            if encrypted_count > 0:
                evidence.append(
                    f"encrypted_dex:{encrypted_count}/"
                    f"{len(dex_entries)} entropy={max_entropy:.2f}"
                )
                score += 2
            elif region_encrypted_count > 0:
                # v4: partial encryption vẫn là signal
                evidence.append(
                    f"encrypted_region:{region_encrypted_count}/"
                    f"{len(dex_entries)} "
                    f"max_window={max_window_entropy:.2f} "
                    f"high_windows={total_high_windows}"
                )
                score += 2

        # --- Native mass ---
        native_req = sig.get("native_mass")
        if native_req and total_native >= native_req:
            evidence.append(f"native_mass:{total_native}>={native_req}")
            score += 1

        # --- Chỉ accept nếu có ít nhất 1 evidence ---
        if score > 0 and score > best_score:
            best_score = score
            best = BytecodeDetection(
                name=name,
                confidence=sig.get("confidence", "low"),
                patchable=sig.get("patchable", False),
                evidence=evidence,
                entropy=max_entropy,
                native_count=total_native,
                notes=sig.get("notes", ""),
                max_window_entropy=max_window_entropy,
                high_entropy_windows=total_high_windows,
            )

    return best


# ============================================================
# PUBLIC HELPER
# ============================================================
def augment_packer_result(
    apk_path: str,
    primary: dict | None,
    signatures: dict | None = None,
) -> dict | None:
    """
    Combine primary detection (từ packer_check.py) với bytecode fallback.
    primary != None → giữ nguyên. primary == None → chạy fallback.
    """
    if primary is not None:
        return primary

    detection = detect_packer_via_bytecode(apk_path, signatures)
    if detection is None:
        return None

    return {
        "name": detection.name,
        "confidence": detection.confidence,
        "patchable": detection.patchable,
        "evidence": detection.evidence,
        "source": "bytecode",
        "notes": detection.notes,
        "max_window_entropy": detection.max_window_entropy,
        "high_entropy_windows": detection.high_entropy_windows,
    }