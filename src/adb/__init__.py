"""
ADB Orchestration Layer — Lucky Patcher mobile features ported to PC via ADB.

LP mobile-only features (Layers 0, 1, 3) that require ADB/device:
- ODEX patching (baksmali/smali on device)
- Patch to Android (services.jar pull/patch/push)
- Modified Play Store install
- BootList script deploy (runs patches at boot)
- Widgets (home screen widgets for patch control)
- lpzip import (custom patch archives)
- Xposed/LSPosed module install (min version 82, entry: com.xposed.XSupport)

Architecture:
- ADBDevice: represents connected device with properties
- ADBOrchestrator: high-level operations with retry/fallback
- ADBCommand: structured command with validation
- ADBFileTransfer: push/pull with progress/verification
- ADBShell: command execution with streaming output

References:
- LP-DeCodes LP_12.10.4_1/unknown/keys/ (real keystore keys)
- patch.chelpus.com protocol (custom patch cloud)
- Xposed min version 82 (API level 23+)
- Package: ru.aaaaaban.installer → obfuscated ru.hhklsyty.wlkllqrcq
"""
from __future__ import annotations

from .bootlist import ADBBootList, ADBBootListResult, deploy_bootlist_script
from .commands import ADBCommand, ADBCommandBuilder, ADBCommandResult
from .device import ADBDevice, ADBDeviceManager, DeviceProperty
from .lpzip import ADBLpzipImporter, ADBLpzipResult, import_lpzip
from .odex import ADBOdexPatcher, ADBOdexPatchResult, patch_odex_on_device
from .orchestrator import ADBOperation, ADBOrchestrator, ADBResult
from .patch_to_android import PatchToAndroid, PatchToAndroidResult, patch_services_jar
from .play_store import (
    ModdedPlayStore,
    ModdedPlayStoreResult,
    install_modded_play_store,
)
from .shell import ADBShell, ADBShellResult, ADBShellStream
from .transfer import ADBFileTransfer, ADBTransferProgress, ADBTransferResult
from .widgets import ADBWidgetManager, ADBWidgetResult, deploy_widgets
from .xposed import (
    XPOSED_MIN_VERSION,
    ADBXposedInstaller,
    ADBXposedResult,
    install_xposed_module,
)

__all__ = [
    "ADBDevice",
    "ADBDeviceManager",
    "DeviceProperty",
    "ADBOrchestrator",
    "ADBOperation",
    "ADBResult",
    "ADBCommand",
    "ADBCommandBuilder",
    "ADBCommandResult",
    "ADBFileTransfer",
    "ADBTransferProgress",
    "ADBTransferResult",
    "ADBShell",
    "ADBShellResult",
    "ADBShellStream",
    "ADBOdexPatcher",
    "ADBOdexPatchResult",
    "patch_odex_on_device",
    "PatchToAndroid",
    "PatchToAndroidResult",
    "patch_services_jar",
    "ModdedPlayStore",
    "ModdedPlayStoreResult",
    "install_modded_play_store",
    "ADBBootList",
    "ADBBootListResult",
    "deploy_bootlist_script",
    "ADBWidgetManager",
    "ADBWidgetResult",
    "deploy_widgets",
    "ADBLpzipImporter",
    "ADBLpzipResult",
    "import_lpzip",
    "ADBXposedInstaller",
    "ADBXposedResult",
    "install_xposed_module",
    "XPOSED_MIN_VERSION",
]

__version__ = "1.0.0"
