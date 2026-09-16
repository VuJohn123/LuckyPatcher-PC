"""
Ký APK với AOSP platform/media/shared keys.
Fallback graceful nếu thiếu jarsigner hoặc key files.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)


class APKSigner:
    KEY_ALIASES = {
        "platform": "platform",
        "media": "media",
        "shared": "shared",
        "testkey": "testkey",
    }

    def __init__(self, tools_dir: str, log_callback=print):
        self.tools_dir = tools_dir
        self.keys_dir = os.path.join(tools_dir, "keys")
        self.log = log_callback

    def sign_apk(self, apk_path: str, key_type: str = "platform",
                 log_callback=None) -> str:
        log = log_callback or self.log

        if key_type not in self.KEY_ALIASES:
            raise ValueError(f"Key type không hỗ trợ: {key_type}")

        if not os.path.exists(apk_path):
            raise FileNotFoundError(apk_path)

        pk8 = os.path.join(self.keys_dir, f"{key_type}.pk8")
        pem = os.path.join(self.keys_dir, f"{key_type}.x509.pem")

        if not (os.path.exists(pk8) and os.path.exists(pem)):
            raise FileNotFoundError(
                f"Thiếu key files: {pk8} / {pem}"
            )

        keystore = self._pk8_to_jks(pk8, pem, key_type, log)
        signed = self._jarsigner(apk_path, keystore, key_type, log)
        return signed

    def _pk8_to_jks(self, pk8: str, pem: str, alias: str, log) -> str:
        """Chuyển PK8 + PEM → JKS keystore."""
        tmp = tempfile.mkdtemp(prefix="sign_")
        p12 = os.path.join(tmp, "key.p12")
        jks = os.path.join(tmp, f"{alias}.jks")

        # Bước 1: pkcs12
        cmd1 = [
            "openssl", "pkcs12", "-export",
            "-in", pem,
            "-inkey", pk8,
            "-out", p12,
            "-name", alias,
            "-passout", "pass:android",
        ]
        self._run(cmd1, log, "openssl pkcs12")

        # Bước 2: keytool import
        cmd2 = [
            "keytool", "-importkeystore",
            "-destkeystore", jks,
            "-deststorepass", "android",
            "-srckeystore", p12,
            "-srcstoretype", "PKCS12",
            "-srcstorepass", "android",
            "-alias", alias,
        ]
        self._run(cmd2, log, "keytool import")
        return jks

    def _jarsigner(self, apk: str, keystore: str, alias: str, log) -> str:
        signed = apk.replace(".apk", "_signed.apk")
        cmd = [
            "jarsigner",
            "-keystore", keystore,
            "-storepass", "android",
            "-keypass", "android",
            "-sigalg", "SHA256withRSA",
            "-digestalg", "SHA-256",
            "-signedjar", signed,
            apk,
            alias,
        ]
        self._run(cmd, log, "jarsigner")
        return signed

    def _run(self, cmd: list[str], log, label: str) -> None:
        if shutil.which(cmd[0]) is None:
            raise RuntimeError(f"Không tìm thấy lệnh: {cmd[0]}")
        log(f"[*] [Signer] {label}...")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"{label} failed: {proc.stderr}")