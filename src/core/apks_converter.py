"""
Chuyển .apks / bundle ZIP → .apk đơn.

Hỗ trợ 4 layouts (tự detect):
  1. universal.apk                    (bundletool --mode=universal)
  2. standalones/*.apk                (bundletool --mode=default, standalone)
  3. splits/*.apk                     (bundletool --mode=default, splits/)
  4. base.apk + split_config.*.apk    (APKPure "apkcube" / raw split ZIP)

ZipSlip guard giống xapk_converter.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
import zipfile

logger = logging.getLogger(__name__)


class APKSConversionError(Exception):
    """Lỗi không thể phục hồi khi convert .apks."""


def is_apks(filepath: str) -> bool:
    """
    Detect bundletool .apks bằng toc.pb.
    KHÔNG dùng để gate convert — chỉ dùng để phân biệt với .xapk.
    """
    if not os.path.isfile(filepath):
        return False
    try:
        with zipfile.ZipFile(filepath, "r") as z:
            return "toc.pb" in z.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def is_bundle_zip(filepath: str) -> bool:
    """
    Detect BẤT KỲ ZIP nào chứa .apk bên trong (root hoặc folder con).
    Dùng cho normalize_input() để không bỏ sót case APKPure .apks.
    """
    if not os.path.isfile(filepath):
        return False
    try:
        with zipfile.ZipFile(filepath, "r") as z:
            return any(n.endswith(".apk") for n in z.namelist())
    except (zipfile.BadZipFile, OSError):
        return False


def convert_apks_to_apk(
    apks_path: str,
    output_dir: str | None = None,
    log_callback=print,
) -> str:
    """
    Convert .apks (mọi layout) → .apk đơn.

    Detect layout tự động theo thứ tự ưu tiên:
      1. universal.apk           → copy
      2. standalones/*.apk       → copy (arm64 > armeabi)
      3. splits/*.apk            → merge
      4. base.apk at root + *    → merge (APKPure apkcube)
    """
    if not os.path.isfile(apks_path):
        raise APKSConversionError(f"File không tồn tại: {apks_path}")

    if not is_bundle_zip(apks_path):
        raise APKSConversionError(
            f"Không phải bundle ZIP hợp lệ (không có .apk bên trong): "
            f"{apks_path}"
        )

    if output_dir is None:
        output_dir = os.path.dirname(apks_path)
    os.makedirs(output_dir, exist_ok=True)

    out_apk = os.path.join(
        output_dir,
        os.path.splitext(os.path.basename(apks_path))[0] + ".apk",
    )

    log_callback(f"[*] [APKS] Converting: {os.path.basename(apks_path)}")
    temp_dir = tempfile.mkdtemp(prefix="apks_")

    try:
        with zipfile.ZipFile(apks_path, "r") as z:
            names = z.namelist()
            _safe_extract(z, temp_dir)

        # --- Layout 1: universal ---
        if "universal.apk" in names:
            log_callback("[*] [APKS] Layout: universal.apk")
            shutil.copy2(os.path.join(temp_dir, "universal.apk"), out_apk)
            log_callback(f"[✔] [APKS] Converted → {out_apk}")
            return out_apk

        # --- Layout 2: standalones/ ---
        standalones = [
            n for n in names
            if n.startswith("standalones/") and n.endswith(".apk")
        ]
        if standalones:
            standalones.sort(key=lambda n: (
                0 if "arm64" in n.lower() else
                1 if "armeabi" in n.lower() else
                2
            ))
            chosen = standalones[0]
            log_callback(f"[*] [APKS] Layout: standalones/ → {chosen}")
            shutil.copy2(os.path.join(temp_dir, chosen), out_apk)
            log_callback(f"[✔] [APKS] Converted → {out_apk}")
            return out_apk

        # --- Layout 3: splits/ ---
        splits = [
            n for n in names
            if n.startswith("splits/") and n.endswith(".apk")
        ]
        if splits:
            splits_dir = os.path.join(temp_dir, "splits")
            base_name = _find_base_split(
                [os.path.basename(s) for s in splits]
            )
            if not base_name:
                raise APKSConversionError(
                    "Không tìm thấy base split trong splits/"
                )
            log_callback(
                f"[*] [APKS] Layout: splits/ — "
                f"base={base_name}, total={len(splits)}"
            )
            merged = _merge_apk_files(
                splits_dir,
                base_name,
                [os.path.basename(s) for s in splits],
            )
            _write_merged(out_apk, merged)
            log_callback(f"[✔] [APKS] Converted → {out_apk}")
            return out_apk

        # --- Layout 4: base.apk at root (APKPure apkcube) ---
        root_apks = [
            n for n in names
            if n.endswith(".apk") and "/" not in n
        ]
        if root_apks:
            base_name = _find_base_split(root_apks)
            if not base_name:
                raise APKSConversionError(
                    f"Không tìm thấy base.apk ở root: {root_apks[:5]}..."
                )
            log_callback(
                f"[*] [APKS] Layout: root splits — "
                f"base={base_name}, total={len(root_apks)}"
            )
            merged = _merge_apk_files(temp_dir, base_name, root_apks)
            _write_merged(out_apk, merged)
            log_callback(f"[✔] [APKS] Converted → {out_apk}")
            return out_apk

        # --- Không detect được ---
        raise APKSConversionError(
            "Không nhận diện được layout .apks. "
            "Cần có: universal.apk | standalones/*.apk | "
            "splits/*.apk | base.apk"
        )

    except APKSConversionError:
        _cleanup_failed_output(out_apk)
        raise
    except Exception as e:
        _cleanup_failed_output(out_apk)
        raise APKSConversionError(f"Lỗi convert .apks: {e}") from e
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================
# INTERNALS
# ============================================================

def _find_base_split(names: list[str]) -> str | None:
    """Ưu tiên: base.apk > base-master.apk > master.apk > *base*.apk."""
    for candidate in ("base.apk", "base-master.apk", "master.apk"):
        if candidate in names:
            return candidate
    for n in names:
        if "base" in n.lower():
            return n
    return None


def _merge_apk_files(
    dir_path: str, base_name: str, all_apks: list[str]
) -> dict[str, bytes]:
    """
    Merge base + splits. Base wins khi trùng tên.
    Chỉ merge .so native libs + resources + dex + manifest.
    """
    merged: dict[str, bytes] = {}

    base_path = os.path.join(dir_path, base_name)
    with zipfile.ZipFile(base_path, "r") as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            merged[info.filename] = z.read(info.filename)

    for name in all_apks:
        if name == base_name:
            continue
        path = os.path.join(dir_path, name)
        try:
            with zipfile.ZipFile(path, "r") as z:
                for info in z.infolist():
                    if info.is_dir():
                        continue
                    if info.filename not in merged:
                        merged[info.filename] = z.read(info.filename)
        except (zipfile.BadZipFile, OSError) as e:
            logger.warning("Bỏ qua split lỗi %s: %s", name, e)

    return merged


def _write_merged(out_path: str, merged: dict[str, bytes]) -> None:
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in merged.items():
            zout.writestr(name, data)


def _safe_extract(zip_file: zipfile.ZipFile, dest_dir: str) -> None:
    """ZipSlip guard — giống xapk_converter."""
    dest_real = os.path.realpath(dest_dir)
    for member in zip_file.namelist():
        member_path = os.path.realpath(os.path.join(dest_real, member))
        if not (
            member_path == dest_real
            or member_path.startswith(dest_real + os.sep)
        ):
            raise APKSConversionError(
                f"Phát hiện path traversal: {member}"
            )
    zip_file.extractall(dest_dir)


def _cleanup_failed_output(path: str) -> None:
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass