"""Hosts blocker — generates ad-blocking hosts file from AdsBlockList."""
from __future__ import annotations
import logging, os
from patcher.base import BasePatcher
logger = logging.getLogger(__name__)

class HostsBlocker(BasePatcher):
    def patch(self) -> int:
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent.parent
        src = root / "assets" / "AdsBlockList.txt"
        out = Path(self.decompiled_path) / "hosts.lp"
        entries: list[str] = []
        try:
            lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
        seen: set[str] = set()
        for line in lines:
            d = line.strip()
            if d and not d.startswith("#") and d not in seen:
                seen.add(d); entries.append(f"0.0.0.0 {d}")
        try:
            out.write_text("# LP-PC hosts block\n" + "\n".join(entries) + "\n", encoding="utf-8")
        except OSError as e:
            self._log_traced(f"[!] hosts write fail: {e}"); return 0
        self._log_traced(f"[✔] Hosts block: {len(entries)} entries")
        return len(entries)
