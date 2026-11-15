"""Plugin manager — load động từ thư mục plugins/."""
from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class PluginManager:
    def __init__(self, plugin_dir: str | None = None):
        if plugin_dir is None:
            plugin_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "plugins",
            )
        self.plugin_dir = Path(plugin_dir)
        self.plugins: dict[str, dict] = {}
        self._loaded = False

    def load_plugins(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        if not self.plugin_dir.exists():
            return

        for file in self.plugin_dir.glob("*.py"):
            if file.name.startswith("_"):
                continue
            module_name = file.stem
            try:
                # Load by file path so plugin modules never collide with the
                # built-in ``plugins`` package or with plugins from other
                # directories that happen to share a module name.
                unique_name = f"_lp_plugin_{module_name}_{id(file)}"
                spec = importlib.util.spec_from_file_location(
                    unique_name, file
                )
                if spec is None or spec.loader is None:
                    logger.warning(
                        "Plugin %s has no importable spec", module_name
                    )
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "register"):
                    info = module.register()
                    if isinstance(info, dict):
                        self.plugins[module_name] = info
                        logger.info("Plugin loaded: %s", module_name)
            except Exception as e:
                logger.exception("Plugin %s load failed: %s", module_name, e)

    def get_all_modes(self) -> dict[str, str]:
        self.load_plugins()
        modes: dict[str, str] = {}
        for info in self.plugins.values():
            modes.update(info.get("patchers", {}))
        return modes

    def get_patcher(self, mode_name: str):
        self.load_plugins()
        for info in self.plugins.values():
            if mode_name in info.get("patchers", {}):
                return info["patchers"][mode_name]
        return None
