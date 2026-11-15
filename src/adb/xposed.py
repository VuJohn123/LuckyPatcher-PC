"""
ADB Xposed Installer — install Xposed/LSPosed module (LP mobile feature).
"""
from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from .orchestrator import ADBOperation, ADBOrchestrator, ADBResult
from .shell import ADBShell

logger = logging.getLogger(__name__)


# Xposed minimum version from LP-DeCodes
XPOSED_MIN_VERSION = 82
XPOSED_ENTRY_POINT = "com.xposed.XSupport"
XPOSED_PACKAGE_ORIGINAL = "ru.aaaaaban.installer"
XPOSED_PACKAGE_OBFUSCATED = "ru.hhklsyty.wlkllqrcq"


@dataclass
class ADBXposedResult:
    """Result of Xposed module installation."""
    success: bool
    module_path: str = ""
    module_version: str = ""
    xposed_version: int = 0
    is_lsposed: bool = False
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def __bool__(self) -> bool:
        return self.success


class ADBXposedInstaller:
    """
    Xposed/LSPosed Module Installer — installs Lucky Patcher Xposed module (LP mobile feature).

    This implements the LP mobile Xposed module installation:
    1. Detect Xposed or LSPosed framework
    2. Build/extract Lucky Patcher Xposed module
    3. Install as Magisk module (LSPosed) or Xposed module (legacy)
    4. Enable module for target packages
    5. Configure hooks (IAP/LVL emulation, signature bypass, etc.)

    LP Xposed module (from LP-DeCodes):
    - Entry point: com.xposed.XSupport
    - Min version: 82
    - Package: ru.aaaaaban.installer (obfuscated: ru.hhklsyty.wlkllqrcq)
    - Hooks: 19 hooks for IAP, LVL, signature verification, etc.

    References:
    - LP-DeCodes LP_12.10.4_1/assets/xposed_init → com.xposed.XSupport
    - LP-DeCodes LP_12.10.4_1/smali/com/xposed/
    """

    def __init__(self, orchestrator: ADBOrchestrator, log_callback: Callable[[str], None] = print):
        self.orchestrator = orchestrator
        self.log = log_callback
        self.device = orchestrator.device
        self.shell = ADBShell(self.device.serial, self.orchestrator.adb_path)
        self.working_dir = "/data/local/tmp/lp_xposed"
        self.module_dir = "/data/adb/modules/luckypatcher_xposed"  # LSPosed/Magisk
        self.legacy_module_dir = "/data/xposed/modules/luckypatcher_xposed"  # Legacy Xposed

    def check_requirements(self) -> ADBResult:
        """Check for Xposed/LSPosed framework."""
        self.log("[*] [Xposed] Checking for Xposed/LSPosed framework...")

        # Check LSPosed (modern, Magisk-based)
        lsposed_check = self.orchestrator.shell("ls /data/adb/modules/lsposed 2>/dev/null || ls /data/adb/modules/zygisk_lsposed 2>/dev/null", require_root=True)
        is_lsposed = lsposed_check.success and lsposed_check.stdout.strip()

        # Check legacy Xposed
        xposed_check = self.orchestrator.shell("ls /data/xposed 2>/dev/null", require_root=True)
        is_xposed = xposed_check.success and xposed_check.stdout.strip()

        # Check Magisk
        self.orchestrator.shell("which magisk", require_root=True)

        if not (is_lsposed or is_xposed):
            self.log("[!] [Xposed] No Xposed/LSPosed framework detected")
            self.log("[!] [Xposed] Install LSPosed via Magisk or Xposed Installer")
            return ADBResult(success=False, operation=ADBOperation.SHELL,
                           error="Xposed/LSPosed framework not found")

        # Get version
        version = 0
        if is_lsposed:
            # LSPosed version from module.prop
            ver_result = self.orchestrator.shell("cat /data/adb/modules/lsposed/module.prop 2>/dev/null | grep versionCode")
            if ver_result.success:
                with contextlib.suppress(Exception):
                    version = int(ver_result.stdout.split("=")[1].strip())
            self.log(f"[+] [Xposed] LSPosed detected (versionCode: {version})")
        elif is_xposed:
            # Legacy Xposed version
            ver_result = self.orchestrator.shell("cat /data/xposed/version 2>/dev/null")
            if ver_result.success:
                with contextlib.suppress(Exception):
                    version = int(ver_result.stdout.strip())
            self.log(f"[+] [Xposed] Legacy Xposed detected (version: {version})")

        if version < XPOSED_MIN_VERSION:
            self.log(f"[!] [Xposed] Version {version} < min required {XPOSED_MIN_VERSION}")
            return ADBResult(success=False, operation=ADBOperation.SHELL,
                           error=f"Xposed version {version} < min required {XPOSED_MIN_VERSION}")

        self.log(f"[*] [Xposed] Requirements OK (version {version} >= {XPOSED_MIN_VERSION})")
        return ADBResult(success=True, operation=ADBOperation.SHELL,
                        stdout="lsposed" if is_lsposed else "xposed")

    def prepare_dirs(self) -> ADBResult:
        """Create module directories."""
        req_result = self.check_requirements()
        is_lsposed = "lsposed" in (req_result.stdout or "")

        if is_lsposed:
            self.orchestrator.shell(f"mkdir -p {self.module_dir}", require_root=True)
        else:
            self.orchestrator.shell(f"mkdir -p {self.legacy_module_dir}", require_root=True)

        self.orchestrator.shell(f"mkdir -p {self.working_dir}", require_root=True)

        return ADBResult(success=True, operation=ADBOperation.SHELL)

    def get_module_structure(self) -> dict:
        """Get LP Xposed module structure from LP-DeCodes."""
        return {
            "package": XPOSED_PACKAGE_OBFUSCATED,
            "entry_point": XPOSED_ENTRY_POINT,
            "min_version": XPOSED_MIN_VERSION,
            "hooks": [
                "com.android.vending.licensing.ILicensingService",
                "com.android.vending.billing.IInAppBillingService",
                "android.app.ApplicationPackageManager",
                "android.content.pm.PackageManager",
                "android.content.pm.PackageParser",
                "android.app.ActivityThread",
                "android.os.Build",
                "java.lang.ClassLoader",
                "dalvik.system.DexFile",
            ],
            "permissions": [
                "android.permission.INTERNET",
                "android.permission.ACCESS_NETWORK_STATE",
            ]
        }

    def build_module_from_source(self) -> ADBResult:
        """
        Build Xposed module from LP-DeCodes smali source.

        Note: This is a placeholder. Real implementation would:
        1. Have LP-DeCodes smali source in assets/xposed_module/
        2. Compile with smali/baksmali
        3. Create module APK
        """
        self.log("[!] [Xposed] Module must be built from LP-DeCodes source")
        self.log("[!] [Xposed] Expected: assets/xposed_module/ (smali source)")

        return ADBResult(success=False, operation=ADBOperation.SHELL,
                       error="Xposed module source not available")

    def extract_module_from_lp(self, lp_apk_path: str) -> ADBResult:
        """
        Extract Xposed module from Lucky Patcher APK.

        LP APK contains the Xposed module as asset or embedded.
        """
        self.log(f"[*] [Xposed] Extracting module from {lp_apk_path}...")

        # Check if LP APK has xposed module
        # LP stores module in assets/xposed_module.apk or similar
        extract_dir = f"{self.working_dir}/extracted"
        self.orchestrator.shell(f"mkdir -p {extract_dir}", require_root=True)

        # Try to find xposed module in LP APK
        result = self.orchestrator.shell(
            f"unzip -l {lp_apk_path} | grep -i xposed",
            require_root=True
        )

        if result.success and result.stdout.strip():
            self.log("[+] [Xposed] Found Xposed module in LP APK")
            # Extract it
            self.orchestrator.shell(
                f"unzip -o {lp_apk_path} 'assets/xposed_module*' -d {extract_dir}",
                require_root=True
            )
            return ADBResult(success=True, operation=ADBOperation.SHELL, stdout=extract_dir)
        else:
            self.log("[!] [Xposed] No Xposed module found in LP APK")
            return ADBResult(success=False, operation=ADBOperation.SHELL,
                           error="Xposed module not in LP APK")

    def create_module_apk(self, module_dir: str) -> ADBResult:
        """
        Create module APK from smali source.

        Uses smali/baksmali to compile module.
        """
        self.log("[*] [Xposed] Building module APK...")

        # This would compile smali from LP-DeCodes
        # For now, assume pre-built module APK is provided
        return ADBResult(success=False, operation=ADBOperation.SHELL,
                       error="Module APK build not implemented")

    def install_module_apk(self, module_apk_path: str) -> ADBResult:
        """Install Xposed module APK."""
        self.log(f"[*] [Xposed] Installing module APK: {module_apk_path}")

        # Install with replace
        result = self.orchestrator.install(module_apk_path, replace=True)

        if result.success:
            self.log("[+] [Xposed] Module APK installed")
        return result

    def install_as_magisk_module(self, module_apk_path: str | None = None) -> ADBResult:
        """
        Install as Magisk module (for LSPosed).

        Creates Magisk module structure:
        /data/adb/modules/luckypatcher_xposed/
          - module.prop
          - system/
            - framework/
              - luckypatcher_xposed.jar (or .apk)
          - service.sh (optional)
          - post-fs-data.sh (optional)
        """
        self.log("[*] [Xposed] Installing as Magisk module...")

        req_result = self.check_requirements()
        is_lsposed = "lsposed" in (req_result.stdout or "")

        if not is_lsposed:
            return ADBResult(success=False, operation=ADBOperation.SHELL,
                           error="LSPosed not detected, use legacy Xposed install")

        # Create module structure
        dirs = [
            self.module_dir,
            f"{self.module_dir}/system/framework",
        ]

        for d in dirs:
            self.orchestrator.shell(f"mkdir -p {d}", require_root=True)

        # Copy module APK/JAR to module dir
        if module_apk_path:
            target = f"{self.module_dir}/system/framework/luckypatcher_xposed.apk"
            self.orchestrator.shell(f"cp {module_apk_path} {target}", require_root=True)
        else:
            # Try to find installed module
            # LSPosed loads modules from /data/adb/modules/<module>/system/framework/
            pass

        # Create module.prop
        module_prop = f"""id=luckypatcher_xposed
name=Lucky Patcher Xposed Module
version=12.10.4
versionCode=121004
author=ChelpuS
description=Lucky Patcher Xposed Module for IAP/LVL emulation and signature bypass
minVersion={XPOSED_MIN_VERSION}
"""
        self.orchestrator.shell(
            f"cat > {self.module_dir}/module.prop << 'EOF'\n{module_prop}\nEOF",
            require_root=True
        )

        # Create xposed_init (entry point list)
        xposed_init = XPOSED_ENTRY_POINT
        self.orchestrator.shell(
            f"cat > {self.module_dir}/xposed_init << 'EOF'\n{xposed_init}\nEOF",
            require_root=True
        )

        # Create service.sh (runs on boot)
        service_sh = """#!/system/bin/sh
# Lucky Patcher Xposed Module - service.sh
# This runs after boot completes

# Wait for boot
while [ "$(getprop sys.boot_completed)" != "1" ]; do
    sleep 1
done

# Module is loaded by LSPosed automatically
# This script can do additional setup if needed
"""
        self.orchestrator.shell(
            f"cat > {self.module_dir}/service.sh << 'EOF'\n{service_sh}\nEOF",
            require_root=True
        )
        self.orchestrator.shell(f"chmod 755 {self.module_dir}/service.sh", require_root=True)

        # Create post-fs-data.sh (runs early)
        post_fs = """#!/system/bin/sh
# Lucky Patcher Xposed Module - post-fs-data.sh
# Runs after /data is mounted

# Ensure module directory exists
mkdir -p /data/local/lp
"""
        self.orchestrator.shell(
            f"cat > {self.module_dir}/post-fs-data.sh << 'EOF'\n{post_fs}\nEOF",
            require_root=True
        )
        self.orchestrator.shell(f"chmod 755 {self.module_dir}/post-fs-data.sh", require_root=True)

        self.log(f"[+] [Xposed] Magisk module created at {self.module_dir}")
        self.log("[!] [Xposed] Reboot to activate module")

        return ADBResult(success=True, operation=ADBOperation.SHELL, stdout=self.module_dir)

    def install_as_legacy_xposed(self, module_apk_path: str | None = None) -> ADBResult:
        """Install as legacy Xposed module (for Xposed Framework)."""
        self.log("[*] [Xposed] Installing as legacy Xposed module...")

        req_result = self.check_requirements()
        is_lsposed = "lsposed" in (req_result.stdout or "")

        if is_lsposed:
            return ADBResult(success=False, operation=ADBOperation.SHELL,
                           error="LSPosed detected, use Magisk module install")

        # Legacy Xposed uses /data/xposed/modules/
        dirs = [
            self.legacy_module_dir,
        ]

        for d in dirs:
            self.orchestrator.shell(f"mkdir -p {d}", require_root=True)

        if module_apk_path:
            target = f"{self.legacy_module_dir}/luckypatcher_xposed.apk"
            self.orchestrator.shell(f"cp {module_apk_path} {target}", require_root=True)

        # Create module.prop
        module_prop = """id=luckypatcher_xposed
name=Lucky Patcher Xposed Module
version=12.10.4
versionCode=121004
author=ChelpuS
description=Lucky Patcher Xposed Module for IAP/LVL emulation and signature bypass
"""
        self.orchestrator.shell(
            f"cat > {self.legacy_module_dir}/module.prop << 'EOF'\n{module_prop}\nEOF",
            require_root=True
        )

        # Create xposed_init
        xposed_init = XPOSED_ENTRY_POINT
        self.orchestrator.shell(
            f"cat > {self.legacy_module_dir}/xposed_init << 'EOF'\n{xposed_init}\nEOF",
            require_root=True
        )

        self.log(f"[+] [Xposed] Legacy module created at {self.legacy_module_dir}")
        self.log("[!] [Xposed] Enable in Xposed Installer and reboot")

        return ADBResult(success=True, operation=ADBOperation.SHELL, stdout=self.legacy_module_dir)

    def enable_module(self, package_name: str = XPOSED_PACKAGE_OBFUSCATED) -> ADBResult:
        """Enable Xposed module for specific package (LSPosed)."""
        # LSPosed uses scoped modules - enable per package
        self.log(f"[*] [Xposed] Enabling module for {package_name}...")

        # For LSPosed, create enable file
        enable_file = "/data/adb/modules/luckypatcher_xposed/enable"
        self.orchestrator.shell(f"echo {package_name} > {enable_file}", require_root=True)

        # Also add to LSPosed config
        lsposed_config = "/data/adb/lspd/config/luckypatcher_xposed.json"
        self.orchestrator.shell(f"mkdir -p $(dirname {lsposed_config})", require_root=True)

        import json
        config = {
            "packageName": package_name,
            "processName": package_name,
            "enabled": True
        }
        self.orchestrator.shell(
            f"cat > {lsposed_config} << 'EOF'\n{json.dumps(config, indent=2)}\nEOF",
            require_root=True
        )

        return ADBResult(success=True, operation=ADBOperation.SHELL)

    def disable_module(self) -> ADBResult:
        """Disable Xposed module."""
        self.log("[*] [Xposed] Disabling module...")

        # Remove enable files
        self.orchestrator.shell("rm -f /data/adb/modules/luckypatcher_xposed/enable", require_root=True)
        self.orchestrator.shell("rm -f /data/adb/lspd/config/luckypatcher_xposed.json", require_root=True)

        return ADBResult(success=True, operation=ADBOperation.SHELL)

    def check_module_status(self) -> ADBResult:
        """Check if module is installed and enabled."""
        # Check Magisk module
        magisk_check = self.orchestrator.shell("ls /data/adb/modules/luckypatcher_xposed", require_root=True)

        # Check legacy
        legacy_check = self.orchestrator.shell("ls /data/xposed/modules/luckypatcher_xposed", require_root=True)

        # Check if enabled
        enable_check = self.orchestrator.shell("cat /data/adb/modules/luckypatcher_xposed/enable 2>/dev/null")

        status = {
            "magisk_module": magisk_check.success,
            "legacy_module": legacy_check.success,
            "enabled_packages": enable_check.stdout.strip() if enable_check.success else "none"
        }

        return ADBResult(success=True, operation=ADBOperation.SHELL, stdout=str(status))

    def install(self, module_apk_path: str | None = None, lp_apk_path: str | None = None) -> ADBXposedResult:
        """
        Full Xposed module installation workflow.

        Args:
            module_apk_path: Path to pre-built module APK
            lp_apk_path: Path to Lucky Patcher APK (to extract module from)
        """
        import time
        start = time.monotonic()

        result = ADBXposedResult(success=False)

        # 1. Check requirements
        req = self.check_requirements()
        if not req.success:
            result.errors.append(req.error)
            return result

        is_lsposed = "lsposed" in (req.stdout or "")
        result.is_lsposed = is_lsposed

        # 2. Prepare dirs
        self.prepare_dirs()

        # 3. Get module APK
        if module_apk_path:
            # User provided module APK
            pass
        elif lp_apk_path:
            # Extract from LP APK
            extract_result = self.extract_module_from_lp(lp_apk_path)
            if extract_result.success:
                # Find extracted module
                find_result = self.orchestrator.shell(f"find {self.working_dir}/extracted -name '*.apk' -o -name '*.jar'")
                if find_result.success and find_result.stdout.strip():
                    module_apk_path = find_result.stdout.strip().splitlines()[0]
            else:
                result.errors.append("Failed to extract module from LP APK")
                return result
        else:
            # Try to build from source (will fail without source)
            build_result = self.build_module_from_source()
            if not build_result.success:
                result.errors.append("No module APK provided and build failed")
                return result

        # 4. Install based on framework
        if is_lsposed:
            install_result = self.install_as_magisk_module(module_apk_path)
        else:
            install_result = self.install_as_legacy_xposed(module_apk_path)

        if not install_result.success:
            result.errors.append(install_result.error or "Module install failed")
            return result

        result.module_path = install_result.stdout or ""

        # 5. Enable for LP package
        self.enable_module(XPOSED_PACKAGE_OBFUSCATED)

        # 6. Check status
        self.check_module_status()

        result.success = True
        result.duration_ms = (time.monotonic() - start) * 1000

        self.log("[+] [Xposed] Module installation complete")
        self.log("[!] [Xposed] Reboot device to activate")

        return result

    def remove(self) -> ADBResult:
        """Remove Xposed module."""
        self.log("[*] [Xposed] Removing module...")

        # Remove Magisk module
        self.orchestrator.shell("rm -rf /data/adb/modules/luckypatcher_xposed", require_root=True)

        # Remove legacy module
        self.orchestrator.shell("rm -rf /data/xposed/modules/luckypatcher_xposed", require_root=True)

        # Remove configs
        self.orchestrator.shell("rm -f /data/adb/lspd/config/luckypatcher_xposed.json", require_root=True)

        self.log("[+] [Xposed] Module removed")
        return ADBResult(success=True, operation=ADBOperation.SHELL)


def install_xposed_module(orchestrator: ADBOrchestrator, module_apk_path: str | None = None,
                           lp_apk_path: str | None = None, log_callback: Callable[[str], None] = print) -> ADBXposedResult:
    """Convenience function for Xposed module installation."""
    installer = ADBXposedInstaller(orchestrator, log_callback)
    return installer.install(module_apk_path, lp_apk_path)
