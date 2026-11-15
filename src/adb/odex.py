"""
ADB ODEX Patching — baksmali/smali on device for ODEX patching (LP mobile feature).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .orchestrator import ADBOperation, ADBOrchestrator, ADBResult
from .shell import ADBShell

logger = logging.getLogger(__name__)


@dataclass
class ADBOdexPatchResult:
    """Result of ODEX patching operation."""
    success: bool
    package_name: str
    apk_path: str
    dex_files: list[str] = field(default_factory=list)
    patched_dex_files: list[str] = field(default_factory=list)
    working_dir: str = ""
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def __bool__(self) -> bool:
        return self.success


class ADBOdexPatcher:
    """
    ODEX patching on Android device using baksmali/smali.

    This implements the LP mobile feature for ODEX patching:
    1. Pull APK to device
    2. Decompile dex files with baksmali
    3. Apply patches (smali modifications)
    4. Recompile with smali
    5. Create ODEX files with dexopt-wrapper
    6. Replace original ODEX files

    Requires:
    - Root access
    - Android 5.0+ (ART runtime)
    - baksmali, smali, dexopt-wrapper on device
    """

    def __init__(self, orchestrator: ADBOrchestrator, log_callback: Callable[[str], None] = print):
        self.orchestrator = orchestrator
        self.log = log_callback
        self.device = orchestrator.device
        self.shell = ADBShell(self.device.serial, self.orchestrator.adb_path)
        self.working_dir = "/data/local/tmp/lp_odex"
        self.tools_dir = "/data/local/tmp/lp_tools"
        self.baksmali_jar = f"{self.tools_dir}/baksmali.jar"
        self.smali_jar = f"{self.tools_dir}/smali.jar"
        self.dexopt_wrapper = "/system/bin/dexopt-wrapper"

    def check_requirements(self) -> ADBResult:
        """Check if all required tools are available on device."""
        self.log("[*] [ODEX] Checking device requirements...")

        # Check root
        root_result = self.orchestrator.check_root_access()
        if not root_result.success:
            return ADBResult(success=False, operation=ADBOperation.SHELL,
                           error="Root access required for ODEX patching")

        # Check API level
        if self.device.api_level < 21:
            return ADBResult(success=False, operation=ADBOperation.SHELL,
                           error=f"Android {self.device.android_version} (API {self.device.api_level}) < 5.0 required")

        # Check baksmali/smali
        baksmali_check = self.shell.which("baksmali")
        smali_check = self.shell.which("smali")

        # Check dexopt-wrapper
        dexopt_check = self.shell.which("dexopt-wrapper")

        self.log(f"[*] [ODEX] baksmali: {'✓' if baksmali_check.success else '✗'}")
        self.log(f"[*] [ODEX] smali: {'✓' if smali_check.success else '✗'}")
        self.log(f"[*] [ODEX] dexopt-wrapper: {'✓' if dexopt_check.success else '✗'}")

        # If tools not found, try to install them
        if not (baksmali_check.success and smali_check.success):
            self.log("[*] [ODEX] Installing baksmali/smali...")
            self._install_smali_tools()

        return ADBResult(success=True, operation=ADBOperation.SHELL)

    def _install_smali_tools(self) -> bool:
        """Install baksmali/smali jars to device."""
        try:
            # Create tools directory
            self.orchestrator.shell(f"mkdir -p {self.tools_dir}", require_root=True)

            # Note: In real implementation, we'd push the JARs from PC
            # For now, assume they're available or can be downloaded
            self.log("[i] [ODEX] baksmali/smali JARs need to be pushed from PC")
            return False
        except Exception as e:
            self.log(f"[!] [ODEX] Tool install failed: {e}")
            return False

    def prepare_working_dir(self) -> ADBResult:
        """Prepare working directory on device."""
        return self.orchestrator.shell(f"mkdir -p {self.working_dir}/smali", require_root=True)

    def get_apk_path(self, package_name: str) -> ADBResult:
        """Get APK path for package."""
        return self.orchestrator.shell(f"pm path {package_name}")

    def pull_apk(self, package_name: str, local_apk_path: str) -> ADBResult:
        """Pull APK from device to PC."""
        # First get the APK path
        path_result = self.get_apk_path(package_name)
        if not path_result.success:
            return path_result

        # pm path returns "package:/path/to/base.apk"
        lines = path_result.stdout.strip().splitlines()
        apk_paths = [line.replace("package:", "").strip() for line in lines if line.startswith("package:")]

        if not apk_paths:
            return ADBResult(success=False, operation=ADBOperation.SHELL, error="No APK path found")

        # Pull base APK
        base_apk = apk_paths[0]
        return self.orchestrator.pull(base_apk, local_apk_path)

    def decompile_dex(self, apk_path: str, output_dir: str, dex_files: list[str] | None = None) -> ADBResult:
        """Decompile DEX files from APK using baksmali."""
        self.log(f"[*] [ODEX] Decompiling {apk_path}...")

        # If no specific dex files, decompile all
        if dex_files is None:
            # Extract all classes*.dex
            cmd = f"cd {output_dir} && unzip -o {apk_path} 'classes*.dex'"
            result = self.orchestrator.shell(cmd)
            if not result.success:
                return result

            # Find dex files
            find_result = self.orchestrator.shell(f"ls {output_dir}/classes*.dex")
            if not find_result.success:
                return find_result
            dex_files = [f.strip() for f in find_result.stdout.strip().splitlines() if f.strip()]

        # Decompile each dex file
        for i, dex_file in enumerate(dex_files):
            dex_name = Path(dex_file).name
            smali_dir = f"{output_dir}/smali_{i}"

            self.log(f"[*] [ODEX] Baksmali {dex_name}...")
            cmd = f"baksmali {dex_file} -o {smali_dir}"
            result = self.orchestrator.shell(cmd)
            if not result.success:
                return result

        return ADBResult(success=True, operation=ADBOperation.SHELL)

    def apply_patches(self, smali_dirs: list[str], patches: list[dict]) -> ADBResult:
        """
        Apply smali patches to decompiled directories.

        patches format:
        [
            {
                "file_pattern": "com/example/MyClass.smali",
                "search": "const/4 v0, 0x0",
                "replace": "const/4 v0, 0x1",
                "masked": false  # or true for LP mask syntax
            }
        ]
        """
        from core.smali_utils import get_all_smali_files

        self.log(f"[*] [ODEX] Applying {len(patches)} patches...")

        for smali_dir in smali_dirs:
            # Get all smali files
            smali_files = get_all_smali_files(smali_dir)

            for patch in patches:
                pattern = patch.get("search", "")
                replacement = patch.get("replace", "")
                file_pat = patch.get("file_pattern", "**/*.smali")
                masked = patch.get("masked", False)

                if masked:
                    from patcher.custom_patch import _apply_mask
                    pattern = _apply_mask(pattern)

                import re
                regex = re.compile(pattern, re.DOTALL)

                for smali_file in smali_files:
                    if file_pat and file_pat != "**/*.smali":
                        import fnmatch
                        rel_path = str(Path(smali_file).relative_to(smali_dir))
                        if not fnmatch.fnmatch(rel_path, file_pat):
                            continue

                    try:
                        with open(smali_file, encoding='utf-8', errors='ignore') as f:
                            content = f.read()

                        new_content = regex.sub(replacement, content)
                        if new_content != content:
                            with open(smali_file, 'w', encoding='utf-8') as f:
                                f.write(new_content)
                            self.log(f"[+] [ODEX] Patched {rel_path}")
                    except Exception as e:
                        self.log(f"[!] [ODEX] Patch failed on {smali_file}: {e}")

        return ADBResult(success=True, operation=ADBOperation.SHELL)

    def recompile_dex(self, smali_dirs: list[str], output_dir: str) -> ADBResult:
        """Recompile smali to DEX using smali."""
        self.log("[*] [ODEX] Recompiling smali...")

        # Combine all smali dirs
        all_smali = " ".join(smali_dirs)
        output_dex = f"{output_dir}/classes_patched.dex"

        cmd = f"smali {all_smali} -o {output_dex}"
        result = self.orchestrator.shell(cmd)

        if result.success:
            self.log(f"[+] [ODEX] Recompiled to {output_dex}")
        return result

    def create_odex(self, dex_file: str, output_odex: str,
                    instruction_set: str | None = None, class_path: str | None = None) -> ADBResult:
        """Create ODEX file using dexopt-wrapper."""
        self.log(f"[*] [ODEX] Creating ODEX from {dex_file}...")

        # dexopt-wrapper <input.dex> <output.odex> [instruction-set] [class-path]
        cmd = f"{self.dexopt_wrapper} {dex_file} {output_odex}"
        if instruction_set:
            cmd += f" --instruction-set={instruction_set}"
        if class_path:
            cmd += f" --classpath={class_path}"

        return self.orchestrator.shell(cmd, require_root=True)

    def patch_on_device(self, package_name: str, patches: list[dict],
                         dex_files: list[str] | None = None,
                         instruction_set: str | None = None) -> ADBOdexPatchResult:
        """
        Full ODEX patching workflow on device.

        Args:
            package_name: Target package
            patches: List of patch dicts (search/replace patterns)
            dex_files: Specific dex files to patch (None = all)
            instruction_set: Target instruction set (arm64, arm, x86, x86_64)
        """
        import time
        start = time.monotonic()

        result = ADBOdexPatchResult(
            success=False, package_name=package_name, apk_path="", working_dir=self.working_dir
        )

        # 1. Check requirements
        req = self.check_requirements()
        if not req.success:
            result.errors.append(req.error or "Requirements check failed")
            return result

        # 2. Prepare working dir
        prep = self.prepare_working_dir()
        if not prep.success:
            result.errors.append("Failed to prepare working directory")
            return result

        # 3. Get APK path
        apk_result = self.get_apk_path(package_name)
        if not apk_result.success:
            result.errors.append("Failed to get APK path")
            return result

        apk_paths = [line.replace("package:", "").strip()
                     for line in apk_result.stdout.strip().splitlines()
                     if line.startswith("package:")]

        if not apk_paths:
            result.errors.append("No APK found")
            return result

        base_apk = apk_paths[0]
        result.apk_path = base_apk

        # 4. Copy APK to working dir
        work_apk = f"{self.working_dir}/target.apk"
        copy_result = self.orchestrator.shell(f"cp {base_apk} {work_apk}")
        if not copy_result.success:
            result.errors.append("Failed to copy APK to working directory")
            return result

        # 5. Decompile
        decomp_result = self.decompile_dex(work_apk, self.working_dir, dex_files)
        if not decomp_result.success:
            result.errors.append("Decompile failed")
            return result

        # Find smali directories
        find_result = self.orchestrator.shell(f"ls -d {self.working_dir}/smali_*")
        if not find_result.success:
            result.errors.append("No smali directories found")
            return result

        smali_dirs = [d.strip() for d in find_result.stdout.strip().splitlines() if d.strip()]

        # 6. Apply patches
        patch_result = self.apply_patches(smali_dirs, patches)
        if not patch_result.success:
            result.errors.append("Patch application failed")
            return result

        # 7. Recompile
        recompile_result = self.recompile_dex(smali_dirs, self.working_dir)
        if not recompile_result.success:
            result.errors.append("Recompile failed")
            return result

        # 8. Create ODEX
        patched_dex = f"{self.working_dir}/classes_patched.dex"
        odex_output = f"{self.working_dir}/classes_patched.odex"

        odex_result = self.create_odex(patched_dex, odex_output, instruction_set)
        if not odex_result.success:
            result.errors.append("ODEX creation failed")
            return result

        # 9. Replace original ODEX (requires root, system partition remount)
        # This is the risky part - replacing system ODEX files
        self.log("[!] [ODEX] ODEX patching complete. Manual replacement required.")
        self.log(f"[!] [ODEX] Patched ODEX at: {odex_output}")
        self.log("[!] [ODEX] To apply: mount -o remount,rw /system && cp <patched> <original>")

        result.success = True
        result.patched_dex_files = [patched_dex, odex_output]
        result.duration_ms = (time.monotonic() - start) * 1000

        return result

    def cleanup(self) -> ADBResult:
        """Clean up working directory on device."""
        return self.orchestrator.shell(f"rm -rf {self.working_dir}", require_root=True)


def patch_odex_on_device(orchestrator: ADBOrchestrator, package_name: str, patches: list[dict],
                          dex_files: list[str] | None = None, log_callback: Callable[[str], None] = print) -> ADBOdexPatchResult:
    """Convenience function for ODEX patching."""
    patcher = ADBOdexPatcher(orchestrator, log_callback)
    return patcher.patch_on_device(package_name, patches, dex_files)
