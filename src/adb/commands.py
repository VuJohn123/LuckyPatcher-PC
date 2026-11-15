"""
ADB Commands — structured command execution with streaming, validation, and result parsing.
"""
from __future__ import annotations

import logging
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from .orchestrator import (
    ADBCommand,
    ADBDevice,
    ADBDeviceManager,
    ADBOperation,
    DeviceProperty,
)

logger = logging.getLogger(__name__)


@dataclass
class ADBCommandResult:
    """Result of ADB command execution with structured parsing."""
    success: bool
    command: ADBCommand
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    error: str = ""
    lines: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def __bool__(self) -> bool:
        return self.success

    @property
    def output(self) -> str:
        return self.stdout

    def get_lines(self) -> Iterator[str]:
        return iter(self.lines)


class ADBCommandBuilder:
    """Fluent builder for ADB commands."""

    def __init__(self, device_serial: str, adb_path: str = "adb"):
        self.device_serial = device_serial
        self.adb_path = adb_path
        self.operation = ADBOperation.SHELL
        self.args: list[str] = []
        self.env: dict[str, str] = {}
        self.timeout = 30
        self.capture_output = True
        self.validate_device = True
        self.require_root = False
        self.stream_output = False
        self.stream_callback: Callable[[str], None] | None = None

    def op(self, operation: ADBOperation) -> ADBCommandBuilder:
        self.operation = operation
        return self

    def arg(self, *args: str) -> ADBCommandBuilder:
        self.args.extend(args)
        return self

    def env_var(self, key: str, value: str) -> ADBCommandBuilder:
        self.env[key] = value
        return self

    def with_timeout(self, seconds: int) -> ADBCommandBuilder:
        self.timeout = seconds
        return self

    def no_capture(self) -> ADBCommandBuilder:
        self.capture_output = False
        return self

    def no_validate(self) -> ADBCommandBuilder:
        self.validate_device = False
        return self

    def root(self) -> ADBCommandBuilder:
        self.require_root = True
        return self

    def stream(self, callback: Callable[[str], None]) -> ADBCommandBuilder:
        self.stream_output = True
        self.stream_callback = callback
        return self

    def build(self) -> ADBCommand:
        return ADBCommand(
            operation=self.operation,
            device_serial=self.device_serial,
            args=self.args,
            env=self.env,
            timeout=self.timeout,
            capture_output=self.capture_output,
            validate_device=self.validate_device,
            require_root=self.require_root,
            stream_output=self.stream_output,
            stream_callback=self.stream_callback,
        )


class ADBCommandExecutor:
    """Executes ADB commands with device context."""

    def __init__(self, device: ADBDevice, adb_path: str = "adb"):
        self.device = device
        self.adb_path = adb_path
        self._lock = threading.Lock()

    def execute(self, command: ADBCommand) -> ADBCommandResult:
        """Execute ADB command."""
        start = time.monotonic()

        cmd = command.to_cmd_list(self.adb_path)
        env = dict(__import__("os").environ, **command.env) if command.env else None

        try:
            if command.stream_output:
                return self._execute_streaming(command, cmd, env, start)

            proc = subprocess.run(
                cmd, env=env, capture_output=True, text=True, timeout=command.timeout,
                creationflags=__import__("sys").platform == "win32" and __import__("subprocess").CREATE_NO_WINDOW or 0
            )

            return ADBCommandResult(
                success=proc.returncode == 0,
                command=command,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                return_code=proc.returncode,
                error=proc.stderr or "" if proc.returncode != 0 else "",
                lines=(proc.stdout or "").strip().splitlines(),
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except subprocess.TimeoutExpired as e:
            return ADBCommandResult(
                success=False, command=command, return_code=-1, error="Timeout",
                lines=(str(e.stdout).strip().splitlines() if getattr(e, "stdout", None) else []),
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return ADBCommandResult(
                success=False, command=command, return_code=-1, error=str(e),
                lines=[], duration_ms=(time.monotonic() - start) * 1000,
            )

    def _execute_streaming(self, command, cmd, env, start):
        proc = subprocess.Popen(
            cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
            creationflags=__import__("sys").platform == "win32" and __import__("subprocess").CREATE_NO_WINDOW or 0
        )
        lines = []
        try:
            stdout, stderr = proc.communicate(timeout=command.timeout)
            lines.extend((stdout or "").strip().splitlines())
            lines.extend((stderr or "").strip().splitlines())
            return ADBCommandResult(
                success=proc.returncode == 0, command=command,
                stdout=stdout or "", stderr=stderr or "",
                return_code=proc.returncode, lines=lines,
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            lines.extend((stdout or "").strip().splitlines())
            lines.extend((stderr or "").strip().splitlines())
            return ADBCommandResult(
                success=False, command=command,
                stdout=stdout or "", stderr=stderr or "",
                return_code=-1, lines=lines,
                duration_ms=(time.monotonic() - start) * 1000,
                error="Timeout",
            )


@contextmanager
def adb_command(device_or_serial, adb_path: str = "adb") -> Iterator[ADBCommandExecutor]:
    """Context manager for ADB command execution."""
    device = (
        device_or_serial
        if isinstance(device_or_serial, ADBDevice)
        else ADBDeviceManager(adb_path=adb_path).get_device(device_or_serial)
    )
    if device is None:
        raise ValueError(f"Device not found: {device_or_serial}")
    yield ADBCommandExecutor(device, adb_path)


# Specialized command builders for common operations
class ADBCommandBuilders:
    """Pre-built ADB command patterns."""

    @staticmethod
    def install(device: ADBDevice, apk_path: str, replace: bool = True, test: bool = False, grant_perms: bool = False) -> ADBCommand:
        args = ["-r"] if replace else []
        if test:
            args.append("-t")
        if grant_perms:
            args.append("-g")
        args.append(apk_path)
        return ADBCommand(ADBOperation.INSTALL, device.serial, args=args)

    @staticmethod
    def uninstall(device: ADBDevice, package_name: str, keep_data: bool = False) -> ADBCommand:
        args = ["-k"] if keep_data else []
        args.append(package_name)
        return ADBCommand(ADBOperation.UNINSTALL, device.serial, args=args)

    @staticmethod
    def push(device: ADBDevice, local: str, remote: str) -> ADBCommand:
        return ADBCommand(ADBOperation.PUSH, device.serial, args=[local, remote])

    @staticmethod
    def pull(device: ADBDevice, remote: str, local: str) -> ADBCommand:
        return ADBCommand(ADBOperation.PULL, device.serial, args=[remote, local])

    @staticmethod
    def shell(device: ADBDevice, command: str, timeout: int = 30, require_root: bool = False) -> ADBCommand:
        return ADBCommand(ADBOperation.SHELL, device.serial, args=[command], timeout=timeout, require_root=require_root)

    @staticmethod
    def shell_stream(device: ADBDevice, command: str, callback: Callable[[str], None], timeout: int = 30, require_root: bool = False) -> ADBCommand:
        return ADBCommand(ADBOperation.SHELL, device.serial, args=[command], timeout=timeout, require_root=require_root, stream_output=True, stream_callback=callback)

    @staticmethod
    def exec_in(device: ADBDevice, command: str, stdin_data: str, timeout: int = 30) -> ADBCommand:
        return ADBCommand(ADBOperation.EXEC_IN, device.serial, args=[command, stdin_data], timeout=timeout)

    @staticmethod
    def exec_out(device: ADBDevice, command: str, timeout: int = 30) -> ADBCommand:
        return ADBCommand(ADBOperation.EXEC_OUT, device.serial, args=[command], timeout=timeout)

    @staticmethod
    def reverse(device: ADBDevice, remote_port: int, local_port: int) -> ADBCommand:
        return ADBCommand(ADBOperation.REVERSE, device.serial, args=[f"tcp:{remote_port}", f"tcp:{local_port}"])

    @staticmethod
    def reverse_remove(device: ADBDevice, remote_port: int) -> ADBCommand:
        return ADBCommand(ADBOperation.REVERSE_REMOVE, device.serial, args=[f"tcp:{remote_port}"])

    @staticmethod
    def reboot(device: ADBDevice, mode: str = "") -> ADBCommand:
        return ADBCommand(ADBOperation.REBOOT, device.serial, args=[mode] if mode else [])

    @staticmethod
    def get_property(device: ADBDevice, prop: DeviceProperty) -> ADBCommand:
        return ADBCommand(ADBOperation.SHELL, device.serial, args=["getprop", prop.value])

    @staticmethod
    def get_serial(device: ADBDevice) -> ADBCommand:
        return ADBCommand(ADBOperation.GET_SERIAL, device.serial, args=["get-serialno"])

    @staticmethod
    def wait_for(device: ADBDevice, timeout: int = 60) -> ADBCommand:
        return ADBCommand(ADBOperation.WAIT_FOR_DEVICE, device.serial, timeout=timeout, validate_device=False)


# Command result parsers
def parse_pm_list_output(output: str) -> list[dict]:
    """Parse 'pm list packages' output."""
    packages = []
    for line in output.strip().splitlines():
        if line.startswith("package:"):
            pkg = line[len("package:"):].strip()
            packages.append({"package": pkg, "line": line})
    return packages


def parse_package_info(output: str) -> dict:
    """Parse 'pm dump <package>' output."""
    info: dict[str, str] = {}
    current_key: str | None = None
    current_value: list[str] = []
    for line in output.strip().splitlines():
        if line.strip().startswith("["):
            if current_key:
                info[current_key] = "\n".join(current_value)
            current_key = line.strip()[1:-1]  # Remove [ ]
            current_value = []
        elif current_key:
            current_value.append(line)
    if current_key:
        info[current_key] = "\n".join(current_value)
    return info


def parse_pm_dump(output: str) -> dict:
    """Parse detailed package dump."""
    result = {"raw": output}
    lines = output.strip().splitlines()
    for line in lines:
            if "=" in line:
                    key, val = line.split("=", 1)
                    result[key.strip()] = val.strip()
    return result


def parse_version_code(output: str) -> int:
    """Extract versionCode from pm dump."""
    try:
            return int(output.split("versionCode=")[1].split()[0])
    except Exception:
            return 0


def parse_version_name(output: str) -> str:
    """Extract versionName from pm dump."""
    try:
            return output.split("versionName=")[1].split()[0]
    except Exception:
            return ""


def parse_install_time(output: str) -> float:
    """Extract firstInstallTime from pm dump (millis)."""
    try:
            return float(output.split("firstInstallTime=")[1].split()[0])
    except Exception:
            return 0


def parse_update_time(output: str) -> float:
    """Extract lastUpdateTime from pm dump (millis)."""
    try:
            return float(output.split("lastUpdateTime=")[1].split()[0])
    except Exception:
            return 0


def parse_signatures(output: str) -> list[str]:
    """Extract signatures from pm dump."""
    sigs = []
    in_sigs = False
    for line in output.strip().splitlines():
            if "signatures:" in line:
                    in_sigs = True
                    continue
            if in_sigs:
                    if line.strip().startswith("Package ["):
                        break
                    sigs.append(line.strip())
    return sigs


# ADB command shortcuts for LP mobile feature implementation
def build_odex_patch_commands(device: ADBDevice, package_name: str, dex_files: list[str],
                              patch_mode: str, output_dir: str) -> list[ADBCommand]:
    """Build ADB command sequence for ODEX patching on device."""
    commands = []

    # Create working directory
    commands.append(ADBCommand(ADBOperation.SHELL, device.serial,
        args=[f"mkdir -p {output_dir}"],
        comment="Create working dir"))

    # Pull APK to device storage if not already there
    # Note: In real implementation, we'd push APK from PC to device first
    device_apk = f"{output_dir}/target.apk"
    commands.append(ADBCommand(ADBOperation.SHELL, device.serial,
        args=[f"pm path {package_name}"],
        comment="Get APK path"))

    # Decompile with baksmali
    for i, dex_file in enumerate(dex_files):
        commands.append(ADBCommand(ADBOperation.SHELL, device.serial,
            args=[f"baksmali {device_apk} -o {output_dir}/smali_{i}"],
            comment=f"Baksmali {dex_file}"))

    # Apply patches (would need patch files on device)
    # Patch logic depends on patch_mode

    # Recompile with smali
    commands.append(ADBCommand(ADBOperation.SHELL, device.serial,
        args=[f"smali {output_dir}/smali_* -o {output_dir}/patched.dex"],
        comment="Smali recompile"))

    return commands


def build_patch_to_android_commands(device: ADBDevice, services_jar_path: str,
                                     patch_files: list[str], output_dir: str) -> list[ADBCommand]:
    """Build ADB command sequence for Patch to Android (services.jar patching)."""
    commands = []

    commands.append(ADBCommand(ADBOperation.SHELL, device.serial,
        args=[f"mkdir -p {output_dir}"],
        comment="Create working dir"))

    # Pull services.jar from framework
    commands.append(ADBCommand(ADBOperation.SHELL, device.serial,
        args=[f"cp /system/framework/services.jar {output_dir}/services.jar"],
        comment="Pull services.jar"))

    # Decompile services.jar
    commands.append(ADBCommand(ADBOperation.SHELL, device.serial,
        args=[f"baksmali {output_dir}/services.jar -o {output_dir}/services_smali"],
        comment="Decompile services.jar"))

    # Apply patches (patch_files contain smali patches)
    # Patch logic here...

    # Recompile services.jar
    commands.append(ADBCommand(ADBOperation.SHELL, device.serial,
        args=[f"smali {output_dir}/services_smali -o {output_dir}/services_patched.dex"],
        comment="Recompile services.dex"))

    # Repack services.jar
    commands.append(ADBCommand(ADBOperation.SHELL, device.serial,
        args=[f"cd {output_dir} && dx --dex --output=services_patched.dex services_patched.dex && jar uf services.jar services_patched.dex"],
        comment="Update services.jar"))

    return commands


XPOSED_MIN_VERSION = 82
XPOSED_PACKAGE = "ru.aaaaaban.installer"  # Original
XPOSED_PACKAGE_OBFUSCATED = "ru.hhklsyty.wlkllqrcq"  # Obfuscated


def build_xposed_install_commands(device: ADBDevice, xposed_zip_path: str,
                                   install_dir: str = "/data/local/lp_xposed") -> list[ADBCommand]:
    """Build ADB command sequence for Xposed/LSPosed module install."""
    commands = []

    # Check Xposed/LSPosed is installed
    commands.append(ADBCommand(ADBOperation.SHELL, device.serial,
        args=["ls /data/adb/modules/lsposed" if device.api_level >= 30 else "ls /data/xposed"],
        comment="Check Xposed/LSPosed"))

    # Create install dir
    commands.append(ADBCommand(ADBOperation.SHELL, device.serial,
        args=[f"mkdir -p {install_dir}"],
        comment="Create Xposed module dir"))

    # Extract Xposed module from zip
    commands.append(ADBCommand(ADBOperation.SHELL, device.serial,
        args=[f"unzip -o {xposed_zip_path} -d {install_dir}"],
        comment="Extract Xposed module"))

    # Enable module (LSPosed)
    commands.append(ADBCommand(ADBOperation.SHELL, device.serial,
        args=[f"echo {XPOSED_PACKAGE_OBFUSCATED} > {install_dir}/enabled"],
        comment="Enable Xposed module"))

    # Create module.prop
    commands.append(ADBCommand(ADBOperation.SHELL, device.serial,
        args=[f"cat > {install_dir}/module.prop << 'EOF'\nid=luckypatcher\nname=Lucky Patcher\nversion=12.10.4\nversionCode=121004\nauthor=ChelpuS\ndescription=LP Decomplied module\nEOF"],
        comment="Create module.prop"))

    return commands


def build_bootlist_commands(device: ADBDevice, patches: list[dict],
                             script_path: str = "/system/bin/lp_boot_patch.sh") -> list[ADBCommand]:
    """Build ADB command sequence for BootList (patch at boot)."""
    commands = []

    # Build boot patch script
    script_lines = [
        "#!/system/bin/sh",
        "# Lucky Patcher Boot Patch Script",
        "# Generated by LP-PC Suite ADB Orchestrator",
        "",
        "wait_for_boot() {",
        "  while [ \"$(getprop sys.boot_completed)\" != \"1\" ]; do sleep 1; done",
        "}",
        "",
        "patch_apps() {",
    ]

    for patch in patches:
        pkg = patch.get("package", "")
        mode = patch.get("mode", "")
        script_lines.append(f'  patch_package "{pkg}" "{mode}"')

    script_lines.extend([
        "}",
        "",
        "wait_for_boot",
        "patch_apps",
        "",
    ])

    script_content = "\n".join(script_lines)

    commands.append(ADBCommand(ADBOperation.SHELL, device.serial,
        args=[f"cat > {script_path} << 'EOF'\n{script_content}\nEOF"],
        comment="Create boot patch script"))

    # Make executable
    commands.append(ADBCommand(ADBOperation.SHELL, device.serial,
        args=[f"chmod 755 {script_path}"],
        comment="Make script executable"))

    # Add to init.rc or equivalent (requires root)
    # For system partition, would need to modify /system/bin/ or /vendor/bin/

    return commands


def build_widget_commands(device: ADBDevice, widget_configs: list[dict]) -> list[ADBCommand]:
    """Build ADB command sequence for widget deployment."""
    # Widgets are typically deployed via:
    # 1. Install widget provider APK (AppWidgetProvider implementation)
        # 2. Enable widget for packages
        # Widgets are part of Android UI, not easily ADB-deployable without app
    # This is a placeholder for the architecture
    return []
