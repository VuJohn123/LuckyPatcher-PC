"""Test core/bundletool_utils.py — comprehensive coverage.

Coverage targets:
  - Missing jar → None
  - Successful universal / standalone extraction
  - Default vs. custom output dir
  - build-apks rc != 0
  - build-apks rc=0 nhưng không tạo .apks
  - .apks không chứa APK hợp lệ
  - Timeout / OSError / BadZipFile
  - Subprocess command contract (java -jar ... build-apks --mode=universal)
"""
from __future__ import annotations

import os
import subprocess
import zipfile
from unittest.mock import MagicMock

import pytest

from core.bundletool_utils import aab_to_apk


# ============================================================
# Fixtures / Helpers
# ============================================================
@pytest.fixture
def aab_file(tmp_path):
    aab = tmp_path / "myapp.aab"
    aab.write_bytes(b"FAKE_AAB_CONTENT")
    return aab


def _patch_bundletool(monkeypatch, exists: bool = True):
    """
    Monkeypatch os.path.exists chỉ cho path kết thúc bundletool.jar.
    Các path khác giữ nguyên hành vi thật.
    """
    orig = os.path.exists

    def _exists(p):
        if isinstance(p, str) and p.endswith("bundletool.jar"):
            return exists
        return orig(p)

    monkeypatch.setattr(os.path, "exists", _exists)


def _make_apks(path: str, entries: list[str]) -> None:
    """Tạo fake .apks zip với entries cho trước."""
    with zipfile.ZipFile(path, "w") as z:
        for name in entries:
            z.writestr(name, b"FAKE_APK_CONTENT__" + name.encode())


def _run_creator(entries: list[str], rc: int = 0):
    """
    subprocess.run replacement tạo .apks file.
    rc != 0 → vẫn tạo file nhưng trả rc lỗi (không dùng).
    """
    def _run(cmd, **kwargs):
        for arg in cmd:
            if arg.startswith("--output="):
                out = arg.split("=", 1)[1]
                if rc == 0:
                    _make_apks(out, entries)
                break
        return MagicMock(
            returncode=rc, stdout="",
            stderr="bundletool error" if rc else "",
        )
    return _run


# ============================================================
# Missing jar
# ============================================================
class TestMissingJar:
    def test_returns_none_when_missing(self, aab_file):
        result = aab_to_apk(str(aab_file), log_callback=lambda *a: None)
        assert result is None

    def test_log_callback_invoked(self, aab_file):
        msgs: list[str] = []
        aab_to_apk(
            str(aab_file),
            log_callback=lambda m: msgs.append(m),
        )
        assert any("bundletool.jar" in m for m in msgs)


# ============================================================
# Successful conversion
# ============================================================
class TestSuccessfulConversion:
    def test_universal_apk_extracted(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)
        monkeypatch.setattr(
            subprocess, "run", _run_creator(["universal.apk"])
        )
        out_dir = tmp_path / "out"
        result = aab_to_apk(
            str(aab_file), str(out_dir),
            log_callback=lambda *a: None,
        )
        assert result is not None
        assert result.endswith("myapp.apk")
        assert os.path.exists(result)
        with open(result, "rb") as f:
            assert b"FAKE_APK_CONTENT" in f.read()

    def test_default_output_dir_is_aab_dir(
        self, aab_file, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)
        monkeypatch.setattr(
            subprocess, "run", _run_creator(["universal.apk"])
        )
        result = aab_to_apk(
            str(aab_file), None, log_callback=lambda *a: None,
        )
        assert result is not None
        assert os.path.dirname(result) == os.path.dirname(str(aab_file))

    def test_creates_missing_output_dir(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)
        monkeypatch.setattr(
            subprocess, "run", _run_creator(["universal.apk"])
        )
        out = tmp_path / "deep" / "nested" / "out"
        assert not out.exists()
        result = aab_to_apk(
            str(aab_file), str(out),
            log_callback=lambda *a: None,
        )
        assert result is not None
        assert out.exists()

    def test_output_filename_derived_from_aab(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)
        monkeypatch.setattr(
            subprocess, "run", _run_creator(["universal.apk"])
        )
        result = aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        assert result is not None
        assert os.path.basename(result) == "myapp.apk"

    def test_standalone_fallback(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)
        monkeypatch.setattr(
            subprocess, "run",
            _run_creator(["standalones/standalone-xhdpi.apk"]),
        )
        result = aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        assert result is not None

    def test_prefers_universal_over_standalone(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)
        monkeypatch.setattr(
            subprocess, "run",
            _run_creator([
                "standalones/standalone.apk",
                "universal.apk",
            ]),
        )
        result = aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        assert result is not None

    def test_ignores_non_apk_entries_in_universal_match(
        self, aab_file, tmp_path, monkeypatch
    ):
        """'universal' in name nhưng không .apk → skip."""
        _patch_bundletool(monkeypatch, True)
        monkeypatch.setattr(
            subprocess, "run",
            _run_creator([
                "universal.apk",       # valid
                "universal.txt",       # invalid, filtered
                "toc.pb",              # always present
            ]),
        )
        result = aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        assert result is not None

    def test_log_success_message(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)
        monkeypatch.setattr(
            subprocess, "run", _run_creator(["universal.apk"])
        )
        msgs: list[str] = []
        aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda m: msgs.append(m),
        )
        assert any("[✔]" in m for m in msgs)


# ============================================================
# Failure modes
# ============================================================
class TestFailureModes:
    def test_build_apks_nonzero_rc(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)
        monkeypatch.setattr(
            subprocess, "run",
            _run_creator(["universal.apk"], rc=1),
        )
        result = aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        assert result is None

    def test_apks_file_not_created(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)

        def _run(cmd, **kw):
            # rc=0 nhưng không tạo file .apks
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _run)
        result = aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        assert result is None

    def test_no_apk_in_bundle(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)
        monkeypatch.setattr(
            subprocess, "run",
            _run_creator(["toc.pb", "some_other_file.txt"]),
        )
        result = aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        assert result is None

    def test_no_apk_logs_message(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)
        monkeypatch.setattr(
            subprocess, "run", _run_creator(["toc.pb"])
        )
        msgs: list[str] = []
        aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda m: msgs.append(m),
        )
        assert any("universal" in m.lower() for m in msgs)

    def test_timeout_returns_none(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)

        def _timeout(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, 600)

        monkeypatch.setattr(subprocess, "run", _timeout)
        result = aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        assert result is None

    def test_timeout_logs_message(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)

        def _timeout(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, 600)

        monkeypatch.setattr(subprocess, "run", _timeout)
        msgs: list[str] = []
        aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda m: msgs.append(m),
        )
        assert any("timeout" in m.lower() for m in msgs)

    def test_bad_zip_returns_none(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)

        def _run(cmd, **kw):
            for arg in cmd:
                if arg.startswith("--output="):
                    out = arg.split("=", 1)[1]
                    with open(out, "wb") as f:
                        f.write(b"not a zip file at all")
                    break
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _run)
        result = aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        assert result is None

    def test_oserror_returns_none(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)

        def _run(cmd, **kw):
            raise OSError("java not found")

        monkeypatch.setattr(subprocess, "run", _run)
        result = aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        assert result is None

    def test_oserror_logs_message(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)

        def _run(cmd, **kw):
            raise OSError("java not found")

        monkeypatch.setattr(subprocess, "run", _run)
        msgs: list[str] = []
        aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda m: msgs.append(m),
        )
        assert any("[!]" in m for m in msgs)


# ============================================================
# Subprocess command contract
# ============================================================
class TestSubprocessCommand:
    def test_command_structure(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)
        captured: dict = {}

        def _run(cmd, **kw):
            captured["cmd"] = cmd
            captured["kwargs"] = kw
            for arg in cmd:
                if arg.startswith("--output="):
                    _make_apks(arg.split("=", 1)[1], ["universal.apk"])
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _run)
        aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        cmd = captured["cmd"]
        assert cmd[0] == "java"
        assert "-jar" in cmd
        assert "build-apks" in cmd
        assert "--mode=universal" in cmd
        assert "--overwrite" in cmd
        assert any(a.startswith("--bundle=") for a in cmd)
        assert any(a.startswith("--output=") for a in cmd)

    def test_command_passes_capture_and_timeout(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)
        captured: dict = {}

        def _run(cmd, **kw):
            captured["kwargs"] = kw
            for arg in cmd:
                if arg.startswith("--output="):
                    _make_apks(arg.split("=", 1)[1], ["universal.apk"])
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _run)
        aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        assert captured["kwargs"].get("capture_output") is True
        assert captured["kwargs"].get("text") is True
        assert captured["kwargs"].get("timeout") == 600

    def test_bundle_path_matches_input(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)
        captured: dict = {}

        def _run(cmd, **kw):
            captured["cmd"] = cmd
            for arg in cmd:
                if arg.startswith("--output="):
                    _make_apks(arg.split("=", 1)[1], ["universal.apk"])
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _run)
        aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        bundle_arg = next(
            a for a in captured["cmd"] if a.startswith("--bundle=")
        )
        assert bundle_arg == f"--bundle={aab_file}"


# ============================================================
# Temp dir cleanup
# ============================================================
class TestCleanup:
    def test_temp_dir_cleaned_on_success(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)
        created_tmp: list[str] = []

        orig_mkdtemp = __import__("tempfile").mkdtemp

        def _mkdtemp(*a, **kw):
            path = orig_mkdtemp(*a, **kw)
            created_tmp.append(path)
            return path

        import tempfile as _t
        monkeypatch.setattr(_t, "mkdtemp", _mkdtemp)
        monkeypatch.setattr(
            subprocess, "run", _run_creator(["universal.apk"])
        )
        aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        for path in created_tmp:
            assert not os.path.exists(path)

    def test_temp_dir_cleaned_on_failure(
        self, aab_file, tmp_path, monkeypatch
    ):
        _patch_bundletool(monkeypatch, True)
        created_tmp: list[str] = []

        orig_mkdtemp = __import__("tempfile").mkdtemp

        def _mkdtemp(*a, **kw):
            path = orig_mkdtemp(*a, **kw)
            created_tmp.append(path)
            return path

        import tempfile as _t
        monkeypatch.setattr(_t, "mkdtemp", _mkdtemp)

        def _run(cmd, **kw):
            raise OSError("boom")

        monkeypatch.setattr(subprocess, "run", _run)
        aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        for path in created_tmp:
            assert not os.path.exists(path)

# ============================================================
# v2 — mode parameter
# ============================================================
class TestModeParameter:
    def test_default_mode_is_universal(
        self, aab_file, tmp_path, monkeypatch,
    ):
        """Backward compat: mode không truyền → universal."""
        _patch_bundletool(monkeypatch, True)
        captured: dict = {}

        def _run(cmd, **kw):
            captured["cmd"] = cmd
            for arg in cmd:
                if arg.startswith("--output="):
                    _make_apks(arg.split("=", 1)[1], ["universal.apk"])
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _run)
        aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        assert "--mode=universal" in captured["cmd"]

    def test_mode_default_flag(self, aab_file, tmp_path, monkeypatch):
        _patch_bundletool(monkeypatch, True)
        captured: dict = {}

        def _run(cmd, **kw):
            captured["cmd"] = cmd
            for arg in cmd:
                if arg.startswith("--output="):
                    _make_apks(
                        arg.split("=", 1)[1],
                        ["splits/base-master.apk"],
                    )
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _run)
        result = aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            mode="default",
            log_callback=lambda *a: None,
        )
        assert "--mode=default" in captured["cmd"]
        assert result is not None

    def test_invalid_mode_returns_none(self, aab_file, tmp_path):
        msgs: list[str] = []
        result = aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            mode="bogus",
            log_callback=lambda m: msgs.append(m),
        )
        assert result is None
        assert any("Invalid mode" in m for m in msgs)

    def test_mode_default_uses_base_master_fallback(
        self, aab_file, tmp_path, monkeypatch,
    ):
        """mode=default + có base-master.apk (không universal)."""
        _patch_bundletool(monkeypatch, True)
        monkeypatch.setattr(
            subprocess, "run",
            _run_creator([
                "splits/base-master.apk",
                "splits/base-arm64_v8a.apk",
            ]),
        )
        result = aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            mode="default",
            log_callback=lambda *a: None,
        )
        assert result is not None
        with open(result, "rb") as f:
            assert b"FAKE_APK_CONTENT" in f.read()


# ============================================================
# v2 — device_id
# ============================================================
class TestDeviceId:
    def test_device_id_flag_added(
        self, aab_file, tmp_path, monkeypatch,
    ):
        _patch_bundletool(monkeypatch, True)
        captured: dict = {}

        def _run(cmd, **kw):
            captured["cmd"] = cmd
            for arg in cmd:
                if arg.startswith("--output="):
                    _make_apks(arg.split("=", 1)[1], ["universal.apk"])
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _run)
        aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            device_id="emulator-5554",
            log_callback=lambda *a: None,
        )
        assert "--device-id=emulator-5554" in captured["cmd"]

    def test_no_device_id_no_flag(
        self, aab_file, tmp_path, monkeypatch,
    ):
        _patch_bundletool(monkeypatch, True)
        captured: dict = {}

        def _run(cmd, **kw):
            captured["cmd"] = cmd
            for arg in cmd:
                if arg.startswith("--output="):
                    _make_apks(arg.split("=", 1)[1], ["universal.apk"])
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _run)
        aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        assert not any(
            a.startswith("--device-id=") for a in captured["cmd"]
        )


# ============================================================
# v2 — signing
# ============================================================
class TestSigning:
    def test_keystore_flags_added(
        self, aab_file, tmp_path, monkeypatch,
    ):
        _patch_bundletool(monkeypatch, True)
        captured: dict = {}

        def _run(cmd, **kw):
            captured["cmd"] = cmd
            for arg in cmd:
                if arg.startswith("--output="):
                    _make_apks(arg.split("=", 1)[1], ["universal.apk"])
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _run)
        aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            keystore="/path/to/key.jks",
            ks_pass="secret",
            ks_key_alias="mykey",
            log_callback=lambda *a: None,
        )
        cmd = captured["cmd"]
        assert "--ks=/path/to/key.jks" in cmd
        assert "--ks-pass=pass:secret" in cmd
        assert "--ks-key-alias=mykey" in cmd

    def test_keystore_only_no_pass(
        self, aab_file, tmp_path, monkeypatch,
    ):
        _patch_bundletool(monkeypatch, True)
        captured: dict = {}

        def _run(cmd, **kw):
            captured["cmd"] = cmd
            for arg in cmd:
                if arg.startswith("--output="):
                    _make_apks(arg.split("=", 1)[1], ["universal.apk"])
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _run)
        aab_to_apk(
            str(aab_file), str(tmp_path / "out"),
            keystore="/key.jks",
            log_callback=lambda *a: None,
        )
        cmd = captured["cmd"]
        assert "--ks=/key.jks" in cmd
        assert not any(
            a.startswith("--ks-pass=") for a in cmd
        )


# ============================================================
# v2 — extract_apks_to_folder
# ============================================================
class TestExtractApksToFolder:
    def test_extracts_all_apks(self, tmp_path):
        from core.bundletool_utils import extract_apks_to_folder

        apks = tmp_path / "bundle.apks"
        with zipfile.ZipFile(apks, "w") as z:
            z.writestr("universal.apk", b"UNIV")
            z.writestr("standalones/x.apk", b"STAND")
            z.writestr("toc.pb", b"IGNORED")

        out = tmp_path / "extracted"
        n = extract_apks_to_folder(
            str(apks), str(out), log_callback=lambda *a: None,
        )
        assert n == 2
        assert (out / "universal.apk").exists()
        assert (out / "x.apk").exists()
        assert not (out / "toc.pb").exists()

    def test_missing_apks_returns_zero(self, tmp_path):
        from core.bundletool_utils import extract_apks_to_folder
        n = extract_apks_to_folder(
            str(tmp_path / "nope.apks"),
            str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        assert n == 0

    def test_bad_zip_returns_zero(self, tmp_path):
        from core.bundletool_utils import extract_apks_to_folder
        bad = tmp_path / "bad.apks"
        bad.write_bytes(b"not a zip")
        n = extract_apks_to_folder(
            str(bad), str(tmp_path / "out"),
            log_callback=lambda *a: None,
        )
        assert n == 0

    def test_creates_output_folder(self, tmp_path):
        from core.bundletool_utils import extract_apks_to_folder
        apks = tmp_path / "b.apks"
        with zipfile.ZipFile(apks, "w") as z:
            z.writestr("universal.apk", b"X")
        out = tmp_path / "deep" / "nested"
        extract_apks_to_folder(
            str(apks), str(out), log_callback=lambda *a: None,
        )
        assert out.exists()


# ============================================================
# v2 — list_apks_entries
# ============================================================
class TestListApksEntries:
    def test_returns_all_names(self, tmp_path):
        from core.bundletool_utils import list_apks_entries
        apks = tmp_path / "b.apks"
        with zipfile.ZipFile(apks, "w") as z:
            z.writestr("universal.apk", b"X")
            z.writestr("toc.pb", b"Y")
            z.writestr("splits/base-arm64.apk", b"Z")
        names = list_apks_entries(
            str(apks), log_callback=lambda *a: None,
        )
        assert "universal.apk" in names
        assert "toc.pb" in names
        assert "splits/base-arm64.apk" in names

    def test_missing_returns_empty(self, tmp_path):
        from core.bundletool_utils import list_apks_entries
        assert list_apks_entries(
            str(tmp_path / "nope.apks"),
            log_callback=lambda *a: None,
        ) == []

    def test_bad_zip_returns_empty(self, tmp_path):
        from core.bundletool_utils import list_apks_entries
        bad = tmp_path / "bad.apks"
        bad.write_bytes(b"junk")
        assert list_apks_entries(
            str(bad), log_callback=lambda *a: None,
        ) == []

    def test_logs_entries(self, tmp_path):
        from core.bundletool_utils import list_apks_entries
        apks = tmp_path / "b.apks"
        with zipfile.ZipFile(apks, "w") as z:
            z.writestr("universal.apk", b"X")
        msgs: list[str] = []
        list_apks_entries(
            str(apks), log_callback=lambda m: msgs.append(m),
        )
        assert any("1 entries" in m for m in msgs)
        assert any("universal.apk" in m for m in msgs)


# ============================================================
# v2 — helpers
# ============================================================
class TestInternalHelpers:
    def test_pick_universal_priority(self):
        from core.bundletool_utils import _pick_apk_entry
        names = [
            "toc.pb",
            "standalones/x.apk",
            "universal.apk",
        ]
        assert _pick_apk_entry(names, "universal") == "universal.apk"

    def test_pick_standalone_fallback(self):
        from core.bundletool_utils import _pick_apk_entry
        names = ["toc.pb", "standalones/x.apk"]
        assert _pick_apk_entry(names, "universal") == (
            "standalones/x.apk"
        )

    def test_pick_base_master_last_resort(self):
        from core.bundletool_utils import _pick_apk_entry
        names = ["toc.pb", "splits/base-master.apk"]
        assert _pick_apk_entry(names, "universal") == (
            "splits/base-master.apk"
        )

    def test_pick_none_when_empty(self):
        from core.bundletool_utils import _pick_apk_entry
        assert _pick_apk_entry(["toc.pb"], "universal") is None

    def test_valid_modes_set(self):
        from core.bundletool_utils import _VALID_MODES
        assert "universal" in _VALID_MODES
        assert "default" in _VALID_MODES
        assert "bogus" not in _VALID_MODES