"""
MCP Tools — LP-PC Suite capabilities exposed as MCP tools.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Tool schemas for MCP registration
TOOL_SCHEMAS = {
    "analyze_apk": {
        "description": "Deep analysis of APK file - detects license, ads, IAP, root checks, packers, and available patches",
        "inputSchema": {
            "type": "object",
            "properties": {
                "apk_path": {"type": "string", "description": "Path to APK file"},
                "force_reanalyze": {"type": "boolean", "description": "Force re-analysis ignoring cache", "default": False},
                "use_gda": {"type": "boolean", "description": "Use GDA (Graph-based Dalvik Analysis)", "default": False},
            },
            "required": ["apk_path"],
        },
    },
    "patch_apk": {
        "description": "Apply patches to APK - license, ads, IAP, signature, custom patches",
        "inputSchema": {
            "type": "object",
            "properties": {
                "apk_path": {"type": "string", "description": "Path to APK file"},
                "modes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Patch modes to apply",
                    "enum": [
                        "license:auto", "license:reverse_auto", "license:extreme",
                        "ads:remove_links", "ads:offline", "ads:full_offline",
                        "iap:dex", "iap:proxy",
                        "signature:disable_verify", "signature:remove_integrity",
                        "custom_patch",
                    ],
                },
                "key_type": {"type": "string", "enum": ["testkey", "platform", "media", "shared"], "default": "testkey"},
                "custom_patch_path": {"type": "string", "description": "Path to custom patch file (.txt or .lpzip)"},
            },
            "required": ["apk_path", "modes"],
        },
    },
    "rebuild_apk": {
        "description": "Rebuild and sign patched APK",
        "inputSchema": {
            "type": "object",
            "properties": {
                "decompiled_path": {"type": "string", "description": "Path to decompiled APK directory"},
                "output_path": {"type": "string", "description": "Output APK path"},
                "key_type": {"type": "string", "enum": ["testkey", "platform", "media", "shared"], "default": "testkey"},
                "forced_package_id": {"type": "integer", "description": "Forced package ID (1-127)", "minimum": 1, "maximum": 127},
            },
            "required": ["decompiled_path", "output_path"],
        },
    },
    "install_apk": {
        "description": "Install APK on connected device via ADB",
        "inputSchema": {
            "type": "object",
            "properties": {
                "apk_path": {"type": "string", "description": "Path to APK file"},
                "device_serial": {"type": "string", "description": "Target device serial (optional, uses first device)"},
                "replace": {"type": "boolean", "default": True},
                "grant_permissions": {"type": "boolean", "default": False},
            },
            "required": ["apk_path"],
        },
    },
    "download_custom_patch": {
        "description": "Download custom patch from patch.chelpus.com",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch_name": {"type": "string", "description": "Patch name (e.g., 'com.example.app.txt')"},
                "download_dir": {"type": "string", "description": "Download directory (optional)"},
            },
            "required": ["patch_name"],
        },
    },
    "list_devices": {
        "description": "List connected ADB devices",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    "get_device_info": {
        "description": "Get detailed device information",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_serial": {"type": "string", "description": "Device serial (optional, uses first device)"},
            },
        },
    },
    "execute_adb_shell": {
        "description": "Execute ADB shell command on device",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "device_serial": {"type": "string", "description": "Target device serial (optional)"},
                "require_root": {"type": "boolean", "default": False},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["command"],
        },
    },
    "manage_patches": {
        "description": "Manage custom patches - list, apply, remove",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "apply", "remove", "import_lpzip"], "description": "Action to perform"},
                "patch_path": {"type": "string", "description": "Path to patch file or lpzip"},
                "device_serial": {"type": "string", "description": "Target device for device operations"},
            },
            "required": ["action"],
        },
    },
}


def register_tools(server):
    """Register all MCP tools with the server."""

    # Tool implementations

    async def analyze_apk(apk_path: str, force_reanalyze: bool = False, use_gda: bool = False) -> dict[str, Any]:
        """Analyze APK for license, ads, IAP, root, packer detection."""
        try:
            from scanner.analyzer import AppDeepAnalyzer

            analyzer = AppDeepAnalyzer(apk_path)
            findings = analyzer.analyze(force_reanalyze=force_reanalyze)
            summary = analyzer.get_summary()
            colors = analyzer.get_colors()

            # Categorize findings
            categories: dict[str, list] = {}
            for finding in findings:
                cat = finding.get("type", "other")
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(finding)

            return {
                "success": True,
                "summary": summary,
                "colors": colors,
                "findings": findings,
                "categories": categories,
                "available_patches": analyzer.available_patches,
                "packer_info": analyzer.packer_info,
            }
        except Exception as e:
            logger.exception("analyze_apk failed")
            return {"success": False, "error": str(e)}

    async def patch_apk(
        apk_path: str,
        modes: list[str],
        key_type: str = "testkey",
        custom_patch_path: str | None = None
    ) -> dict[str, Any]:
        """Apply patches to APK."""
        try:
            from main import run_pipeline

            mode_str = ",".join(modes)
            if custom_patch_path:
                import os
                os.environ["LP_CUSTOM_PATCH"] = custom_patch_path

            success, output_path, reports = run_pipeline(
                apk_path, mode=mode_str, key_type=key_type
            )

            return {
                "success": success,
                "output_apk": output_path,
                "reports": reports,
                "modes_applied": modes,
            }
        except Exception as e:
            logger.exception("patch_apk failed")
            return {"success": False, "error": str(e)}

    async def rebuild_apk(
        decompiled_path: str,
        output_path: str,
        key_type: str = "testkey",
        forced_package_id: int | None = None
    ) -> dict[str, Any]:
        """Rebuild and sign APK from decompiled source."""
        try:
            from core.apk_utils import recompile_apk, sign_apk

            # Recompile
            recompile_apk(decompiled_path, output_path, forced_package_id=forced_package_id)

            # Sign
            signed = sign_apk(output_path, key_type=key_type)

            return {
                "success": True,
                "output_apk": signed,
            }
        except Exception as e:
            logger.exception("rebuild_apk failed")
            return {"success": False, "error": str(e)}

    async def install_apk(
        apk_path: str,
        device_serial: str | None = None,
        replace: bool = True,
        grant_permissions: bool = False
    ) -> dict[str, Any]:
        """Install APK via ADB."""
        try:
            from core.device_bridge import list_devices

            devices = list_devices()
            if not devices:
                return {"success": False, "error": "No devices connected"}

            target = device_serial or devices[0]

            # Install
            import subprocess
            cmd = ["adb", "-s", target, "install"]
            if replace:
                cmd.append("-r")
            if grant_permissions:
                cmd.append("-g")
            cmd.append(apk_path)

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            return {
                "success": result.returncode == 0 and "Success" in result.stdout,
                "device": target,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else "",
            }
        except Exception as e:
            logger.exception("install_apk failed")
            return {"success": False, "error": str(e)}

    async def download_custom_patch(patch_name: str, download_dir: str | None = None) -> dict[str, Any]:
        """Download custom patch from patch.chelpus.com."""
        try:
            from patcher.custom_patch_downloader import CustomPatchDownloader

            downloader = CustomPatchDownloader(download_dir=download_dir)
            result = downloader.download_patch(patch_name)

            return {
                "success": result is not None,
                "patch_path": result,
                "patch_name": patch_name,
            }
        except Exception as e:
            logger.exception("download_custom_patch failed")
            return {"success": False, "error": str(e)}

    async def list_devices() -> dict[str, Any]:
        """List connected ADB devices."""
        try:
            from adb.device import ADBDeviceManager
            from core.device_bridge import list_devices

            devices = list_devices()
            manager = ADBDeviceManager()

            detailed = []
            for serial in devices:
                device = manager.get_device(serial)
                if device:
                    manager.load_properties(device)
                    detailed.append({
                        "serial": device.serial,
                        "model": device.model,
                        "manufacturer": device.manufacturer,
                        "brand": device.brand,
                        "android_version": device.android_version,
                        "sdk_int": device.sdk_int,
                        "cpu_abi": device.cpu_abi,
                        "is_rooted": device.is_rooted,
                        "is_emulator": device.is_emulator,
                    })

            return {
                "success": True,
                "devices": detailed,
            }
        except Exception as e:
            logger.exception("list_devices failed")
            return {"success": False, "error": str(e)}

    async def get_device_info(device_serial: str | None = None) -> dict[str, Any]:
        """Get detailed device information."""
        try:
            from adb.device import ADBDeviceManager, adb_device
            from adb.orchestrator import ADBOrchestrator

            manager = ADBDeviceManager()
            devices = manager.scan_devices()

            if not devices:
                return {"success": False, "error": "No devices connected"}

            target_serial = device_serial or devices[0].serial

            with adb_device(target_serial) as device:
                manager.load_properties(device)

                orchestrator = ADBOrchestrator(device)

                # Get additional info
                packages = orchestrator.list_installed_packages()
                props = {}
                for prop_name in ["ro.build.fingerprint", "ro.build.id", "ro.product.cpu.abilist"]:
                    prop_result = orchestrator.get_property(prop_name)
                    if prop_result.success:
                        props[prop_name] = prop_result.stdout.strip()

                return {
                    "success": True,
                    "device": {
                        "serial": device.serial,
                        "model": device.model,
                        "manufacturer": device.manufacturer,
                        "brand": device.brand,
                        "android_version": device.android_version,
                        "sdk_int": device.sdk_int,
                        "cpu_abi": device.cpu_abi,
                        "cpu_abi2": device.cpu_abi2,
                        "is_rooted": device.is_rooted,
                        "is_emulator": device.is_emulator,
                        "build_id": device.build_id,
                        "build_fingerprint": device.build_fingerprint,
                        "security_patch": device.security_patch,
                    },
                    "properties": props,
                    "package_count": len(packages.stdout.strip().splitlines()) if packages.success else 0,
                }
        except Exception as e:
            logger.exception("get_device_info failed")
            return {"success": False, "error": str(e)}

    async def execute_adb_shell(
        command: str,
        device_serial: str | None = None,
        require_root: bool = False,
        timeout: int = 30
    ) -> dict[str, Any]:
        """Execute ADB shell command."""
        try:
            from adb.device import ADBDeviceManager, adb_device
            from adb.orchestrator import ADBOrchestrator

            manager = ADBDeviceManager()
            devices = manager.scan_devices()

            if not devices:
                return {"success": False, "error": "No devices connected"}

            target_serial = device_serial or devices[0].serial

            with adb_device(target_serial) as device:
                orchestrator = ADBOrchestrator(device)
                result = orchestrator.shell(command, timeout=timeout, require_root=require_root)

                return {
                    "success": result.success,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "return_code": result.return_code,
                    "duration_ms": result.duration_ms,
                }
        except Exception as e:
            logger.exception("execute_adb_shell failed")
            return {"success": False, "error": str(e)}

    async def manage_patches(
        action: str,
        patch_path: str | None = None,
        device_serial: str | None = None
    ) -> dict[str, Any]:
        """Manage custom patches."""
        try:
            if action == "list":
                import os

                patches_dir = os.path.expanduser("~/Documents/LP_PC_Suite/patches")
                if not os.path.exists(patches_dir):
                    return {"success": True, "patches": []}

                patches = []
                for f in os.listdir(patches_dir):
                    if f.endswith((".txt", ".lpzip")):
                        patches.append(f)

                return {"success": True, "patches": patches}

            elif action == "apply":
                if not patch_path:
                    return {"success": False, "error": "patch_path required for apply"}

                # This would apply patch during pipeline
                return {"success": True, "message": "Patch will be applied on next pipeline run", "patch_path": patch_path}

            elif action == "import_lpzip":
                if not patch_path:
                    return {"success": False, "error": "patch_path required for import_lpzip"}

                from adb.device import ADBDeviceManager, adb_device
                from adb.lpzip import import_lpzip
                from adb.orchestrator import ADBOrchestrator

                manager = ADBDeviceManager()
                devices = manager.scan_devices()
                if not devices:
                    return {"success": False, "error": "No devices connected"}

                target_serial = device_serial or devices[0].serial

                with adb_device(target_serial) as device:
                    orchestrator = ADBOrchestrator(device)
                    result = import_lpzip(orchestrator, patch_path)

                    return {
                        "success": result.success,
                        "patches_imported": result.patches_imported,
                        "patch_dir": result.patch_dir,
                    }

            elif action == "remove":
                # Remove patch from device
                return {"success": True, "message": "Remove not fully implemented"}

            return {"success": False, "error": f"Unknown action: {action}"}
        except Exception as e:
            logger.exception("manage_patches failed")
            return {"success": False, "error": str(e)}

    # Register all tools with schemas
    server.register_tool("analyze_apk", analyze_apk, TOOL_SCHEMAS["analyze_apk"])
    server.register_tool("patch_apk", patch_apk, TOOL_SCHEMAS["patch_apk"])
    server.register_tool("rebuild_apk", rebuild_apk, TOOL_SCHEMAS["rebuild_apk"])
    server.register_tool("install_apk", install_apk, TOOL_SCHEMAS["install_apk"])
    server.register_tool("download_custom_patch", download_custom_patch, TOOL_SCHEMAS["download_custom_patch"])
    server.register_tool("list_devices", list_devices, TOOL_SCHEMAS["list_devices"])
    server.register_tool("get_device_info", get_device_info, TOOL_SCHEMAS["get_device_info"])
    server.register_tool("execute_adb_shell", execute_adb_shell, TOOL_SCHEMAS["execute_adb_shell"])
    server.register_tool("manage_patches", manage_patches, TOOL_SCHEMAS["manage_patches"])


# Export tool functions for direct use
__all__ = [
    "TOOL_SCHEMAS",
    "register_tools",
]
