"""
Chuyển đổi .xapk → .apk an toàn.
Đảm bảo: ZipSlip guard, manifest validation, fallback khi split APK lỗi.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import zipfile

logger = logging.getLogger(__name__)


class XAPKConversionError(Exception):
    """Lỗi không thể phục hồi khi convert .xapk."""


def is_xapk(filepath: str) -> bool:
    """
    Kiểm tra magic bytes — không tin vào đuôi file.
    .xapk hợp lệ PHẢI chứa manifest.json trong ZIP root.
    """
    if not os.path.isfile(filepath):
        return False
    try:
        with zipfile.ZipFile(filepath, "r") as z:
            return "manifest.json" in z.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def convert_xapk_to_apk(
    xapk_path: str,
    output_dir: str | None = None,
    log_callback=print,
) -> str:
    """
    Convert .xapk → .apk.

    Xử lý:
      - Base APK đơn lẻ → extract + rezip
      - .xapk chứa split APK → merge base + splits
      - .xapk lỗi → raise XAPKConversionError

    Returns: đường dẫn .apk đã tạo.
    """
    if not os.path.isfile(xapk_path):
        raise XAPKConversionError(f"File không tồn tại: {xapk_path}")

    if not is_xapk(xapk_path):
        raise XAPKConversionError(
            f"Không phải .xapk hợp lệ (thiếu manifest.json): {xapk_path}"
        )

    if output_dir is None:
        output_dir = os.path.dirname(xapk_path)
    os.makedirs(output_dir, exist_ok=True)

    out_apk = os.path.join(
        output_dir,
        os.path.splitext(os.path.basename(xapk_path))[0] + ".apk",
    )

    log_callback(f"[*] [XAPK] Converting: {os.path.basename(xapk_path)}")
    temp_dir = tempfile.mkdtemp(prefix="xapk_")
    try:
        with zipfile.ZipFile(xapk_path, "r") as z:
            _safe_extract(z, temp_dir)

        package_name = _read_package_name(temp_dir)

        all_apks = [f for f in os.listdir(temp_dir) if f.endswith(".apk")]
        if not all_apks:
            raise XAPKConversionError("Không có file .apk nào trong .xapk")

        base_apk = _find_base_apk(all_apks, package_name)
        log_callback(f"[*] [XAPK] Base APK: {base_apk}")

        merged = _merge_apk_contents(temp_dir, base_apk, all_apks)

        with zipfile.ZipFile(out_apk, "w", zipfile.ZIP_DEFLATED) as zout:
            for name, data in merged.items():
                zout.writestr(name, data)

        log_callback(f"[✔] [XAPK] Converted → {out_apk}")
        return out_apk

    except XAPKConversionError:
        _cleanup_failed_output(out_apk)
        raise
    except Exception as e:
        _cleanup_failed_output(out_apk)
        raise XAPKConversionError(f"Lỗi convert .xapk: {e}") from e
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _read_package_name(temp_dir: str) -> str | None:
    """Đọc package_name từ manifest.json (nếu có)."""
    manifest_path = os.path.join(temp_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        return manifest.get("package_name")
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Không đọc được manifest.json: %s", e)
        return None


def _find_base_apk(apk_names: list[str], package_name: str | None) -> str:
    """Ưu tiên: <package>.apk > *base*.apk > *master*.apk > file đầu tiên."""
    if package_name:
        exact = f"{package_name}.apk"
        if exact in apk_names:
            return exact
    for name in apk_names:
        lower = name.lower()
        if "base" in lower or "master" in lower:
            return name
    return apk_names[0]


def _merge_apk_contents(
    temp_dir: str, base_apk: str, all_apks: list[str]
) -> dict[str, bytes]:
    """Merge nội dung base + splits. Base wins khi trùng tên."""
    merged: dict[str, bytes] = {}

    base_path = os.path.join(temp_dir, base_apk)
    with zipfile.ZipFile(base_path, "r") as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            merged[info.filename] = z.read(info.filename)

    for apk_name in all_apks:
        if apk_name == base_apk:
            continue
        apk_path = os.path.join(temp_dir, apk_name)
        try:
            with zipfile.ZipFile(apk_path, "r") as z:
                for info in z.infolist():
                    if info.is_dir():
                        continue
                    if info.filename not in merged:
                        merged[info.filename] = z.read(info.filename)
        except (zipfile.BadZipFile, OSError) as e:
            logger.warning("Bỏ qua split APK lỗi %s: %s", apk_name, e)

    return merged


def _safe_extract(zip_file: zipfile.ZipFile, dest_dir: str) -> None:
    """Chống ZipSlip — path traversal qua symlink/../."""
    dest_real = os.path.realpath(dest_dir)
    for member in zip_file.namelist():
        member_path = os.path.realpath(os.path.join(dest_real, member))
        if not (member_path == dest_real or member_path.startswith(dest_real + os.sep)):
            raise XAPKConversionError(f"Phát hiện path traversal: {member}")
    zip_file.extractall(dest_dir)


def _cleanup_failed_output(path: str) -> None:
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass