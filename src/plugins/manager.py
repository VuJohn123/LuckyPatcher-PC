"""
Plugin Manager — dynamic loading and registration of plugins.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

from .base import (
    CustomPatchPlugin,
    DetectorPlugin,
    IntegrationPlugin,
    PatcherPlugin,
    PluginInfo,
    UIPanelPlugin,
)

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Registry for all plugin types."""

    def __init__(self):
        self.detectors: dict[str, DetectorPlugin] = {}
        self.patchers: dict[str, PatcherPlugin] = {}
        self.custom_patches: dict[str, CustomPatchPlugin] = {}
        self.ui_panels: dict[str, UIPanelPlugin] = {}
        self.integrations: dict[str, IntegrationPlugin] = {}
        self.plugin_infos: dict[str, PluginInfo] = {}

    def register_detector(self, name: str, detector: DetectorPlugin):
        self.detectors[name] = detector
        logger.info(f"Registered detector: {name}")

    def register_patcher(self, name: str, patcher: PatcherPlugin):
        self.patchers[name] = patcher
        logger.info(f"Registered patcher: {name}")

    def register_custom_patch(self, name: str, parser: CustomPatchPlugin):
        self.custom_patches[name] = parser
        logger.info(f"Registered custom patch format: {name}")

    def register_ui_panel(self, name: str, panel: UIPanelPlugin):
        self.ui_panels[name] = panel
        logger.info(f"Registered UI panel: {name}")

    def register_integration(self, name: str, integration: IntegrationPlugin):
        self.integrations[name] = integration
        logger.info(f"Registered integration: {name}")

    def register_plugin_info(self, info: PluginInfo):
        self.plugin_infos[info.name] = info

    def get_detector(self, name: str) -> DetectorPlugin | None:
        return self.detectors.get(name)

    def get_patcher(self, name: str) -> PatcherPlugin | None:
        return self.patchers.get(name)

    def get_custom_patch(self, name: str) -> CustomPatchPlugin | None:
        return self.custom_patches.get(name)

    def get_ui_panel(self, name: str) -> UIPanelPlugin | None:
        return self.ui_panels.get(name)

    def get_integration(self, name: str) -> IntegrationPlugin | None:
        return self.integrations.get(name)

    def get_all_detectors(self) -> dict[str, DetectorPlugin]:
        return self.detectors.copy()

    def get_all_patchers(self) -> dict[str, PatcherPlugin]:
        return self.patchers.copy()

    def get_all_patcher_modes(self) -> dict[str, str]:
        """Get all patcher modes mapped to patcher names."""
        modes = {}
        for patcher in self.patchers.values():
            modes.update(patcher.get_supported_modes())
        return modes


class DetectorRegistry:
    """Registry specifically for detectors used by analyzer."""

    def __init__(self, plugin_registry: PluginRegistry):
        self.plugin_registry = plugin_registry
        self._detector_order: list[str] = []

    def get_ordered_detectors(self) -> list[DetectorPlugin]:
        """Get detectors sorted by priority."""
        if not self._detector_order:
            self._detector_order = sorted(
                self.plugin_registry.detectors.keys(),
                key=lambda n: self.plugin_registry.detectors[n].priority,
                reverse=True
            )
        return [self.plugin_registry.detectors[n] for n in self._detector_order]

    def run_all(self, apk, dex_index, findings: list[dict], available_patches: list[str]) -> None:
        """Run all detectors in priority order."""
        for detector in self.get_ordered_detectors():
            try:
                detector.analyze(apk, dex_index, findings, available_patches)
            except Exception as e:
                logger.exception(f"Detector {detector.detector_name} failed: {e}")


class PatcherRegistry:
    """Registry specifically for patchers used by pipeline."""

    def __init__(self, plugin_registry: PluginRegistry):
        self.plugin_registry = plugin_registry

    def get_patcher_for_mode(self, mode: str) -> PatcherPlugin | None:
        """Get patcher that handles the given mode."""
        modes = self.plugin_registry.get_all_patcher_modes()
        patcher_name = modes.get(mode)
        if patcher_name:
            return self.plugin_registry.patchers.get(patcher_name)
        return None

    def get_patcher(self, name: str) -> PatcherPlugin | None:
        return self.plugin_registry.patchers.get(name)

    def run_patcher(self, patcher_name: str, decompiled_path: str,
                    log_callback: Callable, file_cache=None, **kwargs) -> int:
        """Run a specific patcher by name."""
        patcher = self.plugin_registry.patchers.get(patcher_name)
        if not patcher:
            logger.warning(f"Patcher not found: {patcher_name}")
            return 0

        try:
            return patcher.patch(decompiled_path, log_callback, file_cache, **kwargs)
        except Exception as e:
            logger.exception(f"Patcher {patcher_name} failed: {e}")
            return 0


class PluginManager:
    """
    Plugin Manager — discovers, loads, and manages plugins.

    Scans plugin directories, imports plugin modules, calls register(),
    and populates registries.
    """

    def __init__(self, plugin_dirs: list[str] | None = None):
        self.plugin_dirs = plugin_dirs or [self._default_plugin_dir()]
        self.registry = PluginRegistry()
        self.detector_registry = DetectorRegistry(self.registry)
        self.patcher_registry = PatcherRegistry(self.registry)
        self._loaded = False
        self._load_errors: list[str] = []

    def _default_plugin_dir(self) -> str:
        """Get default plugin directory."""
        base = Path(__file__).resolve().parent
        return str(base)

    def load_plugins(self) -> None:
        """Discover and load all plugins."""
        if self._loaded:
            return

        self._loaded = True
        self._load_errors = []

        for plugin_dir in self.plugin_dirs:
            self._scan_directory(plugin_dir)

        if self._load_errors:
            logger.warning(f"Plugin load errors: {len(self._load_errors)}")
            for err in self._load_errors:
                logger.warning(f"  - {err}")

    def _scan_directory(self, plugin_dir: str) -> None:
        """Scan directory for plugin modules."""
        path = Path(plugin_dir)
        if not path.exists():
            logger.debug(f"Plugin directory not found: {plugin_dir}")
            return

        # Add to sys.path for imports
        parent = str(path.parent)
        if parent not in sys.path:
            sys.path.insert(0, parent)

        for file in path.glob("*.py"):
            if file.name.startswith("_") or file.name == "base.py" or file.name == "manager.py" or file.name == "registry.py" or file.name == "__init__.py":
                continue

            module_name = file.stem
            self._load_plugin_module(module_name, file)

    def _load_plugin_module(self, module_name: str, file_path: Path) -> None:
        """Load a single plugin module."""
        try:
            # Import module
            spec = importlib.util.spec_from_file_location(f"plugins.{module_name}", file_path)
            if spec is None or spec.loader is None:
                self._load_errors.append(f"{module_name}: Could not create spec")
                return

            module = importlib.util.module_from_spec(spec)
            sys.modules[f"plugins.{module_name}"] = module
            spec.loader.exec_module(module)

            # Call register() if present
            if hasattr(module, "register"):
                plugin_data = module.register()
                self._register_plugin_data(module_name, plugin_data)
            else:
                # Try to find decorated classes
                self._find_decorated_classes(module, module_name)

        except Exception as e:
            self._load_errors.append(f"{module_name}: {e}")
            logger.exception(f"Failed to load plugin {module_name}")

    def _register_plugin_data(self, module_name: str, data: dict) -> None:
        """Register plugin data from register() return value."""
        if not isinstance(data, dict):
            self._load_errors.append(f"{module_name}: register() must return dict")
            return

        # Register plugin info
        info = PluginInfo(
            name=data.get("name", module_name),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            description=data.get("description", ""),
            license=data.get("license", "MIT"),
            min_lp_version=data.get("min_lp_version", "1.0.0"),
            dependencies=data.get("dependencies", []),
        )
        self.registry.register_plugin_info(info)

        # Register detectors
        for name, detector_cls in data.get("detectors", {}).items():
            if isinstance(detector_cls, type) and issubclass(detector_cls, DetectorPlugin):
                self.registry.register_detector(name, detector_cls())
            elif isinstance(detector_cls, DetectorPlugin):
                self.registry.register_detector(name, detector_cls)
            else:
                self._load_errors.append(f"{module_name}: Invalid detector {name}")

        # Register patchers
        for name, patcher_cls in data.get("patchers", {}).items():
            if isinstance(patcher_cls, type) and issubclass(patcher_cls, PatcherPlugin):
                self.registry.register_patcher(name, patcher_cls())
            elif isinstance(patcher_cls, PatcherPlugin):
                self.registry.register_patcher(name, patcher_cls)
            else:
                self._load_errors.append(f"{module_name}: Invalid patcher {name}")

        # Register custom patches
        for name, parser_cls in data.get("custom_patches", {}).items():
            if isinstance(parser_cls, type) and issubclass(parser_cls, CustomPatchPlugin):
                self.registry.register_custom_patch(name, parser_cls())
            elif isinstance(parser_cls, CustomPatchPlugin):
                self.registry.register_custom_patch(name, parser_cls)
            else:
                self._load_errors.append(f"{module_name}: Invalid custom patch {name}")

        # Register UI panels
        for name, panel_cls in data.get("ui_panels", {}).items():
            if isinstance(panel_cls, type) and issubclass(panel_cls, UIPanelPlugin):
                self.registry.register_ui_panel(name, panel_cls())
            elif isinstance(panel_cls, UIPanelPlugin):
                self.registry.register_ui_panel(name, panel_cls)
            else:
                self._load_errors.append(f"{module_name}: Invalid UI panel {name}")

        # Register integrations
        for name, integration_cls in data.get("integrations", {}).items():
            if isinstance(integration_cls, type) and issubclass(integration_cls, IntegrationPlugin):
                self.registry.register_integration(name, integration_cls())
            elif isinstance(integration_cls, IntegrationPlugin):
                self.registry.register_integration(name, integration_cls)
            else:
                self._load_errors.append(f"{module_name}: Invalid integration {name}")

    def _find_decorated_classes(self, module, module_name: str) -> None:
        """Find classes decorated with plugin decorators."""
        import inspect

        for name, obj in inspect.getmembers(module, inspect.isclass):
            if getattr(obj, "_is_detector_plugin", False):
                self.registry.register_detector(name, cast(DetectorPlugin, obj()))
            elif getattr(obj, "_is_patcher_plugin", False):
                self.registry.register_patcher(name, cast(PatcherPlugin, obj()))
            elif getattr(obj, "_is_custom_patch_plugin", False):
                self.registry.register_custom_patch(name, cast(CustomPatchPlugin, obj()))
            elif getattr(obj, "_is_ui_panel_plugin", False):
                self.registry.register_ui_panel(name, cast(UIPanelPlugin, obj()))
            elif getattr(obj, "_is_integration_plugin", False):
                self.registry.register_integration(name, cast(IntegrationPlugin, obj()))

    def get_registry(self) -> PluginRegistry:
        """Get the plugin registry."""
        return self.registry

    def get_detector_registry(self) -> DetectorRegistry:
        """Get detector registry."""
        return self.detector_registry

    def get_patcher_registry(self) -> PatcherRegistry:
        """Get patcher registry."""
        return self.patcher_registry

    def get_load_errors(self) -> list[str]:
        """Get list of load errors."""
        return self._load_errors.copy()

    def list_plugins(self) -> list[PluginInfo]:
        """List all loaded plugins."""
        return list(self.registry.plugin_infos.values())


# Global plugin manager instance
_plugin_manager: PluginManager | None = None


def get_plugin_manager(plugin_dirs: list[str] | None = None) -> PluginManager:
    """Get or create global plugin manager."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager(plugin_dirs)
    return _plugin_manager


def register_plugin(plugin_dir: str | None = None) -> PluginManager:
    """Register a new plugin directory and reload."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    if plugin_dir:
        _plugin_manager.plugin_dirs.append(plugin_dir)
    _plugin_manager.load_plugins()
    return _plugin_manager


__all__ = [
    "PluginManager",
    "PluginRegistry",
    "DetectorRegistry",
    "PatcherRegistry",
    "get_plugin_manager",
    "register_plugin",
]
