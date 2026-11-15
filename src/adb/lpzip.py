"""
ADB lpzip Importer — import custom patch archives (LP mobile feature).
"""
from __future__ import annotations

import logging
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .orchestrator import ADBOperation, ADBOrchestrator, ADBResult
from .shell import ADBShell
from .transfer import ADBFileTransfer, ADBTransferResult

logger = logging.getLogger(__name__)


@dataclass
class ADBLpzipResult:
    """Result of lpzip import."""
    success: bool
    patches_imported: list[dict] = field(default_factory=list)
    patch_dir: str = "/data/local/lp/patches"
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def __bool__(self) -> bool:
        return self.success


class ADBLpzipImporter:
    """
    lpzip Importer — imports Lucky Patcher custom patch archives (LP mobile feature).

    This implements the LP mobile "lpzip" feature:
    1. lpzip is a ZIP archive containing custom patches (.txt/.lpzip files)
    2. Import extracts patches to device patch directory
    3. Patches can then be applied via BootList or manual selection

    lpzip format:
    - mypatches.lpzip (ZIP file)
      - patches/
        - patch1.txt
        - patch2.lpzip
      - metadata.json (optional)

    LP-PC Suite can:
    - Create lpzip from local patches
    - Push lpzip to device
    - Extract and register patches on device
    """

    def __init__(self, orchestrator: ADBOrchestrator, log_callback: Callable[[str], None] = print):
        self.orchestrator = orchestrator
        self.log = log_callback
        self.device = orchestrator.device
        self.shell = ADBShell(self.device.serial, self.orchestrator.adb_path)
        self.patch_dir = "/data/local/lp/patches"
        self.working_dir = "/data/local/tmp/lp_lpzip"

    def check_requirements(self) -> ADBResult:
        """Check if lpzip import is possible."""
        self.log("[*] [Lpzip] Checking requirements...")

        # Need root for patch directory
        root_result = self.orchestrator.check_root_access()
        if not root_result.success:
            self.log("[i] [Lpzip] Root not available, using user-writable directory")
            self.patch_dir = "/sdcard/lp_patches"

        self.log("[*] [Lpzip] Requirements OK")
        return ADBResult(success=True, operation=ADBOperation.SHELL)

    def prepare_dirs(self) -> ADBResult:
        """Create patch and working directories."""
        self.orchestrator.shell(f"mkdir -p {self.patch_dir}", require_root=True)
        self.orchestrator.shell(f"mkdir -p {self.working_dir}", require_root=True)
        return ADBResult(success=True, operation=ADBOperation.SHELL)

    def create_lpzip(self, patch_files: list[str], output_path: str,
                     metadata: dict | None = None) -> bool:
        """
        Create lpzip archive from local patch files.

        Args:
            patch_files: List of local patch file paths (.txt, .lpzip)
            output_path: Output lpzip file path
            metadata: Optional metadata dict

        Returns:
            True if successful
        """
        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Add patch files
                for patch_file in patch_files:
                    patch_path = Path(patch_file)
                    if patch_path.exists():
                        arcname = f"patches/{patch_path.name}"
                        zf.write(patch_path, arcname)
                        self.log(f"[+] [Lpzip] Added {patch_path.name}")

                # Add metadata
                if metadata:
                    import json
                    metadata_json = json.dumps(metadata, indent=2)
                    zf.writestr("metadata.json", metadata_json)
                else:
                    # Default metadata
                    default_meta = {
                        "name": "LP-PC Suite Custom Patches",
                        "version": "1.0",
                        "created_by": "LP-PC Suite ADB Orchestrator",
                        "patch_count": len(patch_files)
                    }
                    import json
                    zf.writestr("metadata.json", json.dumps(default_meta, indent=2))

            self.log(f"[+] [Lpzip] Created {output_path}")
            return True
        except Exception as e:
            self.log(f"[!] [Lpzip] Create failed: {e}")
            return False

    def parse_lpzip(self, lpzip_path: str) -> dict:
        """Parse lpzip archive and return metadata + patch list."""
        result: dict = {"patches": [], "metadata": {}}

        try:
            with zipfile.ZipFile(lpzip_path, 'r') as zf:
                for name in zf.namelist():
                    if name.startswith("patches/"):
                        result["patches"].append(name)
                    elif name == "metadata.json":
                        import json
                        result["metadata"] = json.loads(zf.read(name).decode('utf-8'))
        except Exception as e:
            self.log(f"[!] [Lpzip] Parse failed: {e}")

        return result

    def push_lpzip(self, local_lpzip_path: str) -> ADBTransferResult:
        """Push lpzip archive to device."""
        remote_path = f"{self.working_dir}/import.lpzip"
        transfer = ADBFileTransfer(self.device.serial, self.orchestrator.adb_path)
        return transfer.push(local_lpzip_path, remote_path)

    def extract_on_device(self, remote_lpzip_path: str | None = None) -> ADBResult:
        """Extract lpzip on device."""
        remote_lpzip_path = remote_lpzip_path or f"{self.working_dir}/import.lpzip"

        self.log(f"[*] [Lpzip] Extracting {remote_lpzip_path}...")

        # Use unzip on device
        result = self.orchestrator.shell(
            f"cd {self.patch_dir} && unzip -o {remote_lpzip_path} 'patches/*'",
            require_root=True
        )

        if result.success:
            self.log("[+] [Lpzip] Extracted patches to device")
        else:
            self.log(f"[!] [Lpzip] Extract failed: {result.error}")

        return result

    def list_device_patches(self) -> ADBResult:
        """List patches on device."""
        return self.orchestrator.shell(f"ls {self.patch_dir}/patches/ 2>/dev/null || ls {self.patch_dir}/")

    def register_patches(self) -> ADBResult:
        """Register patches with LP (create index)."""
        # LP reads patches from /data/local/lp/patches/
        # Registration is just ensuring they're in the right place
        list_result = self.list_device_patches()
        if list_result.success:
            patches = [p.strip() for p in list_result.stdout.strip().splitlines() if p.strip()]
            self.log(f"[+] [Lpzip] {len(patches)} patches available on device")
            return ADBResult(success=True, operation=ADBOperation.SHELL, stdout="\n".join(patches))
        return list_result

    def import_lpzip(self, local_lpzip_path: str) -> ADBLpzipResult:
        """
        Import lpzip archive to device.

        Full workflow:
        1. Parse lpzip locally
        2. Push to device
        3. Extract on device
        4. Register patches
        """
        import time
        start = time.monotonic()

        result = ADBLpzipResult(success=False, patch_dir=self.patch_dir)

        # 1. Parse locally
        parsed = self.parse_lpzip(local_lpzip_path)
        if not parsed["patches"]:
            result.errors.append("No patches found in lpzip")
            return result

        self.log(f"[*] [Lpzip] Found {len(parsed['patches'])} patches in archive")

        # 2. Check requirements
        req = self.check_requirements()
        if not req.success:
            result.errors.append(req.error)
            return result

        # 3. Prepare dirs
        self.prepare_dirs()

        # 4. Push lpzip
        push_result = self.push_lpzip(local_lpzip_path)
        if not push_result.success:
            result.errors.append(push_result.error or "Push failed")
            return result

        # 5. Extract on device
        extract_result = self.extract_on_device()
        if not extract_result.success:
            result.errors.append(extract_result.error or "Extract failed")
            return result

        # 6. Register
        register_result = self.register_patches()
        if not register_result.success:
            result.errors.append("Registration failed")
            return result

        # Success
        result.success = True
        result.patches_imported = [{"name": p, "path": f"{self.patch_dir}/{p}"} for p in parsed["patches"]]
        result.duration_ms = (time.monotonic() - start) * 1000

        self.log(f"[+] [Lpzip] Import complete: {len(result.patches_imported)} patches")

        return result

    def import_multiple(self, lpzip_paths: list[str]) -> list[ADBLpzipResult]:
        """Import multiple lpzip archives."""
        return [self.import_lpzip(path) for path in lpzip_paths]

    def remove_patches(self, patch_names: list[str] | None = None) -> ADBResult:
        """Remove patches from device."""
        if patch_names:
            for name in patch_names:
                self.orchestrator.shell(f"rm -f {self.patch_dir}/{name}", require_root=True)
        else:
            self.orchestrator.shell(f"rm -rf {self.patch_dir}/*", require_root=True)

        return ADBResult(success=True, operation=ADBOperation.SHELL)

    def create_patch_index(self) -> ADBResult:
        """Create patch index file for LP."""
        index_path = f"{self.patch_dir}/index.json"

        list_result = self.list_device_patches()
        if not list_result.success:
            return list_result

        patches = [p.strip() for p in list_result.stdout.strip().splitlines() if p.strip()]

        import json
        index = {
            "version": 1,
            "patches": [
                {"name": p, "path": f"{self.patch_dir}/{p}", "enabled": True}
                for p in patches
            ]
        }

        result = self.orchestrator.shell(
            f"cat > {index_path} << 'EOF'\n{json.dumps(index, indent=2)}\nEOF",
            require_root=True
        )

        if result.success:
            self.log(f"[+] [Lpzip] Created patch index at {index_path}")

        return result


def import_lpzip(orchestrator: ADBOrchestrator, local_lpzip_path: str,
                  log_callback: Callable[[str], None] = print) -> ADBLpzipResult:
    """Convenience function for lpzip import."""
    importer = ADBLpzipImporter(orchestrator, log_callback)
    return importer.import_lpzip(local_lpzip_path)
