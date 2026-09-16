"""Test iap_proxy_server — socket server."""
import socket
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


# Import module lazily vì nó có thể fail trên CI không có socket
try:
    from patcher.iap_proxy_server import IAPProxyServer
except ImportError:
    pytest.skip("iap_proxy_server không import được", allow_module_level=True)


# ============================================================
# Constructor
# ============================================================
def test_server_constructor():
    s = IAPProxyServer(port=9999)
    assert s.port == 9999


def test_server_default_port():
    s = IAPProxyServer()
    assert s.port == 8888


# ============================================================
# start / stop — dùng port ngẫu nhiên để tránh conflict
# ============================================================
def _find_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("localhost", 0))
        return sock.getsockname()[1]


def test_server_start_and_stop():
    port = _find_free_port()
    s = IAPProxyServer(port=port)
    s.start()
    time.sleep(0.3)  # Cho server bind

    # Verify có thể connect
    try:
        with socket.create_connection(("localhost", port), timeout=2):
            pass
    finally:
        s.stop()


def test_server_multiple_clients():
    port = _find_free_port()
    s = IAPProxyServer(port=port)
    s.start()
    time.sleep(0.3)

    try:
        # Connect 2 client đồng thời
        c1 = socket.create_connection(("localhost", port), timeout=2)
        c2 = socket.create_connection(("localhost", port), timeout=2)
        c1.close()
        c2.close()
    finally:
        s.stop()


def test_server_stop_idempotent():
    port = _find_free_port()
    s = IAPProxyServer(port=port)
    s.start()
    time.sleep(0.3)
    s.stop()
    s.stop()  # Không crash


def test_server_stop_without_start():
    """Stop khi chưa start → không crash."""
    s = IAPProxyServer(port=9999)
    s.stop()


def test_server_start_idempotent():
    """Start 2 lần → vẫn OK."""
    port = _find_free_port()
    s = IAPProxyServer(port=port)
    s.start()
    s.start()  # Không crash
    s.stop()