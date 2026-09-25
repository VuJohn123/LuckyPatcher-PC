"""
Base class cho mọi patcher.

v2 (2026) — trace_id prefix:
  - `_trace_prefix()` helper trả `[tid:xxxx] ` khi có trace context.
  - `patch_files()` log dùng prefix để correlation ID xuyên pipeline.
"""
from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Callable

from core.progress import Progress
from core.smali_utils import get_all_smali_files

logger = logging.getLogger(__name__)

_MAX_PATH_LEN = 250


class BasePatcher(ABC):
    def __init__(
        self,
        decompiled_path: str,
        log_callback=print,
        file_cache=None,
    ):
        self.decompiled_path = decompiled_path
        self.log = log_callback
        self.file_cache = file_cache

    # ============================================================
    # TRACE HELPERS
    # ============================================================
    def _trace_prefix(self) -> str:
        """
        Return '[tid:xxxxxxxx] ' nếu đang trong trace_context,
        ngược lại trả ''.
        """
        try:
            from core.trace_context import get_trace_id
            tid = get_trace_id()
            if tid and tid != "-":
                return f"[tid:{tid}] "
        except Exception:
            pass
        return ""

    def _log_traced(self, message: str) -> None:
        """Log kèm trace prefix — wrap self.log."""
        try:
            self.log(self._trace_prefix() + message)
        except Exception:
            pass

    # ============================================================
    # READ/WRITE
    # ============================================================
    def _read(self, path: str) -> str:
        if self.file_cache:
            try:
                return self.file_cache.read(path)
            except Exception:
                pass
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _write(self, path: str, content: str) -> None:
        if self.file_cache:
            try:
                self.file_cache.write(path, content)
                return
            except Exception:
                pass
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    # ============================================================
    # PATCH DRIVER
    # ============================================================
    def patch_files(
        self,
        transform: Callable[[str, str], str | None],
        *,
        prefilter_keywords: tuple[str, ...] = (),
        label: str = "Patcher",
        show_progress: bool = True,
        path_hints: tuple[str, ...] = (),
    ) -> int:
        """
        Iterate smali files, apply transform(content, filepath).

        path_hints: chỉ scan file có path chứa hint. Fallback FULL nếu
                    prefilter không match file nào → tránh miss app
                    obfuscated / structure bất thường.
        """
        try:
            all_files = list(get_all_smali_files(self.decompiled_path))
        except Exception as e:
            self._log_traced(
                f"[!] [{label}] Get smali files failed: {e}"
            )
            return 0

        total_all = len(all_files)

        # ---- Path prefilter ----
        candidates = all_files
        if path_hints:
            filt = [
                f for f in all_files
                if any(
                    h in f.replace("\\", "/").lower() for h in path_hints
                )
            ]
            if filt:
                candidates = filt
                self._log_traced(
                    f"[*] [{label}] Path prefilter: "
                    f"{len(candidates)}/{total_all} files "
                    f"(hints={path_hints[:3]}...)"
                )
            else:
                self._log_traced(
                    f"[i] [{label}] Path prefilter 0 match — "
                    f"FULL scan {total_all} files"
                )

        total = len(candidates)
        if not path_hints:
            self._log_traced(f"[*] [{label}] Scanning {total} files...")

        prog = (
            Progress(total, label=label, log_callback=self.log,
                     step_pct=10)
            if show_progress else None
        )

        patched = 0
        scanned = 0
        start = time.monotonic()

        for filepath in candidates:
            if prog:
                prog.update()
            if len(filepath) > _MAX_PATH_LEN:
                continue
            try:
                content = self._read(filepath)
            except OSError:
                continue

            scanned += 1

            if prefilter_keywords and not any(
                kw in content for kw in prefilter_keywords
            ):
                continue

            try:
                new_content = transform(content, filepath)
            except Exception as e:
                logger.warning(
                    "[%s] transform failed %s: %s", label, filepath, e
                )
                continue

            if new_content is None or new_content == content:
                continue

            try:
                self._write(filepath, new_content)
                patched += 1
            except OSError as e:
                logger.warning(
                    "[%s] write failed %s: %s", label, filepath, e
                )

        if prog:
            prog.close()

        elapsed = time.monotonic() - start
        self._log_traced(
            f"[✔] [{label}] Patched {patched}/{scanned} files "
            f"({elapsed:.1f}s)"
        )
        return patched

    # ============================================================
    # INTERFACE
    # ============================================================
    @abstractmethod
    def patch(self) -> int:
        raise NotImplementedError