"""
Real compile test — chạy `smali.jar` thật lên generated smali.

Khác với `test_xposed_generator_compilability.py` (regex check label),
test này:
  1. Generate Xposed module → smali files
  2. Compile Xposed API stub Java → .class (dùng javac)
  3. Assemble smali với `smali.jar` → .dex
  4. Assert .dex > 0 bytes + DEX magic bytes

Skips gracefully nếu:
  - `javac` không có trong PATH
  - `tools/bin/smali.jar` không tồn tại
  - Stub compile fail (skip với reason rõ)

Catch:
  - Label collision (như bug :try_start_0 đã fix)
  - Register out of bounds
  - Invalid opcode / class descriptor
  - Instruction format lỗi (.registers mismatch)
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from core.xposed_generator import (
    XposedModuleConfig,
    XposedModuleGenerator,
)

# Paths
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SMALI_JAR = _REPO_ROOT / "tools" / "bin" / "smali.jar"
_JAVAC = shutil.which("javac")
_JAVA = shutil.which("java")


def _have_toolchain() -> bool:
    """Check đủ java + javac + smali.jar."""
    return (
        _JAVA is not None
        and _JAVAC is not None
        and _SMALI_JAR.exists()
    )


pytestmark = pytest.mark.skipif(
    not _have_toolchain(),
    reason="Need java + javac + tools/bin/smali.jar",
)


# ============================================================
# XPOSED API STUB — minimal subset để smali resolve superclass
# ============================================================
_STUB_XC_METHOD_HOOK = """
package de.robv.android.xposed;

public abstract class XC_MethodHook {
    public static class MethodHookParam {
        public Object thisObject;
        public Object[] args;
        public Object getResult() { return null; }
        public void setResult(Object result) {}
    }

    public class Unhook {
        public void unhook() {}
    }

    protected void beforeHookedMethod(MethodHookParam param) throws Throwable {}
    protected void afterHookedMethod(MethodHookParam param) throws Throwable {}
}
"""

_STUB_XPOSED_HELPERS = """
package de.robv.android.xposed;

public class XposedHelpers {
    public static Class<?> findClass(String className, ClassLoader cl) {
        return null;
    }
    public static Object callMethod(Object obj, String method, Object... args) {
        return null;
    }
}
"""

_STUB_XPOSED_BRIDGE = """
package de.robv.android.xposed;

import java.util.Set;

public class XposedBridge {
    public static Set<XC_MethodHook.Unhook> hookAllMethods(
            Class<?> clazz, String methodName, XC_MethodHook callback) {
        return null;
    }
}
"""

_STUB_IXPOSED_HOOK_LOAD = """
package de.robv.android.xposed;

public interface IXposedHookLoadPackage {
    void handleLoadPackage(
        de.robv.android.xposed.callbacks.XC_LoadPackage.LoadPackageParam lpparam
    ) throws Throwable;
}
"""

_STUB_IXPOSED_HOOK_ZYGOTE = """
package de.robv.android.xposed;

public interface IXposedHookZygoteInit {
    void initZygote(StartupParam startupParam) throws Throwable;
    class StartupParam {
        public String modulePath;
    }
}
"""

_STUB_XC_LOAD_PACKAGE = """
package de.robv.android.xposed.callbacks;

public class XC_LoadPackage {
    public static class LoadPackageParam {
        public String packageName;
        public ClassLoader classLoader;
    }
}
"""


def _write_stub_tree(stub_root: Path) -> list[Path]:
    """Ghi tất cả stub Java files, return list paths."""
    base = stub_root / "de" / "robv" / "android" / "xposed"
    (base / "callbacks").mkdir(parents=True, exist_ok=True)

    files = {
        base / "XC_MethodHook.java": _STUB_XC_METHOD_HOOK,
        base / "XposedHelpers.java": _STUB_XPOSED_HELPERS,
        base / "XposedBridge.java": _STUB_XPOSED_BRIDGE,
        base / "IXposedHookLoadPackage.java": _STUB_IXPOSED_HOOK_LOAD,
        base / "IXposedHookZygoteInit.java": _STUB_IXPOSED_HOOK_ZYGOTE,
        base / "callbacks" / "XC_LoadPackage.java": _STUB_XC_LOAD_PACKAGE,
    }
    paths: list[Path] = []
    for path, content in files.items():
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths


def _compile_stubs(java_files: list[Path], out_dir: Path) -> tuple[bool, str]:
    """
    javac compile → .class files trong out_dir.
    Return (ok, stderr). Không dùng -source/-target để tránh conflict JDK 21+.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(_JAVAC),
        "-d", str(out_dir),
        *[str(p) for p in java_files],
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, f"subprocess: {e}"
    return proc.returncode == 0, proc.stderr


def _assemble_smali(smali_dir: Path, out_dex: Path) -> tuple[bool, str]:
    """
    Assemble smali_dir → out_dex, thử nhiều CLI variant để tương thích
    smali 2.x và 3.x.

    Return (ok, detail). Detail chứa output của variant thành công,
    hoặc tổng hợp lỗi của mọi variant khi fail.
    """
    variants: list[list[str]] = [
        # v1: subcommand + short flags, -o trước input
        ["assemble", "-a", "24", "-o", str(out_dex), str(smali_dir)],
        # v2: subcommand + long flags, --output= form
        ["assemble", "--api", "24",
         f"--output={out_dex}", str(smali_dir)],
        # v3: subcommand + short flags, input trước -o
        ["assemble", "-a", "24", str(smali_dir), "-o", str(out_dex)],
        # v4: không subcommand (smali 2.x style)
        ["-a", "24", "-o", str(out_dex), str(smali_dir)],
        # v5: bare (chỉ input, in-place heuristic)
        ["assemble", "-a", "24", str(smali_dir)],
    ]

    errors: list[str] = []
    for idx, args in enumerate(variants, 1):
        cmd = [str(_JAVA), "-jar", str(_SMALI_JAR), *args]
        # Cleanup trước mỗi variant
        if out_dex.exists():
            try:
                out_dex.unlink()
            except OSError:
                pass

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            errors.append(f"v{idx} {args[:2]}: subprocess {e}")
            continue

        out_combined = (
            (proc.stdout or "")
            + "\n-- STDERR --\n"
            + (proc.stderr or "")
        )

        if proc.returncode == 0 and out_dex.exists():
            size = out_dex.stat().st_size
            return True, (
                f"v{idx} OK (size={size})\n"
                f"cmd: {' '.join(cmd)}\n"
                f"{out_combined[:500]}"
            )

        errors.append(
            f"v{idx} rc={proc.returncode} "
            f"dex_exists={out_dex.exists()}\n"
            f"  cmd: {' '.join(cmd)}\n"
            f"  out: {out_combined[:400]}"
        )

    return False, "\n---\n".join(errors)


# ============================================================
# FIXTURES
# ============================================================
@pytest.fixture(scope="module")
def stub_classes(tmp_path_factory) -> Path:
    """Compile stub Java → .class tree, chia sẻ giữa các test."""
    root = tmp_path_factory.mktemp("xposed_stubs")
    java_root = root / "java"
    classes_root = root / "classes"
    java_files = _write_stub_tree(java_root)
    ok, stderr = _compile_stubs(java_files, classes_root)
    if not ok:
        pytest.skip(f"javac failed: {stderr[:500]}")
    return classes_root


# ============================================================
# DEBUG — smali CLI probe (không assert, chỉ print)
# ============================================================
class TestSmaliCLIProbe:
    def test_smali_help_output(self, capsys):
        """Print smali --help → xem syntax để debug."""
        for args in (
            ["--help"],
            ["-h"],
            ["assemble", "--help"],
            ["help", "assemble"],
        ):
            try:
                proc = subprocess.run(
                    [str(_JAVA), "-jar", str(_SMALI_JAR), *args],
                    capture_output=True, text=True, timeout=30,
                )
                print(f"\n=== smali {' '.join(args)} ===")
                print(f"rc={proc.returncode}")
                print("STDOUT:", (proc.stdout or "")[:2000])
                print("STDERR:", (proc.stderr or "")[:2000])
            except Exception as e:
                print(f"\n=== smali {' '.join(args)} raised {e} ===")


# ============================================================
# TESTS
# ============================================================
class TestRealCompile:
    """Compile generated smali thật với smali.jar."""

    def test_iap_module_compiles(self, tmp_path, stub_classes):
        """IAP = 4 targets → test label collision fix."""
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["iap"])
        out = tmp_path / "module"
        result = gen.generate(cfg, str(out))
        assert result.is_valid, f"generator failed: {result.errors}"

        smali_dir = out / "smali"
        dex_out = tmp_path / "classes.dex"
        ok, detail = _assemble_smali(smali_dir, dex_out)

        assert ok, f"smali.jar failed on all variants:\n{detail}"
        assert dex_out.exists()
        assert dex_out.stat().st_size > 0
        with open(dex_out, "rb") as f:
            magic = f.read(4)
        assert magic == b"dex\n"

    def test_all_hooks_compile(self, tmp_path, stub_classes):
        """4 hooks cùng lúc — full stress cho label + register."""
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(
            hooks=["iap", "license", "signature", "install"],
        )
        out = tmp_path / "module"
        result = gen.generate(cfg, str(out))
        assert result.is_valid

        smali_dir = out / "smali"
        dex_out = tmp_path / "classes.dex"
        ok, detail = _assemble_smali(smali_dir, dex_out)
        assert ok, f"smali.jar failed:\n{detail}"
        assert dex_out.stat().st_size > 0

    def test_signature_spoof_compiles(self, tmp_path, stub_classes):
        """Signature hook dùng after_signature_spoof template."""
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["signature"])
        out = tmp_path / "module"
        gen.generate(cfg, str(out))

        smali_dir = out / "smali"
        dex_out = tmp_path / "classes.dex"
        ok, detail = _assemble_smali(smali_dir, dex_out)
        assert ok, f"smali.jar failed:\n{detail}"
        assert dex_out.stat().st_size > 0

    def test_no_target_package_compiles(self, tmp_path, stub_classes):
        """Không có target package → entry dùng path không filter."""
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(hooks=["iap"], target_package="")
        out = tmp_path / "module"
        gen.generate(cfg, str(out))

        smali_dir = out / "smali"
        dex_out = tmp_path / "classes.dex"
        ok, detail = _assemble_smali(smali_dir, dex_out)
        assert ok, f"smali.jar failed:\n{detail}"
        assert dex_out.exists()
        assert dex_out.stat().st_size > 0

    def test_entry_class_in_dex(self, tmp_path, stub_classes):
        """Verify XposedEntry class có trong output dex."""
        gen = XposedModuleGenerator(log_callback=lambda *a: None)
        cfg = XposedModuleConfig(
            hooks=["iap"], target_package="com.example.app",
        )
        out = tmp_path / "module"
        gen.generate(cfg, str(out))

        smali_dir = out / "smali"
        dex_out = tmp_path / "classes.dex"
        ok, detail = _assemble_smali(smali_dir, dex_out)
        assert ok, f"smali.jar failed:\n{detail}"

        data = dex_out.read_bytes()
        assert b"XposedEntry" in data, "XposedEntry not in dex"
        assert b"com/lppc/xposed/hooks" in data, "package not in dex"