"""
ADB Shell — interactive and non-interactive shell execution with streaming.
"""
from __future__ import annotations

import contextlib
import logging
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ADBShellResult:
    """Result of ADB shell command."""
    success: bool
    command: str
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    error: str = ""
    duration_ms: float = 0.0
    lines: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.success

    @property
    def output(self) -> str:
        return self.stdout

    def get_lines(self) -> Iterator[str]:
        return iter(self.lines)


@dataclass
class ADBShellStream:
    """Streaming shell session with stdin/stdout/stderr pipes."""
    process: subprocess.Popen
    stdin: Callable[[str], None] | None = None
    stdout: Iterator[str] | None = None
    stderr: Iterator[str] | None = None
    closed: bool = False

    def write(self, data: str) -> bool:
        """Write to stdin."""
        if self.closed or not self.process.stdin:
            return False
        try:
            self.process.stdin.write(data)
            self.process.stdin.flush()
            return True
        except Exception:
            return False

    def read_stdout(self) -> str | None:
        """Read line from stdout."""
        if self.closed or not self.process.stdout:
            return None
        try:
            return self.process.stdout.readline()
        except Exception:
            return None

    def read_stderr(self) -> str | None:
        """Read line from stderr."""
        if self.closed or not self.process.stderr:
            return None
        try:
            return self.process.stderr.readline()
        except Exception:
            return None

    def close(self) -> int:
        """Close shell and return exit code."""
        if self.closed:
            return -1
        self.closed = True
        if self.process.stdin is not None:
            with contextlib.suppress(Exception):
                self.process.stdin.close()
        try:
            return self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            return -1


class ADBShell:
    """ADB shell executor with streaming support."""

    def __init__(self, device_serial: str, adb_path: str = "adb", default_timeout: int = 30):
        self.device_serial = device_serial
        self.adb_path = adb_path
        self.default_timeout = default_timeout

    def execute(self, command: str, timeout: int | None = None, capture_output: bool = True,
                require_root: bool = False, env: dict[str, str] | None = None) -> ADBShellResult:
        """Execute shell command non-interactively."""
        timeout = timeout or self.default_timeout
        start = time.monotonic()

        cmd = [self.adb_path, "-s", self.device_serial, "shell"]
        if require_root:
            cmd.append("su -c")
        cmd.append(command)

        env = dict(__import__("os").environ, **(env or {}))

        try:
            proc = subprocess.run(
                cmd, capture_output=capture_output, text=True, timeout=timeout, env=env,
                creationflags=self._creation_flags()
            )
            return ADBShellResult(
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
            return ADBShellResult(
                success=False, command=command, return_code=-1, error="Timeout",
                lines=(str(e.stdout).strip().splitlines() if getattr(e, "stdout", None) else []),
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return ADBShellResult(success=False, command=command, return_code=-1, error=str(e),
                                duration_ms=(time.monotonic() - start) * 1000)

    def execute_streaming(self, command: str, timeout: int | None = None,
                          require_root: bool = False,
                          on_stdout: Callable[[str], None] | None = None,
                          on_stderr: Callable[[str], None] | None = None) -> ADBShellResult:
        """Execute shell command with streaming output callbacks."""
        timeout = timeout or self.default_timeout
        start = time.monotonic()

        cmd = [self.adb_path, "-s", self.device_serial, "shell"]
        if require_root:
            cmd.append("su -c")
        cmd.append(command)

        lines = []

        def _stdout_reader(pipe, callback):
            try:
                for line in iter(pipe.readline, ''):
                    if not line:
                        break
                    line = line.rstrip('\n')
                    lines.append(line)
                    if callback:
                        with contextlib.suppress(Exception):
                            callback(line)
            finally:
                pipe.close()

        def _stderr_reader(pipe, callback):
            try:
                for line in iter(pipe.readline, ''):
                    if not line:
                        break
                    if callback:
                        with contextlib.suppress(Exception):
                            callback(line.rstrip('\n'))
            finally:
                pipe.close()

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
                creationflags=self._creation_flags()
            )

            stdout_thread = threading.Thread(target=_stdout_reader, args=(proc.stdout, on_stdout))
            stderr_thread = threading.Thread(target=_stderr_reader, args=(proc.stderr, on_stderr))
            stdout_thread.daemon = True
            stderr_thread.daemon = True
            stdout_thread.start()
            stderr_thread.start()

            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_thread.join(timeout=1)
                stderr_thread.join(timeout=1)
                return ADBShellResult(
                    success=False, command=command, return_code=-1, error="Timeout",
                    lines=lines, duration_ms=(time.monotonic() - start) * 1000,
                )

            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)

            return ADBShellResult(
                success=proc.returncode == 0,
                command=command,
                stdout="\n".join(lines),
                stderr="",  # Already streamed
                return_code=proc.returncode,
                error="" if proc.returncode == 0 else "Non-zero exit",
                lines=lines,
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return ADBShellResult(success=False, command=command, return_code=-1, error=str(e),
                                duration_ms=(time.monotonic() - start) * 1000)

    def open_session(self, command: str = "sh", require_root: bool = False) -> ADBShellStream:
        """Open interactive shell session."""
        cmd = [self.adb_path, "-s", self.device_serial, "shell"]
        if require_root:
            cmd.append("su")
        cmd.append(command)

        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
            creationflags=self._creation_flags()
        )

        def _write_stdin(data: str):
            if proc.stdin is None:
                return
            try:
                proc.stdin.write(data)
                proc.stdin.flush()
            except Exception:
                pass

        def _stdout_iter():
            try:
                for line in iter(proc.stdout.readline, ''):
                    yield line.rstrip('\n')
            finally:
                proc.stdout.close()

        def _stderr_iter():
            try:
                for line in iter(proc.stderr.readline, ''):
                    yield line.rstrip('\n')
            finally:
                proc.stderr.close()

        return ADBShellStream(
            process=proc,
            stdin=_write_stdin,
            stdout=_stdout_iter(),
            stderr=_stderr_iter(),
        )

    def execute_multiple(self, commands: list[str], timeout: int | None = None,
                         require_root: bool = False, stop_on_error: bool = True) -> list[ADBShellResult]:
        """Execute multiple shell commands sequentially."""
        results = []
        for cmd in commands:
            result = self.execute(cmd, timeout, require_root=require_root)
            results.append(result)
            if stop_on_error and not result.success:
                break
        return results

    def execute_script(self, script_content: str, timeout: int | None = None,
                       require_root: bool = False) -> ADBShellResult:
        """Execute multi-line script by piping to shell."""
        timeout = timeout or self.default_timeout * 2
        start = time.monotonic()

        cmd = [self.adb_path, "-s", self.device_serial, "shell"]
        if require_root:
            cmd.append("su")

        try:
            proc = subprocess.run(
                cmd, input=script_content, capture_output=True, text=True, timeout=timeout,
                creationflags=self._creation_flags()
            )
            return ADBShellResult(
                success=proc.returncode == 0,
                command=f"script ({len(script_content)} chars)",
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                return_code=proc.returncode,
                error=proc.stderr or "" if proc.returncode != 0 else "",
                lines=(proc.stdout or "").strip().splitlines(),
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except subprocess.TimeoutExpired:
            return ADBShellResult(success=False, command="script", return_code=-1, error="Timeout",
                                duration_ms=(time.monotonic() - start) * 1000)
        except Exception as e:
            return ADBShellResult(success=False, command="script", return_code=-1, error=str(e),
                                duration_ms=(time.monotonic() - start) * 1000)

    def execute_script_streaming(self, script_content: str, timeout: int | None = None,
                                 require_root: bool = False,
                                 on_stdout: Callable[[str], None] | None = None,
                                 on_stderr: Callable[[str], None] | None = None) -> ADBShellResult:
        """Execute script with streaming output."""
        timeout = timeout or self.default_timeout * 2
        start = time.monotonic()

        cmd = [self.adb_path, "-s", self.device_serial, "shell"]
        if require_root:
            cmd.append("su")

        lines = []

        def _stdout_reader(pipe, callback):
            try:
                for line in iter(pipe.readline, ''):
                    if not line:
                        break
                    line = line.rstrip('\n')
                    lines.append(line)
                    if callback:
                        with contextlib.suppress(Exception):
                            callback(line)
            finally:
                pipe.close()

        def _stderr_reader(pipe, callback):
            try:
                for line in iter(pipe.readline, ''):
                    if not line:
                        break
                    if callback:
                        with contextlib.suppress(Exception):
                            callback(line.rstrip('\n'))
            finally:
                pipe.close()

        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
                creationflags=self._creation_flags()
            )

            # Write script to stdin
            if proc.stdin:
                proc.stdin.write(script_content)
                proc.stdin.close()

            stdout_thread = threading.Thread(target=_stdout_reader, args=(proc.stdout, on_stdout))
            stderr_thread = threading.Thread(target=_stderr_reader, args=(proc.stderr, on_stderr))
            stdout_thread.daemon = True
            stderr_thread.daemon = True
            stdout_thread.start()
            stderr_thread.start()

            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_thread.join(timeout=1)
                stderr_thread.join(timeout=1)
                return ADBShellResult(success=False, command="script", return_code=-1, error="Timeout",
                                    lines=lines, duration_ms=(time.monotonic() - start) * 1000)

            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)

            return ADBShellResult(
                success=proc.returncode == 0, command="script",
                stdout="\n".join(lines), return_code=proc.returncode,
                error="" if proc.returncode == 0 else "Non-zero exit",
                lines=lines, duration_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return ADBShellResult(success=False, command="script", return_code=-1, error=str(e),
                                duration_ms=(time.monotonic() - start) * 1000)

    def _creation_flags(self) -> int:
        return __import__("sys").platform == "win32" and __import__("subprocess").CREATE_NO_WINDOW or 0

    # Convenience methods for common shell operations

    def ls(self, path: str = "/", long: bool = True, all_files: bool = False) -> ADBShellResult:
        """List directory contents."""
        flags = []
        if long:
            flags.append("-l")
        if all_files:
            flags.append("-a")
        cmd = f"ls {' '.join(flags)} {path}"
        return self.execute(cmd)

    def cat(self, file_path: str) -> ADBShellResult:
        """Read file contents."""
        return self.execute(f"cat {file_path}")

    def echo(self, text: str, file_path: str | None = None, append: bool = False) -> ADBShellResult:
        """Write text to file or stdout."""
        if file_path:
            op = ">>" if append else ">"
            return self.execute(f'echo "{text}" {op} {file_path}')
        return self.execute(f'echo "{text}"')

    def mkdir(self, path: str, parents: bool = True) -> ADBShellResult:
        """Create directory."""
        flags = "-p" if parents else ""
        return self.execute(f"mkdir {flags} {path}")

    def rm(self, path: str, recursive: bool = False, force: bool = True) -> ADBShellResult:
        """Remove file or directory."""
        flags = []
        if recursive:
            flags.append("-r")
        if force:
            flags.append("-f")
        return self.execute(f"rm {' '.join(flags)} {path}")

    def cp(self, src: str, dst: str, recursive: bool = False) -> ADBShellResult:
        """Copy file or directory."""
        flags = "-r" if recursive else ""
        return self.execute(f"cp {flags} {src} {dst}")

    def mv(self, src: str, dst: str) -> ADBShellResult:
        """Move/rename file or directory."""
        return self.execute(f"mv {src} {dst}")

    def chmod(self, mode: str, path: str, recursive: bool = False) -> ADBShellResult:
        """Change file permissions."""
        flags = "-R" if recursive else ""
        return self.execute(f"chmod {flags} {mode} {path}")

    def chown(self, owner: str, path: str, recursive: bool = False) -> ADBShellResult:
        """Change file owner."""
        flags = "-R" if recursive else ""
        return self.execute(f"chown {flags} {owner} {path}")

    def find(self, path: str, pattern: str = "*", type_filter: str | None = None) -> ADBShellResult:
        """Find files matching pattern."""
        cmd = f"find {path} -name '{pattern}'"
        if type_filter:
            cmd += f" -type {type_filter}"
        return self.execute(cmd)

    def grep(self, pattern: str, file_path: str, recursive: bool = False,
             ignore_case: bool = False) -> ADBShellResult:
        """Search for pattern in file(s)."""
        flags = []
        if recursive:
            flags.append("-r")
        if ignore_case:
            flags.append("-i")
        return self.execute(f"grep {' '.join(flags)} '{pattern}' {file_path}")

    def stat(self, path: str, format_str: str = "%s") -> ADBShellResult:
        """Get file status."""
        return self.execute(f"stat -c '{format_str}' {path}")

    def which(self, command: str) -> ADBShellResult:
        """Find executable in PATH."""
        return self.execute(f"which {command}")

    def getprop(self, prop: str) -> ADBShellResult:
        """Get system property."""
        return self.execute(f"getprop {prop}")

    def setprop(self, prop: str, value: str) -> ADBShellResult:
        """Set system property (requires root)."""
        return self.execute(f"setprop {prop} {value}", require_root=True)

    def pm(self, subcommand: str, *args) -> ADBShellResult:
        """Package manager command."""
        return self.execute(f"pm {subcommand} {' '.join(args)}")

    def am(self, subcommand: str, *args) -> ADBShellResult:
        """Activity manager command."""
        return self.execute(f"am {subcommand} {' '.join(args)}")

    def dumpsys(self, service: str) -> ADBShellResult:
        """Dump system service info."""
        return self.execute(f"dumpsys {service}")

    def logcat(self, filter_spec: str = "*:V", lines: int | None = None) -> ADBShellResult:
        """Get logcat output."""
        cmd = "logcat -d"
        if lines:
            cmd += f" -t {lines}"
        cmd += f" {filter_spec}"
        return self.execute(cmd)

    def su(self, command: str) -> ADBShellResult:
        """Execute command as root."""
        return self.execute(command, require_root=True)

    def check_root(self) -> ADBShellResult:
        """Check if root access is available."""
        return self.execute("id", require_root=True)


@contextlib.contextmanager
def adb_shell(device_serial: str, adb_path: str = "adb"):
    """Context manager for ADB shell."""
    yield ADBShell(device_serial, adb_path)
