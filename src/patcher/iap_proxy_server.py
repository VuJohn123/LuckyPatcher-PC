"""
HTTP proxy server giả mạo Google Play Billing.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import random
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)


class _ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        # Tắt log mặc định noisy của http.server
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            request = json.loads(raw.decode("utf-8", errors="ignore"))
        except (ValueError, OSError):
            request = {}

        method = request.get("method", self.path.strip("/"))
        package_name = request.get("packageName", "com.example.app")
        product_id = request.get("productId", "product")

        response = self._route(method, package_name, product_id, request)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def _route(self, method, package_name, product_id, request):
        if "buy" in method or "getBuyIntent" in method:
            return self._buy_intent(package_name, product_id, request)
        if "purchase" in method or "getPurchases" in method:
            return self._get_purchases(package_name)
        if "supported" in method or "isBillingSupported" in method:
            return {"code": 0, "message": "Billing supported"}
        if "consume" in method or "consumePurchase" in method:
            return {"code": 0, "message": "Purchase consumed"}
        return {"code": 0, "message": "Success"}

    def _buy_intent(self, package_name, product_id, request):
        order_id = (
            f"GPA.{random.randint(1000,9999)}-"
            f"{random.randint(1000,9999)}-"
            f"{random.randint(10000,99999)}"
        )
        token_raw = f"{package_name}:{product_id}:{order_id}:{int(time.time()*1000)}"
        purchase_token = base64.b64encode(token_raw.encode()).decode()

        purchase_data = {
            "orderId": order_id,
            "packageName": package_name,
            "productId": product_id,
            "purchaseTime": int(time.time() * 1000),
            "purchaseState": 0,
            "purchaseToken": purchase_token,
            "autoRenewing": False,
            "developerPayload": request.get("developerPayload", ""),
        }

        # Lưu IAP nếu cần
        try:
            from patcher.iap_manager import IAPManager
            mgr = IAPManager()
            if mgr.save_for_restore_enabled:
                mgr.save_purchase(package_name, product_id, purchase_data)
            if mgr.auto_repeat_enabled:
                repeat = mgr.auto_repeat(package_name, product_id)
                if repeat:
                    return repeat
        except Exception as e:
            logger.warning("IAPManager save failed: %s", e)

        signature = base64.b64encode(
            hashlib.sha1(json.dumps(purchase_data).encode()).digest()
        ).decode()

        return {
            "code": 0,
            "message": "Success",
            "purchaseData": json.dumps(purchase_data),
            "signature": signature,
        }

    def _get_purchases(self, package_name):
        return {"code": 0, "purchases": [], "message": "Success"}


class IAPProxyServer:
    def __init__(self, host: str = "localhost", port: int = 8888):
        self.host = host
        self.port = port
        self.server: HTTPServer | None = None

    def start(self):
        try:
            self.server = HTTPServer((self.host, self.port), _ProxyHandler)
            logger.info("IAPProxyServer running on %s:%d", self.host, self.port)
            self.server.serve_forever()
        except OSError as e:
            logger.error("Proxy server failed: %s", e)

    def stop(self):
        if self.server:
            try:
                self.server.shutdown()
            except Exception:
                pass