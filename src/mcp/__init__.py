"""
MCP Server — Model Context Protocol server for AI agent integration.

Exposes LP-PC Suite capabilities via MCP protocol:
- analyze_apk: Deep analysis of APK (license, ads, IAP, root, packer detection)
- patch_apk: Apply patches (license, ads, IAP, signature, custom)
- rebuild_apk: Rebuild and sign patched APK
- install_apk: Install APK via ADB
- download_custom_patch: Download patch from patch.chelpus.com
- list_devices: List connected ADB devices
- get_device_info: Get device properties
- execute_adb_shell: Execute ADB shell command
- manage_patches: List/apply/remove custom patches

MCP Protocol:
- JSON-RPC 2.0 over stdio
- Tools: structured function calls
- Resources: file/data access
- Prompts: reusable prompt templates

Integration with AI agents (Claude, GPT, etc.) via MCP clients.
"""
from __future__ import annotations

from .prompts import register_prompts
from .resources import register_resources
from .server import MCPServer, MCPServerConfig, run_mcp_server
from .tools import TOOL_SCHEMAS, register_tools

__all__ = [
    "MCPServer",
    "MCPServerConfig",
    "run_mcp_server",
    "TOOL_SCHEMAS",
    "register_tools",
    "register_resources",
    "register_prompts",
]

__version__ = "1.0.0"
