"""
Progress reporter — tqdm nếu có, else log_callback.

Usage:
    p = Progress(total=54481, label="Zip", log_callback=print)
    p.update(100)          # tăng 100
    p.set(n)               # set vị trí
    p.close()
"""
from __future__ import annotations

import time
from typing import Callable

try:
    from tqdm import tqdm as _tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


class Progress:
    """
    Emit log mỗi khi vượt ngưỡng % (mặc định 5%).
    Nếu tqdm có và `use_tqdm=True` → dùng tqdm bar.
    """

    def __init__(
        self,
        total: int,
        label: str = "",
        log_callback: Callable[[str], None] | None = None,
        use_tqdm: bool = False,
        step_pct: int = 5,
    ):
        self.total = max(1, total)
        self.label = label
        self.log = log_callback
        self.step_pct = step_pct
        self._count = 0
        self._last_pct = -1
        self._start = time.monotonic()
        self._tqdm = None

        if use_tqdm and HAS_TQDM:
            self._tqdm = _tqdm(
                total=self.total,
                desc=label,
                unit="f",
                ncols=80,
                leave=True,
                dynamic_ncols=True,
            )

    def update(self, n: int = 1) -> None:
        self._count += n
        if self._tqdm:
            self._tqdm.update(n)
            return
        if not self.log:
            return
        pct = int(self._count * 100 / self.total)
        if pct >= self._last_pct + self.step_pct:
            elapsed = time.monotonic() - self._start
            self.log(
                f"[i] [{self.label}] {pct}% "
                f"({self._count}/{self.total}, {elapsed:.0f}s)"
            )
            self._last_pct = pct

    def set(self, n: int) -> None:
        delta = n - self._count
        if delta > 0:
            self.update(delta)

    def close(self) -> None:
        if self._tqdm:
            self._tqdm.close()
            return
        if self.log:
            elapsed = time.monotonic() - self._start
            self.log(
                f"[✔] [{self.label}] Done {self._count} in "
                f"{elapsed:.1f}s"
            )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()