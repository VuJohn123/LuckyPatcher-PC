"""Theo dõi logcat để phát hiện lỗi runtime + đề xuất patch."""
from __future__ import annotations

import logging
import re
import subprocess
import threading

logger = logging.getLogger(__name__)

_PATTERNS = {
    "gms_error": (
        re.compile(r"Google Play services.*not available|"
                   r"isGooglePlayServicesAvailable.*error", re.I),
        "Phát hiện lỗi GMS — thử mode 'gms_spoof'.",
    ),
    "license_error": (
        re.compile(r"License check.*fail|dontAllow|NOT_LICENSED", re.I),
        "Phát hiện lỗi License — thử mode 'license:extreme'.",
    ),
    "billing_error": (
        re.compile(r"Billing.*error|purchase.*fail|RESPONSE_CODE.*[^0]", re.I),
        "Phát hiện lỗi Billing — thử mode 'iap:dex'.",
    ),
    "signature_error": (
        re.compile(r"Signature.*mismatch|verify.*fail", re.I),
        "Phát hiện lỗi Signature — thử mode 'sig_disable'.",
    ),
}


class RuntimeDebugger:
    def __init__(self, package: str, log_callback=print,
                 suggestion_callback=None):
        self.package = package
        self.log = log_callback
        self.suggest = suggestion_callback
        self._stop = threading.Event()
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        try:
            self._proc = subprocess.Popen(
                ["adb", "logcat", "-s", f"{self.package}:*", "*:E"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except OSError as e:
            self.log(f"[!] logcat start failed: {e}")
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        self.log(f"[*] [Debugger] Watching logcat: {self.package}")

    def _read_loop(self) -> None:
        if not self._proc or not self._proc.stdout:
            return
        for line in self._proc.stdout:
            if self._stop.is_set():
                break
            self._analyze(line)

    def _analyze(self, line: str) -> None:
        for _, (pattern, suggestion) in _PATTERNS.items():
            if pattern.search(line):
                self.log(f"[!] {suggestion}")
                if self.suggest:
                    try:
                        self.suggest(suggestion)
                    except Exception:
                        pass
                return

    def stop(self) -> None:
        self._stop.set()
        if self._proc:
            try:
                self._proc.terminate()
            except OSError:
                pass