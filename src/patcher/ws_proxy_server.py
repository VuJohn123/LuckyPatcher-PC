"""
WebSocket proxy server — thay thế HTTP cho app dùng WS.
Optional: chỉ chạy nếu websockets lib có sẵn.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import random
import time

logger = logging.getLogger(__name__)

try:
    from websockets.server import serve
    WS_AVAILABLE = True
except ImportError:
    WS_AVAILABLE = False


def _build_buy_intent(package_name: str, product_id: str,
                      developer_payload: str = "") -> dict:
    order_id = (
        f"GPA.{random.randint(1000,9999)}-"
        f"{random.randint(1000,9999)}-"
        f"{random.randint(10000,99999)}"
    )
    token = base64.b64encode(
        f"{package_name}:{product_id}:{order_id}:{int(time.time()*1000)}".encode()
    ).decode()

    purchase_data = {
        "orderId": order_id,
        "packageName": package_name,
        "productId": product_id,
        "purchaseTime": int(time.time() * 1000),
        "purchaseState": 0,
        "purchaseToken": token,
        "autoRenewing": False,
        "developerPayload": developer_payload,
    }
    signature = base64.b64encode(
        hashlib.sha1(json.dumps(purchase_data).encode()).digest()
    ).decode()

    return {
        "code": 0,
        "message": "Success",
        "purchaseData": json.dumps(purchase_data),
        "signature": signature,
    }


class WSBillingProxy:
    def __init__(self, host: str = "0.0.0.0", port: int = 8889,
                 log_callback=print):
        self.host = host
        self.port = port
        self.log = log_callback
        self._server = None

    async def _handle(self, websocket):
        self.log(f"[*] [WSProxy] Client: {websocket.remote_address}")
        try:
            async for message in websocket:
                response = self._route(message)
                await websocket.send(json.dumps(response))
        except Exception as e:
            logger.warning("WS connection error: %s", e)

    def _route(self, message: str) -> dict:
        try:
            req = json.loads(message)
        except json.JSONDecodeError:
            return {"error": "invalid json"}

        method = req.get("method", "")
        package = req.get("packageName", "com.example.app")
        product = req.get("productId", "product")

        if "getBuyIntent" in method or "buy" in method:
            return _build_buy_intent(package, product,
                                     req.get("developerPayload", ""))
        if "getPurchases" in method:
            return {"code": 0, "purchases": [], "message": "Success"}
        if "isBillingSupported" in method:
            return {"code": 0, "message": "Billing supported"}
        if "consumePurchase" in method:
            return {"code": 0, "message": "Consumed"}
        return {"code": 0, "message": "Success"}

    async def _serve(self):
        self._server = await serve(self._handle, self.host, self.port,
                                    ping_interval=30, ping_timeout=10)
        self.log(f"[*] [WSProxy] Listening {self.host}:{self.port}")
        await self._server.wait_closed()

    def start(self):
        if not WS_AVAILABLE:
            self.log("[!] websockets không có — bỏ qua WS proxy")
            return
        asyncio.run(self._serve())

    def stop(self):
        if self._server:
            self._server.close()