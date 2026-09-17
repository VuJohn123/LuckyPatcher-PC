"""Test patcher/multi_patch_combiner.py."""
from unittest.mock import MagicMock, patch

import pytest

from patcher.multi_patch_combiner import MultiPatchCombiner


def test_init(tmp_path):
    c = MultiPatchCombiner(str(tmp_path))
    assert c.decompiled_path == str(tmp_path)


def test_apply_patches_empty(tmp_path):
    c = MultiPatchCombiner(str(tmp_path))
    result = c.apply_patches([])
    assert result == {"success": [], "failed": []}


def test_apply_patches_unknown_mode(tmp_path):
    c = MultiPatchCombiner(str(tmp_path))
    result = c.apply_patches(["nonexistent_mode"])
    assert "nonexistent_mode" in result["failed"]
    assert result["success"] == []


def test_apply_patches_success(tmp_path):
    mock_patcher = MagicMock()
    mock_patcher.patch.return_value = 1
    mock_cls = MagicMock(return_value=mock_patcher)

    c = MultiPatchCombiner(str(tmp_path))
    with patch(
        "patcher.multi_patch_combiner.get_patcher_class",
        return_value=mock_cls,
    ):
        result = c.apply_patches(["license"])
        assert "license" in result["success"]
        assert mock_patcher.patch.called


def test_apply_patches_patcher_exception(tmp_path):
    mock_cls = MagicMock(side_effect=RuntimeError("boom"))

    c = MultiPatchCombiner(str(tmp_path))
    with patch(
        "patcher.multi_patch_combiner.get_patcher_class",
        return_value=mock_cls,
    ):
        result = c.apply_patches(["license"])
        assert "license" in result["failed"]


def test_apply_patches_multiple(tmp_path):
    mock_patcher = MagicMock()
    mock_patcher.patch.return_value = 1
    mock_cls = MagicMock(return_value=mock_patcher)

    c = MultiPatchCombiner(str(tmp_path))
    with patch(
        "patcher.multi_patch_combiner.get_patcher_class",
        return_value=mock_cls,
    ):
        result = c.apply_patches(["license", "ads"])
        assert len(result["success"]) == 2
        assert result["failed"] == []