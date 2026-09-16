"""Base class cho mọi patcher — đảm bảo interface thống nhất."""
from __future__ import annotations

from abc import ABC, abstractmethod


class BasePatcher(ABC):
    """
    Contract chung cho mọi patcher.

    Subclass BẮT BUỘC implement:
        - patch() -> int

    Property tự động:
        - self.decompiled_path: đường dẫn thư mục đã giải nén
        - self.log: hàm log_callback
        - self.file_cache: FileContentCache hoặc None
    """

    def __init__(self, decompiled_path: str, log_callback=print, file_cache=None):
        self.decompiled_path = decompiled_path
        self.log = log_callback
        self.file_cache = file_cache

    @abstractmethod
    def patch(self) -> int:
        """
        Thực hiện patch. Trả về số file đã thay đổi (int ≥ 0).
        Trả về 0 nếu không có thay đổi nào.
        """
        raise NotImplementedError

    # ----- Helper dùng chung -----
    def _read(self, path: str) -> str:
        """Đọc file, ưu tiên cache nếu có."""
        if self.file_cache:
            return self.file_cache.read(path)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _write(self, path: str, content: str) -> None:
        """Ghi file, ưu tiên cache nếu có."""
        if self.file_cache:
            self.file_cache.write(path, content)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)