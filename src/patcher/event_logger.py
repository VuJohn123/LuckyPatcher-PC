"""
Inject event logger vào APK để ghi lại các lời gọi billing.
Log ghi vào /sdcard/lp_pc_events.log trên thiết bị.

v2:
  - Dùng `_METHOD_MODS` để match mọi modifier combination.
  - Prefilter bằng BILLING_METHODS (chỉ scan file có billing hint).
  - Idempotent: không inject 2 lần.
  - FileCache-aware.
  - Giữ alias `inject_logging()` cho backward compat với tests + lazy_loader.
  - EventLogger.smali viết lại đúng cú pháp (không còn try/catch lỗi).
"""
from __future__ import annotations

import logging
import os
import re

from core.smali_utils import _METHOD_MODS
from patcher.base import BasePatcher

logger = logging.getLogger(__name__)

# ---- Smali class content (đúng cú pháp) ----
LOGGER_SMALI = """.class public Lcom/lppc/logger/EventLogger;
.super Ljava/lang/Object;
.source "EventLogger.java"


# static fields
.field private static final LOG_PATH:Ljava/lang/String; = "/sdcard/lp_pc_events.log"


# direct methods
.method public constructor <init>()V
    .registers 0
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    return-void
.end method


# public static methods
.method public static log(Ljava/lang/String;Ljava/lang/String;)V
    .registers 8

    :try_start_0
    new-instance v0, Ljava/io/FileWriter;
    const-string v1, "/sdcard/lp_pc_events.log"
    const/4 v2, 0x1
    invoke-direct {v0, v1, v2}, Ljava/io/FileWriter;-><init>(Ljava/lang/String;Z)V

    new-instance v1, Ljava/io/BufferedWriter;
    invoke-direct {v1, v0}, Ljava/io/BufferedWriter;-><init>(Ljava/io/Writer;)V

    new-instance v2, Ljava/lang/StringBuilder;
    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V

    invoke-static {}, Ljava/lang/System;->currentTimeMillis()J
    move-result-wide v3
    invoke-virtual {v2, v3, v4}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    const-string v3, " | "
    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2, p0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string v3, " | "
    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2, p1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string v3, "\\n"
    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;
    move-result-object v2

    invoke-virtual {v1, v2}, Ljava/io/BufferedWriter;->write(Ljava/lang/String;)V

    invoke-virtual {v1}, Ljava/io/BufferedWriter;->close()V
    invoke-virtual {v0}, Ljava/io/FileWriter;->close()V
    :try_end_0
    .catch Ljava/io/IOException; {:try_start_0 .. :try_end_0} :catch_0
    .catch Ljava/lang/Exception; {:try_start_0 .. :try_end_0} :catch_0

    goto :goto_0

    :catch_0
    move-exception v0
    :goto_0
    return-void
.end method
"""

# Billing method names — prefilter + inject target
BILLING_METHODS = (
    "launchBillingFlow",
    "queryPurchases",
    "getBuyIntent",
    "startConnection",
    "initiatePurchase",
)

# Method signature — match mọi modifier combo, capture method name
_REGISTERS_LINE = re.compile(
    r"(\.method\s+" + _METHOD_MODS + r"(" +
    "|".join(re.escape(m) for m in BILLING_METHODS) +
    r")\(.*?\)\s*(?:V|L[^\s;]*;)\s+"
    r"\.(?:registers|locals)\s+\d+\s*)",
    re.DOTALL,
)

_LOGGER_CLASS_PATH = "smali/com/lppc/logger/EventLogger.smali"
_LOGGER_CLASS_FQN = "Lcom/lppc/logger/EventLogger;"


class EventLogger(BasePatcher):
    # ============================================================
    # CLASS INJECTION
    # ============================================================
    def _inject_class(self) -> bool:
        """Return True nếu class được thêm (chưa tồn tại)."""
        path = os.path.join(self.decompiled_path, _LOGGER_CLASS_PATH)
        if os.path.exists(path):
            return False

        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._write(path, LOGGER_SMALI)
            return True
        except OSError as e:
            logger.warning("Inject EventLogger class failed: %s", e)
            return False

    # ============================================================
    # INJECT LOGGING CALLS
    # ============================================================
    def _transform(self, content: str, filepath: str) -> str | None:
        """Inject log call vào đầu billing method."""
        if not any(m in content for m in BILLING_METHODS):
            return None
        if "com/lppc/logger/EventLogger" in content:
            return None  # đã inject

        original = content
        for match in _REGISTERS_LINE.finditer(content):
            full = match.group(1)
            method_name = match.group(2)

            log_call = (
                '\n    const-string v0, "Billing"\n'
                f'    const-string v1, "{method_name} called"\n'
                f'    invoke-static {{v0, v1}}, '
                f'{_LOGGER_CLASS_FQN}->log('
                'Ljava/lang/String;Ljava/lang/String;)V'
            )
            content = content.replace(full, full + log_call, 1)

        return content if content != original else None

    # ============================================================
    # PUBLIC API
    # ============================================================
    def inject_logging(self) -> int:
        """
        Backward-compat alias cho `patch()`.
        Test + lazy_loader gọi tên này.
        """
        return self.patch()

    def patch(self) -> int:
        self.log("[*] [EventLogger] Injecting event logging...")
        count = 0

        if self._inject_class():
            count += 1
            self.log("[+] [EventLogger] Added EventLogger class")

        injected = self.patch_files(
            self._transform,
            prefilter_keywords=BILLING_METHODS,
            label="EventLogger",
        )
        count += injected

        self.log(f"[✔] [EventLogger] Total changes: {count}")
        return count