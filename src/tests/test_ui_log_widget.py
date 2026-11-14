"""UI test cho LogWidget — QPlainTextEdit wrapper."""
from __future__ import annotations

import pytest

from ui.log_widget import LogWidget


@pytest.fixture
def widget(qtbot):
    w = LogWidget()
    qtbot.addWidget(w)
    return w


class TestConstruction:
    def test_readonly(self, widget):
        assert widget.isReadOnly()

    def test_max_blocks_constant(self):
        assert LogWidget.MAX_BLOCKS == 5000

    def test_max_blocks_applied(self, widget):
        # QPlainTextEdit.maximumBlockCount()
        assert widget.maximumBlockCount() == 5000

    def test_empty_initially(self, widget):
        assert widget.toPlainText() == ""


class TestAppendLog:
    def test_append_single(self, widget):
        widget.append_log("[i] hello")
        assert "hello" in widget.toPlainText()

    def test_append_multiple(self, widget):
        widget.append_log("line 1")
        widget.append_log("line 2")
        widget.append_log("line 3")
        text = widget.toPlainText()
        assert "line 1" in text
        assert "line 3" in text

    def test_append_empty_ignored(self, widget):
        widget.append_log("")
        assert widget.toPlainText() == ""

    def test_append_none_ignored(self, widget):
        widget.append_log(None)
        assert widget.toPlainText() == ""

    def test_cursor_at_end_after_append(self, widget):
        widget.append_log("test message")
        cursor = widget.textCursor()
        assert cursor.position() == len(widget.toPlainText())


class TestAppendAlias:
    def test_append_method_alias(self, widget):
        widget.append("[i] alias")
        assert "alias" in widget.toPlainText()


class TestClearLog:
    def test_clear_removes_all(self, widget):
        widget.append_log("a")
        widget.append_log("b")
        widget.clear_log()
        assert widget.toPlainText() == ""

    def test_clear_empty_no_crash(self, widget):
        widget.clear_log()
        assert widget.toPlainText() == ""


class TestBlockCap:
    def test_many_lines_capped(self, widget):
        for i in range(6000):
            widget.append_log(f"line {i}")
        # maximumBlockCount enforces cap
        assert widget.blockCount() <= LogWidget.MAX_BLOCKS


class TestAutoScroll:
    def _fill(self, widget, qtbot, n=100):
        widget.resize(400, 160)
        widget.show()
        qtbot.waitExposed(widget)
        for i in range(n):
            widget.append_log(f"line {i} " + "x" * 40)
        qtbot.waitUntil(
            lambda: widget.verticalScrollBar().maximum() > 0, timeout=3000
        )
        return widget.verticalScrollBar()

    def test_follows_when_at_bottom(self, widget, qtbot):
        bar = self._fill(widget, qtbot)
        assert bar.value() == bar.maximum()
        widget.append_log("another line")
        assert bar.value() == bar.maximum()

    def test_does_not_yank_while_reading(self, widget, qtbot):
        bar = self._fill(widget, qtbot)
        bar.setValue(0)
        assert bar.value() == 0
        widget.append_log("new line while reading")
        assert bar.value() == 0, "log jumped to the bottom while reading"
