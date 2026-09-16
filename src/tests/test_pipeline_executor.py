"""Test pipeline executor — process_mode + execute_modes + _classify_modes."""
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from core.pipeline_executor import (
    _classify_modes,
    execute_modes,
    process_mode,
)


# ============================================================
# process_mode — fallback modes (không cần patcher class)
# ============================================================
def test_process_mode_unknown_no_fallback():
    """Mode lạ → patched=False, không crash."""
    result = process_mode(
        "unknown_xyz_999", "/tmp", [], None, lambda *_: None
    )
    assert result["patched"] is False
    assert result["label"] == ""


def test_process_mode_save_purchase():
    with patch("patcher.iap_manager.IAPManager") as mock_cls:
        result = process_mode(
            "save_purchase", "/tmp", [], "/tmp/x.apk", lambda *_: None
        )
        assert result["patched"] is True
        assert "Save" in result["label"]
        mock_cls.assert_called_once()


def test_process_mode_auto_repeat():
    with patch("patcher.iap_manager.IAPManager"):
        result = process_mode(
            "auto_repeat", "/tmp", [], "/tmp/x.apk", lambda *_: None
        )
        assert result["patched"] is True
        assert "Auto" in result["label"]


def test_process_mode_clone():
    with patch("patcher.app_cloner.AppCloner") as mock_cls:
        result = process_mode(
            "clone", "/tmp", [], "/tmp/test.apk", lambda *_: None
        )
        assert result["patched"] is True
        assert "Cloned" in result["label"]
        mock_cls.assert_called_once()


def test_process_mode_clone_no_apk():
    """clone không có apk_path → vẫn không crash."""
    with patch("patcher.app_cloner.AppCloner"):
        result = process_mode(
            "clone", "/tmp", [], None, lambda *_: None
        )
        assert result["patched"] is True


def test_process_mode_backup(tmp_path):
    apk = tmp_path / "test.apk"
    apk.write_bytes(b"fake-apk-content")
    result = process_mode(
        "backup", str(tmp_path), [], str(apk), lambda *_: None
    )
    assert result["patched"] is True
    assert "Backup" in result["label"]


# ============================================================
# process_mode — với patcher class
# ============================================================
def test_process_mode_patcher_returns_positive(tmp_path):
    mock_patcher = MagicMock()
    mock_patcher.patch.return_value = 3
    mock_cls = MagicMock(return_value=mock_patcher)

    with patch(
        "core.pipeline_executor.get_patcher_class",
        return_value=mock_cls,
    ):
        result = process_mode(
            "license", str(tmp_path), [], str(tmp_path / "x.apk"),
            lambda *_: None,
        )
        assert result["patched"] is True
        assert "3" in result["label"]


def test_process_mode_patcher_returns_zero(tmp_path):
    mock_patcher = MagicMock()
    mock_patcher.patch.return_value = 0
    mock_cls = MagicMock(return_value=mock_patcher)

    with patch(
        "core.pipeline_executor.get_patcher_class",
        return_value=mock_cls,
    ):
        result = process_mode(
            "license", str(tmp_path), [], str(tmp_path / "x.apk"),
            lambda *_: None,
        )
        assert result["patched"] is False


def test_process_mode_patcher_exception_isolated(tmp_path):
    """Exception trong patcher không lan ra ngoài."""
    logs = []
    mock_cls = MagicMock(side_effect=RuntimeError("patch boom"))

    with patch(
        "core.pipeline_executor.get_patcher_class",
        return_value=mock_cls,
    ):
        result = process_mode(
            "license", str(tmp_path), [], str(tmp_path / "x.apk"),
            logs.append,
        )
        assert result["patched"] is False
        assert any("patch boom" in str(l) for l in logs)


def test_process_mode_ads_uses_remove_activities(tmp_path):
    mock_patcher = MagicMock()
    mock_patcher.remove_activities.return_value = 2
    mock_cls = MagicMock(return_value=mock_patcher)

    with patch(
        "core.pipeline_executor.get_patcher_class",
        return_value=mock_cls,
    ):
        result = process_mode(
            "ads", str(tmp_path), ["act1", "act2"],
            str(tmp_path / "x.apk"), lambda *_: None,
        )
        assert result["patched"] is True
        mock_patcher.remove_activities.assert_called_once_with(
            ["act1", "act2"]
        )


def test_process_mode_with_report(tmp_path):
    """Patcher chỉ có execute_with_report → dùng report."""
    mock_patcher = MagicMock(spec=["execute_with_report"])
    mock_patcher.execute_with_report.return_value = {
        "total_patched": 7
    }
    mock_cls = MagicMock(return_value=mock_patcher)

    with patch(
        "core.pipeline_executor.get_patcher_class",
        return_value=mock_cls,
    ):
        result = process_mode(
            "iap_dex", str(tmp_path), [], str(tmp_path / "x.apk"),
            lambda *_: None,
        )
        assert result["patched"] is True
        assert result["report"]["total_patched"] == 7


# ============================================================
# _classify_modes
# ============================================================
def test_classify_no_group_modes():
    parallel, sequential = _classify_modes(["iap_dex", "change_perms"])
    assert "iap_dex" in parallel
    assert "change_perms" in parallel
    assert sequential == []


def test_classify_same_group_first_parallel_rest_sequential():
    parallel, sequential = _classify_modes(
        ["license", "license_extreme"]
    )
    assert parallel == ["license"]
    assert sequential == ["license_extreme"]


def test_classify_mixed_groups():
    parallel, sequential = _classify_modes([
        "license", "ads", "sig_disable",
        "license_extreme",       # duplicate group
        "ads_offline",           # duplicate group
    ])
    assert "license" in parallel
    assert "ads" in parallel
    assert "sig_disable" in parallel
    assert "license_extreme" in sequential
    assert "ads_offline" in sequential


def test_classify_empty_list():
    parallel, sequential = _classify_modes([])
    assert parallel == []
    assert sequential == []


# ============================================================
# execute_modes
# ============================================================
def test_execute_modes_empty(tmp_path):
    applied, reports = execute_modes(
        [], str(tmp_path), [], None, lambda *_: None
    )
    assert applied == []
    assert reports == {}


def test_execute_modes_all_sequential(tmp_path):
    """Force all modes vào sequential để tránh subprocess."""
    mock_patcher = MagicMock()
    mock_patcher.patch.return_value = 2
    mock_cls = MagicMock(return_value=mock_patcher)

    with patch(
        "core.pipeline_executor._classify_modes",
        return_value=([], ["license"]),
    ), patch(
        "core.pipeline_executor.get_patcher_class",
        return_value=mock_cls,
    ):
        applied, reports = execute_modes(
            ["license"], str(tmp_path), [],
            str(tmp_path / "x.apk"), lambda *_: None,
        )
        assert len(applied) >= 1


def test_execute_modes_with_signals_sequential(tmp_path):
    mock_patcher = MagicMock()
    mock_patcher.patch.return_value = 1
    mock_cls = MagicMock(return_value=mock_patcher)
    signals = MagicMock()

    with patch(
        "core.pipeline_executor._classify_modes",
        return_value=([], ["license"]),
    ), patch(
        "core.pipeline_executor.get_patcher_class",
        return_value=mock_cls,
    ):
        execute_modes(
            ["license"], str(tmp_path), [],
            str(tmp_path / "x.apk"), lambda *_: None, signals,
        )
        assert signals.progress.emit.called
        assert signals.status.emit.called


def test_execute_modes_handles_patcher_error(tmp_path):
    """Lỗi trong sequential không crash execute_modes."""
    logs = []
    mock_cls = MagicMock(side_effect=RuntimeError("sequential boom"))

    with patch(
        "core.pipeline_executor._classify_modes",
        return_value=([], ["license"]),
    ), patch(
        "core.pipeline_executor.get_patcher_class",
        return_value=mock_cls,
    ):
        applied, reports = execute_modes(
            ["license"], str(tmp_path), [],
            str(tmp_path / "x.apk"), logs.append,
        )
        # Không crash, error được log
        assert any("sequential boom" in str(l) for l in logs)


def test_execute_modes_collects_reports(tmp_path):
    mock_patcher = MagicMock(spec=["execute_with_report"])
    mock_patcher.execute_with_report.return_value = {
        "total_patched": 4
    }
    mock_cls = MagicMock(return_value=mock_patcher)

    with patch(
        "core.pipeline_executor._classify_modes",
        return_value=([], ["iap_dex"]),
    ), patch(
        "core.pipeline_executor.get_patcher_class",
        return_value=mock_cls,
    ):
        applied, reports = execute_modes(
            ["iap_dex"], str(tmp_path), [],
            str(tmp_path / "x.apk"), lambda *_: None,
        )
        assert "iap_dex" in reports
        assert reports["iap_dex"]["total_patched"] == 4