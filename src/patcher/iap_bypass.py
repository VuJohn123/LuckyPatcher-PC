"""
IAP Bypass orchestrator — chọn dex hoặc proxy mode.
"""
from __future__ import annotations

import logging
import socket
import threading
import time

logger = logging.getLogger(__name__)


class IAPBypass:
    def __init__(self, decompiled_path: str, mode: str = "proxy",
                 proxy_port: int = 8888, log_callback=print, file_cache=None):
        self.decompiled_path = decompiled_path
        self.mode = mode
        self.proxy_port = proxy_port
        self.log = log_callback
        self.file_cache = file_cache
        self.proxy_server = None
        self.proxy_thread = None

    def _wait_for_proxy(self, timeout: float = 10.0) -> bool:
        """Poll cho đến khi proxy server ready."""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            try:
                with socket.create_connection(("localhost", self.proxy_port), timeout=1):
                    return True
            except (ConnectionRefusedError, OSError):
                time.sleep(0.3)
        return False

    def _run_dex_mode(self) -> int:
        from patcher.iap_dex_patcher import IAPDexPatcher
        patcher = IAPDexPatcher(
            self.decompiled_path,
            log_callback=self.log,
            file_cache=self.file_cache,
        )
        return patcher.patch()

    def _run_proxy_mode(self) -> int:
        from patcher.iap_proxy_server import IAPProxyServer
        from patcher.iap_smali_patcher import IAPSmaliPatcher
        from patcher.signature_patcher import SignatureVerifyPatcher
        from core.device_bridge import setup_reverse_port

        # 1. Disable signature checks
        sig = SignatureVerifyPatcher(
            self.decompiled_path,
            log_callback=self.log,
            file_cache=self.file_cache,
        )
        sig_count = sig.patch()

        # 2. Start proxy server
        self.proxy_server = IAPProxyServer(port=self.proxy_port)
        self.proxy_thread = threading.Thread(
            target=self.proxy_server.start, daemon=True
        )
        self.proxy_thread.start()

        if not self._wait_for_proxy(timeout=10.0):
            self.log("[!] Proxy server không khởi động kịp")
            return sig_count

        # 3. Setup ADB reverse
        if not setup_reverse_port(self.proxy_port, self.proxy_port):
            self.log("[!] ADB reverse thất bại — proxy có thể không hoạt động")
        else:
            self.log(f"[*] ADB reverse: device:{self.proxy_port} → PC:{self.proxy_port}")

        # 4. Patch smali
        smali = IAPSmaliPatcher(self.decompiled_path, log_callback=self.log)
        smali_count = smali.patch_billing_calls(
            proxy_host="localhost", proxy_port=self.proxy_port
        )

        return sig_count + smali_count

    def execute(self) -> bool:
        try:
            if self.mode == "dex":
                count = self._run_dex_mode()
            else:
                count = self._run_proxy_mode()
            return count > 0
        except Exception as e:
            self.log(f"[!] [IAPBypass] Error: {e}")
            logger.exception("IAPBypass failed")
            return False

    def execute_with_report(self) -> dict:
        report = {"patterns": {}, "total_patched": 0}
        try:
            if self.mode == "dex":
                from patcher.iap_dex_patcher import IAPDexPatcher
                patcher = IAPDexPatcher(
                    self.decompiled_path,
                    log_callback=self.log,
                    file_cache=self.file_cache,
                )
                report = patcher.patch_with_report()
            else:
                count = self._run_proxy_mode()
                report["patterns"]["proxy_mode"] = count > 0
                report["total_patched"] = count
        except Exception as e:
            self.log(f"[!] [IAPBypass] {e}")
            logger.exception("IAPBypass report failed")
        return report

    def patch(self) -> int:
        """Interface tương thích lazy_loader."""
        return 1 if self.execute() else 0