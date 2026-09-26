"""UI test cho PreviewDialog — renders patch list."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QPushButton, QTextEdit

from ui.preview_dialog import PreviewDialog


@pytest.fixture
def dialog(qtbot):
    patches = [
        {"label": "license", "mode": "auto",
         "description": "Auto license patch"},
        {"label": "ads", "mode": "remove"},
        {"label": "backup"},
    ]
    dlg = PreviewDialog(patches)
    qtbot.addWidget(dlg)
    return dlg


def _find_button(widget, text_substr: str):
    for btn in widget.findChildren(QPushButton):
        if text_substr.lower() in btn.text().lower():
            return btn
    return None


class TestConstruction:
    def test_window_title(self, dialog):
        assert "Xem trước" in dialog.windowTitle()

    def test_has_text_edit(self, dialog):
        assert dialog.findChild(QTextEdit) is not None

    def test_renders_all_labels(self, dialog):
        text = dialog.findChild(QTextEdit).toPlainText()
        assert "license" in text
        assert "ads" in text
        assert "backup" in text

    def test_renders_modes(self, dialog):
        text = dialog.findChild(QTextEdit).toPlainText()
        assert "Mode: auto" in text
        assert "Mode: remove" in text

    def test_renders_descriptions(self, dialog):
        text = dialog.findChild(QTextEdit).toPlainText()
        assert "Auto license patch" in text


class TestSignals:
    def test_accept_on_continue(self, dialog, qtbot):
        btn = _find_button(dialog, "Tiếp tục")
        assert btn is not None
        with qtbot.waitSignal(dialog.accepted, timeout=500):
            btn.click()

    def test_reject_on_back(self, dialog, qtbot):
        btn = _find_button(dialog, "Quay lại")
        assert btn is not None
        with qtbot.waitSignal(dialog.rejected, timeout=500):
            btn.click()


class TestEdgeCases:
    def test_empty_patches_no_crash(self, qtbot):
        dlg = PreviewDialog([])
        qtbot.addWidget(dlg)
        assert dlg.findChild(QTextEdit).toPlainText() == ""

    def test_patch_with_unknown_label(self, qtbot):
        dlg = PreviewDialog([{"mode": "x"}])
        qtbot.addWidget(dlg)
        text = dlg.findChild(QTextEdit).toPlainText()
        assert "?" in text