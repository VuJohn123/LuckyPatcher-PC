"""
Plugin Architecture — dynamic loading of community detectors/patchers.

LP-PC Suite Plugin System:
- Plugins are Python packages in src/plugins/
- Each plugin implements detector and/or patcher interfaces
- Auto-discovered and registered at startup
- Can extend: detection, patching, custom patches, UI panels

Plugin Types:
1. Detector Plugin: Adds new detection logic (e.g., new packer, new SDK)
2. Patcher Plugin: Adds new patch modes (e.g., new license bypass, new ads removal)
3. Custom Patch Plugin: Adds custom patch format support
4. UI Plugin: Adds new panels/widgets to the GUI
5. Integration Plugin: Adds external service integration

Plugin Interface:
```python
# plugin.py
def register():
    return {
        "name": "my_plugin",
        "version": "1.0.0",
        "detectors": {
            "my_detector": MyDetectorClass,
        },
        "patchers": {
            "my_patch_mode": MyPatcherClass,
        },
        "custom_patches": {
            "my_format": MyCustomPatchParser,
        },
        "ui_panels": {
            "my_panel": MyPanelClass,
        },
    }
```

Discovery:
- Scans src/plugins/ for plugin.py files
- Imports and calls register()
- Registers detectors/patchers with core registries
"""
from __future__ import annotations

from .base import (
    CustomPatchPlugin,
    DetectorPlugin,
    IntegrationPlugin,
    PatcherPlugin,
    UIPanelPlugin,
)
from .manager import (
    DetectorRegistry,
    PatcherRegistry,
    PluginInfo,
    PluginManager,
    PluginRegistry,
    get_plugin_manager,
    register_plugin,
)

__all__ = [
    "PluginManager",
    "PluginInfo",
    "register_plugin",
    "get_plugin_manager",
    "DetectorPlugin",
    "PatcherPlugin",
    "CustomPatchPlugin",
    "UIPanelPlugin",
    "IntegrationPlugin",
    "PluginRegistry",
    "DetectorRegistry",
    "PatcherRegistry",
]

__version__ = "1.0.0"
