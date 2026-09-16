"""
Inject event logger vào APK để ghi lại các lời gọi billing.
Log ghi vào /sdcard/lp_pc_events.log trên thiết bị.
"""
from __future__ import annotations

import logging
import os
import re

from core.smali_utils import get_all_smali_files

logger = logging.getLogger(__name__)

LOGGER_SMALI = """.class public Lcom/lppc/logger/EventLogger;
.super Ljava/lang/Object;
.source "EventLogger.java"

.method public static log(Ljava/lang/String;Ljava/lang/String;)V
    .registers 6
    :try_start
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
    const-string p0, " | "
    invoke-virtual {v2, p0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v2, p1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    const-string p0, "\\n"
    invoke-virtual {v2, p0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;
    move-result-object p0
    invoke-virtual {v1, p0}, Ljava/io/BufferedWriter;->write(Ljava/lang/String;)V
    invoke-virtual {v1}, Ljava/io/BufferedWriter;->close()V
    invoke-virtual {v0}, Ljava/io/FileWriter;->close()V
    :try_end
    .catch Ljava/io/IOException; {:try_start .. :try_end} :end_try
    :end_try
    return-void
.end method
"""

BILLING_METHODS = ("launchBillingFlow", "queryPurchases", "getBuyIntent", "startConnection")


class EventLogger:
    def __init__(self, decompiled_path: str, log_callback=print, file_cache=None):
        self.decompiled_path = decompiled_path
        self.log = log_callback
        self.file_cache = file_cache

    def _read(self, path: str) -> str:
        if self.file_cache:
            return self.file_cache.read(path)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _write(self, path: str, content: str) -> None:
        if self.file_cache:
            self.file_cache.write(path, content)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

    def _inject_class(self) -> bool:
        logger_dir = os.path.join(
            self.decompiled_path, "smali", "com", "lppc", "logger",
        )
        os.makedirs(logger_dir, exist_ok=True)
        path = os.path.join(logger_dir, "EventLogger.smali")
        if os.path.exists(path):
            return False
        if self.file_cache:
            self.file_cache.write(path, LOGGER_SMALI)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(LOGGER_SMALI)
        return True

    def inject_logging(self) -> int:
        self.log("[*] [EventLogger] Injecting event logging...")
        count = 0

        if self._inject_class():
            count += 1
            self.log("[+] Added EventLogger class")

        for filepath in get_all_smali_files(self.decompiled_path):
            if len(filepath) > 250:
                continue
            content = self._read(filepath)
            original = content
            modified = False

            for method in BILLING_METHODS:
                if method not in content:
                    continue
                pattern = re.compile(
                    r'(\.method\s+(?:public|private|static)\s+(?:final\s+)?'
                    + re.escape(method) + r'\(.*?\)\s*(?:V|L.*?;)\s*)',
                    re.DOTALL,
                )
                match = pattern.search(content)
                if not match:
                    continue
                insert_pos = match.end()
                log_call = (
                    '\n    const-string v0, "Billing"\n'
                    f'    const-string v1, "{method} called"\n'
                    '    invoke-static {v0, v1}, '
                    'Lcom/lppc/logger/EventLogger;->log(Ljava/lang/String;Ljava/lang/String;)V\n'
                )
                content = content[:insert_pos] + log_call + content[insert_pos:]
                modified = True

            if modified and content != original:
                self._write(filepath, content)
                count += 1

        self.log(f"[*] [EventLogger] Injected into {count} files")
        return count

    def patch(self) -> int:
        return self.inject_logging()