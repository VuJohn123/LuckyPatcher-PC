"""
Tiện ích xử lý Smali — regex + file cache + APK cache.
Tối ưu: re2 > re, orjson > json, memory-mapped files.

FileContentCache dùng LRU cho reads (maxsize) + buffer cho writes.
Tránh OOM khi patch match 30,000+ file smali.
"""
from __future__ import annotations

import hashlib
import mmap
import os
import time
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor, as_completed

# Regex engine — stdlib re (ổn định, đủ API)
import re  # type: ignore
RE_ENGINE = "re"

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
_METHOD_MODS = (
    r"(?:(?:public|private|protected|static|final|synthetic|abstract|"
    r"declared-synchronized)\s+)+"
)

REGEX_BOOLEAN_METHOD = re.compile(
    r"\.method\s+" + _METHOD_MODS + r"(\S+)\s*\(.*?\)\s*Z\s*.*?\.end\s+method",
    re.DOTALL,
)

REGEX_IAP_BILLING_METHOD = re.compile(
    r"\.method\s+" + _METHOD_MODS
    + r"(\S+)\s*\([^)]*\)\s*(V|Landroid/os/Bundle;)\s*.*?\.end\s+method",
    re.DOTALL,
)

REGEX_SIGNATURE_METHOD = re.compile(
    r"\.method\s+" + _METHOD_MODS
    + r"(\w+)\s*\(.*?\)\s*Z\s*\.registers\s+\d+\s*.*?\.end\s+method",
    re.DOTALL,
)

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
# FILE CONTENT CACHE — LRU read + buffered write
# ============================================================
class FileContentCache:
    """
    Cache nội dung file smali trong RAM.

    READ: LRU OrderedDict, maxsize = 2000 file (~10-20 MB).
          Miss → load from disk (mmap nếu > 1MB) → evict LRU.
    WRITE: Dict unbounded nhưng flush theo threshold để tránh OOM.
          Auto-flush khi buffer vượt `write_flush_threshold` file.
    """

    DEFAULT_READ_CACHE_SIZE = 2000
    DEFAULT_WRITE_FLUSH_THRESHOLD = 5000

    def __init__(
        self,
        decompiled_path: str,
        max_read_cache: int | None = None,
        write_flush_threshold: int | None = None,
        log_callback=None,
    ):
        self.decompiled_path = decompiled_path
        self.max_read_cache = (
            max_read_cache or self.DEFAULT_READ_CACHE_SIZE
        )
        self.write_flush_threshold = (
            write_flush_threshold or self.DEFAULT_WRITE_FLUSH_THRESHOLD
        )
        self._read_cache: OrderedDict[str, str] = OrderedDict()
        self._modified: dict[str, str] = {}
        self._log = log_callback or (lambda _: None)
        self._read_hits = 0
        self._read_misses = 0
        self._write_count = 0

    # ---------------- READ ----------------
    def read(self, filepath: str) -> str:
        # Modified buffer wins
        if filepath in self._modified:
            return self._modified[filepath]

        # LRU cache hit
        if filepath in self._read_cache:
            self._read_cache.move_to_end(filepath)
            self._read_hits += 1
            return self._read_cache[filepath]

        # Cache miss → load from disk
        self._read_misses += 1
        content = self._load_from_disk(filepath)
        self._read_cache[filepath] = content

        # Evict oldest if over capacity
        while len(self._read_cache) > self.max_read_cache:
            self._read_cache.popitem(last=False)

        return content

    def _load_from_disk(self, filepath: str) -> str:
        try:
            size = os.path.getsize(filepath)
            if size > 1024 * 1024:
                with open(filepath, "r+b") as f:
                    with mmap.mmap(f.fileno(), 0) as mm:
                        return mm.read().decode("utf-8", errors="ignore")
            else:
                with open(filepath, "r", encoding="utf-8",
                          errors="ignore") as f:
                    return f.read()
        except (OSError, IOError, ValueError):
            return ""

    # ---------------- WRITE ----------------
    def write(self, filepath: str, content: str) -> None:
        self._modified[filepath] = content
        self._write_count += 1

        # Auto-flush if buffer grows too large (tránh OOM)
        if len(self._modified) >= self.write_flush_threshold:
            self._log(
                f"[i] [FileCache] Buffer {len(self._modified)} file "
                f"→ auto-flush"
            )
            self.flush(self._log)

    def flush(self, log_callback=print) -> None:
        """Ghi tất cả file modified xuống disk."""
        count = 0
        for filepath, content in self._modified.items():
            try:
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, "w", encoding="utf-8",
                          buffering=128 * 1024) as f:
                    f.write(content)
                count += 1
            except (OSError, IOError, ValueError, TypeError) as e:
                log_callback(f"[!] [FileCache] {filepath}: {e}")
        log_callback(f"[*] [FileCache] Đã ghi {count} file")
        self._modified.clear()
        # Read cache clear để tránh stale data
        self._read_cache.clear()

    # ---------------- INTROSPECTION ----------------
    def get_modified_files(self) -> list[str]:
        return list(self._modified.keys())

    def is_modified(self, filepath: str) -> bool:
        return filepath in self._modified

    def get_stats(self) -> dict:
        return {
            "read_hits": self._read_hits,
            "read_misses": self._read_misses,
            "read_cache_size": len(self._read_cache),
            "modified_buffer_size": len(self._modified),
            "write_count": self._write_count,
        }


# ============================================================
# PARALLEL PROCESSOR (unchanged)
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
                    total += result if isinstance(result, int) else (
                        1 if result else 0
                    )
                except Exception as e:
                    print(f"[!] [Parallel] {futures[future]}: {e}")
        return total


# ============================================================
# APK CACHE (with TTL enforcement — G1 helper)
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
            "cached_at": time.time(),
        })
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(data)
        except OSError:
            pass

    def is_expired(self, apk_path: str, ttl_days: int = 30) -> bool:
        """Check nếu cache entry quá cũ → force re-analyze."""
        cache_path = self.get_cache_path(apk_path)
        if not os.path.exists(cache_path):
            return True
        age_days = (time.time() - os.path.getmtime(cache_path)) / 86400
        return age_days > ttl_days