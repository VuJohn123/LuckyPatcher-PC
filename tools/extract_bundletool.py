"""
Giải nén bundletool.jar từ split-zip.
Có fallback graceful: không crash nếu split-zip hỏng.
"""
from __future__ import annotations

import glob
import os
import sys
import zipfile


def _try_zip(path: str) -> zipfile.ZipFile | None:
    """Mở zip, trả về None nếu lỗi thay vì raise."""
    try:
        return zipfile.ZipFile(path, "r")
    except (zipfile.BadZipFile, OSError):
        return None


def _extract_jar_from(zip_path: str, tools_dir: str) -> str | None:
    """Thử extract .jar từ 1 file zip. Trả về path hoặc None."""
    z = _try_zip(zip_path)
    if z is None:
        return None
    try:
        jars = [n for n in z.namelist() if n.endswith(".jar")]
        if not jars:
            return None
        z.extract(jars[0], tools_dir)
        extracted = os.path.join(tools_dir, os.path.basename(jars[0]))
        target = os.path.join(tools_dir, "bundletool.jar")
        if os.path.abspath(extracted) != os.path.abspath(target):
            os.replace(extracted, target)
        return target
    finally:
        z.close()


def extract_bundletool(tools_dir: str) -> str | None:
    """Thử nhiều chiến lược để có bundletool.jar."""
    target = os.path.join(tools_dir, "bundletool.jar")
    if os.path.exists(target):
        print(f"[i] bundletool.jar đã tồn tại: {target}")
        return target

    # Chiến lược 1: thử bundletool.zip trực tiếp (không phải split)
    main = os.path.join(tools_dir, "bundletool.zip")
    if os.path.exists(main):
        result = _extract_jar_from(main, tools_dir)
        if result:
            print(f"[✔] bundletool.jar ready (từ .zip): {result}")
            return result

    # Chiến lược 2: merge split-zip
    parts = sorted(glob.glob(os.path.join(tools_dir, "bundletool.z[0-9]*")))
    if parts and os.path.exists(main):
        merged = os.path.join(tools_dir, "_bundletool_merged.zip")
        try:
            with open(merged, "wb") as out:
                for part in parts:
                    with open(part, "rb") as f:
                        out.write(f.read())
                with open(main, "rb") as f:
                    out.write(f.read())

            result = _extract_jar_from(merged, tools_dir)
            if result:
                print(f"[✔] bundletool.jar ready (merged): {result}")
                return result
        except OSError as e:
            print(f"[!] Không merge được split-zip: {e}")
        finally:
            if os.path.exists(merged):
                try:
                    os.remove(merged)
                except OSError:
                    pass

    print("[i] Không tạo được bundletool.jar — chỉ ảnh hưởng tính năng AAB → APK")
    print("[i] Tải thủ công: https://github.com/google/bundletool/releases")
    return None


def main() -> int:
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    result = extract_bundletool(tools_dir)
    # Không return lỗi — chỉ là optional tool
    return 0


if __name__ == "__main__":
    sys.exit(main())