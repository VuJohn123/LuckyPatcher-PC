"""Test plugin manager — load từ thư mục."""
import os
import tempfile

from core.plugin_manager import PluginManager


def test_empty_plugin_dir():
    with tempfile.TemporaryDirectory() as tmp:
        pm = PluginManager(plugin_dir=tmp)
        assert pm.get_all_modes() == {}


def test_load_valid_plugin():
    with tempfile.TemporaryDirectory() as tmp:
        # Tạo plugin directory với __init__.py và 1 plugin
        os.makedirs(os.path.join(tmp, "plugins"))
        with open(os.path.join(tmp, "plugins", "__init__.py"), "w") as f:
            f.write("")
        with open(os.path.join(tmp, "plugins", "demo.py"), "w") as f:
            f.write(
                "def register():\n"
                "    return {'name': 'Demo', 'patchers': {'demo_mode': 'x.Y'}}\n"
            )
        pm = PluginManager(plugin_dir=os.path.join(tmp, "plugins"))
        modes = pm.get_all_modes()
        assert "demo_mode" in modes