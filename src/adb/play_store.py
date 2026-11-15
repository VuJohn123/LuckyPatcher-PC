"""
ADB Modded Play Store — install modified Google Play Store (LP mobile feature).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from .orchestrator import ADBOperation, ADBOrchestrator, ADBResult
from .shell import ADBShell

logger = logging.getLogger(__name__)


@dataclass
class ModdedPlayStoreResult:
    """Result of Modded Play Store installation."""
    success: bool
    version_installed: str = ""
    package_name: str = "com.android.vending"
    backup_path: str = ""
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def __bool__(self) -> bool:
        return self.success


class ModdedPlayStore:
    """
    Install Modified Google Play Store (LP mobile feature).

    This implements the LP mobile "Install modified Google Play" feature:
    1. Download modded Play Store APK (matching device architecture/version)
    2. Backup original Play Store
    3. Install modded version
    4. Apply patches for IAP/LVL emulation

    Modded Play Store allows:
    - IAP emulation (fake purchases)
    - LVL emulation (fake license verification)
    - Bypassing Play Store checks
    """

    # Known modded Play Store versions and sources
    PLAY_STORE_VERSIONS = {
        "arm64-v8a": [
            "43.7.19", "42.9.17", "41.8.15", "40.7.13"
        ],
        "armeabi-v7a": [
            "43.7.19", "42.9.17", "41.8.15", "40.7.13"
        ],
        "x86_64": [
            "43.7.19", "42.9.17"
        ],
        "x86": [
            "43.7.19", "42.9.17"
        ],
    }

    def __init__(self, orchestrator: ADBOrchestrator, log_callback: Callable[[str], None] = print):
        self.orchestrator = orchestrator
        self.log = log_callback
        self.device = orchestrator.device
        self.shell = ADBShell(self.device.serial, self.orchestrator.adb_path)
        self.working_dir = "/data/local/tmp/lp_play_store"

    def check_requirements(self) -> ADBResult:
        """Check root, API level."""
        self.log("[*] [ModPlayStore] Checking requirements...")

        # Root required
        root_result = self.orchestrator.check_root_access()
        if not root_result.success:
            return ADBResult(success=False, operation=ADBOperation.SHELL,
                           error="Root access required for Modded Play Store")

        # API 19+
        if self.device.api_level < 19:
            return ADBResult(success=False, operation=ADBOperation.SHELL,
                           error=f"Android {self.device.android_version} (API {self.device.api_level}) < 4.4 required")

        self.log("[*] [ModPlayStore] Requirements OK")
        return ADBResult(success=True, operation=ADBOperation.SHELL)

    def get_device_arch(self) -> str:
        """Get device CPU architecture."""
        return self.device.cpu_abi or "arm64-v8a"

    def get_current_play_store_version(self) -> ADBResult:
        """Get currently installed Play Store version."""
        return self.orchestrator.shell("pm dump com.android.vending | grep versionName")

    def backup_original_play_store(self) -> ADBResult:
        """Backup original Play Store APK."""
        self.log("[*] [ModPlayStore] Backing up original Play Store...")

        # Get APK path
        path_result = self.orchestrator.shell("pm path com.android.vending")
        if not path_result.success:
            return path_result

        apk_paths = [line.replace("package:", "").strip()
                     for line in path_result.stdout.strip().splitlines()
                     if line.startswith("package:")]

        if not apk_paths:
            return ADBResult(success=False, operation=ADBOperation.SHELL, error="Play Store not found")

        # Backup to working dir
        backup_dir = f"{self.working_dir}/backup"
        self.orchestrator.shell(f"mkdir -p {backup_dir}", require_root=True)

        for i, apk_path in enumerate(apk_paths):
            backup_path = f"{backup_dir}/vending_{i}.apk"
            result = self.orchestrator.shell(f"cp {apk_path} {backup_path}", require_root=True)
            if result.success:
                self.log(f"[+] [ModPlayStore] Backed up to {backup_path}")

        return ADBResult(success=True, operation=ADBOperation.SHELL, stdout=backup_dir)

    def download_modded_apk(self, version: str | None = None, arch: str | None = None) -> ADBResult:
        """
        Download modded Play Store APK.

        Note: This is a placeholder. Real implementation would:
        1. Download from known sources (patch.chelpus.com, etc.)
        2. Verify checksum
        3. Push to device
        """
        arch = arch or self.get_device_arch()
        version = version or self.PLAY_STORE_VERSIONS.get(arch, ["latest"])[0]

        self.log(f"[*] [ModPlayStore] Downloading modded Play Store {version} for {arch}...")

        # Placeholder - in reality, we'd download from a trusted source
        # For now, assume user provides the APK
        self.log("[!] [ModPlayStore] Modded Play Store APK must be provided manually")
        self.log("[!] [ModPlayStore] Push it to device with: adb push modded_vending.apk /data/local/tmp/")

        return ADBResult(success=False, operation=ADBOperation.SHELL,
                       error="Modded Play Store APK not provided")

    def install_modded_apk(self, apk_path: str) -> ADBResult:
        """Install modded Play Store APK."""
        self.log(f"[*] [ModPlayStore] Installing {apk_path}...")

        # Uninstall original first (if not system app)
        # Play Store is usually a system app, so we need to replace it
        # This requires root and remounting /system

        remount = self.orchestrator.shell("mount -o remount,rw /system", require_root=True)
        if not remount.success:
            return ADBResult(success=False, operation=ADBOperation.SHELL,
                           error="Failed to remount /system as read-write")

        try:
            # Get original APK location
            path_result = self.orchestrator.shell("pm path com.android.vending")
            apk_paths = [line.replace("package:", "").strip()
                         for line in path_result.stdout.strip().splitlines()
                         if line.startswith("package:")]

            if not apk_paths:
                return ADBResult(success=False, operation=ADBOperation.SHELL, error="Original Play Store not found")

            original_apk = apk_paths[0]

            # Replace original APK
            result = self.orchestrator.shell(f"cp {apk_path} {original_apk}", require_root=True)
            if not result.success:
                return result

            # Fix permissions
            self.orchestrator.shell(f"chmod 644 {original_apk}", require_root=True)
            self.orchestrator.shell(f"chown root:root {original_apk}", require_root=True)

            self.log("[+] [ModPlayStore] Play Store replaced")

            # Restart Play Store
            self.orchestrator.shell("am force-stop com.android.vending")
            self.orchestrator.shell("am start -n com.android.vending/com.google.android.finsky.activities.MainActivity")

            return ADBResult(success=True, operation=ADBOperation.SHELL)
        finally:
            self.orchestrator.shell("mount -o remount,ro /system", require_root=True)

    def apply_iap_patches(self) -> ADBResult:
        """Apply IAP/LVL emulation patches to modded Play Store."""
        self.log("[*] [ModPlayStore] Applying IAP/LVL patches...")

        # Patches would modify Play Store to:
        # 1. Redirect IAP requests to Lucky Patcher proxy
        # 2. Redirect LVL requests to Lucky Patcher
        # 3. Fake purchase receipts

        # This is typically done via Xposed module, not by patching Play Store directly
        # The modded Play Store usually includes these patches pre-applied

        self.log("[i] [ModPlayStore] IAP/LVL patches should be pre-applied in modded APK")
        return ADBResult(success=True, operation=ADBOperation.SHELL)

    def test_modded_play_store(self) -> ADBResult:
        """Test if modded Play Store works."""
        self.log("[*] [ModPlayStore] Testing modded Play Store...")

        # Check if Play Store responds to IAP intents
        test_intent = "am start -a com.android.vending.billing.PURCHASE"
        result = self.orchestrator.shell(test_intent)

        # Check logs for Lucky Patcher proxy
        self.orchestrator.shell("logcat -d -t 100 | grep -i luckypatcher")

        return ADBResult(success=result.success, operation=ADBOperation.SHELL)

    def install(self, modded_apk_path: str | None = None, version: str | None = None) -> ModdedPlayStoreResult:
        """
        Full Modded Play Store installation workflow.

        Args:
            modded_apk_path: Path to modded Play Store APK on device
            version: Specific version to install (auto-detect if None)
        """
        import time
        start = time.monotonic()

        result = ModdedPlayStoreResult(success=False)

        # 1. Check requirements
        req = self.check_requirements()
        if not req.success:
            result.errors.append(req.error)
            return result

        # 2. Prepare working dir
        self.orchestrator.shell(f"mkdir -p {self.working_dir}", require_root=True)

        # 3. Backup original
        backup = self.backup_original_play_store()
        result.backup_path = backup.stdout or ""

        # 4. Get modded APK
        if modded_apk_path:
            # User provided APK path on device
            pass
        else:
            # Try to download
            dl_result = self.download_modded_apk(version)
            if not dl_result.success:
                result.errors.append("Modded Play Store APK required but not provided")
                return result
            modded_apk_path = "/data/local/tmp/modded_vending.apk"  # assumed

        # 5. Install modded APK
        install_result = self.install_modded_apk(modded_apk_path)
        if not install_result.success:
            result.errors.append(install_result.error or "Install failed")
            return result

        # 6. Apply IAP patches
        self.apply_iap_patches()

        # 7. Test
        self.test_modded_play_store()

        # Get installed version
        version_result = self.get_current_play_store_version()
        if version_result.success:
            result.version_installed = version_result.stdout.strip()

        result.success = True
        result.duration_ms = (time.monotonic() - start) * 1000

        return result

    def restore_original(self) -> ADBResult:
        """Restore original Play Store from backup."""
        self.log("[*] [ModPlayStore] Restoring original Play Store...")

        backup_dir = f"{self.working_dir}/backup"

        remount = self.orchestrator.shell("mount -o remount,rw /system", require_root=True)
        if not remount.success:
            return ADBResult(success=False, operation=ADBOperation.SHELL,
                           error="Failed to remount /system")

        try:
            path_result = self.orchestrator.shell("pm path com.android.vending")
            apk_paths = [line.replace("package:", "").strip()
                         for line in path_result.stdout.strip().splitlines()
                         if line.startswith("package:")]

            for i, apk_path in enumerate(apk_paths):
                backup_apk = f"{backup_dir}/vending_{i}.apk"
                check = self.orchestrator.shell(f"ls {backup_apk}", require_root=True)
                if check.success:
                    self.orchestrator.shell(f"cp {backup_apk} {apk_path}", require_root=True)
                    self.log(f"[+] [ModPlayStore] Restored {apk_path}")
        finally:
            self.orchestrator.shell("mount -o remount,ro /system", require_root=True)

        return ADBResult(success=True, operation=ADBOperation.SHELL)


def install_modded_play_store(orchestrator: ADBOrchestrator, modded_apk_path: str | None = None,
                               version: str | None = None, log_callback: Callable[[str], None] = print) -> ModdedPlayStoreResult:
    """Convenience function for Modded Play Store installation."""
    installer = ModdedPlayStore(orchestrator, log_callback)
    return installer.install(modded_apk_path, version)
