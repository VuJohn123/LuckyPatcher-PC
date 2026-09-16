"""
Giải nén bundletool.jar từ split-zip.
Graceful fallback — không bao giờ crash.
"""
from __future__ import annotations

import glob
import os
import sys
import zipfile


def _extract_jar_from(zip_path: str, tools_dir: str) -> str | None:
    """
    Thử extract .jar từ 1 file zip.
    Trả về path hoặc None. Không raise bất kỳ exception nào.
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            jars = [n for n in z.namelist() if n.endswith(".jar")]
            if not jars:
                return None

            # Đọc trực tiếp bytes → ghi thủ công (tránh z.extract hay crash)
            try:
                jar_data = z.read(jars[0])
            except (zipfile.BadZipFile, OSError, RuntimeError) as e:
                print(f"[!] Không đọc được jar trong {os.path.basename(zip_path)}: {e}")
                return None

            if not jar_data or len(jar_data) < 4:
                print(f"[!] Jar rỗng trong {os.path.basename(zip_path)}")
                return None

            # Kiểm tra magic bytes của JAR (ZIP header: PK\x03\x04)
            if jar_data[:4] != b"PK\x03\x04":
                print(f"[!] Dữ liệu jar không hợp lệ (magic bytes sai)")
                return None

            target = os.path.join(tools_dir, "bundletool.jar")
            with open(target, "wb") as f:
                f.write(jar_data)
            return target

    except zipfile.BadZipFile as e:
        print(f"[!] {os.path.basename(zip_path)} không phải zip hợp lệ: {e}")
        return None
    except (OSError, RuntimeError) as e:
        print(f"[!] Lỗi xử lý {os.path.basename(zip_path)}: {e}")
        return None


def extract_bundletool(tools_dir: str) -> str | None:
    """Thử nhiều chiến lược để có bundletool.jar. Không raise."""
    target = os.path.join(tools_dir, "bundletool.jar")
    if os.path.exists(target) and os.path.getsize(target) > 4:
        print(f"[i] bundletool.jar đã tồn tại: {target}")
        return target

    main = os.path.join(tools_dir, "bundletool.zip")

    # Chiến lược 1: bundletool.zip trực tiếp
    if os.path.exists(main):
        print(f"[*] Thử extract từ {main}...")
        result = _extract_jar_from(main, tools_dir)
        if result:
            print(f"[✔] bundletool.jar ready: {result}")
            return result

    # Chiến lược 2: merge split-zip
    parts = sorted(glob.glob(os.path.join(tools_dir, "bundletool.z[0-9]*")))
    if parts and os.path.exists(main):
        print(f"[*] Thử merge {len(parts)} split-parts + main...")
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
            print(f"[!] Không merge được: {e}")
        finally:
            if os.path.exists(merged):
                try:
                    os.remove(merged)
                except OSError:
                    pass

    # Chiến lược 3: tìm bất kỳ file bundletool*.jar nào đã có
    for pattern in ("bundletool*.jar", "bundletool-all*.jar"):
        for f in glob.glob(os.path.join(tools_dir, pattern)):
            if os.path.getsize(f) > 4:
                print(f"[i] Tìm thấy: {f}")
                return f

    print()
    print("[i] ════════════════════════════════════════════════════════════")
    print("[i] Không tạo được bundletool.jar")
    print("[i] Tính năng AAB → APK sẽ không hoạt động.")
    print("[i] Tải thủ công tại:")
    print("[i]   https://github.com/google/bundletool/releases")
    print("[i] Đặt file .jar vào: tools/bundletool.jar")
    print("[i] ════════════════════════════════════════════════════════════")
    return None


def main() -> int:
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    extract_bundletool(tools_dir)
    return 0  # Luôn return 0 — tool optional


if __name__ == "__main__":
    sys.exit(main())