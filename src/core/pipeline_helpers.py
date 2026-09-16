"""Helper functions cho pipeline — tách khỏi main.py."""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(config: dict) -> logging.Logger:
    """Cấu hình logging — idempotent."""
    logger = logging.getLogger("lp_pc_suite")
    if logger.handlers:
        return logger

    log_cfg = config.get("logging", {})
    level_name = log_cfg.get("level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    log_file = log_cfg.get("file", "logs/pipeline.log")
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        handler = RotatingFileHandler(
            log_file,
            maxBytes=log_cfg.get("max_bytes", 10 * 1024 * 1024),
            backupCount=log_cfg.get("backup_count", 5),
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)
    except OSError:
        # Fallback: không ghi file, chỉ dùng console
        logging.basicConfig(level=level)
    return logger


def normalize_input(path: str, config: dict, log) -> str:
    """
    Chuẩn hóa input:
      - .apk   → giữ nguyên
      - .xapk  → convert thành .apk (BẮT BUỘC)
      - folder → merge split APK thành .apk
    """
    if not path:
        raise ValueError("Đường dẫn input rỗng")
    if not os.path.exists(path):
        raise ValueError(f"Input không tồn tại: {path}")

    # Case 1: .apk
    if os.path.isfile(path) and path.lower().endswith(".apk"):
        log("[*] Input là .apk — bỏ qua conversion")
        return path

    # Case 2: .xapk
    from core.xapk_converter import (
        XAPKConversionError, convert_xapk_to_apk, is_xapk,
    )
    if os.path.isfile(path) and (path.lower().endswith(".xapk") or is_xapk(path)):
        if not config.get("conversion", {}).get("auto_convert_xapk", True):
            raise ValueError("Input là .xapk nhưng auto_convert_xapk bị tắt")
        try:
            return convert_xapk_to_apk(path, log_callback=log)
        except XAPKConversionError as e:
            raise ValueError(f"Convert .xapk thất bại: {e}") from e

    # Case 3: folder split APK
    if os.path.isdir(path):
        if not config.get("conversion", {}).get("allow_split_apk", True):
            raise ValueError("Input là folder nhưng allow_split_apk bị tắt")
        from core.apk_utils import merge_split_apks
        apks = [f for f in os.listdir(path) if f.lower().endswith(".apk")]
        if not apks:
            raise ValueError(f"Folder không chứa .apk: {path}")
        out = os.path.join(os.path.dirname(path), "merged.apk")
        merge_split_apks(path, out, log)
        return out

    raise ValueError(f"Không hỗ trợ định dạng input: {path}")