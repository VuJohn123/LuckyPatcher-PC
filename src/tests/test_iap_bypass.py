"""Test IAPBypass — mock proxy + smali patcher."""
from unittest.mock import MagicMock, patch

from patcher.iap_bypass import IAPBypass


def test_init_dex_mode():
    with patch("patcher.iap_bypass.IAPDexPatcher"):
        bp = IAPBypass("/tmp/x", mode="dex", log_callback=lambda *_: None)
        assert bp.mode == "dex"


def test_init_proxy_mode():
    with patch("patcher.iap_bypass.IAPProxyServer"), \
         patch("patcher.iap_bypass.IAPSmaliPatcher"), \
         patch("patcher.iap_bypass.SignatureVerifyPatcher"):
        bp = IAPBypass("/tmp/x", mode="proxy", log_callback=lambda *_: None)
        assert bp.mode == "proxy"


def test_execute_dex_success():
    with patch("patcher.iap_bypass.IAPDexPatcher") as mock_cls:
        mock_cls.return_value.patch.return_value = 5
        bp = IAPBypass("/tmp/x", mode="dex", log_callback=lambda *_: None)
        assert bp.execute() is True


def test_execute_dex_zero():
    with patch("patcher.iap_bypass.IAPDexPatcher") as mock_cls:
        mock_cls.return_value.patch.return_value = 0
        bp = IAPBypass("/tmp/x", mode="dex", log_callback=lambda *_: None)
        assert bp.execute() is False


def test_execute_with_report_dex():
    with patch("patcher.iap_bypass.IAPDexPatcher") as mock_cls:
        mock_cls.return_value.patch_with_report.return_value = {
            "patterns": {"x": True}, "total_patched": 3
        }
        bp = IAPBypass("/tmp/x", mode="dex", log_callback=lambda *_: None)
        report = bp.execute_with_report()
        assert report["total_patched"] == 3


def test_patch_interface():
    with patch.object(IAPBypass, "execute", return_value=True):
        bp = IAPBypass("/tmp/x", mode="dex", log_callback=lambda *_: None)
        assert bp.patch() == 1


def test_patch_interface_fail():
    with patch.object(IAPBypass, "execute", return_value=False):
        bp = IAPBypass("/tmp/x", mode="dex", log_callback=lambda *_: None)
        assert bp.patch() == 0