"""Phân loại nhanh APK — trả về danh sách màu."""
from __future__ import annotations

import re
import zipfile

from androguard.core.apk import APK
from androguard.core.dex import DEX


class AppClassifier:
    """Phân loại APK — chỉ dùng cho quick scan (màu sắc)."""

    def __init__(self, apk_path: str | None = None):
        self.apk_path = apk_path
        self.apk = APK(apk_path) if apk_path else None

    def classify(self) -> list[str]:
        if not self.apk:
            return ["white"]
        colors = []
        if self._has_license():
            colors.append("green")
        if self._has_ads():
            colors.append("blue")
        if self._is_system():
            colors.append("purple")
        return colors if colors else ["white"]

    def _has_license(self) -> bool:
        try:
            dex_bytes = self._get_dex_bytes()
            if dex_bytes and len(dex_bytes) >= 2:
                dex = DEX(dex_bytes)
                for cls in dex.get_classes():
                    class_name = cls.get_name()
                    if "OfflineLicenseHelper" in class_name:
                        continue
                    if re.search(
                        r"(license|licensing|lvl|LicenseCheck)",
                        class_name, re.IGNORECASE,
                    ):
                        return True
        except Exception:
            pass
        return False

    def _has_ads(self) -> bool:
        try:
            for act in self.apk.get_activities():
                if re.search(
                    r"com\.google\.android\.gms\.ads|"
                    r"com\.facebook\.ads|com\.unity3d\.ads",
                    act,
                ):
                    return True
        except Exception:
            pass
        return False

    def _is_system(self) -> bool:
        try:
            pkg = self.apk.get_package()
            return pkg.startswith(("com.android.", "com.google.android."))
        except Exception:
            return False

    def _get_dex_bytes(self) -> bytes | None:
        try:
            with zipfile.ZipFile(self.apk_path, "r") as z:
                dex_files = [n for n in z.namelist() if n.endswith(".dex")]
                if dex_files:
                    data = z.read(dex_files[0])
                    if len(data) >= 2:
                        return data
        except Exception:
            pass
        return None