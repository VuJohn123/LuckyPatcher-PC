"""
Script sắp xếp lại thư mục tools/ theo layout chuẩn:
  tools/
  ├── bin/                     # Executables & JARs
  │   ├── apktool.jar
  │   ├── baksmali.jar
  │   ├── smali.jar
  │   ├── uber-apk-signer.jar
  │   ├── bundletool.jar       (extracted)
  │   └── GDA/                 (GDA.exe + DLLs)
  ├── keys/                    # Giữ nguyên
  ├── proxy_service/           # Giữ nguyên
  ├── scripts/
  │   └── extract_bundletool.py
  └── README.md

Chạy 1 lần: python tools/reorganize.py
Idempotent — chạy lại không lỗi.
"""
from __future__ import annotations

import os
import shutil
import sys
import zipfile
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
BIN_DIR = TOOLS_DIR / "bin"
SCRIPTS_DIR = TOOLS_DIR / "scripts"


JARS = [
    "apktool.jar",
    "baksmali.jar",
    "smali.jar",
    "uber-apk-signer.jar",
]


def _log(msg: str) -> None:
    print(f"[reorg] {msg}")


def _move_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        _log(f"  skip (đã tồn tại): {dst.name}")
        return False
    shutil.move(str(src), str(dst))
    _log(f"  moved: {src.name} -> {dst.relative_to(TOOLS_DIR)}")
    return True


def _extract_bundletool() -> None:
    """Extract bundletool.jar từ bundletool.zip (multi-part)."""
    target = BIN_DIR / "bundletool.jar"
    if target.exists():
        _log("bundletool.jar đã có — bỏ qua extract")
        return

    z01 = TOOLS_DIR / "bundletool.z01"
    z02 = TOOLS_DIR / "bundletool.z02"
    zmain = TOOLS_DIR / "bundletool.zip"

    if not zmain.exists():
        _log("Không tìm thấy bundletool.zip — bỏ qua")
        return

    # Ghép multi-part zip nếu cần
    combined = TOOLS_DIR / "_bundletool_combined.zip"
    try:
        with open(combined, "wb") as out:
            for part in [z01, z02, zmain]:
                if part.exists():
                    with open(part, "rb") as f:
                        shutil.copyfileobj(f, out)
        _log(f"  combined -> {combined.name}")

        with zipfile.ZipFile(combined, "r") as z:
            jar_names = [n for n in z.namelist() if n.endswith(".jar")]
            if not jar_names:
                _log("  zip không chứa .jar — bỏ qua")
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(jar_names[0]) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            _log(f"  extracted: {jar_names[0]} -> bin/bundletool.jar")
    except Exception as e:
        _log(f"  extract failed: {e}")
    finally:
        if combined.exists():
            combined.unlink()


def _move_gda() -> None:
    """Di chuyển GDA.exe + folder GDA vào bin/."""
    gda_exe = TOOLS_DIR / "GDA.exe"
    gda_dir = TOOLS_DIR / "GDA"
    target_dir = BIN_DIR / "GDA"

    if gda_exe.exists() or gda_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        if gda_exe.exists():
            _move_if_exists(gda_exe, target_dir / "GDA.exe")
        if gda_dir.exists():
            for f in gda_dir.iterdir():
                _move_if_exists(f, target_dir / f.name)
            try:
                gda_dir.rmdir()
                _log("  removed empty: GDA/")
            except OSError:
                pass


def _move_scripts() -> None:
    """Move extract_bundletool.py vào scripts/."""
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    _move_if_exists(
        TOOLS_DIR / "extract_bundletool.py",
        SCRIPTS_DIR / "extract_bundletool.py",
    )


def _cleanup_bundletool_parts() -> None:
    """Xóa z01/z02/zip sau khi extract (giữ đĩa sạch)."""
    for name in ("bundletool.z01", "bundletool.z02", "bundletool.zip"):
        p = TOOLS_DIR / name
        if p.exists() and (BIN_DIR / "bundletool.jar").exists():
            p.unlink()
            _log(f"  cleaned: {name}")


def _write_readme() -> None:
    """Viết README — dùng list-join để tránh triple-quote conflict."""
    readme = TOOLS_DIR / "README.md"

    lines = [
        "# LP-PC Suite - Tools",
        "",
        "## Cau truc",
        "",
        "```",
        "tools/",
        "|-- bin/                     # Executables & JARs",
        "|   |-- apktool.jar          # Decompile / recompile APK",
        "|   |-- baksmali.jar         # Dex -> Smali (fallback)",
        "|   |-- smali.jar            # Smali -> Dex (fallback)",
        "|   |-- uber-apk-signer.jar  # Sign APK",
        "|   |-- bundletool.jar       # AAB -> APK",
        "|   `-- GDA/                 # GDA.exe + runtime",
        "|-- keys/                    # AOSP signing keys",
        "|   |-- testkey.pk8, testkey.x509.pem",
        "|   |-- platform.pk8, platform.x509.pem",
        "|   |-- media.pk8, media.x509.pem",
        "|   `-- shared.pk8, shared.x509.pem",
        "|-- proxy_service/           # AIDL proxy smali (IAP emulation)",
        "|-- scripts/",
        "|   `-- extract_bundletool.py",
        "`-- README.md",
        "```",
        "",
        "## Setup lan dau",
        "",
        "```cmd",
        "python tools\\reorganize.py",
        "```",
        "",
        "Se:",
        "1. Tao bin/, di chuyen JARs vao",
        "2. Extract bundletool.jar tu bundletool.zip",
        "3. Di chuyen GDA vao bin/GDA/",
        "4. Di chuyen script vao scripts/",
        "5. Xoa file zip cu sau khi extract",
        "",
        "## Yeu cau",
        "",
        "- Java 8+ (cho apktool, uber-apk-signer)",
        "- Python 3.11+",
        "- adb (optional - cai APK len thiet bi)",
        "- openssl + keytool (optional - sign voi platform/media/shared keys)",
        "",
    ]
    readme.write_text("\n".join(lines), encoding="utf-8")
    _log("  wrote: README.md")


def main() -> int:
    _log(f"Tools dir: {TOOLS_DIR}")
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    _log("Tao bin/")

    _log("Di chuyen JARs...")
    for jar in JARS:
        _move_if_exists(TOOLS_DIR / jar, BIN_DIR / jar)

    _log("Extract bundletool...")
    _extract_bundletool()

    _log("Di chuyen GDA...")
    _move_gda()

    _log("Di chuyen scripts...")
    _move_scripts()

    _log("Cleanup bundletool parts...")
    _cleanup_bundletool_parts()

    _log("Viet README...")
    _write_readme()

    _log("[OK] Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())