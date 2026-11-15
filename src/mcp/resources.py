"""
MCP Resources — file/data access for AI agents.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)


def register_resources(server):
    """Register all MCP resources with the server."""

    # Resource implementations

    def get_changelog() -> str:
        """Get CHANGELOG.md content."""
        try:
            with open("CHANGELOG.md", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading CHANGELOG: {e}"

    def get_research() -> str:
        """Get RESEARCH.md content."""
        try:
            with open("RESEARCH.md", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading RESEARCH: {e}"

    def get_know() -> str:
        """Get KNOW.md content."""
        try:
            with open("KNOW.md", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading KNOW: {e}"

    def get_config() -> str:
        """Get default.yaml config."""
        try:
            with open("config/default.yaml", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading config: {e}"

    def get_ads_blocklist() -> str:
        """Get AdsBlockList.txt content."""
        try:
            with open("assets/AdsBlockList.txt", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading AdsBlockList: {e}"

    def get_patch_history() -> str:
        """Get patch history."""
        try:
            with open("workspace/patch_history.json", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading patch history: {e}"

    def get_metrics() -> str:
        """Get metrics."""
        try:
            with open("workspace/metrics.json", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading metrics: {e}"

    def list_custom_patches() -> str:
        """List available custom patches."""
        try:
            patches_dir = os.path.expanduser("~/Documents/LP_PC_Suite/patches")
            if not os.path.exists(patches_dir):
                return "[]"

            patches = []
            for f in os.listdir(patches_dir):
                if f.endswith((".txt", ".lpzip")):
                    path = os.path.join(patches_dir, f)
                    stat = os.stat(path)
                    patches.append({
                        "name": f,
                        "path": path,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    })

            return json.dumps(patches, indent=2)
        except Exception as e:
            return f"Error listing patches: {e}"

    def get_version() -> str:
        """Get version info."""
        try:
            with open("version.json", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading version: {e}"

    def get_supported_modes() -> str:
        """Get list of supported patch modes."""
        from core.mode_registry import MODE_MAP, PARALLEL_GROUPS

        return json.dumps({
            "modes": MODE_MAP,
            "parallel_groups": PARALLEL_GROUPS,
        }, indent=2)

    # Register resources
    server.register_resource("file://changelog", get_changelog, {
        "name": "CHANGELOG.md",
        "description": "Project changelog",
        "mimeType": "text/markdown",
    })

    server.register_resource("file://research", get_research, {
        "name": "RESEARCH.md",
        "description": "Deep research on Lucky Patcher internals",
        "mimeType": "text/markdown",
    })

    server.register_resource("file://know", get_know, {
        "name": "KNOW.md",
        "description": "Knowledge base and implementation notes",
        "mimeType": "text/markdown",
    })

    server.register_resource("file://config", get_config, {
        "name": "default.yaml",
        "description": "Default configuration",
        "mimeType": "application/yaml",
    })

    server.register_resource("file://ads_blocklist", get_ads_blocklist, {
        "name": "AdsBlockList.txt",
        "description": "Lucky Patcher ad blocking patterns (LP format)",
        "mimeType": "text/plain",
    })

    server.register_resource("file://patch_history", get_patch_history, {
        "name": "patch_history.json",
        "description": "History of applied patches",
        "mimeType": "application/json",
    })

    server.register_resource("file://metrics", get_metrics, {
        "name": "metrics.json",
        "description": "Performance metrics",
        "mimeType": "application/json",
    })

    server.register_resource("file://custom_patches", list_custom_patches, {
        "name": "custom_patches",
        "description": "List of available custom patches",
        "mimeType": "application/json",
    })

    server.register_resource("file://version", get_version, {
        "name": "version.json",
        "description": "Version information",
        "mimeType": "application/json",
    })

    server.register_resource("file://supported_modes", get_supported_modes, {
        "name": "supported_modes",
        "description": "All supported patch modes and groups",
        "mimeType": "application/json",
    })


__all__ = ["register_resources"]
