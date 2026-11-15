"""
MCP Prompts — reusable prompt templates for AI agents.
"""
from __future__ import annotations


def register_prompts(server):
    """Register all MCP prompts with the server."""

    # Prompt implementations

    def analyze_apk_prompt(apk_path: str, focus: str = "all") -> list[dict[str, str]]:
        """Prompt for analyzing an APK."""
        return [
            {
                "role": "system",
                "content": "You are an expert Android reverse engineer analyzing APKs with LP-PC Suite."
            },
            {
                "role": "user",
                "content": f"""Analyze the APK at {apk_path}.

Focus: {focus}

Please:
1. Call analyze_apk tool with the APK path
2. Interpret the findings for license verification, ads, IAP, root detection, and packers
3. Recommend appropriate patch modes based on detected features
4. Note any packer warnings (PairIP, 360, Tencent) that may prevent patching
5. Provide a summary of available patches and their likelihood of success

Return a structured analysis report."""
            }
        ]

    def patch_apk_prompt(apk_path: str, modes: list[str], key_type: str = "testkey") -> list[dict[str, str]]:
        """Prompt for patching an APK."""
        return [
            {
                "role": "system",
                "content": "You are an expert Android patcher using LP-PC Suite."
            },
            {
                "role": "user",
                "content": f"""Patch the APK at {apk_path} with the following modes:
{', '.join(modes)}

Key type: {key_type}

Please:
1. Call patch_apk tool with the specified parameters
2. Monitor the pipeline progress
3. Report the output APK path and any patches applied
4. If any patches fail, explain why and suggest alternatives
5. Verify the output APK is valid

Return the patching result with output APK path."""
            }
        ]

    def install_apk_prompt(apk_path: str, device_serial: str | None = None) -> list[dict[str, str]]:
        """Prompt for installing APK on device."""
        return [
            {
                "role": "system",
                "content": "You are an Android deployment expert using LP-PC Suite."
            },
            {
                "role": "user",
                "content": f"""Install the APK at {apk_path} on the target device.

Device serial: {device_serial or 'auto-detect'}

Please:
1. Call list_devices to see available devices
2. Call install_apk with the APK path and device serial
3. Verify installation success
4. If signature mismatch, handle uninstall/reinstall
5. Report installation status

Return installation result."""
            }
        ]

    def full_pipeline_prompt(apk_path: str, goal: str = "remove_license_and_ads") -> list[dict[str, str]]:
        """Prompt for full analysis + patch + install pipeline."""
        goals = {
            "remove_license_and_ads": ["license:auto", "ads:full_offline"],
            "remove_license": ["license:auto"],
            "remove_ads": ["ads:full_offline"],
            "iap_emulation": ["iap:dex"],
            "full_patch": ["license:extreme", "ads:full_offline", "iap:dex"],
            "custom": [],
        }

        modes = goals.get(goal, [])

        return [
            {
                "role": "system",
                "content": "You are an expert Android modder using LP-PC Suite for complete APK modification pipeline."
            },
            {
                "role": "user",
                "content": f"""Execute the complete pipeline for APK at {apk_path}.

Goal: {goal}
Patch modes: {', '.join(modes) if modes else 'custom'}

Please execute this complete workflow:
1. ANALYZE: Call analyze_apk to detect features
2. RECOMMEND: Based on analysis, confirm or adjust patch modes
3. PATCH: Call patch_apk with recommended modes
4. REBUILD: Verify output APK is created
5. INSTALL: Call list_devices, then install_apk on target device
6. VERIFY: Confirm installation

If any step fails, explain why and suggest recovery.

Return complete pipeline report with all steps."""
            }
        ]

    def device_management_prompt(action: str, device_serial: str | None = None) -> list[dict[str, str]]:
        """Prompt for device management tasks."""
        actions = {
            "list": "List all connected devices with details",
            "info": f"Get detailed info for device {device_serial or 'first device'}",
            "shell": "Execute shell command (specify command in follow-up)",
            "install": "Install APK (specify APK path in follow-up)",
            "uninstall": "Uninstall package (specify package name in follow-up)",
        }

        return [
            {
                "role": "system",
                "content": "You are an ADB device management expert using LP-PC Suite."
            },
            {
                "role": "user",
                "content": f"""Device management task: {actions.get(action, action)}

Device: {device_serial or 'auto-detect'}

Please use the appropriate MCP tools to complete this task."""
            }
        ]

    def custom_patch_prompt(action: str, patch_name: str | None = None) -> list[dict[str, str]]:
        """Prompt for custom patch management."""
        return [
            {
                "role": "system",
                "content": "You are a custom patch expert for Lucky Patcher format patches."
            },
            {
                "role": "user",
                "content": f"""Custom patch management: {action}

Patch name: {patch_name or 'N/A'}

Available actions:
- list: List all available custom patches
- download: Download patch from patch.chelpus.com
- import_lpzip: Import lpzip archive to device
- apply: Apply patch during next pipeline run

Please use the manage_patches tool to perform this action."""
            }
        ]

    def troubleshoot_prompt(issue: str, apk_path: str | None = None, device_serial: str | None = None) -> list[dict[str, str]]:
        """Prompt for troubleshooting common issues."""
        return [
            {
                "role": "system",
                "content": "You are an expert troubleshooter for LP-PC Suite APK patching issues."
            },
            {
                "role": "user",
                "content": f"""Troubleshoot this issue: {issue}

APK: {apk_path or 'not specified'}
Device: {device_serial or 'not specified'}

Common issues and solutions:
1. "Packer detected" → Check packer type, may need hex patches or be unpatchable
2. "Signature mismatch" → Uninstall existing app, or use different key type
3. "No patches applied" → Check if APK has target features (license, ads, IAP)
4. "Install failed" → Check device connection, storage, signature
5. "Analysis failed" → Try force_reanalyze, check APK validity

Please:
1. Analyze the APK if path provided
2. Check device status if device provided
3. Run relevant diagnostic tools
4. Provide step-by-step solution

Return troubleshooting report with recommended actions."""
            }
        ]

    def adb_mobile_features_prompt(feature: str, device_serial: str | None = None) -> list[dict[str, str]]:
        """Prompt for ADB-based mobile features (ODEX, Patch to Android, etc.)."""
        features = {
            "odex_patch": "ODEX patching on device using baksmali/smali",
            "patch_to_android": "Patch to Android (services.jar modification)",
            "modded_play_store": "Install modified Google Play Store",
            "bootlist": "Deploy BootList script for auto-patching on boot",
            "widgets": "Deploy Lucky Patcher home screen widgets",
            "lpzip": "Import custom patch lpzip archive to device",
            "xposed": "Install Lucky Patcher Xposed/LSPosed module",
        }

        return [
            {
                "role": "system",
                "content": "You are an expert in Lucky Patcher mobile features ported to PC via ADB."
            },
            {
                "role": "user",
                "content": f"""Execute Lucky Patcher mobile feature via ADB: {features.get(feature, feature)}

Device: {device_serial or 'auto-detect'}

This requires:
- Root access on device
- Android 5.0+ (API 21+) for most features
- Xposed/LSPosed for Xposed module

Please:
1. Check device requirements (root, API level)
2. Execute the feature using appropriate ADB orchestrator
3. Report success/failure with details
4. Provide next steps (reboot, manual steps, etc.)

Return feature execution report."""
            }
        ]

    # Register prompts
    server.register_prompt("analyze_apk", analyze_apk_prompt, {
        "description": "Analyze APK and recommend patches",
        "arguments": [
            {"name": "apk_path", "description": "Path to APK file", "required": True},
            {"name": "focus", "description": "Analysis focus area", "required": False},
        ],
    })

    server.register_prompt("patch_apk", patch_apk_prompt, {
        "description": "Patch APK with specified modes",
        "arguments": [
            {"name": "apk_path", "description": "Path to APK file", "required": True},
            {"name": "modes", "description": "List of patch modes", "required": True},
            {"name": "key_type", "description": "Signing key type", "required": False},
        ],
    })

    server.register_prompt("install_apk", install_apk_prompt, {
        "description": "Install APK on device",
        "arguments": [
            {"name": "apk_path", "description": "Path to APK file", "required": True},
            {"name": "device_serial", "description": "Target device serial", "required": False},
        ],
    })

    server.register_prompt("full_pipeline", full_pipeline_prompt, {
        "description": "Complete analysis + patch + install pipeline",
        "arguments": [
            {"name": "apk_path", "description": "Path to APK file", "required": True},
            {"name": "goal", "description": "Patching goal preset", "required": False},
        ],
    })

    server.register_prompt("device_management", device_management_prompt, {
        "description": "Device management tasks",
        "arguments": [
            {"name": "action", "description": "Action to perform", "required": True},
            {"name": "device_serial", "description": "Target device serial", "required": False},
        ],
    })

    server.register_prompt("custom_patch", custom_patch_prompt, {
        "description": "Custom patch management",
        "arguments": [
            {"name": "action", "description": "Action to perform", "required": True},
            {"name": "patch_name", "description": "Patch name", "required": False},
        ],
    })

    server.register_prompt("troubleshoot", troubleshoot_prompt, {
        "description": "Troubleshoot patching issues",
        "arguments": [
            {"name": "issue", "description": "Issue description", "required": True},
            {"name": "apk_path", "description": "APK path (optional)", "required": False},
            {"name": "device_serial", "description": "Device serial (optional)", "required": False},
        ],
    })

    server.register_prompt("adb_mobile_features", adb_mobile_features_prompt, {
        "description": "Execute ADB-based mobile features",
        "arguments": [
            {"name": "feature", "description": "Feature to execute", "required": True},
            {"name": "device_serial", "description": "Target device serial", "required": False},
        ],
    })


__all__ = ["register_prompts"]
