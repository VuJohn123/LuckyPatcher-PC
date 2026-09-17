"""
Ký APK với AOSP platform/media/shared keys.

Ưu tiên apksigner (Android SDK build-tools) — hỗ trợ v1+v2+v3+v4.
Fallback jarsigner (v1 only) nếu không có apksigner.
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
        self._apksigner = self._find_apksigner()

    # ---------------- FIND APKSIGNER ----------------
    def _find_apksigner(self) -> str | None:
        """Tìm apksigner (PATH > ANDROID_HOME/build-tools/<ver>)."""
        exe = shutil.which("apksigner") or shutil.which("apksigner.bat")
        if exe:
            return exe

        sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        if not sdk:
            return None

        build_tools = os.path.join(sdk, "build-tools")
        if not os.path.isdir(build_tools):
            return None

        exe_name = "apksigner.bat" if os.name == "nt" else "apksigner"
        versions = sorted(os.listdir(build_tools), reverse=True)
        for v in versions:
            candidate = os.path.join(build_tools, v, exe_name)
            if os.path.exists(candidate):
                return candidate
        return None

    # ---------------- PUBLIC API ----------------
    def sign_apk(
        self,
        apk_path: str,
        key_type: str = "platform",
        log_callback=None,
    ) -> str:
        log = log_callback or self.log

        if key_type not in self.KEY_ALIASES:
            raise ValueError(f"Key type không hỗ trợ: {key_type}")

        if not os.path.exists(apk_path):
            raise FileNotFoundError(apk_path)

        pk8 = os.path.join(self.keys_dir, f"{key_type}.pk8")
        pem = os.path.join(self.keys_dir, f"{key_type}.x509.pem")

        if not (os.path.exists(pk8) and os.path.exists(pem)):
            raise FileNotFoundError(f"Thiếu key files: {pk8} / {pem}")

        # Convert pk8+pem → p12
        p12 = self._pk8_to_p12(pk8, pem, key_type, log)

        # Try apksigner first (v1+v2+v3+v4)
        if self._apksigner:
            log(f"[*] [Signer] Dùng apksigner: {self._apksigner}")
            try:
                return self._sign_with_apksigner(
                    apk_path, p12, key_type, log
                )
            except Exception as e:
                log(f"[!] [Signer] apksigner fail: {e} — fallback jarsigner")
        else:
            log(
                "[!] [Signer] apksigner không có — fallback jarsigner "
                "(chỉ v1, có thể fail trên Android 11+)"
            )

        # Fallback jarsigner
        jks = self._p12_to_jks(p12, key_type, log)
        return self._jarsigner(apk_path, jks, key_type, log)

    # ---------------- APKSIGNER PATH ----------------
    def _sign_with_apksigner(
        self, apk_path: str, p12: str, alias: str, log
    ) -> str:
        signed = apk_path.replace(".apk", "_signed.apk")
        cmd = [
            self._apksigner,
            "sign",
            "--ks", p12,
            "--ks-type", "PKCS12",
            "--ks-pass", "pass:android",
            "--ks-key-alias", alias,
            "--key-pass", "pass:android",
            "--v1-signing-enabled", "true",
            "--v2-signing-enabled", "true",
            "--v3-signing-enabled", "true",
            "--out", signed,
            apk_path,
        ]
        log(f"[*] [Signer] apksigner sign --ks-type PKCS12 ...")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"apksigner failed: {proc.stderr or proc.stdout}"
            )
        log("[✔] [Signer] Signed with apksigner (v1+v2+v3)")
        return signed

    # ---------------- JARSIGNER FALLBACK ----------------
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

    # ---------------- CONVERSION ----------------
    def _pk8_to_p12(
        self, pk8: str, pem: str, alias: str, log
    ) -> str:
        """Convert pk8+pem → PKCS12 (apksigner accepts directly)."""
        tmp = tempfile.mkdtemp(prefix="sign_")
        p12 = os.path.join(tmp, "key.p12")

        cmd = [
            "openssl", "pkcs12", "-export",
            "-in", pem,
            "-inkey", pk8,
            "-out", p12,
            "-name", alias,
            "-passout", "pass:android",
        ]
        self._run(cmd, log, "openssl pkcs12")
        return p12

    def _p12_to_jks(self, p12: str, alias: str, log) -> str:
        """Convert p12 → JKS (cho jarsigner fallback)."""
        tmp = os.path.dirname(p12)
        jks = os.path.join(tmp, f"{alias}.jks")

        cmd = [
            "keytool", "-importkeystore",
            "-destkeystore", jks,
            "-deststorepass", "android",
            "-srckeystore", p12,
            "-srcstoretype", "PKCS12",
            "-srcstorepass", "android",
            "-alias", alias,
        ]
        self._run(cmd, log, "keytool import")
        return jks

    # ---------------- RUN HELPER ----------------
    def _run(self, cmd: list[str], log, label: str) -> None:
        if shutil.which(cmd[0]) is None:
            raise RuntimeError(f"Không tìm thấy lệnh: {cmd[0]}")
        log(f"[*] [Signer] {label}...")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"{label} failed: {proc.stderr}")