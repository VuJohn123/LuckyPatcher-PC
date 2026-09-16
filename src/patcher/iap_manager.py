"""Quản lý giao dịch IAP — lưu JSON, hỗ trợ auto-repeat."""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()


class IAPManager:
    def __init__(self, storage_path: str | None = None):
        if storage_path is None:
            storage_path = os.path.join(
                os.path.expanduser("~"), "Documents", "LP_PC_Suite",
                "iap_transactions.json",
            )
        self.storage_path = storage_path
        self.auto_repeat_enabled = False
        self.save_for_restore_enabled = False

    def _load(self) -> list[dict]:
        if not os.path.exists(self.storage_path):
            return []
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, data: list[dict]) -> None:
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.storage_path),
                                    suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.storage_path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    def save_purchase(self, package_name: str, product_id: str,
                      purchase_data: dict) -> int:
        with _LOCK:
            transactions = self._load()
            tid = len(transactions) + 1
            transactions.append({
                "id": tid,
                "package": package_name,
                "product": product_id,
                "data": purchase_data,
                "timestamp": time.time(),
            })
            try:
                self._save(transactions)
            except OSError as e:
                logger.error("save_purchase failed: %s", e)
            return tid

    def get_saved_purchases(self, package_name: str | None = None) -> list[dict]:
        with _LOCK:
            transactions = self._load()
        if package_name:
            return [t for t in transactions if t.get("package") == package_name]
        return transactions

    def auto_repeat(self, package_name: str, product_id: str) -> dict | None:
        for t in self.get_saved_purchases(package_name):
            if t.get("product") == product_id:
                return {
                    "code": 0,
                    "message": "Success (auto-repeat)",
                    "purchaseData": json.dumps(t.get("data", {})),
                    "signature": "LP-PC-Suite-AutoRepeat",
                }
        return None

    def delete_purchase(self, transaction_id: int) -> None:
        with _LOCK:
            transactions = [t for t in self._load() if t.get("id") != transaction_id]
            try:
                self._save(transactions)
            except OSError as e:
                logger.error("delete_purchase failed: %s", e)