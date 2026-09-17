"""Test config loading — deep merge, env override, YAML fallback."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from core.config import _deep_merge, load_config


# ============================================================
# Fixture: disable adaptive tune cho mọi test trong module này
# ============================================================
@pytest.fixture(autouse=True)
def _disable_auto_tune():
    """
    Auto-tune thay đổi giá trị theo hardware thực tế → test flaky.
    Patch thành no-op để test giá trị từ YAML/defaults thuần.
    """
    with patch("core.config._apply_adaptive_tune",
               side_effect=lambda cfg, *a, **kw: cfg):
        yield


# ============================================================
# Deep merge
# ============================================================
def test_deep_merge_overrides_nested():
    base = {"a": {"b": 1, "c": 2}, "d": 3}
    override = {"a": {"b": 99}}
    result = _deep_merge(base, override)
    assert result["a"]["b"] == 99
    assert result["a"]["c"] == 2  # giữ nguyên
    assert result["d"] == 3


def test_deep_merge_does_not_mutate_inputs():
    base = {"a": {"b": 1}}
    override = {"a": {"b": 2}}
    _deep_merge(base, override)
    assert base["a"]["b"] == 1  # không bị mutate
    assert override["a"]["b"] == 2


# ============================================================
# load_config — fallback khi không có file
# ============================================================
def test_defaults_when_no_file(tmp_path):
    """Path không tồn tại → dùng defaults (đã tắt auto-tune)."""
    nonexistent = str(tmp_path / "does_not_exist.yaml")
    config = load_config(nonexistent)

    # apktool_memory default = "auto" → không auto-tune → giữ "auto"
    # Hoặc test giá trị ổn định khác không bị auto-tune
    assert config["pipeline"]["keep_workspace"] is True
    assert config["conversion"]["auto_convert_xapk"] is True
    assert config["logging"]["level"] == "auto"  # chưa tune
    assert config["auto_tune"]["enabled"] is True


# ============================================================
# load_config — YAML override
# ============================================================
def test_load_yaml_override(tmp_path):
    """YAML user override được merge vào defaults."""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
pipeline:
  apktool_memory: "8192m"
  apktool_jobs: 6
logging:
  level: DEBUG
""", encoding="utf-8")

    config = load_config(str(yaml_file))

    # Không auto-tune → giữ giá trị YAML
    assert config["pipeline"]["apktool_memory"] == "8192m"
    assert config["pipeline"]["apktool_jobs"] == 6
    assert config["logging"]["level"] == "DEBUG"

    # Defaults vẫn được giữ ở chỗ YAML không override
    assert config["pipeline"]["keep_workspace"] is True


# ============================================================
# load_config — YAML lỗi → fallback defaults
# ============================================================
def test_invalid_yaml_falls_back_to_defaults(tmp_path):
    """YAML lỗi cú pháp → fallback defaults, không crash."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("invalid: yaml: [unclosed", encoding="utf-8")

    config = load_config(str(bad))

    # Không auto-tune → apktool_memory = "auto" (default)
    assert config["pipeline"]["apktool_memory"] == "auto"
    assert config["pipeline"]["keep_workspace"] is True
    assert config["logging"]["level"] == "auto"


# ============================================================
# load_config — preset (LP_PRESET env)
# ============================================================
def test_preset_env_var(tmp_path, monkeypatch):
    """LP_PRESET=fast → preset được apply."""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
presets:
  fast:
    pipeline:
      fast_mode: true
      use_gda: false
    ui:
      log_visible: false
""", encoding="utf-8")

    monkeypatch.setenv("LP_PRESET", "fast")
    config = load_config(str(yaml_file))

    assert config["pipeline"]["fast_mode"] is True
    assert config["pipeline"]["use_gda"] is False
    assert config["ui"]["log_visible"] is False


def test_preset_env_invalid(tmp_path, monkeypatch):
    """LP_PRESET=tên_không_tồn_tại → không crash, dùng defaults."""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("presets: {fast: {pipeline: {fast_mode: true}}}",
                         encoding="utf-8")

    monkeypatch.setenv("LP_PRESET", "nonexistent")
    config = load_config(str(yaml_file))

    # Vẫn load được, không crash
    assert config is not None
    assert "pipeline" in config


# ============================================================
# load_config — env var override
# ============================================================
def test_env_override_int(tmp_path, monkeypatch):
    """LP_LOGGING_MAX_BYTES=999 → override int value."""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("logging:\n  max_bytes: 5000\n", encoding="utf-8")

    monkeypatch.setenv("LP_LOGGING_MAX_BYTES", "999")
    config = load_config(str(yaml_file))
    assert config["logging"]["max_bytes"] == 999


def test_env_override_bool(tmp_path, monkeypatch):
    """LP_PIPELINE_KEEP_WORKSPACE=false → override bool."""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("pipeline:\n  keep_workspace: true\n",
                         encoding="utf-8")

    monkeypatch.setenv("LP_PIPELINE_KEEP_WORKSPACE", "false")
    config = load_config(str(yaml_file))
    assert config["pipeline"]["keep_workspace"] is False


def test_env_override_nested(tmp_path, monkeypatch):
    """LP_NETWORK_CONNECT_TIMEOUT=30 → override nested key."""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text(
        "network:\n  connect_timeout: 10\n", encoding="utf-8"
    )

    monkeypatch.setenv("LP_NETWORK_CONNECT_TIMEOUT", "30")
    config = load_config(str(yaml_file))
    assert config["network"]["connect_timeout"] == 30


def test_env_override_unknown_key_ignored(tmp_path, monkeypatch):
    """Env var không match key nào → bỏ qua, không crash."""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("pipeline: {}\n", encoding="utf-8")

    monkeypatch.setenv("LP_TOTALLY_FAKE_KEY", "value")
    config = load_config(str(yaml_file))

    # Key mới không được tạo
    assert "totally_fake_key" not in config["pipeline"]


# ============================================================
# Auto-tune integration (có patch riêng)
# ============================================================
def test_auto_tune_can_be_disabled(tmp_path):
    """auto_tune.enabled=false → không chạy tuner."""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
auto_tune:
  enabled: false
pipeline:
  apktool_memory: "4096m"
""", encoding="utf-8")

    # Không cần patch — enabled=false tự tắt
    config = load_config(str(yaml_file))
    assert config["pipeline"]["apktool_memory"] == "4096m"


def test_auto_tune_when_enabled(tmp_path):
    """auto_tune.enabled=true → tuner chạy (mock để không phụ thuộc HW)."""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
auto_tune:
  enabled: true
pipeline:
  apktool_memory: auto
""", encoding="utf-8")

    # Mock tuner để trả kết quả cố định
    with patch("core.config._apply_adaptive_tune") as mock_tune:
        def _fake_tune(cfg, apk_path, mode):
            cfg["pipeline"]["apktool_memory"] = "4096m"
            return cfg
        mock_tune.side_effect = _fake_tune

        config = load_config(str(yaml_file))
        assert mock_tune.called
        assert config["pipeline"]["apktool_memory"] == "4096m"