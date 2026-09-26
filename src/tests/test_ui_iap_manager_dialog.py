"""UI test cho IAPManagerDialog — list + delete + repeat."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QPushButton

from ui.iap_manager_dialog import IAPManagerDialog


@pytest.fixture
def iap_mock():
    m = MagicMock()
    m.get_saved_purchases.return_value = [
        {"id": 1, "package": "com.a", "product": "pro",
         "timestamp": 1700000000},
        {"id": 2, "package": "com.b", "product": "vip",
         "timestamp": 1700001000},
    ]
    return m


@pytest.fixture
def dialog(qtbot, iap_mock):
    dlg = IAPManagerDialog(iap_mock)
    qtbot.addWidget(dlg)
    return dlg


def _find_button(widget, text_substr: str):
    for btn in widget.findChildren(QPushButton):
        if text_substr.lower() in btn.text().lower():
            return btn
    return None


class TestConstruction:
    def test_window_title(self, dialog):
        assert "IAP" in dialog.windowTitle()

    def test_list_has_2_items(self, dialog):
        assert dialog.list.count() == 2

    def test_list_items_have_id_data(self, dialog):
        item0 = dialog.list.item(0)
        assert item0.data(Qt.ItemDataRole.UserRole) == 1
        item1 = dialog.list.item(1)
        assert item1.data(Qt.ItemDataRole.UserRole) == 2

    def test_item_text_contains_package(self, dialog):
        text = dialog.list.item(0).text()
        assert "com.a" in text
        assert "pro" in text


class TestLoad:
    def test_reload_refreshes_list(self, dialog, iap_mock):
        iap_mock.get_saved_purchases.return_value = [
            {"id": 99, "package": "new.pkg", "product": "x",
             "timestamp": 0},
        ]
        dialog._load()
        assert dialog.list.count() == 1

    def test_load_handles_exception(self, dialog, iap_mock):
        iap_mock.get_saved_purchases.side_effect = RuntimeError("boom")
        dialog._load()
        assert dialog.list.count() == 0

    def test_refresh_button_triggers_load(self, dialog, qtbot, iap_mock):
        btn = _find_button(dialog, "Làm mới")
        assert btn is not None
        iap_mock.get_saved_purchases.reset_mock()
        btn.click()
        assert iap_mock.get_saved_purchases.called


class TestDelete:
    def test_delete_no_selection_no_op(self, dialog, iap_mock):
        dialog._delete()
        iap_mock.delete_purchase.assert_not_called()

    def test_delete_with_selection(self, dialog, iap_mock):
        dialog.list.setCurrentRow(0)
        dialog._delete()
        iap_mock.delete_purchase.assert_called_once_with(1)

    def test_delete_reloads_list(self, dialog, iap_mock):
        dialog.list.setCurrentRow(0)
        iap_mock.get_saved_purchases.reset_mock()
        dialog._delete()
        # _delete calls _load → get_saved_purchases lại
        assert iap_mock.get_saved_purchases.called

    def test_delete_error_shows_warning(
        self, dialog, iap_mock, monkeypatch,
    ):
        calls: list = []
        monkeypatch.setattr(
            "ui.iap_manager_dialog.QMessageBox.warning",
            lambda *a, **kw: calls.append(True),
        )
        iap_mock.delete_purchase.side_effect = RuntimeError("err")
        dialog.list.setCurrentRow(0)
        dialog._delete()
        assert calls


class TestRepeat:
    def test_repeat_no_selection_no_op(self, dialog, iap_mock):
        dialog._repeat()
        iap_mock.auto_repeat.assert_not_called()

    def test_repeat_with_selection(
        self, dialog, iap_mock, monkeypatch,
    ):
        monkeypatch.setattr(
            "ui.iap_manager_dialog.QMessageBox.information",
            lambda *a, **kw: None,
        )
        dialog.list.setCurrentRow(0)
        dialog._repeat()
        iap_mock.auto_repeat.assert_called_once_with("com.a", "pro")

    def test_repeat_second_item(
        self, dialog, iap_mock, monkeypatch,
    ):
        monkeypatch.setattr(
            "ui.iap_manager_dialog.QMessageBox.information",
            lambda *a, **kw: None,
        )
        dialog.list.setCurrentRow(1)
        dialog._repeat()
        iap_mock.auto_repeat.assert_called_once_with("com.b", "vip")

    def test_repeat_shows_info(
        self, dialog, iap_mock, monkeypatch,
    ):
        calls: list = []
        monkeypatch.setattr(
            "ui.iap_manager_dialog.QMessageBox.information",
            lambda *a, **kw: calls.append(True),
        )
        dialog.list.setCurrentRow(0)
        dialog._repeat()
        assert calls


class TestClose:
    def test_close_button_accepts(self, dialog, qtbot):
        btn = _find_button(dialog, "Đóng")
        assert btn is not None
        with qtbot.waitSignal(dialog.accepted, timeout=500):
            btn.click()