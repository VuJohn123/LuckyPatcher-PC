"""
Tiện ích xử lý Smali — regex + file cache + APK cache.
Tối ưu: orjson > json, memory-mapped files.

LƯU Ý VỀ REGEX ENGINE:
  - Dùng stdlib `re` (ổn định, đầy đủ API: DOTALL, IGNORECASE, lookahead)
  - KHÔNG dùng google-re2: API khác biệt (không có re.DOTALL), thiếu
    lookahead/lookbehind, và regex trong module này không phải hot path
    (chỉ chạy trên file smali ~KB, không phải string MB).
  - Nếu cần tốc độ regex cao hơn trong tương lai, viết adapter class
    riêng wrap re2.Options() để tương thích flag.
"""
from __future__ import annotations

import hashlib
import mmap
import os
import re  # stdlib — ổn định, đầy đủ API
from concurrent.futures import ProcessPoolExecutor, as_completed

RE_ENGINE = "re"  # constant để hiển thị startup info

# JSON engine: orjson (Rust) > stdlib json
try:
    import orjson as _orjson
    JSON_FAST = True

    def json_loads(data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        return _orjson.loads(data)

    def json_dumps(obj) -> str:
        return _orjson.dumps(obj).decode("utf-8")

except ImportError:
    import json as _json
    JSON_FAST = False

    def json_loads(data):
        return _json.loads(data)

    def json_dumps(obj) -> str:
        return _json.dumps(obj)


# ============================================================
# REGEX CONSTANTS
# ============================================================

# Match nhiều modifier (public, static, final, ...) theo thứ tự bất kỳ
_METHOD_MODS = (
    r"(?:(?:public|private|protected|static|final|synthetic|abstract|"
    r"declared-synchronized)\s+)+"
)

# Group 1 = tên method
REGEX_BOOLEAN_METHOD = re.compile(
    r"\.method\s+" + _METHOD_MODS + r"(\S+)\s*\(.*?\)\s*Z\s*.*?\.end\s+method",
    re.DOTALL,
)

# Group 1 = tên method, group 2 = return type (V | Bundle)
REGEX_IAP_BILLING_METHOD = re.compile(
    r"\.method\s+" + _METHOD_MODS
    + r"(\S+)\s*\([^)]*\)\s*(V|Landroid/os/Bundle;)\s*.*?\.end\s+method",
    re.DOTALL,
)

# Group 1 = tên method
REGEX_SIGNATURE_METHOD = re.compile(
    r"\.method\s+" + _METHOD_MODS
    + r"(\w+)\s*\(.*?\)\s*Z\s*\.registers\s+\d+\s*.*?\.end\s+method",
    re.DOTALL,
)

# Group 1 = tên method
REGEX_INTEGRITY_METHOD = re.compile(
    r"\.method\s+" + _METHOD_MODS + r"(\S+)\s*\(.*?\)\s*Z\s*.*?\.end\s+method",
    re.DOTALL,
)

REGEX_LICENSE_METHOD = REGEX_BOOLEAN_METHOD

REGEX_SERVERMANAGEDPOLICY_CONSTRUCTOR = re.compile(
    r"(\.method\s+public\s+constructor\s+<init>\(.*?\)V\s*.*?\.end\s+method)",
    re.DOTALL,
)

REGEX_INVOKE_LICENSE = re.compile(r".*invoke.*LicenseChecker.*\n")
REGEX_INVOKE_ILICENSING = re.compile(r".*invoke.*ILicensingService.*\n")

REGEX_ADS_URL = re.compile(r'"https?://[^"]*')

REGEX_MANIFEST_PERMISSION = re.compile(
    r'<uses-permission\s+android:name="([^"]+)"\s*/?>', re.IGNORECASE
)
REGEX_MANIFEST_ACTIVITY = re.compile(
    r'<activity[^>]*android:name="([^"]+)"[^/]*/?>', re.DOTALL
)
REGEX_MANIFEST_RECEIVER = re.compile(
    r'<receiver[^>]*android:name="([^"]+)"[^/]*/?>', re.DOTALL
)


# ============================================================
# PATH HELPERS
# ============================================================

def get_smali_dirs(decompiled_path: str) -> list[str]:
    smali_dirs = []
    try:
        for item in os.listdir(decompiled_path):
            item_path = os.path.join(decompiled_path, item)
            if os.path.isdir(item_path) and item.startswith("smali"):
                smali_dirs.append(item_path)
    except OSError:
        pass
    return smali_dirs if smali_dirs else [os.path.join(decompiled_path, "smali")]


def get_all_smali_files(decompiled_path: str) -> list[str]:
    files: list[str] = []
    for smali_dir in get_smali_dirs(decompiled_path):
        for root, _dirs, filenames in os.walk(smali_dir):
            for f in filenames:
                if f.endswith(".smali"):
                    files.append(os.path.join(root, f))
    return files


# ============================================================
# FILE CACHE
# ============================================================

class FileContentCache:
    def __init__(self, decompiled_path: str):
        self.decompiled_path = decompiled_path
        self.cache: dict[str, str] = {}

    def read(self, filepath: str) -> str:
        if filepath not in self.cache:
            try:
                file_size = os.path.getsize(filepath)
                if file_size > 1024 * 1024:
                    with open(filepath, "r+b") as f:
                        with mmap.mmap(f.fileno(), 0) as mm:
                            self.cache[filepath] = mm.read().decode(
                                "utf-8", errors="ignore"
                            )
                else:
                    with open(filepath, "r", encoding="utf-8",
                              errors="ignore") as f:
                        self.cache[filepath] = f.read()
            except (OSError, IOError, ValueError):
                self.cache[filepath] = ""
        return self.cache[filepath]

    def write(self, filepath: str, content: str) -> None:
        self.cache[filepath] = content

    def flush(self, log_callback=print) -> None:
        """
        Ghi tất cả file đã cache xuống disk.

        Error isolation: lỗi 1 file không dừng flush các file khác.
        Catch ValueError (null char trong path) và TypeError (key không phải str).
        """
        count = 0
        for filepath, content in self.cache.items():
            try:
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, "w", encoding="utf-8",
                          buffering=128 * 1024) as f:
                    f.write(content)
                count += 1
            except (OSError, IOError, ValueError, TypeError) as e:
                log_callback(f"[!] [FileCache] {filepath}: {e}")
        log_callback(f"[*] [FileCache] Đã ghi {count} file")
        self.cache.clear()

    def get_modified_files(self) -> list[str]:
        return list(self.cache.keys())

    def is_modified(self, filepath: str) -> bool:
        return filepath in self.cache


# ============================================================
# PARALLEL PROCESSOR
# ============================================================

class ParallelFileProcessor:
    def __init__(self, max_workers: int | None = None):
        self.max_workers = max_workers or min(os.cpu_count() or 4, 8)

    def process(self, files: list[str], worker_func, *args, **kwargs) -> int:
        total = 0
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(worker_func, f, *args, **kwargs): f
                for f in files
            }
            for future in as_completed(futures):
                try:
                    result = future.result()
                    total += result if isinstance(result, int) else (1 if result else 0)
                except Exception as e:
                    print(f"[!] [Parallel] {futures[future]}: {e}")
        return total


# ============================================================
# APK CACHE
# ============================================================

class APKCache:
    def __init__(self, cache_dir: str | None = None):
        if cache_dir is None:
            cache_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "workspace", "cache",
            )
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    def get_cache_path(self, apk_path: str) -> str:
        hasher = hashlib.md5()
        with open(apk_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return os.path.join(self.cache_dir, f"{hasher.hexdigest()}.json")

    def get_cached_analysis(self, apk_path: str) -> dict | None:
        cache_path = self.get_cache_path(apk_path)
        if not os.path.exists(cache_path):
            return None
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json_loads(f.read())
        except (OSError, ValueError):
            return None

    def save_analysis(self, apk_path: str, findings: list,
                      summary: dict, colors: list) -> None:
        cache_path = self.get_cache_path(apk_path)
        data = json_dumps({
            "findings": findings,
            "summary": summary,
            "colors": colors,
        })
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(data)
        except OSError:
            pass