"""
ADB Orchestrator — high-level ADB operations with retry, fallback, and structured results.
"""
from __future__ import annotations

import logging
import subprocess
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum

from .device import ADBDevice, ADBDeviceManager, DeviceProperty

logger = logging.getLogger(__name__)


class ADBOperation(Enum):
    """Standard ADB operations."""
    INSTALL = "install"
    UNINSTALL = "uninstall"
    PUSH = "push"
    PULL = "pull"
    SHELL = "shell"
    EXEC_IN = "exec-in"
    EXEC_OUT = "exec-out"
    REVERSE = "reverse"
    REVERSE_REMOVE = "reverse_remove"
    REBOOT = "reboot"
    WAIT_FOR_DEVICE = "wait_for_device"
    GET_SERIAL = "get_serial"
    GET_STATE = "get_state"
    ROOT = "root"
    UNSROOT = "unsroot"


@dataclass
class ADBResult:
    """Result of ADB operation."""
    success: bool
    operation: ADBOperation
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    error: str = ""
    duration_ms: float = 0.0
    lines: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def __bool__(self) -> bool:
        return self.success


@dataclass
class ADBCommand:
    """Structured ADB command with validation."""
    operation: ADBOperation
    device_serial: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    timeout: int = 30
    capture_output: bool = True
    validate_device: bool = True
    require_root: bool = False
    comment: str = ""

    # For shell commands: stream output line by line
    stream_output: bool = False
    stream_callback: Callable[[str], None] | None = None

    def to_cmd_list(self, adb_path: str) -> list[str]:
        """Convert to command list for subprocess."""
        cmd = [adb_path, "-s", self.device_serial]
        cmd.append(self.operation.value)
        cmd.extend(self.args)
        return cmd


@dataclass
class ADBCommandResult:
    """Result of ADB command execution."""
    success: bool
    command: ADBCommand
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    error: str = ""
    lines: list[str] = field(default_factory=list)  # For streamed output

    def __bool__(self) -> bool:
        return self.success


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


@contextmanager
def adb_session(device_or_serial: ADBDevice | str, adb_path: str = "adb"):
    """ADB session context manager with device validation."""
    device = (
        device_or_serial
        if isinstance(device_or_serial, ADBDevice)
        else ADBDeviceManager(adb_path=adb_path).get_device(device_or_serial)
    )
    if device is None:
        raise ValueError(f"Device not found: {device_or_serial}")
    orchestrator = ADBOrchestrator(device=device, adb_path=adb_path)
    try:
        yield orchestrator
    finally:
        pass


class ADBOrchestrator:
    """
    High-level ADB orchestrator with:
    - Retry logic with exponential backoff
    - Device validation
    - Structured result handling
    - Operation tracing (for MCP integration)
    """

    def __init__(self, device: ADBDevice, adb_path: str = "adb", trace_id: str = ""):
        self.device = device
        self.adb_path = adb_path
        self.trace_id = trace_id or ""
        self._lock = __import__("threading").Lock()
        self._last_result: ADBResult | None = None
        self._history: list[ADBResult] = []
        self.max_retries = 3
        self.retry_delay_base = 1.0
        self.retry_max_delay = 10.0

    def _build_command(self, operation: ADBOperation, *args, **kwargs) -> ADBCommand:
        return ADBCommand(
            operation=operation,
            device_serial=self.device.serial,
            args=list(args),
            **kwargs
        )

    def _execute(self, command: ADBCommand) -> ADBResult:
        """Execute ADB command with retries."""
        last_error = ""

        for attempt in range(self.max_retries):
            start = time.monotonic()

            # Device validation
            if command.validate_device:
                val = self._validate_device()
                if not val.success:
                    return val

            # Root check
            if command.require_root and not self.device.is_rooted:
                return ADBResult(
                    success=False,
                    operation=command.operation,
                    error="Device not rooted (required for this operation)",
                    return_code=-1,
                )

            cmd = command.to_cmd_list(self.adb_path)
            env = dict(__import__("os").environ, **command.env) if command.env else None

            try:
                if command.stream_output:
                    return self._execute_streaming(command, cmd, env, start)

                proc = subprocess.run(
                    cmd, env=env, capture_output=command.capture_output,
                    text=True, timeout=command.timeout,
                    creationflags=__import__("sys").platform == "win32" and __import__("subprocess").CREATE_NO_WINDOW or 0
                )

                return ADBResult(
                    success=proc.returncode == 0,
                    operation=command.operation,
                    stdout=proc.stdout or "",
                    stderr=proc.stderr or "",
                    return_code=proc.returncode,
                    error=proc.stderr or "" if proc.returncode != 0 else "",
                    duration_ms=(time.monotonic() - start) * 1000,
                )
            except subprocess.TimeoutExpired:
                last_error = f"Timeout after {command.timeout}s"
                logger.warning("[%s] ADB %s attempt %d/%d failed: %s",
                               self.trace_id, command.operation, attempt + 1, self.max_retries, last_error)
            except Exception as e:
                last_error = str(e)
                logger.warning("[%s] ADB %s attempt %d/%d failed: %s",
                               self.trace_id, command.operation, attempt + 1, self.max_retries, last_error)

            # Exponential backoff
            delay = min(self.retry_delay_base * (2 ** attempt), self.retry_max_delay)
            time.sleep(delay)

        return ADBResult(
            success=False, operation=command.operation, error=last_error, return_code=-1
        )

    def _execute_streaming(self, command, cmd, env, start):
        """Execute ADB command with streaming output."""
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
            return ADBResult(
                success=proc.returncode == 0, operation=command.operation,
                stdout=stdout or "", stderr=stderr or "",
                return_code=proc.returncode, lines=lines,
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            lines.extend((stdout or "").strip().splitlines())
            lines.extend((stderr or "").strip().splitlines())
            return ADBResult(
                success=False, operation=command.operation,
                stdout=stdout or "", stderr=stderr or "",
                return_code=-1, lines=lines,
                duration_ms=(time.monotonic() - start) * 1000,
                error="Timeout",
            )

    def _validate_device(self) -> ADBResult:
        """Validate device is connected and responsive."""
        cmd = ADBCommand(operation=ADBOperation.GET_STATE, device_serial=self.device.serial, timeout=5)
        result = self._execute_raw(cmd)
        return result

    def _execute_raw(self, command: ADBCommand) -> ADBResult:
        """Execute without device validation (used by _validate_device)."""
        start = time.monotonic()
        cmd = command.to_cmd_list(self.adb_path)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=command.timeout)
            return ADBResult(
                success=proc.returncode == 0, operation=command.operation,
                stdout=proc.stdout, stderr=proc.stderr, return_code=proc.returncode,
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return ADBResult(success=False, operation=command.operation, error=str(e),
                             return_code=-1, duration_ms=(time.monotonic() - start) * 1000)

    # ============================================================
    # PUBLIC OPERATIONS
    # ============================================================

    def install(self, apk_path: str, replace: bool = True, test: bool = False,
                grant_permissions: bool = False) -> ADBResult:
        """Install APK with options."""
        args = ["-r"] if replace else []
        if test:
            args.append("-t")
        if grant_permissions:
            args.append("-g")
        args.append(apk_path)
        return self._execute(ADBCommand(ADBOperation.INSTALL, self.device.serial, args=args))

    def uninstall(self, package_name: str, keep_data: bool = False) -> ADBResult:
        """Uninstall package."""
        args = ["-k"] if keep_data else []
        args.append(package_name)
        return self._execute(ADBCommand(ADBOperation.UNINSTALL, self.device.serial, args=args))

    def push(self, local_path: str, remote_path: str, verify: bool = True) -> ADBResult:
        """Push file to device."""
        return self._execute(ADBCommand(ADBOperation.PUSH, device_serial=self.device.serial, args=[local_path, remote_path]))

    def pull(self, remote_path: str, local_path: str, verify: bool = True) -> ADBResult:
        """Pull file from device."""
        return self._execute(ADBCommand(ADBOperation.PULL, device_serial=self.device.serial, args=[remote_path, local_path]))

    def shell(self, command: str, timeout: int = 30, require_root: bool = False) -> ADBResult:
        """Execute shell command on device."""
        return self._execute(ADBCommand(ADBOperation.SHELL, self.device.serial, args=[command], timeout=timeout, require_root=require_root))

    def exec_in(self, command: str, stdin_data: str, timeout: int = 30) -> ADBResult:
        """Execute command with stdin."""
        return self._execute(ADBCommand(ADBOperation.EXEC_IN, device_serial=self.device.serial, args=[command, stdin_data], timeout=timeout))

    def exec_out(self, command: str, timeout: int = 30) -> ADBResult:
        """Execute command and capture stdout."""
        return self._execute(ADBCommand(ADBOperation.EXEC_OUT, device_serial=self.device.serial, args=[command], timeout=timeout))

    def reverse(self, remote_port: int, local_port: int) -> ADBResult:
        """Reverse port forwarding."""
        return self._execute(ADBCommand(ADBOperation.REVERSE, self.device.serial, args=[f"tcp:{remote_port}", f"tcp:{local_port}"]))

    def reverse_remove(self, remote_port: int) -> ADBResult:
        """Remove reverse port forwarding."""
        return self._execute(ADBCommand(ADBOperation.REVERSE_REMOVE, self.device.serial, args=[f"tcp:{remote_port}"]))

    def reboot(self, mode: str = "") -> ADBResult:
        """Reboot device. mode: 'recovery', 'bootloader', or '' for normal."""
        return self._execute(ADBCommand(ADBOperation.REBOOT, device_serial=self.device.serial, args=[mode] if mode else []))

    def wait_for_device(self, timeout: int = 60) -> ADBResult:
        """Wait for device to be online."""
        return self._execute(ADBCommand(ADBOperation.WAIT_FOR_DEVICE, device_serial=self.device.serial, timeout=timeout))

    def get_property(self, prop: DeviceProperty) -> ADBResult:
        """Get device property."""
        return self._execute(ADBCommand(ADBOperation.SHELL, device_serial=self.device.serial, args=["getprop", prop.value]))

    # ============================================================
    # COMPOSITE OPERATIONS (LP mobile features)
    # ============================================================

    def check_dexopt_wrapper(self) -> ADBResult:
        """Check if dexopt-wrapper is available on device."""
        return self.shell("which dexopt-wrapper")

    def check_baksmali(self) -> ADBResult:
        """Check if baksmali/smali are available on device."""
        return self.shell("which baksmali && which smali")

    def check_busybox(self) -> ADBResult:
        """Check if busybox is available."""
        return self.shell("busybox --version")

    def check_root_access(self) -> ADBResult:
        """Verify root access with detailed check."""
        return self.shell("su -c 'id'", require_root=True)

    def get_package_info(self, package_name: str) -> ADBResult:
        """Get detailed package info."""
        return self.shell(f"pm dump {package_name}")

    def list_installed_packages(self, filter_user: bool = True) -> ADBResult:
        """List all installed packages."""
        cmd = "pm list packages"
        if filter_user:
            cmd += " -3"  # Third-party only
        return self.shell(cmd)

    def grant_permissions(self, package_name: str, *permissions: str) -> ADBResult:
        """Grant runtime permissions to package."""
        if not permissions:
            return ADBResult(success=False, operation=ADBOperation.SHELL, error="No permissions specified")
        return self.shell(f"pm grant {package_name} {' '.join(permissions)}")

    def revoke_permissions(self, package_name: str, *permissions: str) -> ADBResult:
        """Revoke runtime permissions from package."""
        if not permissions:
            return ADBResult(success=False, operation=ADBOperation.SHELL, error="No permissions specified")
        return self.shell(f"pm revoke {package_name} {' '.join(permissions)}")

    def clear_app_data(self, package_name: str) -> ADBResult:
        """Clear app data (requires root for system apps)."""
        return self.shell(f"pm clear {package_name}")

    def force_stop(self, package_name: str) -> ADBResult:
        """Force stop package."""
        return self.shell(f"am force-stop {package_name}")

    def start_activity(self, package_name: str, activity_name: str, *extras) -> ADBResult:
        """Start activity with intent extras."""
        intent = f"am start -n {package_name}/{activity_name}"
        for extra in extras:
            intent += f" {extra}"
        return self.shell(intent)

    def send_broadcast(self, action: str, *extras) -> ADBResult:
        """Send broadcast intent."""
        intent = f"am broadcast -a {action}"
        for extra in extras:
            intent += f" {extra}"
        return self.shell(intent)

    # ============================================================
    # TRACE / METRICS
    # ============================================================

    def get_last_result(self) -> ADBResult | None:
        return self._last_result

    def get_history(self) -> list[ADBResult]:
        return self._history.copy()

    def clear_history(self) -> None:
        self._history.clear()

    def _record_result(self, result: ADBResult) -> ADBResult:
        self._last_result = result
        self._history.append(result)
        return result

    # Override _execute to record
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        # This allows orchestrator.trace("text") style calls
        return lambda *a, **kw: self._record_result(object.__getattribute__(self, name)(*a, **kw))
