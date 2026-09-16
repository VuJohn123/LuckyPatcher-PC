"""Test IAP manager — save/load/delete/repeat."""
import os
import tempfile

from patcher.iap_manager import IAPManager


def _make(tmp: str) -> IAPManager:
    return IAPManager(storage_path=os.path.join(tmp, "iap.json"))


def test_save_and_get():
    with tempfile.TemporaryDirectory() as tmp:
        m = _make(tmp)
        tid = m.save_purchase("com.app", "coins", {"orderId": "x"})
        assert tid == 1
        purchases = m.get_saved_purchases()
        assert len(purchases) == 1


def test_get_by_package():
    with tempfile.TemporaryDirectory() as tmp:
        m = _make(tmp)
        m.save_purchase("com.a", "p1", {})
        m.save_purchase("com.b", "p2", {})
        assert len(m.get_saved_purchases("com.a")) == 1


def test_auto_repeat():
    with tempfile.TemporaryDirectory() as tmp:
        m = _make(tmp)
        m.save_purchase("com.app", "coins", {"orderId": "x"})
        resp = m.auto_repeat("com.app", "coins")
        assert resp is not None
        assert resp["code"] == 0
        assert "auto-repeat" in resp["message"].lower()


def test_auto_repeat_missing():
    with tempfile.TemporaryDirectory() as tmp:
        m = _make(tmp)
        assert m.auto_repeat("no", "no") is None


def test_delete():
    with tempfile.TemporaryDirectory() as tmp:
        m = _make(tmp)
        tid = m.save_purchase("com.app", "coins", {})
        m.delete_purchase(tid)
        assert m.get_saved_purchases() == []