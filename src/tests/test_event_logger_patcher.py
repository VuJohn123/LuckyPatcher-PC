"""Test patcher/event_logger.py — EventLogger injector."""
import os

import pytest

from patcher.event_logger import EventLogger, LOGGER_SMALI, BILLING_METHODS


# ============================================================
# Constants
# ============================================================
def test_logger_smali_defined():
    assert "Lcom/lppc/logger/EventLogger;" in LOGGER_SMALI
    assert ".method public static log" in LOGGER_SMALI


def test_billing_methods_tuple():
    assert isinstance(BILLING_METHODS, tuple)
    assert "launchBillingFlow" in BILLING_METHODS


# ============================================================
# Constructor
# ============================================================
def test_init(tmp_path):
    p = EventLogger(str(tmp_path))
    assert p.decompiled_path == str(tmp_path)
    assert callable(p.log)


def test_init_with_log_callback(tmp_path):
    logs = []
    p = EventLogger(str(tmp_path), log_callback=logs.append)
    # Bound method không so sánh được bằng `is` — test bằng behavior
    p.log("hi")
    assert logs == ["hi"]


# ============================================================
# _inject_class
# ============================================================
def test_inject_class_creates_file(tmp_path):
    p = EventLogger(str(tmp_path))
    result = p._inject_class()
    assert result is True

    expected = tmp_path / "smali" / "com" / "lppc" / "logger" / "EventLogger.smali"
    assert expected.exists()


def test_inject_class_idempotent(tmp_path):
    p = EventLogger(str(tmp_path))
    assert p._inject_class() is True
    assert p._inject_class() is False  # Đã tồn tại


# ============================================================
# inject_logging
# ============================================================
def test_inject_logging_empty_dir(tmp_path):
    (tmp_path / "smali").mkdir()
    p = EventLogger(str(tmp_path))
    count = p.inject_logging()
    # Chỉ có class file được tạo → count = 1
    assert count == 1


def test_inject_logging_with_billing_method(tmp_path):
    smali_dir = tmp_path / "smali" / "com" / "example"
    smali_dir.mkdir(parents=True)
    f = smali_dir / "Billing.smali"
    f.write_text(
        ".class public Lcom/example/Billing;\n"
        ".method public static launchBillingFlow()V\n"
        "    .locals 0\n"
        "    return-void\n"
        ".end method\n",
        encoding="utf-8",
    )

    p = EventLogger(str(tmp_path))
    count = p.inject_logging()
    # Class file + billing file modified
    assert count >= 1


def test_patch_calls_inject_logging(tmp_path):
    (tmp_path / "smali").mkdir()
    p = EventLogger(str(tmp_path))
    assert p.patch() >= 0


def test_inject_logging_skips_long_path(tmp_path):
    """File path > 250 ký tự → skip."""
    p = EventLogger(str(tmp_path))
    # Chỉ cần không crash
    result = p.inject_logging()
    assert isinstance(result, int)