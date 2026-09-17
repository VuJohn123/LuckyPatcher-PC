"""Test patcher/ws_proxy_server.py."""
from unittest.mock import MagicMock, patch

import pytest

from patcher.ws_proxy_server import WSBillingProxy, WS_AVAILABLE, _build_buy_intent


# ============================================================
# Constants
# ============================================================
def test_ws_available_flag_defined():
    assert isinstance(WS_AVAILABLE, bool)


# ============================================================
# _build_buy_intent
# ============================================================
def test_build_buy_intent():
    result = _build_buy_intent("com.app", "prod1")
    assert result["code"] == 0
    assert "purchaseData" in result
    assert "signature" in result


def test_build_buy_intent_with_payload():
    result = _build_buy_intent("com.app", "prod1", "mypayload")
    assert "mypayload" in result["purchaseData"]


# ============================================================
# Constructor
# ============================================================
def test_init_default():
    p = WSBillingProxy()
    assert p.host == "0.0.0.0"
    assert p.port == 8889


def test_init_custom():
    p = WSBillingProxy(host="127.0.0.1", port=9999)
    assert p.host == "127.0.0.1"
    assert p.port == 9999


# ============================================================
# _route
# ============================================================
def test_route_buy():
    p = WSBillingProxy()
    msg = '{"method": "getBuyIntent", "packageName": "com.app", "productId": "p"}'
    result = p._route(msg)
    assert result["code"] == 0


def test_route_purchases():
    p = WSBillingProxy()
    msg = '{"method": "getPurchases", "packageName": "com.app"}'
    result = p._route(msg)
    assert result["code"] == 0
    assert "purchases" in result


def test_route_supported():
    p = WSBillingProxy()
    msg = '{"method": "isBillingSupported"}'
    result = p._route(msg)
    assert result["code"] == 0


def test_route_consume():
    p = WSBillingProxy()
    msg = '{"method": "consumePurchase"}'
    result = p._route(msg)
    assert result["code"] == 0


def test_route_unknown_method():
    p = WSBillingProxy()
    msg = '{"method": "unknown"}'
    result = p._route(msg)
    assert result["code"] == 0


def test_route_invalid_json():
    p = WSBillingProxy()
    result = p._route("not valid json {{{")
    assert "error" in result


# ============================================================
# start — khi không có websockets lib
# ============================================================
def test_start_without_ws_lib():
    """Nếu websockets không cài → log message, không crash."""
    with patch("patcher.ws_proxy_server.WS_AVAILABLE", False):
        p = WSBillingProxy()
        logs = []
        p.log = logs.append
        p.start()
        # Không crash


# ============================================================
# stop
# ============================================================
def test_stop_without_server():
    p = WSBillingProxy()
    p.stop()  # Không crash


def test_stop_with_server():
    p = WSBillingProxy()
    p._server = MagicMock()
    p.stop()
    p._server.close.assert_called_once()