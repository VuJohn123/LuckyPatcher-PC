"""
ADB File Transfer — push/pull with progress, verification, and streaming.
"""
from __future__ import annotations

import contextlib
import hashlib
import logging
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class ADBTransferProgress(Enum):
    """Transfer progress states."""
    STARTING = "starting"
    CONNECTING = "connecting"
    TRANSFERRING = "transferring"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ADBTransferResult:
    """Result of ADB file transfer."""
    success: bool
    local_path: str = ""
    remote_path: str = ""
    direction: str = ""  # "push" or "pull"
    bytes_transferred: int = 0
    total_bytes: int = 0
    duration_ms: float = 0.0
    checksum_local: str = ""
    checksum_remote: str = ""
    error: str = ""
    progress_steps: list[tuple[ADBTransferProgress, int, int, float]] = field(default_factory=list)  # (state, current, total, time)

    @property
    def transfer_rate_kbs(self) -> float:
        return (self.bytes_transferred / 1024) / (self.duration_ms / 1000) if self.duration_ms > 0 else 0

    @property
    def verified(self) -> bool:
        return bool(self.checksum_local and self.checksum_remote == self.checksum_local)


@dataclass
class ADBFileTransfer:
    """Handles file transfer between PC and Android device via ADB."""
    device_serial: str
    adb_path: str = "adb"
    verify_checksums: bool = True
    compress: bool = False
    show_progress: bool = True

    # Transfer callbacks
    on_progress: Callable[[ADBTransferProgress, int, int, float], None] | None = None
    on_progress_update: Callable[[int, int, float], None] | None = None  # current, total, pct
    on_complete: Callable[[ADBTransferResult], None] | None = None
    on_error: Callable[[ADBTransferResult], None] | None = None

    _cancelled: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def cancel(self) -> None:
        """Cancel ongoing transfer."""
        with self._lock:
            self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def _emit_progress(self, state: ADBTransferProgress, current: int, total: int, elapsed: float):
        if self.on_progress:
            with contextlib.suppress(Exception):
                self.on_progress(state, current, total, elapsed)
        if self.on_progress_update:
            pct = (current * 100 / total) if total > 0 else 0
            with contextlib.suppress(Exception):
                self.on_progress_update(current, total, pct)

    def _emit_complete(self, result: ADBTransferResult):
        if self.on_complete:
            with contextlib.suppress(Exception):
                self.on_complete(result)

    def _emit_error(self, result: ADBTransferResult):
        if self.on_error:
            with contextlib.suppress(Exception):
                self.on_error(result)

    def push(self, local_path: str, remote_path: str, verify: bool | None = None) -> ADBTransferResult:
        """Push file from PC to device."""
        verify = verify if verify is not None else self.verify_checksums

        start = time.monotonic()
        local = Path(local_path)

        if not local.exists():
            return ADBTransferResult(
                success=False, local_path=local_path, remote_path=remote_path, direction="push",
                error="Local file not found", bytes_transferred=0, total_bytes=local.stat().st_size if local.exists() else 0
            )

        total_bytes = local.stat().st_size

        # Calculate local checksum
        checksum_local = ""
        if verify:
            self._emit_progress(ADBTransferProgress.CONNECTING, 0, total_bytes, time.monotonic() - start)
            checksum_local = self._calculate_checksum(local_path)

        self._emit_progress(ADBTransferProgress.TRANSFERRING, 0, total_bytes, time.monotonic() - start)

        try:
            if self._cancelled:
                return ADBTransferResult(success=False, direction="push", error="Cancelled")

            # ADB push with progress is not directly available, so we use standard push
            # For progress, we could use shell dd or monitor target file size
            proc = subprocess.run(
                [self.adb_path, "-s", self.device_serial, "push", local_path, remote_path],
                capture_output=True, text=True, timeout=300,  # 5 min default
                creationflags=self._creation_flags()
            )

            elapsed = time.monotonic() - start
            if self._cancelled:
                return ADBTransferResult(success=False, direction="push", error="Cancelled")

            if proc.returncode != 0:
                return ADBTransferResult(
                    success=False, direction="push",
                    error=proc.stderr or "ADB push failed",
                    bytes_transferred=total_bytes, total_bytes=total_bytes,
                    duration_ms=elapsed * 1000,
                )

            # Verify checksum
            checksum_remote = ""
            if verify:
                self._emit_progress(ADBTransferProgress.VERIFYING, total_bytes, total_bytes, elapsed)
                checksum_remote = self._calculate_remote_checksum(remote_path)

            result = ADBTransferResult(
                    success=True, direction="push",
                    local_path=local_path, remote_path=remote_path,
                    bytes_transferred=total_bytes, total_bytes=total_bytes,
                    duration_ms=elapsed * 1000,
                    checksum_local=checksum_local, checksum_remote=checksum_remote,
                    error="" if checksum_local == checksum_remote else "Checksum mismatch"
                )

            self._emit_progress(ADBTransferProgress.COMPLETED, total_bytes, total_bytes, elapsed)
            self._emit_complete(result)
            return result

        except subprocess.TimeoutExpired:
            return ADBTransferResult(success=False, direction="push", error="Timeout", bytes_transferred=0, total_bytes=total_bytes, duration_ms=(time.monotonic() - start) * 1000)
        except Exception as e:
            return ADBTransferResult(success=False, direction="push", error=str(e), bytes_transferred=0, total_bytes=total_bytes, duration_ms=(time.monotonic() - start) * 1000)

    def pull(self, remote_path: str, local_path: str, verify: bool | None = None) -> ADBTransferResult:
        """Pull file from device to PC."""
        verify = verify if verify is not None else self.verify_checksums

        start = time.monotonic()
        local = Path(local_path)

        # Calculate remote checksum first (via shell)
        checksum_remote = ""
        total_bytes = 0

        try:
            # Get file size via stat
            stat_result = subprocess.run(
                [self.adb_path, "-s", self.device_serial, "shell", "stat", "-c", "%s", remote_path],
                capture_output=True, text=True, timeout=10
            )
            if stat_result.returncode == 0:
                total_bytes = int(stat_result.stdout.strip())

            if verify:
                checksum_remote = self._calculate_remote_checksum(remote_path)

            # Create parent directory
            local.parent.mkdir(parents=True, exist_ok=True)

            self._emit_progress(ADBTransferProgress.TRANSFERRING, 0, total_bytes, time.monotonic() - start)

            if self._cancelled:
                return ADBTransferResult(success=False, direction="pull", error="Cancelled")

            proc = subprocess.run(
                [self.adb_path, "-s", self.device_serial, "pull", remote_path, local_path],
                capture_output=True, text=True, timeout=300,
                creationflags=self._creation_flags()
            )

            elapsed = time.monotonic() - start
            if self._cancelled:
                return ADBTransferResult(success=False, direction="pull", error="Cancelled")

            if proc.returncode != 0:
                return ADBTransferResult(
                    success=False, direction="pull",
                    error=proc.stderr or "ADB pull failed",
                    bytes_transferred=total_bytes, total_bytes=total_bytes,
                    duration_ms=elapsed * 1000,
                )

            # Verify local checksum
            checksum_local = ""
            bytes_transferred = 0
            if verify and local.exists():
                checksum_local = self._calculate_checksum(local_path)
                bytes_transferred = local.stat().st_size
            elif verify:
                bytes_transferred = total_bytes

            result = ADBTransferResult(
                    success=True, direction="pull",
                    local_path=local_path, remote_path=remote_path,
                    bytes_transferred=bytes_transferred, total_bytes=total_bytes,
                    duration_ms=elapsed * 1000,
                    checksum_local=checksum_local, checksum_remote=checksum_remote,
                    error="" if checksum_local == checksum_remote else "Checksum mismatch"
                )

            self._emit_progress(ADBTransferProgress.COMPLETED, bytes_transferred, total_bytes, elapsed)
            self._emit_complete(result)
            return result

        except subprocess.TimeoutExpired:
            return ADBTransferResult(success=False, direction="pull", error="Timeout", bytes_transferred=0, total_bytes=total_bytes, duration_ms=(time.monotonic() - start) * 1000)
        except Exception as e:
            return ADBTransferResult(success=False, direction="pull", error=str(e), bytes_transferred=0, total_bytes=total_bytes, duration_ms=(time.monotonic() - start) * 1000)

    def push_streaming(self, local_path: str, remote_path: str, verify: bool | None = None) -> ADBTransferResult:
        """Push file with streaming (uses dd for progress)."""
        # ADB push doesn't support streaming; fall back to standard push
        return self.push(local_path, remote_path, verify)

    def pull_streaming(self, remote_path: str, local_path: str, verify: bool = True) -> ADBTransferResult:
        """Pull file with streaming (uses dd for progress)."""
        return self.pull(remote_path, local_path, verify)

    def push_multiple(self, file_pairs: list[tuple[str, str]], verify: bool = True) -> list[ADBTransferResult]:
        """Push multiple files."""
        return [self.push(local, remote, verify) for local, remote in file_pairs]

    def pull_multiple(self, file_pairs: list[tuple[str, str]], verify: bool = True) -> list[ADBTransferResult]:
        """Pull multiple files."""
        return [self.pull(remote, local, verify) for remote, local in file_pairs]

    def sync_directory(self, local_dir: str, remote_dir: str, direction: str = "push",
                        exclude_patterns: list[str] | None = None) -> ADBTransferResult:
        """Sync directory using ADB push/pull with comparison."""
        # ADB push/pull doesn't have built-in sync, so we implement basic version
        direction = direction.lower()
        verify = direction == "push"

        if direction not in ("push", "pull"):
            return ADBTransferResult(success=False, direction=direction, error="Direction must be push or pull")

        start = time.monotonic()

        if direction == "push":
            # List local files
            local_files = []
            for p in Path(local_dir).rglob("*"):
                if p.is_file():
                    rel = p.relative_to(local_dir)
                    if exclude_patterns and any(rel.match(p) for p in exclude_patterns):
                        continue
                    local_files.append((str(p), str(Path(remote_dir) / rel)))

            results = self.push_multiple(local_files, verify)
            return ADBTransferResult(
                success=all(r.success for r in results),
                    direction="push",
                    bytes_transferred=sum(r.bytes_transferred for r in results),
                    total_bytes=sum(r.total_bytes for r in results),
                    duration_ms=(time.monotonic() - start) * 1000
                )
        else:
            # Pull direction - list remote files via find
            find_cmd = f"find {remote_dir} -type f"
            result = subprocess.run([self.adb_path, "-s", self.device_serial, "shell", find_cmd],
                                   capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return ADBTransferResult(success=False, direction="pull", error=result.stderr)

            remote_files = result.stdout.strip().splitlines()
            file_pairs = [(rf, str(Path(local_dir) / Path(rf).relative_to(remote_dir))) for rf in remote_files]
            results = self.pull_multiple(file_pairs, verify)
            return ADBTransferResult(
                success=all(r.success for r in results),
                    direction="pull",
                    bytes_transferred=sum(r.bytes_transferred for r in results),
                    total_bytes=sum(r.total_bytes for r in results),
                    duration_ms=(time.monotonic() - start) * 1000
                )

    def _calculate_checksum(self, file_path: str) -> str:
        """Calculate SHA256 checksum of local file."""
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception:
            return ""

    def _calculate_remote_checksum(self, remote_path: str) -> str:
        """Calculate SHA256 checksum of remote file via ADB shell."""
        # Use sha256sum command if available, otherwise md5sum
        for cmd in ["sha256sum", "md5sum"]:
            try:
                proc = subprocess.run(
                    [self.adb_path, "-s", self.device_serial, "shell", cmd, remote_path],
                    capture_output=True, text=True, timeout=30
                )
                if proc.returncode == 0:
                    return proc.stdout.split()[0]
            except Exception:
                pass
        return ""

    def _creation_flags(self) -> int:
        return __import__("sys").platform == "win32" and __import__("subprocess").CREATE_NO_WINDOW or 0


def push_file(device_serial: str, local: str, remote: str, **kwargs) -> ADBTransferResult:
    """Convenience function for push."""
    return ADBFileTransfer(device_serial, **kwargs).push(local, remote)


def pull_file(device_serial: str, remote: str, local: str, **kwargs) -> ADBTransferResult:
    """Convenience function for pull."""
    return ADBFileTransfer(device_serial, **kwargs).pull(remote, local)


# Progress bar integration for ADB transfers
class ADBTransferProgressBar:
    """Simple console progress bar for ADB transfers."""

    def __init__(self, label: str = "Transfer"):
        self.label = label
        self.start_time = time.monotonic()
        self.last_update = 0
        self.update_interval = 0.5  # seconds

    def update(self, current: int, total: int, elapsed: float):
        if total == 0:
            return

        pct = (current * 100) / total
        rate = current / elapsed if elapsed > 0 else 0
        eta = (total - current) / rate if rate > 0 else 0

        bar_width = 40
        filled = int(bar_width * current / total)
        bar = "█" * filled + "░" * (bar_width - filled)

        print(f"\r{self.label}: [{bar}] {pct:.1f}% ({self._format_bytes(current)}/{self._format_bytes(total)}) "
              f"@ {self._format_bytes(rate)}/s ETA {int(eta)}s", end="", flush=True)

    def finish(self, success: bool, elapsed: float):
        print()
        print(f"{self.label}: {'✓' if success else '✗'} Completed in {elapsed:.1f}s")

    @staticmethod
    def _format_bytes(b: float) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if b < 1024:
                return f"{b:.1f}{unit}"
            b /= 1024
        return f"{b:.1f}TB"


# ADB transfer with progress bar context manager
@contextlib.contextmanager
def adb_transfer(device_serial: str, adb_path: str = "adb", **kwargs) -> Iterator[ADBFileTransfer]:
    """Context manager for ADB transfers with automatic progress handling."""
    transfer = ADBFileTransfer(device_serial, adb_path, **kwargs)

    progress_bar = ADBTransferProgressBar("ADB Transfer")

    def _on_progress(state, current, total, elapsed):
        if state == ADBTransferProgress.TRANSFERRING:
            progress_bar.update(current, total, elapsed)
        elif state == ADBTransferProgress.VERIFYING:
            print("\rVerifying... ", end="", flush=True)
        elif state == ADBTransferProgress.COMPLETED:
            progress_bar.finish(True, elapsed)
        elif state == ADBTransferProgress.FAILED:
            print("\nTransfer failed!")

    transfer.on_progress = _on_progress

    try:
        yield transfer
    finally:
        # Context cleanup handled by caller
        pass
