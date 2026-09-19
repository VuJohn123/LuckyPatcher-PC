"""Test core/tool_updater.py — version check + GitHub release query."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import core.tool_updater as tu
from core.tool_updater import (
    _TOOL_REGISTRY,
    ToolUpdateInfo,
    _detect_local_version,
    _fetch_latest_release,
    _is_newer,
    _load_cache,
    _save_cache,
    check_all_updates,
)


# ============================================================
# Registry integrity
# ============================================================
class TestRegistry:
    def test_has_expected_tools(self):
        for name in ("apktool", "uber-apk-signer", "bundletool",
                     "smali", "baksmali"):
            assert name in _TOOL_REGISTRY

    def test_all_entries_have_repo_and_jar(self):
        for name, cfg in _TOOL_REGISTRY.items():
            assert "repo" in cfg
            assert "jar" in cfg
            assert cfg["jar"].endswith(".jar")


# ============================================================
# _detect_local_version
# ============================================================
class TestDetectLocalVersion:
    def test_filename_fallback_when_no_cmd(self, tmp_path):
        jar = tmp_path / "apktool_2.9.3.jar"
        jar.write_bytes(b"fake")
        cfg = {"version_cmd": None, "version_regex": None}
        assert _detect_local_version(jar, cfg) == "2.9.3"

    def test_filename_no_version_returns_empty(self, tmp_path):
        jar = tmp_path / "apktool.jar"
        jar.write_bytes(b"fake")
        cfg = {"version_cmd": None, "version_regex": None}
        assert _detect_local_version(jar, cfg) == ""

    def test_version_cmd_success(self, tmp_path):
        jar = tmp_path / "apktool.jar"
        jar.write_bytes(b"fake")
        cfg = {
            "version_cmd": ["java", "-jar", "{jar}", "--version"],
            "version_regex": r"(\d+\.\d+\.\d+)",
        }
        fake = MagicMock(stdout="apktool 2.9.3\n", stderr="", returncode=0)
        with patch.object(subprocess, "run", return_value=fake):
            assert _detect_local_version(jar, cfg) == "2.9.3"

    def test_version_cmd_from_stderr(self, tmp_path):
        jar = tmp_path / "apktool.jar"
        jar.write_bytes(b"fake")
        cfg = {
            "version_cmd": ["java", "-jar", "{jar}", "--version"],
            "version_regex": r"(\d+\.\d+\.\d+)",
        }
        fake = MagicMock(stdout="", stderr="v2.8.0\n", returncode=0)
        with patch.object(subprocess, "run", return_value=fake):
            assert _detect_local_version(jar, cfg) == "2.8.0"

    def test_version_cmd_no_match_returns_empty(self, tmp_path):
        jar = tmp_path / "apktool.jar"
        jar.write_bytes(b"fake")
        cfg = {
            "version_cmd": ["java", "-jar", "{jar}", "--version"],
            "version_regex": r"(\d+\.\d+\.\d+)",
        }
        fake = MagicMock(stdout="garbage", stderr="", returncode=0)
        with patch.object(subprocess, "run", return_value=fake):
            assert _detect_local_version(jar, cfg) == ""

    def test_version_cmd_oserror_returns_empty(self, tmp_path):
        jar = tmp_path / "apktool.jar"
        jar.write_bytes(b"fake")
        cfg = {
            "version_cmd": ["java", "-jar", "{jar}", "--version"],
            "version_regex": r"(\d+\.\d+\.\d+)",
        }
        with patch.object(subprocess, "run", side_effect=OSError("no java")):
            assert _detect_local_version(jar, cfg) == ""

    def test_version_cmd_timeout_returns_empty(self, tmp_path):
        jar = tmp_path / "apktool.jar"
        jar.write_bytes(b"fake")
        cfg = {
            "version_cmd": ["java", "-jar", "{jar}", "--version"],
            "version_regex": r"(\d+\.\d+\.\d+)",
        }
        with patch.object(
            subprocess, "run",
            side_effect=subprocess.TimeoutExpired("java", 10),
        ):
            assert _detect_local_version(jar, cfg) == ""


# ============================================================
# _fetch_latest_release
# ============================================================
class TestFetchLatestRelease:
    def test_success_with_jar_asset(self):
        response_data = {
            "tag_name": "v2.9.3",
            "assets": [
                {"name": "apktool_2.9.3.jar",
                 "browser_download_url": "https://example.com/apktool.jar"},
            ],
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        import urllib.request
        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            result = _fetch_latest_release("iBotPeaches/Apktool", 5.0)

        assert result is not None
        assert result["version"] == "2.9.3"
        assert "apktool.jar" in result["download_url"]

    def test_no_jar_asset_returns_empty_url(self):
        response_data = {"tag_name": "v1.0.0", "assets": []}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        import urllib.request
        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            result = _fetch_latest_release("x/y", 5.0)

        assert result is not None
        assert result["version"] == "1.0.0"
        assert result["download_url"] == ""

    def test_network_error_returns_none(self):
        import urllib.request
        with patch.object(
            urllib.request, "urlopen",
            side_effect=OSError("network down"),
        ):
            assert _fetch_latest_release("x/y", 5.0) is None

    def test_no_version_in_tag(self):
        response_data = {"tag_name": "nightly", "assets": []}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        import urllib.request
        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            result = _fetch_latest_release("x/y", 5.0)

        assert result is not None
        assert result["version"] == ""


# ============================================================
# _is_newer
# ============================================================
class TestIsNewer:
    def test_empty_installed_returns_true(self):
        assert _is_newer("2.0.0", "") is True

    def test_newer_latest_returns_true(self):
        assert _is_newer("2.9.4", "2.9.3") is True

    def test_same_version_returns_false(self):
        assert _is_newer("2.9.3", "2.9.3") is False

    def test_older_latest_returns_false(self):
        assert _is_newer("2.9.2", "2.9.3") is False

    def test_invalid_installed_returns_false(self):
        assert _is_newer("2.0.0", "invalid") is False


# ============================================================
# Cache
# ============================================================
class TestCache:
    def test_load_missing_returns_none(self, tmp_path):
        assert _load_cache(tmp_path / "nonexistent.json") is None

    def test_load_fresh_returns_list(self, tmp_path):
        cache = tmp_path / "cache.json"
        payload = [
            {"name": "apktool", "installed": "2.8.0",
             "latest": "2.9.3", "update_available": True,
             "download_url": "x"},
        ]
        cache.write_text(json.dumps(payload), encoding="utf-8")

        result = _load_cache(cache)
        assert result is not None
        assert len(result) == 1
        assert result[0].name == "apktool"

    def test_load_expired_returns_none(self, tmp_path):
        cache = tmp_path / "cache.json"
        cache.write_text("[]", encoding="utf-8")
        # Set mtime 48h ago
        old = time.time() - 48 * 3600
        os.utime(cache, (old, old))

        # _CACHE_HOURS default = 24
        assert _load_cache(cache) is None

    def test_load_corrupt_returns_none(self, tmp_path):
        cache = tmp_path / "cache.json"
        cache.write_text("{invalid", encoding="utf-8")
        assert _load_cache(cache) is None

    def test_save_creates_file(self, tmp_path):
        cache = tmp_path / "sub" / "cache.json"
        cache.parent.mkdir()
        results = [
            ToolUpdateInfo(
                name="apktool", installed="2.8.0", latest="2.9.3",
                update_available=True, download_url="x",
            ),
        ]
        _save_cache(cache, results)
        assert cache.exists()
        data = json.loads(cache.read_text(encoding="utf-8"))
        assert data[0]["name"] == "apktool"

    def test_save_handles_error_gracefully(self, tmp_path):
        cache = tmp_path / "cache.json"
        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            _save_cache(cache, [])  # should not raise


# ============================================================
# check_all_updates — integration
# ============================================================
class TestCheckAllUpdates:
    def test_disabled_via_env(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tu, "_DISABLE", True)
        msgs: list[str] = []
        result = check_all_updates(str(tmp_path), log_callback=msgs.append)
        assert result == []
        assert any("Disabled" in m for m in msgs)

    def test_cache_hit_returns_cached(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tu, "_DISABLE", False)
        cache = tmp_path / ".update_cache.json"
        payload = [
            {"name": "apktool", "installed": "1.0.0",
             "latest": "2.0.0", "update_available": True,
             "download_url": "x"},
        ]
        cache.write_text(json.dumps(payload), encoding="utf-8")

        msgs: list[str] = []
        result = check_all_updates(str(tmp_path), log_callback=msgs.append)
        assert len(result) == 1
        assert any("cache" in m.lower() for m in msgs)

    def test_no_jars_in_tools_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tu, "_DISABLE", False)
        (tmp_path / "bin").mkdir()
        result = check_all_updates(
            str(tmp_path), log_callback=lambda *a: None,
        )
        assert result == []

    def test_update_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tu, "_DISABLE", False)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "apktool.jar").write_bytes(b"fake")

        # Mock version detect + release fetch
        monkeypatch.setattr(tu, "_detect_local_version",
                            lambda *a, **kw: "2.8.0")
        monkeypatch.setattr(
            tu, "_fetch_latest_release",
            lambda *a, **kw: {
                "version": "2.9.3",
                "download_url": "https://example.com/a.jar",
            },
        )

        msgs: list[str] = []
        result = check_all_updates(str(tmp_path), log_callback=msgs.append)
        assert len(result) >= 1
        assert any(r.name == "apktool" for r in result)
        assert any("2.9.3" in m for m in msgs)

    def test_no_update_when_current(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tu, "_DISABLE", False)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "apktool.jar").write_bytes(b"fake")

        monkeypatch.setattr(tu, "_detect_local_version",
                            lambda *a, **kw: "2.9.3")
        monkeypatch.setattr(
            tu, "_fetch_latest_release",
            lambda *a, **kw: {"version": "2.9.3", "download_url": ""},
        )

        result = check_all_updates(
            str(tmp_path), log_callback=lambda *a: None,
        )
        assert result == []

    def test_fetch_fail_skips_tool(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tu, "_DISABLE", False)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "apktool.jar").write_bytes(b"fake")

        monkeypatch.setattr(tu, "_detect_local_version",
                            lambda *a, **kw: "2.8.0")
        monkeypatch.setattr(tu, "_fetch_latest_release",
                            lambda *a, **kw: None)

        result = check_all_updates(
            str(tmp_path), log_callback=lambda *a: None,
        )
        assert result == []

    def test_no_version_in_release_skips(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tu, "_DISABLE", False)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "apktool.jar").write_bytes(b"fake")

        monkeypatch.setattr(tu, "_detect_local_version",
                            lambda *a, **kw: "2.8.0")
        monkeypatch.setattr(
            tu, "_fetch_latest_release",
            lambda *a, **kw: {"version": "", "download_url": ""},
        )

        result = check_all_updates(
            str(tmp_path), log_callback=lambda *a: None,
        )
        assert result == []


# ============================================================
# ToolUpdateInfo
# ============================================================
class TestToolUpdateInfo:
    def test_dataclass_fields(self):
        info = ToolUpdateInfo(
            name="x", installed="1", latest="2",
            update_available=True, download_url="url",
        )
        assert info.name == "x"
        assert info.__dict__["download_url"] == "url"