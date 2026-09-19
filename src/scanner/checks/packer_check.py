"""
Packer detection — nhận diện APK bị pack/bảo vệ.

Mục đích:
  - Cảnh báo user APK packed → patch license/iap/ads có thể fail silently
  - Đặc biệt PairIP (Google Play) khiến LicensePatcher match 0 files vì
    license logic nằm trong native VM (libpairipcore.so), không phải
    LVL chuẩn `com.android.vending.licensing.*`.

Detect bằng 4 nguồn (primary tier):
  1. Manifest application class name
  2. DEX class prefixes
  3. Native libs (.so trong lib/<abi>/)
  4. Assets entries

Bytecode fallback (tier 5): triển khai ở `packer_bytecode.py` — chạy khi
primary tier không match được gì. Wrapper `check_packer_with_fallback()`
gộp cả 2 tier trong 1 call.

Reference signatures (tổng hợp từ APKiD / public research):
  - PairIP: com.pairip.* (Google Play App Signing protection)
  - 360 Jiagu: com.qihoo.util.*, libjiagu.so
  - Tencent Legu: com.tencent.StubShell.*, libshell.so
  - Bangcle: com.bangcle.*, libsecexe.so
  - Alibaba: com.ali.mobisecenhance.*
  - IJiami: s.h.e.l.l.*, libshella.so
  - LIAPP: com.liapp.*
  - SecNeo: com.secneo.*
  - DexGuard: com.guardsquare.dexguard.* (obfuscator, patchable)
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from androguard.core.dex import DEX

logger = logging.getLogger(__name__)

_ANDROID_NS = "{http://schemas.android.com/apk/res/android}"


# ============================================================
# SIGNATURE TABLE
# ============================================================
# confidence: "high" (chắc chắn), "medium", "low"
# patchable: False = không patch được với static tool hiện tại
_PACKER_SIGNATURES: dict[str, dict] = {
    "PairIP (Google Play)": {
        "confidence": "high",
        "patchable": False,
        "app_classes": [
            "com.pairip.application.Application",
        ],
        "dex_prefixes": [
            "Lcom/pairip/application/",
            "Lcom/pairip/licensecheck/",
            "Lcom/pairip/VMRunner",
            "Lcom/pairip/StartupLauncher",
        ],
        "native_libs": ["libpairipcore.so"],
        "assets": [],
    },
    "360 Jiagu": {
        "confidence": "high",
        "patchable": False,
        "app_classes": [
            "com.qihoo.util.StubApplication",
            "com.stub.StubApp",
        ],
        "dex_prefixes": [
            "Lcom/qihoo/util/",
            "Lcom/stub/StubApp",
        ],
        "native_libs": [
            "libjiagu.so", "libjiagu_art.so",
            "libjiagu_x86.so", "libjiagu_x64.so",
        ],
        "assets": [],
    },
    "Tencent Legu": {
        "confidence": "high",
        "patchable": False,
        "app_classes": [
            "com.tencent.StubShell.TxAppEntry",
        ],
        "dex_prefixes": ["Lcom/tencent/StubShell/"],
        "native_libs": [
            "libshell.so", "libshella.so",
            "libtup.so", "libtosprotection.so",
        ],
        "assets": [],
    },
    "Bangcle": {
        "confidence": "high",
        "patchable": False,
        "app_classes": [
            "com.bangcle.application.ProtectApplication",
        ],
        "dex_prefixes": ["Lcom/bangcle/"],
        "native_libs": [
            "libsecexe.so", "libsecmain.so", "libsecpreload.so",
        ],
        "assets": ["classes.jar"],
    },
    "Alibaba Mobile Security": {
        "confidence": "high",
        "patchable": False,
        "app_classes": [
            "com.ali.mobisecenhance.StubApplication",
        ],
        "dex_prefixes": ["Lcom/ali/mobisecenhance/"],
        "native_libs": ["libmobisec.so", "libfakejni.so"],
        "assets": [],
    },
    "IJiami": {
        "confidence": "high",
        "patchable": False,
        "app_classes": ["s.h.e.l.l.S"],
        "dex_prefixes": ["Ls/h/e/l/l/"],
        "native_libs": ["libshella.so", "libshella-2.so"],
        "assets": ["ijiami.dat", "ijiami.ajm"],
    },
    "LIAPP": {
        "confidence": "high",
        "patchable": False,
        "app_classes": ["com.liapp.application.LIAPPApplication"],
        "dex_prefixes": ["Lcom/liapp/"],
        "native_libs": ["libliapp.so", "libliappstart.so"],
        "assets": [],
    },
    "SecNeo": {
        "confidence": "high",
        "patchable": False,
        "app_classes": ["com.secneo.apkwrapper.ApplicationWrapper"],
        "dex_prefixes": ["Lcom/secneo/"],
        "native_libs": ["libsecexe.so", "libsecmain.so"],
        "assets": [],
    },
    "Krypton": {
        "confidence": "medium",
        "patchable": False,
        "app_classes": [],
        "dex_prefixes": ["Lcom/krypton/"],
        "native_libs": ["libkrypton.so"],
        "assets": [],
    },
    "DexGuard": {
        "confidence": "medium",
        "patchable": True,   # Obfuscator, không phải packer cứng
        "app_classes": [],
        "dex_prefixes": ["Lcom/guardsquare/dexguard/"],
        "native_libs": [],
        "assets": ["DexGuard"],
    },
}


# ============================================================
# PUBLIC API — PRIMARY TIER
# ============================================================
def check_packer(
    apk,
    apk_path: str,
    get_all_dex_bytes,
    findings: list[dict],
    available_patches: list[str],
) -> dict | None:
    """
    Detect packer qua 4 nguồn chính (app/lib/asset/dex-prefix).

    Append finding vào `findings` nếu phát hiện.

    Returns:
        dict info packer detected (hoặc None nếu clean).
        Shape: {name, confidence, patchable, evidence}
    """
    app_class = _get_application_class(apk)
    entries = _get_zip_entries(apk)
    native_libs = _native_lib_names(entries)
    assets = _asset_names(entries)

    detected: list[tuple[str, dict, list[str]]] = []

    for name, sig in _PACKER_SIGNATURES.items():
        evidence: list[str] = []

        # 1. Application class
        if app_class and sig["app_classes"]:
            for cls in sig["app_classes"]:
                if app_class == cls or app_class.startswith(cls + "."):
                    evidence.append(f"Application: {app_class}")
                    break

        # 2. Native libs
        if native_libs and sig["native_libs"]:
            for lib in sig["native_libs"]:
                if lib in native_libs:
                    evidence.append(f"Native lib: {lib}")

        # 3. Assets
        if assets and sig["assets"]:
            for asset in sig["assets"]:
                if asset in assets:
                    evidence.append(f"Asset: assets/{asset}")

        # 4. DEX class prefixes (chậm hơn, chỉ scan nếu chưa có evidence)
        if not evidence and sig["dex_prefixes"]:
            dex_hit = _scan_dex_prefixes(
                get_all_dex_bytes, sig["dex_prefixes"]
            )
            if dex_hit:
                evidence.append(f"DEX class: {dex_hit}")

        if evidence:
            detected.append((name, sig, evidence))

    if not detected:
        findings.append({
            "type": "no_packer",
            "color": None,
            "title": "Packer / Protector",
            "description": "Not detected",
            "details": [],
            "action": None,
        })
        return None

    # Chọn packer có confidence cao nhất
    detected.sort(
        key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(
            x[1]["confidence"], 3
        )
    )
    primary_name, primary_sig, primary_evidence = detected[0]

    patchable = primary_sig["patchable"]
    confidence = primary_sig["confidence"]

    # Color: red nếu không patchable, yellow nếu patchable
    color = "yellow" if patchable else "red"

    # Warning message
    if patchable:
        warning = (
            "APK có obfuscation — patch có thể chạy nhưng kết quả "
            "analyzer có thể kém chính xác."
        )
    else:
        warning = (
            "APK packed bằng protector cứng. Các patch license/iap/ads "
            "có thể patch 0 files (silent fail) vì logic bảo vệ nằm "
            "trong native VM (lib*.so). Cân nhắc dùng công cụ unpack "
            "trước hoặc chấp nhận patch chỉ 1 phần."
        )

    details = [f"Confidence: {confidence}"] + primary_evidence
    if len(detected) > 1:
        details.append(
            f"Other signatures: {', '.join(d[0] for d in detected[1:])}"
        )

    findings.append({
        "type": "packer",
        "color": color,
        "title": f"Packed: {primary_name}",
        "description": warning,
        "details": details,
        "action": None,
    })

    logger.info(
        "Packer detected: %s (confidence=%s, patchable=%s, evidence=%d)",
        primary_name, confidence, patchable, len(primary_evidence),
    )

    return {
        "name": primary_name,
        "confidence": confidence,
        "patchable": patchable,
        "evidence": primary_evidence,
    }


# ============================================================
# PUBLIC API — WITH BYTECODE FALLBACK (tier 5)
# ============================================================
def check_packer_with_fallback(
    apk,
    apk_path: str,
    get_all_dex_bytes,
    findings: list[dict],
    available_patches: list[str],
) -> dict | None:
    """
    Same as `check_packer` nhưng thêm bytecode fallback tier.

    Flow:
      1. Gọi `check_packer` (primary 4 tier).
      2. Nếu primary None → gọi `augment_packer_result` (bytecode tier).
      3. Nếu bytecode match → append finding + trả về dict.

    Dùng wrapper này để 1 call site duy nhất — không cần sửa analyzer.

    Return shape giống `check_packer`: {name, confidence, patchable,
    evidence} hoặc None.
    """
    # --- Tier 1-4: primary ---
    primary = check_packer(
        apk, apk_path, get_all_dex_bytes, findings, available_patches,
    )
    if primary is not None:
        return primary

    # --- Tier 5: bytecode fallback ---
    # Note: check_packer đã append "no_packer" finding khi return None.
    # Nếu bytecode match → ta cần sửa finding đó, không phải append thêm.
    try:
        from scanner.checks.packer_bytecode import augment_packer_result
    except ImportError as e:
        logger.debug("Bytecode fallback unavailable: %s", e)
        return None

    try:
        fallback = augment_packer_result(apk_path, None)
    except Exception as e:
        logger.warning("Bytecode fallback crashed: %s", e)
        return None

    if fallback is None:
        return None

    # Bytecode match → replace "no_packer" finding nếu có
    _replace_no_packer_finding(findings, fallback, apk_path)

    return fallback


def _replace_no_packer_finding(
    findings: list[dict],
    fallback: dict,
    apk_path: str,
) -> None:
    """
    Nếu `findings` đang chứa `no_packer` (do primary None), thay thế
    bằng finding `packer` từ bytecode fallback.
    Nếu không có `no_packer` → append mới.
    """
    packable = fallback.get("patchable", False)
    color = "yellow" if packable else "red"

    if packable:
        warning = (
            "APK có obfuscation (detected qua bytecode) — patch có thể "
            "chạy nhưng kết quả analyzer có thể kém chính xác."
        )
    else:
        warning = (
            "APK packed — phát hiện qua bytecode fallback. Các patch "
            "license/iap/ads có thể patch 0 files (silent fail) vì "
            "logic bảo vệ nằm trong native VM."
        )

    details = (
        [f"Confidence: {fallback.get('confidence', '?')}"]
        + fallback.get("evidence", [])
        + ["Source: bytecode fallback"]
    )

    new_finding = {
        "type": "packer",
        "color": color,
        "title": f"Packed: {fallback['name']}",
        "description": warning,
        "details": details,
        "action": None,
    }

    # Replace in-place
    for i, f in enumerate(findings):
        if f.get("type") == "no_packer":
            findings[i] = new_finding
            return

    # Không có no_packer → append
    findings.append(new_finding)


# ============================================================
# HELPERS
# ============================================================
def _get_application_class(apk) -> str | None:
    """Đọc android:name của thẻ <application>."""
    # Cách 1: parse manifest XML
    try:
        import xml.etree.ElementTree as _ET
        raw = apk.get_android_manifest_axml().get_xml()
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        root = _ET.fromstring(raw)
        app = root.find("application")
        if app is not None:
            cls = app.get(f"{_ANDROID_NS}name")
            if cls:
                return cls.lstrip(".")
    except Exception:
        pass

    # Cách 2: get_android_manifest_xml
    try:
        xml = apk.get_android_manifest_xml()
        for app in xml.findall("application"):
            cls = app.get(f"{_ANDROID_NS}name")
            if cls:
                return cls.lstrip(".")
    except Exception:
        pass

    return None


def _get_zip_entries(apk) -> set[str]:
    """All entry names trong APK zip."""
    try:
        files = apk.get_files()
        return set(files) if files else set()
    except Exception:
        return set()


def _native_lib_names(entries: set[str]) -> set[str]:
    """Basename của .so trong lib/<abi>/."""
    names: set[str] = set()
    for e in entries:
        if e.startswith("lib/") and e.endswith(".so"):
            names.add(e.rsplit("/", 1)[-1])
    return names


def _asset_names(entries: set[str]) -> set[str]:
    """Asset paths (không có prefix 'assets/')."""
    return {
        e[len("assets/"):]
        for e in entries
        if e.startswith("assets/")
    }


def _scan_dex_prefixes(
    get_all_dex_bytes, prefixes: list[str],
) -> str | None:
    """
    Scan DEX classes tìm class có prefix match.
    Return class name đầu tiên match (không có leading 'L').
    """
    for dex_name, dex_bytes in get_all_dex_bytes():
        try:
            dex = DEX(dex_bytes)
        except Exception:
            continue
        try:
            for cls in dex.get_classes():
                try:
                    cname = cls.get_name()
                except Exception:
                    continue
                for prefix in prefixes:
                    if cname.startswith(prefix):
                        return cname
        except Exception as e:
            logger.debug("DEX scan failed %s: %s", dex_name, e)
            continue
    return None