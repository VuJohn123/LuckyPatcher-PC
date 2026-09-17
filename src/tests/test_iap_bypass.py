"""Test patcher/iap_bypass.py — orchestrator."""
import socket
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from patcher.iap_bypass import IAPBypass


# ============================================================
# Constructor
# ============================================================
def test_init_default(tmp_path):
    b = IAPBypass(str(tmp_path))
    assert b.mode == "proxy"
    assert b.proxy_port == 8888


def test_init_dex_mode(tmp_path):
    b = IAPBypass(str(tmp_path), mode="dex")
    assert b.mode == "dex"


def test_init_proxy_mode(tmp_path):
    b = IAPBypass(str(tmp_path), mode="proxy")
    assert b.mode == "proxy"


def test_init_custom_port(tmp_path):
    b = IAPBypass(str(tmp_path), proxy_port=9999)
    assert b.proxy_port == 9999


# ============================================================
# _run_dex_mode
# ============================================================
def test_run_dex_mode(tmp_path):
    mock_patcher = MagicMock()
    mock_patcher.patch.return_value = 5
    mock_cls = MagicMock(return_value=mock_patcher)

    b = IAPBypass(str(tmp_path), mode="dex")
    with patch(
        "patcher.iap_bypass.IAPDexPatcher", mock_cls
    ):
        count = b._run_dex_mode()
        assert count == 5


# ============================================================
# execute — dex mode
# ============================================================
def test_execute_dex_success(tmp_path):
    mock_patcher = MagicMock()
    mock_patcher.patch.return_value = 3
    mock_cls = MagicMock(return_value=mock_patcher)

    b = IAPBypass(str(tmp_path), mode="dex")
    with patch("patcher.iap_bypass.IAPDexPatcher", mock_cls):
        assert b.execute() is True


def test_execute_dex_zero(tmp_path):
    mock_patcher = MagicMock()
    mock_patcher.patch.return_value = 0
    mock_cls = MagicMock(return_value=mock_patcher)

    b = IAPBypass(str(tmp_path), mode="dex")
    with patch("patcher.iap_bypass.IAPDexPatcher", mock_cls):
        assert b.execute() is False


def test_execute_dex_exception(tmp_path):
    mock_cls = MagicMock(side_effect=RuntimeError("boom"))
    b = IAPBypass(str(tmp_path), mode="dex")
    with patch("patcher.iap_bypass.IAPDexPatcher", mock_cls):
        assert b.execute() is False


# ============================================================
# execute_with_report — dex mode
# ============================================================
def test_execute_with_report_dex(tmp_path):
    mock_patcher = MagicMock()
    mock_patcher.patch_with_report.return_value = {
        "patterns": {"x": True},
        "total_patched": 3,
    }
    mock_cls = MagicMock(return_value=mock_patcher)

    b = IAPBypass(str(tmp_path), mode="dex")
    with patch("patcher.iap_bypass.IAPDexPatcher", mock_cls):
        report = b.execute_with_report()
        assert report["total_patched"] == 3


def test_execute_with_report_exception(tmp_path):
    mock_cls = MagicMock(side_effect=RuntimeError("boom"))
    b = IAPBypass(str(tmp_path), mode="dex")
    with patch("patcher.iap_bypass.IAPDexPatcher", mock_cls):
        report = b.execute_with_report()
        assert report["total_patched"] == 0


# ============================================================
# patch interface
# ============================================================
def test_patch_interface(tmp_path):
    with patch.object(IAPBypass, "execute", return_value=True):
        b = IAPBypass(str(tmp_path), mode="dex")
        assert b.patch() == 1


def test_patch_interface_fail(tmp_path):
    with patch.object(IAPBypass, "execute", return_value=False):
        b = IAPBypass(str(tmp_path), mode="dex")
        assert b.patch() == 0


# ============================================================
# _wait_for_proxy
# ============================================================
def test_wait_for_proxy_timeout():
    """Không có server → timeout, trả False."""
    b = IAPBypass("/tmp", proxy_port=65534)
    result = b._wait_for_proxy(timeout=0.5)
    assert result is False


def test_wait_for_proxy_success():
    """Có server listening → True."""
    with socket.socket() as server:
        server.bind(("localhost", 0))
        server.listen(1)
        port = server.getsockname()[1]

        b = IAPBypass("/tmp", proxy_port=port)
        result = b._wait_for_proxy(timeout=2.0)
        assert result is True