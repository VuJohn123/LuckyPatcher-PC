"""UI test cho AppListWidget — card list + filter + signals."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu

from ui.app_list_widget import (
    _COLOR_EMOJI,
    _COLOR_MAP,
    AppListWidget,
    _AppItemWidget,
)


@pytest.fixture
def widget(qtbot):
    w = AppListWidget()
    qtbot.addWidget(w)
    return w


# ============================================================
# Construction
# ============================================================
class TestConstruction:
    def test_empty_initially(self, widget):
        assert widget.count() == 0
        assert widget.all_items == []

    def test_single_selection_mode(self, widget):
        assert (
            widget.selectionMode()
            == AppListWidget.SelectionMode.SingleSelection
        )


# ============================================================
# add_app
# ============================================================
class TestAddApp:
    def test_add_single_app(self, widget):
        widget.add_app("Test App", "com.test", ["green"])
        assert widget.count() == 1
        assert len(widget.all_items) == 1

    def test_add_multiple_apps(self, widget):
        widget.add_app("A", "com.a", ["green"])
        widget.add_app("B", "com.b", ["blue"])
        assert widget.count() == 2

    def test_item_data_stored(self, widget):
        widget.add_app(
            "My App", "com.example", ["green", "blue"],
        )
        item = widget.item(0)
        data = item.data(Qt.ItemDataRole.UserRole)
        assert data["name"] == "My App"
        assert data["package"] == "com.example"
        assert data["colors"] == ["green", "blue"]
        assert data["is_patched"] is False

    def test_is_patched_flag(self, widget):
        widget.add_app("A", "com.a", ["green"], is_patched=True)
        data = widget.item(0).data(Qt.ItemDataRole.UserRole)
        assert data["is_patched"] is True

    def test_size_hint_set(self, widget):
        widget.add_app("A", "com.a", ["green"])
        item = widget.item(0)
        # item sizeHint phản ánh widget's minimumHeight (64) qua layout
        size = item.sizeHint()
        assert size.height() >= 50  # computed value có thể nhỏ hơn minimumHeight
        # Actual minimum enforced
        w = widget.itemWidget(item)
        assert w.minimumHeight() >= 60

    def test_row_not_clipped_by_card_height(self, widget):
        """The row must be at least as tall as the card, or it gets cut."""
        widget.add_app("A", "com.a", ["green"])
        item = widget.item(0)
        w = widget.itemWidget(item)
        assert w is not None
        assert item.sizeHint().height() >= w.minimumHeight()

    def test_widget_attached(self, widget):
        widget.add_app("A", "com.a", ["green"])
        item = widget.item(0)
        w = widget.itemWidget(item)
        assert isinstance(w, _AppItemWidget)

    def test_unknown_color_falls_back(self, widget):
        widget.add_app("A", "com.a", ["bogus"])
        # Không crash
        assert widget.count() == 1

    def test_empty_colors_list(self, widget):
        widget.add_app("A", "com.a", [])
        assert widget.count() == 1


# ============================================================
# _colors_to_findings mapping
# ============================================================
class TestColorsToFindings:
    def test_green_license(self, widget):
        findings = widget._colors_to_findings(["green"])
        assert len(findings) == 1
        assert findings[0]["type"] == "license"

    def test_blue_ads(self, widget):
        findings = widget._colors_to_findings(["blue"])
        assert findings[0]["type"] == "ads"

    def test_yellow_custom(self, widget):
        findings = widget._colors_to_findings(["yellow"])
        assert findings[0]["type"] == "custom_patch"

    def test_purple_boot(self, widget):
        findings = widget._colors_to_findings(["purple"])
        assert findings[0]["type"] == "system_boot"

    def test_orange_system(self, widget):
        findings = widget._colors_to_findings(["orange"])
        assert findings[0]["type"] == "system"

    def test_red_protected(self, widget):
        findings = widget._colors_to_findings(["red"])
        assert findings[0]["type"] == "protected"

    def test_multiple_colors(self, widget):
        findings = widget._colors_to_findings(
            ["green", "blue", "red"]
        )
        types = {f["type"] for f in findings}
        assert types == {"license", "ads", "protected"}

    def test_white_no_findings(self, widget):
        assert widget._colors_to_findings(["white"]) == []

    def test_empty_no_findings(self, widget):
        assert widget._colors_to_findings([]) == []


# ============================================================
# filter — by text
# ============================================================
class TestFilterByText:
    def test_filter_by_name(self, widget):
        widget.add_app("Alpha Game", "com.alpha", ["blue"])
        widget.add_app("Beta Tool", "com.beta", ["green"])
        widget.filter("alpha", "All")
        assert not widget.item(0).isHidden()
        assert widget.item(1).isHidden()

    def test_filter_by_package(self, widget):
        widget.add_app("A", "com.foo.bar", ["green"])
        widget.add_app("B", "com.other", ["green"])
        widget.filter("foo", "All")
        assert not widget.item(0).isHidden()
        assert widget.item(1).isHidden()

    def test_filter_case_insensitive(self, widget):
        widget.add_app("UPPERCASE", "com.x", ["green"])
        widget.filter("uppercase", "All")
        assert not widget.item(0).isHidden()

    def test_empty_filter_shows_all(self, widget):
        widget.add_app("A", "com.a", ["green"])
        widget.add_app("B", "com.b", ["blue"])
        widget.filter("", "All")
        assert not widget.item(0).isHidden()
        assert not widget.item(1).isHidden()

    def test_none_filter_shows_all(self, widget):
        widget.add_app("A", "com.a", ["green"])
        widget.filter(None, "All")
        assert not widget.item(0).isHidden()

    def test_no_match_hides_all(self, widget):
        widget.add_app("A", "com.a", ["green"])
        widget.add_app("B", "com.b", ["blue"])
        widget.filter("zzzz", "All")
        assert widget.item(0).isHidden()
        assert widget.item(1).isHidden()


# ============================================================
# filter — by type
# ============================================================
class TestFilterByType:
    def test_license_check_filter(self, widget):
        widget.add_app("A", "com.a", ["green"])
        widget.add_app("B", "com.b", ["blue"])
        widget.filter("", "License check")
        assert not widget.item(0).isHidden()
        assert widget.item(1).isHidden()

    def test_ads_filter(self, widget):
        widget.add_app("A", "com.a", ["blue"])
        widget.add_app("B", "com.b", ["green"])
        widget.filter("", "Ads")
        assert not widget.item(0).isHidden()
        assert widget.item(1).isHidden()

    def test_custom_patch_filter(self, widget):
        widget.add_app("A", "com.a", ["yellow"])
        widget.add_app("B", "com.b", ["green"])
        widget.filter("", "Custom patch")
        assert not widget.item(0).isHidden()
        assert widget.item(1).isHidden()

    def test_system_filter_includes_purple(self, widget):
        widget.add_app("A", "com.a", ["purple"])
        widget.add_app("B", "com.b", ["green"])
        widget.filter("", "System")
        assert not widget.item(0).isHidden()
        assert widget.item(1).isHidden()

    def test_system_filter_includes_orange(self, widget):
        widget.add_app("A", "com.a", ["orange"])
        widget.filter("", "System")
        assert not widget.item(0).isHidden()

    def test_all_filter_shows_all(self, widget):
        widget.add_app("A", "com.a", ["green"])
        widget.add_app("B", "com.b", ["blue"])
        widget.filter("", "All")
        assert not widget.item(0).isHidden()
        assert not widget.item(1).isHidden()


# ============================================================
# filter — localized labels (combo shows vi text)
# ============================================================
class TestFilterByLocalizedLabel:
    """Toolbar combo passes its localized text straight to filter()."""

    def _populate(self, widget):
        widget.add_app("LicApp", "com.a", ["green"])
        widget.add_app("AdsApp", "com.b", ["blue"])
        widget.add_app("SysApp", "com.c", ["purple"])

    def test_vietnamese_license(self, widget):
        self._populate(widget)
        widget.filter("", "Kiểm tra License")
        assert [not widget.item(i).isHidden() for i in range(3)] == [
            True, False, False,
        ]

    def test_vietnamese_ads(self, widget):
        self._populate(widget)
        widget.filter("", "Quảng cáo")
        assert [not widget.item(i).isHidden() for i in range(3)] == [
            False, True, False,
        ]

    def test_vietnamese_system(self, widget):
        self._populate(widget)
        widget.filter("", "Hệ thống")
        assert [not widget.item(i).isHidden() for i in range(3)] == [
            False, False, True,
        ]

    def test_vietnamese_all(self, widget):
        self._populate(widget)
        widget.filter("", "Tất cả")
        assert [not widget.item(i).isHidden() for i in range(3)] == [
            True, True, True,
        ]

    def test_localized_label_case_insensitive(self, widget):
        self._populate(widget)
        widget.filter("", "quảng cáo")
        assert not widget.item(1).isHidden()
        assert widget.item(0).isHidden()


# ============================================================
# clear_all
# ============================================================
class TestClearAll:
    def test_clear_removes_all(self, widget):
        widget.add_app("A", "com.a", ["green"])
        widget.add_app("B", "com.b", ["blue"])
        widget.clear_all()
        assert widget.count() == 0
        assert widget.all_items == []

    def test_clear_empty_no_crash(self, widget):
        widget.clear_all()
        assert widget.count() == 0


# ============================================================
# Current item change
# ============================================================
class TestCurrentItemChanged:
    def test_selected_property_set(self, widget):
        widget.add_app("A", "com.a", ["green"])
        widget.add_app("B", "com.b", ["blue"])
        widget.setCurrentRow(1)
        item_w = widget.itemWidget(widget.item(1))
        assert item_w.property("selected") is True

    def test_previous_item_deselected(self, widget):
        widget.add_app("A", "com.a", ["green"])
        widget.add_app("B", "com.b", ["blue"])
        widget.setCurrentRow(0)
        widget.setCurrentRow(1)
        item0_w = widget.itemWidget(widget.item(0))
        assert item0_w.property("selected") is False


# ============================================================
# Context menu
# ============================================================
class TestContextMenu:
    def test_bad_pos_no_crash(self, widget, monkeypatch):
        """Position ngoài item — không crash."""
        monkeypatch.setattr(QMenu, "exec", lambda *a, **kw: None)
        from PyQt6.QtCore import QPoint
        widget._show_context_menu(QPoint(-10, -10))

    def test_menu_constructed_for_item(self, widget, monkeypatch):
        """Item hợp lệ → QMenu.exec được gọi."""
        widget.add_app("A", "com.a", ["green"])
        calls: list = []
        monkeypatch.setattr(
            QMenu, "exec",
            lambda self, *a, **kw: calls.append(True) or None,
        )
        # Position giữa item 0
        rect = widget.visualItemRect(widget.item(0))
        widget._show_context_menu(rect.center())
        assert calls


# ============================================================
# Color maps
# ============================================================
class TestColorMaps:
    def test_all_7_colors_mapped(self):
        expected = {
            "green", "yellow", "blue", "purple",
            "orange", "red", "white",
        }
        assert set(_COLOR_MAP.keys()) == expected
        assert set(_COLOR_EMOJI.keys()) == expected

    def test_hex_format(self):
        for v in _COLOR_MAP.values():
            assert v.startswith("#")
            assert len(v) == 7


# ============================================================
# _AppItemWidget standalone
# ============================================================
class TestAppItemWidget:
    def test_basic_construction(self, qtbot):
        w = _AppItemWidget("Name", "com.x", ["green"])
        qtbot.addWidget(w)
        assert w.minimumHeight() >= 60

    def test_is_patched_shows_clover(self, qtbot):
        w = _AppItemWidget("Name", "com.x", ["green"], is_patched=True)
        qtbot.addWidget(w)
        # Tooltip chứa "Đã patch"
        assert "Đã patch" in w.toolTip()

    def test_tooltip_has_colors(self, qtbot):
        w = _AppItemWidget("N", "com.x", ["green", "blue"])
        qtbot.addWidget(w)
        tip = w.toolTip()
        assert "Name" not in tip or "N" in tip
        assert "Green" in tip or "green" in tip

    def test_badge_creation(self, qtbot):
        w = _AppItemWidget("N", "com.x", ["purple"])
        qtbot.addWidget(w)
        badge = w._badge("SYS", "#d29922")
        assert badge.text() == "SYS"
