"""Single source of truth cho phiên bản ứng dụng.

Trước đây version bị lặp ở 4 nơi (`src/__init__.py`, `core/github_updater.py`,
log khởi động trong `ui/main_window.py`, `sidebar.version` trong i18n) và
lệch nhau (4.0.0 vs v5.0.0). Mọi nơi PHẢI import từ đây.
"""
from __future__ import annotations

VERSION = "5.0.0"

# Dùng cho User-Agent + hiển thị ngắn gọn.
VERSION_TAG = f"v{VERSION}"
