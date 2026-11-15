"""
ADB Device management — connection, properties, root check, capabilities.
"""
from __future__ import annotations

import logging
import re
import subprocess
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class DeviceProperty(Enum):
    """Device properties queried via ADB."""
    SERIAL = "ro.serialno"
    MODEL = "ro.product.model"
    MANUFACTURER = "ro.product.manufacturer"
    BRAND = "ro.product.brand"
    ANDROID_VERSION = "ro.build.version.release"
    SDK_INT = "ro.build.version.sdk"
    CPU_ABI = "ro.product.cpu.abi"
    CPU_ABI2 = "ro.product.cpu.abi2"
    IS_EMULATOR = "ro.boot.qemu"
    IS_ROOTED = "ro.debuggable"
    BUILD_ID = "ro.build.id"
    BUILD_FINGERPRINT = "ro.build.fingerprint"
    SECURITY_PATCH = "ro.build.version.security_patch"
    INTERNAL_STORAGE = "ro.internal.storage"
    EXTERNAL_STORAGE = "EXTERNAL_STORAGE"


@dataclass
class ADBDevice:
    """Represents an ADB-connected Android device."""
    serial: str
    model: str = ""
    manufacturer: str = ""
    brand: str = ""
    android_version: str = ""
    sdk_int: int = 0
    cpu_abi: str = ""
    cpu_abi2: str = ""
    is_emulator: bool = False
    is_rooted: bool = False
    build_id: str = ""
    build_fingerprint: str = ""
    security_patch: str = ""
    _properties_loaded: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def display_name(self) -> str:
        return f"{self.brand} {self.model} ({self.serial})" if self.model else self.serial

    @property
    def api_level(self) -> int:
        return self.sdk_int

    @property
    def supports_odex_patching(self) -> bool:
        """Check if device supports ODEX patching (ART runtime, Android 5.0+)."""
        return self.sdk_int >= 21 and not self.is_emulator

    @property
    def supports_xposed(self) -> bool:
        """Check if device supports Xposed/LSPosed (Android 5.0+)."""
        return self.sdk_int >= 21

    @property
    def supports_patch_to_android(self) -> bool:
        """Patch to Android requires root + Android 4.4+."""
        return self.is_rooted and self.sdk_int >= 19


@dataclass
class ADBDeviceManager:
    """Manages ADB device connections and discovery."""
    adb_path: str = "adb"
    _device_cache: dict[str, ADBDevice] = field(default_factory=dict)
    _cache_ttl: float = 30.0  # seconds
    _last_scan: float = 0

    def __post_init__(self):
        self._lock = threading.Lock()
        # Validate ADB path
        import shutil
        if not shutil.which(self.adb_path):
            raise RuntimeError(f"ADB not found at {self.adb_path}. Install Android Platform Tools.")

    def scan_devices(self, force: bool = False) -> list[ADBDevice]:
        """Scan for connected devices. Returns list of ADBDevice."""
        with self._lock:
            if not force and (time.time() - self._last_scan) < self._cache_ttl:
            # Return cached devices
                return list(self._device_cache.values())

            devices = []
            try:
                proc = subprocess.run(
                [self.adb_path, "devices", "-l"],
                capture_output=True, text=True, timeout=10
            )
                lines = proc.stdout.strip().splitlines()
                for line in lines[1:]:  # Skip "List of devices attached"
                    if not line.strip():
                        continue
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    serial = parts[0]
                    if "unauthorized" in line or "offline" in line:
                        # Device exists but not authorized
                        logger.warning("Device %s is unauthorized or offline", serial)
                        continue
                    device = ADBDevice(serial=serial)
                    devices.append(device)
            except subprocess.TimeoutExpired:
                logger.error("ADB devices scan timed out")
            except Exception as e:
                logger.error("ADB devices scan failed: %s", e)

            # Update cache
            self._device_cache = {d.serial: d for d in devices}
            self._last_scan = time.time()
            return devices

    def get_device(self, serial: str) -> ADBDevice | None:
        """Get device by serial. Loads properties if not cached."""
        devices = self.scan_devices()
        return next((d for d in devices if d.serial == serial), None)

    def load_properties(self, device: ADBDevice) -> ADBDevice:
        """Load all device properties via ADB shell getprop."""
        with device._lock:
            if device._properties_loaded:
                return device

            props = {}
            try:
                # Single ADB call to get all needed properties
                # Using 'getprop' without args returns all properties
                proc = subprocess.run(
                    [self.adb_path, "-s", device.serial, "shell", "getprop"],
                    capture_output=True, text=True, timeout=15
                )
                for line in proc.stdout.strip().splitlines():
                    match = re.match(r'\[\s*(.+?)\s*\]:\s*\[(.*)\]', line)
                    if match:
                        props[match.group(1)] = match.group(2)
            except Exception as e:
                logger.error("Failed to load properties for %s: %s", device.serial, e)

            device.model = props.get(DeviceProperty.MODEL.value, "")
            device.manufacturer = props.get(DeviceProperty.MANUFACTURER.value, "")
            device.brand = props.get(DeviceProperty.BRAND.value, "")
            device.android_version = props.get(DeviceProperty.ANDROID_VERSION.value, "")
            device.sdk_int = int(props.get(DeviceProperty.SDK_INT.value, "0") or "0")
            device.cpu_abi = props.get(DeviceProperty.CPU_ABI.value, "")
            device.cpu_abi2 = props.get(DeviceProperty.CPU_ABI2.value, "")
            device.is_emulator = props.get(DeviceProperty.IS_EMULATOR.value, "").lower() == "true"
            device.build_id = props.get(DeviceProperty.BUILD_ID.value, "")
            device.build_fingerprint = props.get(DeviceProperty.BUILD_FINGERPRINT.value, "")
            device.security_patch = props.get(DeviceProperty.SECURITY_PATCH.value, "")

            # Check root status
            device.is_rooted = self._check_root(device)

            device._properties_loaded = True
            return device

    def _check_root(self, device: ADBDevice) -> bool:
        """Check if device has root access via ADB shell su -c 'id'."""
        try:
            result = subprocess.run(
                [self.adb_path, "-s", device.serial, "shell", "su", "-c", "id"],
                capture_output=True, text=True, timeout=5
            )
            return "uid=0" in result.stdout
        except Exception:
            return False

    def get_property(self, device: ADBDevice, prop: DeviceProperty) -> str:
        """Get single device property."""
        return device.__dict__.get(prop.value.lower(), "")


@contextmanager
def adb_device(device_or_serial: ADBDevice | str, adb_path: str = "adb"):
    """Context manager for ADB device operations with automatic property loading."""
    manager = ADBDeviceManager(adb_path=adb_path)
    device = (
        device_or_serial
        if isinstance(device_or_serial, ADBDevice)
        else manager.get_device(device_or_serial)
    )
    if device is None:
        raise ValueError(f"Device not found: {device_or_serial}")
    try:
        yield manager.load_properties(device)
    finally:
        pass


def get_device_manager(adb_path: str = "adb") -> ADBDeviceManager:
    """Get singleton ADBDeviceManager."""
    return ADBDeviceManager(adb_path=adb_path)


def wait_for_device(adb_path: str, serial: str, timeout: int = 60) -> ADBDevice:
    """Wait for device to come online. Raises RuntimeError if timeout."""
    manager = ADBDeviceManager(adb_path=adb_path)
    start = time.time()
    while time.time() - start < timeout:
        device = manager.get_device(serial)
        if device:
            return device
        time.sleep(2)
    raise RuntimeError(f"Device {serial} not available after {timeout}s")
