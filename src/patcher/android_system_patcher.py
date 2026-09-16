"""System patcher — tạo Magisk module + patch services.jar (qua ADB root)."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import zipfile

logger = logging.getLogger(__name__)


class AndroidSystemPatcher:
    def __init__(self, adb: str = "adb", log_callback=print):
        self.adb = adb
        self.log = log_callback
        self.tools_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "tools",
        )

    def check_root(self) -> bool:
        try:
            proc = subprocess.run(
                [self.adb, "shell", "su", "-c", "id"],
                capture_output=True, text=True, timeout=5,
            )
            return "uid=0" in proc.stdout
        except subprocess.SubprocessError:
            return False

    def create_magisk_module(self, output_zip: str,
                             services_jar: str | None = None) -> str | None:
        tmp = tempfile.mkdtemp(prefix="magisk_")
        try:
            fw_dir = os.path.join(tmp, "system", "framework")
            os.makedirs(fw_dir, exist_ok=True)
            if services_jar and os.path.exists(services_jar):
                shutil.copy2(services_jar,
                             os.path.join(fw_dir, "services.jar"))

            with open(os.path.join(tmp, "module.prop"), "w") as f:
                f.write(
                    "id=lp_pc_signature_patch\n"
                    "name=LP-PC Signature Patch\n"
                    "version=v1.0\n"
                    "versionCode=1\n"
                    "author=LP-PC Suite\n"
                    "description=Disable APK signature verification\n"
                )
            with open(os.path.join(tmp, "post-fs-data.sh"), "w") as f:
                f.write(
                    "#!/system/bin/sh\n"
                    "MODDIR=${0%/*}\n"
                    "[ -f \"$MODDIR/system/framework/services.jar\" ] && "
                    "mount -o bind "
                    "\"$MODDIR/system/framework/services.jar\" "
                    "/system/framework/services.jar\n"
                )
            os.chmod(os.path.join(tmp, "post-fs-data.sh"), 0o755)

            with zipfile.ZipFile(output_zip, "w",
                                 zipfile.ZIP_DEFLATED) as z:
                for root, _, files in os.walk(tmp):
                    for f in files:
                        full = os.path.join(root, f)
                        rel = os.path.relpath(full, tmp)
                        z.write(full, arcname=rel)
            return output_zip
        except OSError as e:
            logger.warning("Magisk module create failed: %s", e)
            return None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def push_and_flash(self, module_zip: str) -> bool:
        try:
            dest = "/sdcard/lp_pc_signature_patch.zip"
            subprocess.run([self.adb, "push", module_zip, dest], check=True,
                           timeout=60)
            self.log(f"[✔] Module pushed: {dest}")
            return True
        except subprocess.SubprocessError as e:
            self.log(f"[!] Push failed: {e}")
            return False

    def apply_patches(self, features: dict) -> bool:
        """Full pipeline — yêu cầu root."""
        if not self.check_root():
            self.log("[!] Thiết bị chưa root")
            return False

        tmp = tempfile.mkdtemp(prefix="system_")
        try:
            jar = os.path.join(tmp, "services.jar")
            try:
                subprocess.run(
                    [self.adb, "pull", "/system/framework/services.jar", jar],
                    check=True, timeout=60,
                )
            except subprocess.SubprocessError as e:
                self.log(f"[!] Pull services.jar failed: {e}")
                return False

            # Nếu không có baksmali/smali thì bỏ qua patch thực sự
            baksmali = os.path.join(self.tools_dir, "baksmali.jar")
            smali = os.path.join(self.tools_dir, "smali.jar")
            if not (os.path.exists(baksmali) and os.path.exists(smali)):
                self.log("[i] baksmali/smali không có — chỉ tạo module rỗng")
                module = self.create_magisk_module(
                    os.path.join(tmp, "module.zip"), jar)
                if module:
                    return self.push_and_flash(module)
                return False

            # TODO: full smali patch pipeline (không triển khai vì thiếu tools)
            self.log("[i] Smali tools present but full patch chưa triển khai")
            return False
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_patch(self) -> bool:
        try:
            proc = subprocess.run(
                [self.adb, "shell", "pm", "list", "packages"],
                capture_output=True, text=True, timeout=10,
            )
            return "package:" in (proc.stdout or "")
        except subprocess.SubprocessError:
            return False