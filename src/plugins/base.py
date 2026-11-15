"""
Plugin Base Classes — interfaces for detector, patcher, and UI plugins.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PluginInfo:
    """Plugin metadata."""
    name: str
    version: str
    author: str = ""
    description: str = ""
    license: str = "MIT"
    min_lp_version: str = "1.0.0"
    dependencies: list[str] = field(default_factory=list)
    entry_point: str = "plugin.py"


class DetectorPlugin(ABC):
    """
    Base class for detector plugins.

    Detectors analyze APKs and produce findings.
    They can add new detection types or enhance existing ones.
    """

    @property
    @abstractmethod
    def detector_name(self) -> str:
        """Unique detector name."""
        pass

    @property
    @abstractmethod
    def detector_type(self) -> str:
        """Type of detection: 'license', 'ads', 'iap', 'root', 'packer', 'custom'."""
        pass

    @property
    def priority(self) -> int:
        """Execution priority (higher runs first)."""
        return 50

    @property
    def requires_dex_index(self) -> bool:
        """Whether detector needs DexIndex (structural analysis)."""
        return True

    @abstractmethod
    def analyze(self, apk, dex_index, findings: list[dict], available_patches: list[str]) -> None:
        """
        Analyze APK and add findings.

        Args:
            apk: androguard APK object
            dex_index: DexIndex for structural analysis
            findings: List to append findings to
            available_patches: List to append available patch actions
        """
        pass

    def get_finding_template(self) -> dict:
        """Default finding template."""
        return {
            "type": self.detector_type,
            "color": "yellow",
            "title": "",
            "description": "",
            "details": [],
            "action": None,
        }


class PatcherPlugin(ABC):
    """
    Base class for patcher plugins.

    Patchers apply modifications to decompiled APKs.
    They implement specific patch modes.
    """

    @property
    @abstractmethod
    def patcher_name(self) -> str:
        """Unique patcher name (e.g., 'license_extreme', 'ads_custom')."""
        pass

    @property
    @abstractmethod
    def patcher_modes(self) -> list[str]:
        """Mode strings this patcher handles (e.g., ['license:custom'])."""
        pass

    @property
    def requires_resources(self) -> bool:
        """Whether patcher needs resources (manifest, XML)."""
        return False

    @property
    def parallel_safe(self) -> bool:
        """Whether patcher can run in parallel with others."""
        return True

    @abstractmethod
    def patch(self, decompiled_path: str, log_callback: Callable[[str], None],
              file_cache=None, **kwargs) -> int:
        """
        Apply patches to decompiled APK.

        Args:
            decompiled_path: Path to decompiled APK
            log_callback: Function to call for logging
            file_cache: FileContentCache for efficient I/O
            **kwargs: Additional mode-specific arguments

        Returns:
            Number of files patched
        """
        pass

    def get_supported_modes(self) -> dict[str, str]:
        """Map mode strings to patcher name for registry."""
        return dict.fromkeys(self.patcher_modes, self.patcher_name)


class CustomPatchPlugin(ABC):
    """
    Base class for custom patch format plugins.

    Adds support for new patch file formats.
    """

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Format name (e.g., 'lpzip', 'hexpatch', 'mobimart')."""
        pass

    @property
    @abstractmethod
    def file_extensions(self) -> list[str]:
        """Supported file extensions (e.g., ['.lpzip', '.txt'])."""
        pass

    @abstractmethod
    def parse(self, file_path: str) -> list[dict]:
        """
        Parse patch file and return instructions.

        Returns:
            List of instruction dicts with target_file, operations
        """
        pass

    @abstractmethod
    def apply(self, instructions: list[dict], decompiled_path: str,
              log_callback: Callable[[str], None], file_cache=None) -> int:
        """
        Apply parsed instructions.

        Returns:
            Number of files patched
        """
        pass


class UIPanelPlugin(ABC):
    """
    Base class for UI panel plugins.

    Adds new panels to the LP-PC Suite GUI.
    """

    @property
    @abstractmethod
    def panel_name(self) -> str:
        """Unique panel name."""
        pass

    @property
    @abstractmethod
    def panel_title(self) -> str:
        """Display title."""
        pass

    @property
    def panel_icon(self) -> str:
        """Icon (emoji or path)."""
        return "🔧"

    @property
    def panel_category(self) -> str:
        """Category: 'tools', 'analysis', 'patches', 'settings'."""
        return "tools"

    @abstractmethod
    def create_panel(self, parent, controller) -> Any:
        """
        Create and return the panel widget.

        Args:
            parent: Parent widget
            controller: AppController instance

        Returns:
            QWidget instance
        """
        pass

    def get_menu_action(self) -> dict | None:
        """Optional menu action for toolbox."""
        return None


class IntegrationPlugin(ABC):
    """
    Base class for integration plugins.

    Connects LP-PC Suite with external services.
    """

    @property
    @abstractmethod
    def integration_name(self) -> str:
        """Integration name (e.g., 'github', 'telegram', 'discord')."""
        pass

    @property
    def config_schema(self) -> dict:
        """Configuration schema for this integration."""
        return {}

    @abstractmethod
    def initialize(self, config: dict) -> bool:
        """Initialize integration with config."""
        pass

    @abstractmethod
    def send_notification(self, title: str, message: str, **kwargs) -> bool:
        """Send notification via integration."""
        pass

    def on_patch_complete(self, apk_path: str, modes: list[str], success: bool, output: str) -> None:
        """Called when patch pipeline completes."""
        return None

    def on_analysis_complete(self, apk_path: str, findings: list[dict]) -> None:
        """Called when analysis completes."""
        return None


# Plugin decorators for easy registration
def detector_plugin(cls):
    """Decorator to register a detector plugin class."""
    cls._is_detector_plugin = True
    return cls


def patcher_plugin(cls):
    """Decorator to register a patcher plugin class."""
    cls._is_patcher_plugin = True
    return cls


def custom_patch_plugin(cls):
    """Decorator to register a custom patch plugin class."""
    cls._is_custom_patch_plugin = True
    return cls


def ui_panel_plugin(cls):
    """Decorator to register a UI panel plugin class."""
    cls._is_ui_panel_plugin = True
    return cls


def integration_plugin(cls):
    """Decorator to register an integration plugin class."""
    cls._is_integration_plugin = True
    return cls


# Example plugin implementations (for reference)
"""
# Example: New packer detector
@detector_plugin
class MyPackerDetector(DetectorPlugin):
    detector_name = "my_packer"
    detector_type = "packer"
    priority = 60

    def analyze(self, apk, dex_index, findings, available_patches):
        # Check for custom packer signature
        if "com.mypacker.Protector" in str(dex_index.classes):
            findings.append({
                **self.get_finding_template(),
                "color": "red",
                "title": "Packed: MyPacker",
                "description": "App protected by MyPacker (hard packer)",
                "details": ["Class: com.mypacker.Protector"],
                "action": None,
            })
            # Mark as unpatchable
            available_patches.append("my_packer")

# Example: Custom license patcher
@patcher_plugin
class MyLicensePatcher(PatcherPlugin):
    patcher_name = "license_custom"
    patcher_modes = ["license:custom"]

    def patch(self, decompiled_path, log_callback, file_cache=None, **kwargs):
        # Custom license patching logic
        from core.smali_utils import get_all_smali_files
        import re

        patched = 0
        for smali_file in get_all_smali_files(decompiled_path):
            content = file_cache.read(smali_file) if file_cache else open(smali_file).read()
            # Custom patching...
            if modified:
                if file_cache:
                    file_cache.write(smali_file, content)
                else:
                    open(smali_file, 'w').write(content)
                patched += 1
        return patched

# Example: Custom patch format
@custom_patch_plugin
class MyPatchFormat(CustomPatchPlugin):
    format_name = "myformat"
    file_extensions = [".mypatch"]

    def parse(self, file_path):
        # Parse custom format
        return []

    def apply(self, instructions, decompiled_path, log_callback, file_cache=None):
        return 0

# Example: UI panel
@ui_panel_plugin
class MyPanel(UIPanelPlugin):
    panel_name = "my_panel"
    panel_title = "My Tool"
    panel_category = "tools"

    def create_panel(self, parent, controller):
        from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("My Custom Panel"))
        return panel

    def get_menu_action(self):
        return {"name": "My Tool", "callback": lambda: print("My tool!")}

# Example: Integration
@integration_plugin
class TelegramIntegration(IntegrationPlugin):
    integration_name = "telegram"

    def initialize(self, config):
        self.bot_token = config.get("bot_token")
        self.chat_id = config.get("chat_id")
        return bool(self.bot_token and self.chat_id)

    def send_notification(self, title, message, **kwargs):
        # Send via Telegram API
        return True

    def on_patch_complete(self, apk_path, modes, success, output):
        if success:
            self.send_notification("Patch Complete", f"{apk_path} patched with {modes}")
"""


__all__ = [
    "PluginInfo",
    "DetectorPlugin",
    "PatcherPlugin",
    "CustomPatchPlugin",
    "UIPanelPlugin",
    "IntegrationPlugin",
    "detector_plugin",
    "patcher_plugin",
    "custom_patch_plugin",
    "ui_panel_plugin",
    "integration_plugin",
]
