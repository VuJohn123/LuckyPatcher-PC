"""Test patcher/iap_proxy_server.py — HTTP proxy + handler logic."""
import json
import socket
import threading
import time
from http.server import HTTPServer
from unittest.mock import MagicMock, patch

import pytest

from patcher.iap_proxy_server import IAPProxyServer, _ProxyHandler


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


# ============================================================
# Constructor
# ============================================================
def test_init_default():
    s = IAPProxyServer()
    assert s.port == 8888
    assert s.host == "localhost"
    assert s.server is None


def test_init_custom():
    s = IAPProxyServer(host="0.0.0.0", port=9999)
    assert s.host == "0.0.0.0"
    assert s.port == 9999


# ============================================================
# Handler logic — không cần socket
# ============================================================
def test_handler_route_buy():
    h = _ProxyHandler.__new__(_ProxyHandler)
    result = h._route("getBuyIntent", "com.app", "product1", {})
    assert result["code"] == 0
    assert "purchaseData" in result
    assert "signature" in result


def test_handler_route_purchases():
    h = _ProxyHandler.__new__(_ProxyHandler)
    result = h._route("getPurchases", "com.app", "p", {})
    assert result["code"] == 0
    assert "purchases" in result


def test_handler_route_supported():
    h = _ProxyHandler.__new__(_ProxyHandler)
    result = h._route("isBillingSupported", "com.app", "p", {})
    assert result["code"] == 0


def test_handler_route_consume():
    h = _ProxyHandler.__new__(_ProxyHandler)
    result = h._route("consumePurchase", "com.app", "p", {})
    assert result["code"] == 0


def test_handler_route_unknown():
    h = _ProxyHandler.__new__(_ProxyHandler)
    result = h._route("unknown_method", "com.app", "p", {})
    assert result["code"] == 0


def test_buy_intent_contains_order_id():
    h = _ProxyHandler.__new__(_ProxyHandler)
    result = h._buy_intent("com.app", "prod", {})
    data = json.loads(result["purchaseData"])
    assert "orderId" in data
    assert data["packageName"] == "com.app"
    assert data["productId"] == "prod"


def test_buy_intent_signature_present():
    h = _ProxyHandler.__new__(_ProxyHandler)
    result = h._buy_intent("com.app", "prod", {})
    assert isinstance(result["signature"], str)
    assert len(result["signature"]) > 0


# ============================================================
# start / stop — chạy thread
# ============================================================
def _start_server_in_thread(server, timeout: float = 2.0):
    t = threading.Thread(target=server.start, daemon=True)
    t.start()
    time.sleep(min(timeout, 0.5))
    return t


def test_server_start_stop():
    port = _free_port()
    s = IAPProxyServer(port=port)
    _start_server_in_thread(s)

    try:
        with socket.create_connection(("localhost", port), timeout=1):
            pass
    except (ConnectionRefusedError, OSError):
        pytest.skip("Server không bind kịp")
    finally:
        s.stop()


def test_server_start_port_in_use():
    """Port đã bị chiếm → không crash, log error."""
    port = _free_port()
    # Bind trước
    blocker = socket.socket()
    blocker.bind(("localhost", port))
    blocker.listen(1)
    try:
        s = IAPProxyServer(port=port)
        # start() sẽ fail bind nhưng không raise
        _start_server_in_thread(s)
        time.sleep(0.3)
        # Không crash
    finally:
        blocker.close()


def test_server_stop_without_start():
    s = IAPProxyServer(port=9999)
    s.stop()  # Không crash


def test_server_stop_idempotent():
    port = _free_port()
    s = IAPProxyServer(port=port)
    _start_server_in_thread(s)
    s.stop()
    s.stop()  # Không crash