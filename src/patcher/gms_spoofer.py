"""
Giả mạo Google Play Services — thêm stub + patch check.
"""
from __future__ import annotations

import logging
import os
import re

from core.smali_utils import get_all_smali_files

logger = logging.getLogger(__name__)

GMS_STUB = """.class public Lcom/google/android/gms/common/GoogleApiAvailability;
.super Ljava/lang/Object;
.source "GMSSpoofer.java"

.method public static getInstance()Lcom/google/android/gms/common/GoogleApiAvailability;
    .registers 1
    new-instance v0, Lcom/google/android/gms/common/GoogleApiAvailability;
    invoke-direct {v0}, Lcom/google/android/gms/common/GoogleApiAvailability;-><init>()V
    return-object v0
.end method

.method public isGooglePlayServicesAvailable(Landroid/content/Context;)I
    .registers 1
    const/4 v0, 0x0
    return v0
.end method

.method public isUserResolvableError(I)Z
    .registers 1
    const/4 v0, 0x0
    return v0
.end method

.method public getErrorString(I)Ljava/lang/String;
    .registers 1
    const-string v0, "SUCCESS"
    return-object v0
.end method
"""


class GMSSpoofer:
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

    def _inject_stub(self) -> bool:
        stub_dir = os.path.join(
            self.decompiled_path, "smali",
            "com", "google", "android", "gms", "common",
        )
        os.makedirs(stub_dir, exist_ok=True)
        stub_path = os.path.join(stub_dir, "GoogleApiAvailability.smali")

        if os.path.exists(stub_path):
            return False

        if self.file_cache:
            self.file_cache.write(stub_path, GMS_STUB)
        else:
            with open(stub_path, "w", encoding="utf-8") as f:
                f.write(GMS_STUB)
        return True

    def patch(self) -> int:
        self.log("[*] [GMSSpoofer] Spoofing Google Play Services...")
        count = 0

        if self._inject_stub():
            count += 1
            self.log("[+] Added GoogleApiAvailability stub")

        pattern_avail = re.compile(
            r'(\.method\s+(?:public|private|static)\s+(?:final\s+)?(\S+)\s*\(.*?\)\s*I\s*'
            r'.*?invoke.*?isGooglePlayServicesAvailable.*?\.end\s+method)',
            re.DOTALL,
        )
        pattern_signin = re.compile(
            r'(invoke-static\s+\{.*?\},\s+'
            r'Lcom/google/android/gms/auth/api/signin/GoogleSignIn;->'
            r'getLastSignedInAccount\(.*?\)Lcom/google/android/gms/auth/api/signin/'
            r'GoogleSignInAccount;)'
        )

        for filepath in get_all_smali_files(self.decompiled_path):
            if len(filepath) > 250:
                continue
            content = self._read(filepath)
            original = content
            modified = False

            if "isGooglePlayServicesAvailable" in content:
                for match in pattern_avail.finditer(content):
                    header = match.group(0).split("\n")[0]
                    replacement = (
                        f"{header}\n"
                        "    .locals 1\n"
                        "    const/4 v0, 0x0\n"
                        "    return v0\n"
                        ".end method"
                    )
                    content = content.replace(match.group(0), replacement)
                    modified = True
                    count += 1

            if "GoogleSignIn" in content and "getLastSignedInAccount" in content:
                new_content, n = pattern_signin.subn(
                    r"# \1  # Disabled by LP-PC Suite", content
                )
                if n > 0:
                    content = new_content
                    modified = True
                    count += n

            if modified and content != original:
                self._write(filepath, content)

        self.log(f"[*] [GMSSpoofer] Total changes: {count}")
        return count