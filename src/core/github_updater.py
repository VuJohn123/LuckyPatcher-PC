"""
Auto-updater qua GitHub raw.

Fetch version.json từ raw.githubusercontent.com, so sánh version,
emit signal nếu có update mới. Non-blocking, chạy trong thread riêng.

Format version.json:
{
  "version": "4.1.0",
  "release_date": "2026-10-01",
  "min_python": "3.11",
  "changelog": ["Fix X", "Add Y"],
  "download_url": "https://github.com/user/repo/releases/..."
}
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


CURRENT_VERSION = "4.0.0"

DEFAULT_UPDATE_URL = (
    "https://raw.githubusercontent.com/Freezdy413485/"
    "LP-PC-Suite/main/version.json"
)


@dataclass
class UpdateInfo:
    version: str
    release_date: str = ""
    changelog: list[str] = field(default_factory=list)
    download_url: str = ""
    min_python: str = ""

    def to_html(self) -> str:
        lines = [
            f"<b>Phiên bản mới: {self.version}</b>",
            f"Ngày phát hành: {self.release_date}" if self.release_date else "",
            "",
        ]
        if self.changelog:
            lines.append("<b>Thay đổi:</b>")
            for item in self.changelog:
                lines.append(f"  • {item}")
        if self.min_python:
            lines.append("")
            lines.append(f"Yêu cầu Python ≥ {self.min_python}")
        return "<br>".join(l for l in lines if l is not None)


def _parse_version(v: str) -> tuple[int, ...]:
    """'4.1.2' → (4, 1, 2). An toàn với suffix."""
    parts = []
    for p in v.split("."):
        try:
            parts.append(int("".join(c for c in p if c.isdigit()) or "0"))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _is_newer(remote: str, current: str) -> bool:
    return _parse_version(remote) > _parse_version(current)


class GitHubUpdater:
    """Checker — không block UI, chạy trong thread riêng."""

    def __init__(
        self,
        update_url: str = DEFAULT_UPDATE_URL,
        current_version: str = CURRENT_VERSION,
        timeout: float = 8.0,
    ):
        self.update_url = update_url
        self.current_version = current_version
        self.timeout = timeout

    def check_sync(self) -> UpdateInfo | None:
        """Chạy đồng bộ — dùng cho CLI hoặc gọi trong thread."""
        try:
            import requests
        except ImportError:
            logger.warning("requests chưa cài — bỏ qua check update")
            return None

        try:
            resp = requests.get(
                self.update_url,
                timeout=self.timeout,
                headers={"User-Agent": f"LP-PC-Suite/{self.current_version}"},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.info("Update check failed: %s", e)
            return None

        remote_version = str(data.get("version", "")).strip()
        if not remote_version:
            return None

        if not _is_newer(remote_version, self.current_version):
            logger.info(
                "Đã ở phiên bản mới nhất (%s)", self.current_version
            )
            return None

        return UpdateInfo(
            version=remote_version,
            release_date=str(data.get("release_date", "")),
            changelog=list(data.get("changelog", [])),
            download_url=str(data.get("download_url", "")),
            min_python=str(data.get("min_python", "")),
        )

    def check_async(
        self, callback: Callable[[UpdateInfo | None], None]
    ) -> None:
        """
        Chạy check trong thread riêng. callback nhận UpdateInfo hoặc None.
        Callback SẼ chạy trong worker thread — caller phải tự đẩy về
        main thread bằng Qt signal nếu cần update UI.
        """
        def _worker():
            try:
                info = self.check_sync()
            except Exception as e:
                logger.exception("Updater worker crashed: %s", e)
                info = None
            try:
                callback(info)
            except Exception as e:
                logger.exception("Updater callback failed: %s", e)

        threading.Thread(target=_worker, daemon=True).start()