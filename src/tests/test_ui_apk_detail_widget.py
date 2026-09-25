"""
UI test cho APKDetailWidget — không cần full MainWindow.

Dùng pytest-qt `qtbot` fixture để tạo QApplication headless-safe.
"""
from __future__ import annotations

import pytest

from PyQt6.QtCore import Qt

from ui.apk_detail_widget import (
    APKDetailWidget,
    _COLOR_MAP,
    _TYPE_TO_ACTION,
)


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def widget(qtbot):
    w = APKDetailWidget()
    qtbot.addWidget(w)
    return w


def _sample_result(findings=None, colors=None):
    return {
        "findings": findings or [],
        "summary": {
            "app_name": "Test App",
            "package": "com.example.test",
            "version": "1.0.0",
            "size": 12 * 1024 * 1024,
        },
        "colors": colors or ["white"],
    }


# ============================================================
# Header + Summary
# ============================================================
class TestHeader:
    def test_header_renders_app_name(self, widget):
        widget.populate(_sample_result())
        # Search tất cả QLabel text
        all_labels = _collect_label_texts(widget)
        assert any("Test App" in t for t in all_labels), all_labels

    def test_header_renders_package(self, widget):
        widget.populate(_sample_result())
        all_labels = _collect_label_texts(widget)
        assert any("com.example.test" in t for t in all_labels)

    def test_format_size_mb(self, widget):
        assert "12.0 MB" in widget._format_size(12 * 1024 * 1024)

    def test_format_size_gb(self, widget):
        assert "1.5 GB" in widget._format_size(int(1.5 * 1024**3))

    def test_format_size_bytes(self, widget):
        assert widget._format_size(512) == "512.0 B"

    def test_format_size_zero(self, widget):
        assert widget._format_size(0) == "0 B"

    def test_elide_short_text(self, widget):
        assert widget._elide("hello", 10) == "hello"

    def test_elide_long_text(self, widget):
        out = widget._elide("a" * 100, 10)
        assert out == "a" * 7 + "..."

    def test_elide_empty(self, widget):
        assert widget._elide("", 10) == ""


# ============================================================
# Clear
# ============================================================
class TestClear:
    def test_clear_removes_all_widgets(self, widget):
        widget.populate(_sample_result())
        n_before = widget.content_layout.count()
        assert n_before > 0
        widget.clear()
        assert widget.content_layout.count() == 0

    def test_populate_is_idempotent(self, widget):
        widget.populate(_sample_result())
        widget.populate(_sample_result())
        # Không crash, không duplicate về mặt logic
        assert widget.content_layout.count() > 0


# ============================================================
# Color bar
# ============================================================
class TestColorBar:
    def test_color_bar_renders_license_label(self, widget):
        widget.populate(_sample_result(colors=["green"]))
        all_labels = _collect_label_texts(widget)
        assert any("License" in t for t in all_labels)

    def test_color_bar_multiple(self, widget):
        widget.populate(_sample_result(colors=["green", "blue"]))
        all_labels = _collect_label_texts(widget)
        assert any("License" in t for t in all_labels)
        assert any("Ads" in t for t in all_labels)

    def test_color_bar_unknown_fallback(self, widget):
        widget.populate(_sample_result(colors=["bogus"]))
        # Không crash
        assert widget.content_layout.count() > 0


# ============================================================
# Packer warning
# ============================================================
class TestPackerWarning:
    def test_packer_warning_renders(self, widget):
        findings = [{
            "type": "packer",
            "color": "red",
            "title": "Packed: PairIP",
            "description": "APK packed by PairIP",
            "details": ["libpairipcore.so"],
        }]
        widget.populate(_sample_result(findings=findings))
        all_labels = _collect_label_texts(widget)
        assert any("PairIP" in t for t in all_labels)

    def test_no_packer_no_warning(self, widget):
        widget.populate(_sample_result())
        all_labels = _collect_label_texts(widget)
        assert not any("Packed:" in t for t in all_labels)


# ============================================================
# Features
# ============================================================
class TestFeatures:
    def test_feature_group_renders_title(self, widget):
        findings = [{
            "type": "license",
            "color": "green",
            "title": "License Verification Found",
            "description": "Class: Lx/LicenseValidator;",
        }]
        widget.populate(_sample_result(findings=findings))
        all_labels = _collect_label_texts(widget)
        assert any("License Verification Found" in t for t in all_labels)


# ============================================================
# Quick Actions signal
# ============================================================
class TestQuickActions:
    def test_license_finding_emits_remove_license(
        self, widget, qtbot,
    ):
        findings = [{
            "type": "license",
            "color": "green",
            "title": "License",
            "description": "x",
            "action": "remove_license",
        }]
        widget.populate(_sample_result(findings=findings))

        # Find button by text pattern
        btn = _find_button(widget, "License")
        assert btn is not None

        with qtbot.waitSignal(
            widget.patch_action_requested, timeout=1000
        ) as blocker:
            btn.click()
        assert blocker.args == ["remove_license"]

    def test_iap_action_emits_correct_key(self, widget, qtbot):
        findings = [{
            "type": "iap",
            "color": "green",
            "title": "IAP",
            "description": "Billing",
            "action": "iap_emulation",
        }]
        widget.populate(_sample_result(findings=findings))

        btn = _find_button(widget, "IAP")
        assert btn is not None

        with qtbot.waitSignal(
            widget.patch_action_requested, timeout=1000
        ) as blocker:
            btn.click()
        assert blocker.args == ["iap_emulation"]

    def test_derive_action_from_type(self, widget):
        f = {"type": "license", "title": "x"}  # không có action
        assert widget._derive_action(f) == "remove_license"

    def test_derive_action_explicit(self, widget):
        f = {"type": "license", "action": "custom_override"}
        assert widget._derive_action(f) == "custom_override"

    def test_derive_action_unknown_type_returns_none(self, widget):
        f = {"type": "bogus_type"}
        assert widget._derive_action(f) is None

    def test_type_to_action_map_has_license(self):
        assert _TYPE_TO_ACTION["license"] == "remove_license"

    def test_type_to_action_map_has_iap(self):
        assert _TYPE_TO_ACTION["iap"] == "iap_emulation"

    def test_type_to_action_map_has_ads(self):
        assert _TYPE_TO_ACTION["ads"] == "remove_ads"


# ============================================================
# Rebuild / Menu signals
# ============================================================
class TestPrimarySignals:
    def test_rebuild_requested_emitted(self, widget, qtbot):
        widget.populate(_sample_result())
        btn = _find_button(widget, "Rebuild")
        assert btn is not None
        with qtbot.waitSignal(widget.rebuild_requested, timeout=1000):
            btn.click()

    def test_menu_of_patches_requested(self, widget, qtbot):
        widget.populate(_sample_result())
        btn = _find_button(widget, "Menu")
        assert btn is not None
        with qtbot.waitSignal(
            widget.menu_of_patches_requested, timeout=1000
        ):
            btn.click()


# ============================================================
# Helpers
# ============================================================
def _collect_label_texts(widget) -> list[str]:
    from PyQt6.QtWidgets import QLabel
    return [
        lbl.text() for lbl in widget.findChildren(QLabel) if lbl.text()
    ]


def _find_button(widget, text_substring: str):
    from PyQt6.QtWidgets import QPushButton
    for btn in widget.findChildren(QPushButton):
        if text_substring.lower() in btn.text().lower():
            return btn
    return None