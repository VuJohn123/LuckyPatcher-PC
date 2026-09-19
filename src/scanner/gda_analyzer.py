"""
GDA integration — phân tích APK bằng GDA.exe (nếu có).
Graceful: không crash nếu GDA không tồn tại.

Security note:
  Dùng `tempfile.mkstemp()` thay vì `tempfile.mktemp()` — tránh TOCTOU
  race condition (mktemp deprecated từ Python 2.3 vì lỗ hổng bảo mật).
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile

logger = logging.getLogger(__name__)


class GDAAnalyzer:
    def __init__(self, gda_path: str | None = None):
        if gda_path is None:
            tools_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "tools",
            )
            gda_path = os.path.join(tools_dir, "GDA.exe")
        self.gda_exe = gda_path

    def analyze(self, apk_path: str, timeout: int = 120) -> dict:
        findings = {"license_classes": [], "iap_classes": [], "ad_urls": []}

        if not os.path.exists(self.gda_exe):
            logger.debug("GDA không tìm thấy: %s", self.gda_exe)
            return findings

        # --- Safe tempfile: mkstemp tạo unique + fd đã open (atomic) ---
        # fd phải được close trước khi pass path cho external tool, nếu
        # không Windows sẽ lock file và GDA không ghi được.
        fd, report = tempfile.mkstemp(
            suffix=".txt", prefix="gda_", text=True,
        )
        os.close(fd)

        try:
            proc = subprocess.run(
                [self.gda_exe, "-a", apk_path, "-o", report],
                capture_output=True, text=True, timeout=timeout,
            )
            if proc.returncode != 0:
                logger.debug("GDA exit %d", proc.returncode)
                return findings

            if not os.path.exists(report):
                return findings

            with open(report, "r", encoding="utf-8",
                      errors="ignore") as f:
                content = f.read()

            findings["license_classes"] = re.findall(
                r"L(?:com/google/android/vending/licensing/LicenseValidator;?)",
                content,
            )
            findings["iap_classes"] = re.findall(
                r"L(?:com/android/vending/billing/IInAppBillingService\$Stub;?)",
                content,
            )
            findings["ad_urls"] = re.findall(
                r'https?://[^"\'\s]+(?:doubleclick|admob|applovin|unityads|'
                r"googlesyndication)[^\"'\s]*",
                content,
            )[:20]

        except subprocess.TimeoutExpired:
            logger.warning("GDA timeout")
        except (OSError, ValueError) as e:
            logger.warning("GDA error: %s", e)
        finally:
            if os.path.exists(report):
                try:
                    os.remove(report)
                except OSError:
                    pass

        return findings