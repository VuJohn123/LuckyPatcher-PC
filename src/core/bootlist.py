"""
BootList manager — auto re-apply patches on pipeline restart.

LP Parity: Lucky Patcher có BootList — danh sách app sẽ patch khi boot.
Format file: `workspace/bootlist.json`.

Cấu trúc:
    {
        "version": 1,
        "entries": [
            {
                "package": "com.example.app",
                "apk_path": "/path/to/app.apk",
                "modes": ["iap_dex", "license"],
                "custom_patch": null,
                "apk_hash": "md5...",
                "created_at": 1234567890.0,
                "last_applied": 1234567890.0,
                "apply_count": 3,
                "reason": "user requested boot patch"
            }
        ]
    }

Cách hoạt động:
  - Pipeline entry (main.py) check bootlist → re-apply nếu APK hash match
  - User add qua GUI hoặc CLI: `--add-to-bootlist`
  - Chỉ apply khi: hash match + modes chưa đổi + signature bypass OK
  - Không apply khi: missing APK, hash mismatch, corrupt entry
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field

logger = logging.getLogger(__name__)

_BOOTLIST_VERSION = 1
_MAX_ENTRIES = 200
_LOCK = threading.Lock()


@dataclass
class BootlistEntry:
    package: str
    apk_path: str
    modes: list[str] = field(default_factory=list)
    custom_patch: str | None = None
    apk_hash: str = ""
    created_at: float = field(default_factory=time.time)
    last_applied: float = 0.0
    apply_count: int = 0
    reason: str = "user requested boot patch"

    @property
    def age_days(self) -> float:
        return (time.time() - self.created_at) / 86400.0


class BootListManager:
    """
    Quản lý bootlist file (workspace/bootlist.json).
    Thread-safe với module-level lock.
    """

    def __init__(self, bootlist_path: str | None = None,
                 log_callback=print):
        if bootlist_path is None:
            base = os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            ))
            bootlist_path = os.path.join(
                base, "workspace", "bootlist.json"
            )
        self.bootlist_path = bootlist_path
        os.makedirs(os.path.dirname(bootlist_path), exist_ok=True)
        self.log = log_callback

    # ============================================================
    # LOAD / SAVE
    # ============================================================
    def _load(self) -> dict:
        if not os.path.exists(self.bootlist_path):
            return {"version": _BOOTLIST_VERSION, "entries": []}
        try:
            with open(self.bootlist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {"version": _BOOTLIST_VERSION, "entries": []}
            if "entries" not in data:
                data["entries"] = []
            data.setdefault("version", _BOOTLIST_VERSION)
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Bootlist load failed: %s", e)
            return {"version": _BOOTLIST_VERSION, "entries": []}

    def _save_atomic(self, data: dict) -> None:
        fd, tmp = tempfile.mkstemp(
            dir=os.path.dirname(self.bootlist_path), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.bootlist_path)
        except Exception:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            raise

    # ============================================================
    # PUBLIC API
    # ============================================================
    def add_entry(
        self,
        package: str,
        apk_path: str,
        modes: list[str],
        custom_patch: str | None = None,
        reason: str = "user requested boot patch",
    ) -> bool:
        """Add / update entry. Return True nếu added/updated."""
        if not package or not apk_path:
            self.log("[!] [BootList] package/apk_path không hợp lệ")
            return False

        if not os.path.exists(apk_path):
            self.log("[!] [BootList] APK không tồn tại: " + apk_path)
            return False

        try:
            apk_hash = _compute_file_hash(apk_path)
        except OSError as e:
            self.log("[!] [BootList] Hash fail: " + str(e))
            return False

        with _LOCK:
            data = self._load()
            entries = data.get("entries", [])

            existing = None
            for e in entries:
                if (e.get("package") == package
                        and e.get("apk_path") == apk_path):
                    existing = e
                    break

            now = time.time()
            if existing:
                existing["modes"] = list(modes)
                existing["custom_patch"] = custom_patch
                existing["apk_hash"] = apk_hash
                existing["reason"] = reason
                self.log("[i] [BootList] Updated " + package)
            else:
                new_entry = asdict(BootlistEntry(
                    package=package,
                    apk_path=apk_path,
                    modes=list(modes),
                    custom_patch=custom_patch,
                    apk_hash=apk_hash,
                    created_at=now,
                    reason=reason,
                ))
                entries.append(new_entry)
                self.log(
                    "[✔] [BootList] Added " + package
                    + " (modes=" + str(modes) + ")"
                )

            if len(entries) > _MAX_ENTRIES:
                entries = entries[-_MAX_ENTRIES:]

            data["entries"] = entries
            try:
                self._save_atomic(data)
                return True
            except OSError as e:
                self.log("[!] [BootList] Save failed: " + str(e))
                return False

    def remove_entry(self, package: str) -> bool:
        with _LOCK:
            data = self._load()
            before = len(data.get("entries", []))
            data["entries"] = [
                e for e in data.get("entries", [])
                if e.get("package") != package
            ]
            after = len(data["entries"])
            if before == after:
                self.log("[i] [BootList] Không tìm thấy " + package)
                return False
            try:
                self._save_atomic(data)
                self.log("[✔] [BootList] Removed " + package)
                return True
            except OSError as e:
                self.log("[!] [BootList] Save failed: " + str(e))
                return False

    def get_entries(self) -> list[dict]:
        with _LOCK:
            return list(self._load().get("entries", []))

    def has_package(self, package: str) -> bool:
        for e in self.get_entries():
            if e.get("package") == package:
                return True
        return False

    # ============================================================
    # RE-APPLY PIPELINE
    # ============================================================
    def get_pending_reapply(
        self,
        verify_hash: bool = True,
    ) -> list[dict]:
        """
        Return entries cần re-apply (APK hash vẫn match).
        """
        pending: list[dict] = []
        for entry in self.get_entries():
            apk_path = entry.get("apk_path", "")
            if not apk_path or not os.path.exists(apk_path):
                self.log(
                    "[i] [BootList] Skip "
                    + str(entry.get("package")) + ": APK missing"
                )
                continue

            if verify_hash:
                stored_hash = entry.get("apk_hash", "")
                if stored_hash:
                    try:
                        current = _compute_file_hash(apk_path)
                        if current != stored_hash:
                            self.log(
                                "[i] [BootList] Skip "
                                + str(entry.get("package"))
                                + ": hash mismatch"
                            )
                            continue
                    except OSError:
                        continue

            pending.append(entry)
        return pending

    def mark_applied(self, package: str) -> None:
        """Update last_applied + apply_count sau khi re-apply."""
        with _LOCK:
            data = self._load()
            for e in data.get("entries", []):
                if e.get("package") == package:
                    e["last_applied"] = time.time()
                    e["apply_count"] = int(e.get("apply_count", 0)) + 1
                    break
            try:
                self._save_atomic(data)
            except OSError as e:
                logger.warning("BootList mark_applied fail: %s", e)

    def clear(self) -> None:
        with _LOCK:
            try:
                self._save_atomic({
                    "version": _BOOTLIST_VERSION,
                    "entries": [],
                })
                self.log("[✔] [BootList] Cleared")
            except OSError as e:
                logger.warning("BootList clear fail: %s", e)


# ============================================================
# HELPERS
# ============================================================
def _compute_file_hash(path: str, chunk_size: int = 65536) -> str:
    hasher = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


_default_manager: BootListManager | None = None
_manager_lock = threading.Lock()


def get_bootlist(
    bootlist_path: str | None = None,
    log_callback=print,
) -> BootListManager:
    global _default_manager
    if _default_manager is None or bootlist_path is not None:
        with _manager_lock:
            if bootlist_path is not None or _default_manager is None:
                _default_manager = BootListManager(
                    bootlist_path, log_callback=log_callback,
                )
    return _default_manager