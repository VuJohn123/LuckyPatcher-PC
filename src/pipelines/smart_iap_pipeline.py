"""Tự động chạy IAP dex patch khi phát hiện app có BILLING."""
from __future__ import annotations

import logging

from core.event_bus import event_bus

logger = logging.getLogger(__name__)


class SmartIAPPipeline:
    def __init__(self, pipeline_callback=None, log_callback=print):
        self.cb = pipeline_callback
        self.log = log_callback
        event_bus.subscribe("apk.analysis.complete", self._on_analysis)

    def _on_analysis(self, data: dict) -> None:
        if not data:
            return
        findings = data.get("findings", [])
        apk_path = data.get("apk_path")
        if not apk_path:
            return
        has_iap = any(f.get("type") == "iap" for f in findings)
        if not has_iap or not self.cb:
            return
        self.log(f"[*] [SmartIAP] Auto-patching {apk_path}")
        try:
            self.cb(apk_path, "iap_dex")
        except Exception as e:
            logger.warning("SmartIAP failed: %s", e)