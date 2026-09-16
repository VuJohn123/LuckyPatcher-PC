"""Test config loader — deep merge + fallback."""
import os
import tempfile

import yaml

from core.config import _deep_merge, load_config


def test_defaults_when_no_file():
    cfg = load_config("/nonexistent/path.yaml")
    assert cfg["pipeline"]["apktool_memory"] == "4096m"
    assert cfg["conversion"]["auto_convert_xapk"] is True
    assert cfg["signing"]["key_type"] == "testkey"


def test_deep_merge_overrides_nested():
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    override = {"a": {"y": 99, "z": 4}}
    merged = _deep_merge(base, override)
    assert merged["a"] == {"x": 1, "y": 99, "z": 4}
    assert merged["b"] == 3


def test_deep_merge_does_not_mutate_inputs():
    base = {"a": {"x": 1}}
    override = {"a": {"y": 2}}
    _deep_merge(base, override)
    assert base == {"a": {"x": 1}}
    assert override == {"a": {"y": 2}}


def test_load_yaml_override():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "c.yaml")
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                {"pipeline": {"apktool_memory": "8192m"}}, f
            )
        cfg = load_config(path)
        assert cfg["pipeline"]["apktool_memory"] == "8192m"
        # Field không override vẫn giữ default
        assert cfg["pipeline"]["keep_workspace"] is True


def test_invalid_yaml_falls_back_to_defaults():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "bad.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write("!!!invalid: yaml: [")
        cfg = load_config(path)
        assert cfg["pipeline"]["apktool_memory"] == "4096m"