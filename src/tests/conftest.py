"""
Đảm bảo `src/` nằm trong sys.path khi pytest chạy test.
Cho phép test import được `core.*`, `patcher.*`, `scanner.*`.
"""
import os
import sys

_SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT_DIR = os.path.abspath(os.path.join(_SRC_DIR, ".."))

for p in (_SRC_DIR, _ROOT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)