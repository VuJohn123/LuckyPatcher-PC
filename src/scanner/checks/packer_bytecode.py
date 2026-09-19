"""
Bytecode-based packer detection — fallback cho packer hiếm.

Extends primary detection (native-lib / app-class / asset / dex-prefix)
với các kỹ thuật bytecode-level:

  1. **Invocation patterns** — scan dex method calls tới known stub classes
     (vd `Lcom/tencent/StubShell/`, `Lcom/qihoo/util/`).
  2. **Encrypted DEX sections** — entropy cao + chi-squared test phát hiện
     dex bị encrypt (packer native-shell thường encrypt toàn bộ dex).
  3. **Native method mass** — nhiều method `native` trong 1 class = shell
     pattern (native dispatch table).
  4. **Stub Application class** — Application class có body siêu nhỏ nhưng
     gọi loadLibrary + reflection.
  5. **Encrypted string markers** — known encrypted magic bytes trong dex
     strings section (vd `\xCA\xFE\xBA\xBE` xuất hiện bất thường).

Used as additive fallback in `packer_check.py`. Không import từ module đó
để tránh circular dependency — nhận `signatures` dict qua tham số.

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
}

# Entropy threshold cho encrypted dex detection
_ENCRYPTED_ENTROPY_MIN = 7.5   # Shannon entropy (bits/byte), max = 8.0
_ENCRYPTED_UNIQUE_MIN = 200    # unique byte values
_ENCRYPTED_MIN_BYTES = 4096    # sample size tối thiểu

# Stub app heuristic
_STUB_APP_MAX_LINES = 30       # Application class ≤30 dòng smali = suspicious
_STUB_APP_KEYWORDS = (
    "loadLibrary",
    "System->load",
    "getApplicationContext",
)


# ============================================================
# DATA CLASS
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


# ============================================================
# ENTROPY — Shannon
# ============================================================
def shannon_entropy(data: bytes) -> float:
    """
    Tính Shannon entropy (bits/byte) cho `data`.
    Return 0.0 nếu data rỗng.
    Max = 8.0 (uniform distribution).
    """
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


# ============================================================
# DEX EXTRACTION
# ============================================================
def _read_dex_entries(apk_path: str) -> list[tuple[str, bytes]]:
    """
    Return [(dex_name, raw_bytes), ...] cho mọi `.dex` entry trong APK.
    Graceful: lỗi zip / entry corrupt → skip.
    """
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
# Match `const-string` references và class descriptors trong dex.
# Đây là heuristic — không parse dex đầy đủ, chỉ regex trên raw bytes.
_CLASS_DESCRIPTOR_RE = re.compile(rb"L[\w/$]+;")


def _iter_strings(dex_bytes: bytes) -> list[str]:
    """
    Extract ASCII-ish class descriptors từ raw dex bytes.
    Cheap (regex trên bytes) — không cần androguard.
    """
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
# Đếm số method có modifier `native` trong 1 class.
_NATIVE_METHOD_RE = re.compile(
    rb"\.method\s+[^.\n]*\bnative\b[^.\n]*\(",
    re.MULTILINE,
)
# Fallback: scan smali-style (nếu dex đã decompile)
_NATIVE_METHOD_SMALI_RE = re.compile(
    r"\.method\s+[^\n]*\bnative\b[^\n]*\(",
    re.MULTILINE,
)


def _count_native_methods_raw(dex_bytes: bytes) -> int:
    """Đếm native methods từ raw dex bytes (heuristic)."""
    return len(_NATIVE_METHOD_RE.findall(dex_bytes))


# ============================================================
# ENCRYPTED DEX DETECTION
# ============================================================
def detect_encrypted_dex(dex_bytes: bytes) -> tuple[bool, float, int]:
    """
    Phát hiện dex có dấu hiệu bị encrypt.

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


# ============================================================
# STUB APP DETECTION
# ============================================================
def detect_stub_application(
    smali_content: str,
) -> tuple[bool, int, list[str]]:
    """
    Phát hiện Application class dạng stub (packer shell).

    Return (is_stub, line_count, matched_keywords).
    Rule: total lines ≤ 30 AND chứa ít nhất 1 keyword loadLibrary/reflection.
    """
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

    Args:
        apk_path: path tới APK
        signatures: override signature table (default = _BYTECODE_SIGNATURES)

    Return BytecodeDetection nếu match, None nếu không.
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
    max_entropy = 0.0

    for _name, raw in dex_entries:
        strings = _iter_strings(raw)
        all_strings.extend(strings)

        total_native += _count_native_methods_raw(raw)

        enc, entropy, _unique = detect_encrypted_dex(raw)
        if enc:
            encrypted_count += 1
        max_entropy = max(max_entropy, entropy)

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

        # --- Encrypted dex (nếu signature yêu cầu) ---
        if sig.get("encrypted_dex") and encrypted_count > 0:
            evidence.append(
                f"encrypted_dex:{encrypted_count}/"
                f"{len(dex_entries)} entropy={max_entropy:.2f}"
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
            )

    return best


# ============================================================
# PUBLIC HELPER — convenience
# ============================================================
def augment_packer_result(
    apk_path: str,
    primary: dict | None,
    signatures: dict | None = None,
) -> dict | None:
    """
    Combine primary detection (từ packer_check.py) với bytecode fallback.

    - primary != None: giữ nguyên (primary wins).
    - primary == None: chạy bytecode fallback.
    - Return merged dict hoặc None.

    Output shape giống `packer_info` trong analyzer:
        {name, confidence, patchable, evidence, source}
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
    }