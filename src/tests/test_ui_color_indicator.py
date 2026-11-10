"""UI test cho ColorIndicator."""
from __future__ import annotations

import pytest

from ui.color_indicator import _COLOR_MAP, ColorIndicator


@pytest.fixture
def indicator(qtbot):
    w = ColorIndicator("green", size=12)
    qtbot.addWidget(w)
    return w


class TestConstruction:
    def test_default_color(self, qtbot):
        w = ColorIndicator()
        qtbot.addWidget(w)
        assert w.toolTip() == "White"

    def test_default_size(self, qtbot):
        w = ColorIndicator()
        qtbot.addWidget(w)
        assert w.width() == 12
        assert w.height() == 12

    def test_custom_size(self, qtbot):
        w = ColorIndicator(size=20)
        qtbot.addWidget(w)
        assert w.width() == 20
        assert w.height() == 20

    def test_initial_color_applied(self, indicator):
        assert "background-color" in indicator.styleSheet()

    def test_tooltip_shows_color(self, indicator):
        assert indicator.toolTip() == "Green"


class TestSetColor:
    def test_change_color(self, indicator):
        indicator.set_color("blue")
        assert indicator.toolTip() == "Blue"
        assert "#1f6feb" in indicator.styleSheet()

    def test_unknown_color_fallback(self, indicator):
        indicator.set_color("bogus")
        assert "Bogus" in indicator.toolTip()
        # Fallback hex
        assert "#8b949e" in indicator.styleSheet()

    def test_border_radius_half_width(self, indicator):
        # size=12 → radius 6
        assert "border-radius: 6px" in indicator.styleSheet()

    def test_all_7_colors(self, indicator):
        for c in ("green", "yellow", "blue", "purple",
                  "orange", "red", "white"):
            indicator.set_color(c)
            assert c.capitalize() in indicator.toolTip()


class TestColorMap:
    def test_has_7_colors(self):
        assert len(_COLOR_MAP) == 7

    def test_hex_format(self):
        for v in _COLOR_MAP.values():
            assert v.startswith("#")
            assert len(v) == 7
