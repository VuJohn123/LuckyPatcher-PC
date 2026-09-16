"""Root detection + LP detection."""
from __future__ import annotations

import logging

from androguard.core.dex import DEX

logger = logging.getLogger(__name__)

_ROOT_KEYWORDS = ("root", "magisk", "supersu", "busybox",
                  "isdevicerooted", "checkroot")
_LP_KEYWORDS = ("luckypatcher", "lucky_patcher", "com.chelpu")


def check_root_detection(get_all_dex_bytes, findings) -> None:
    for dex_name, dex_bytes in get_all_dex_bytes():
        try:
            dex = DEX(dex_bytes)
            for cls in dex.get_classes():
                for method in cls.get_methods():
                    mn = method.get_name().lower()
                    if any(kw in mn for kw in _ROOT_KEYWORDS):
                        findings.append({
                            "type": "root_detection",
                            "color": None,
                            "title": "Root Detection",
                            "description": "App may detect root access",
                            "details": [f"Method: {method.get_name()}"],
                            "action": None,
                        })
                        return
        except Exception as e:
            logger.debug("root scan failed %s: %s", dex_name, e)
            continue


def check_lp_detection(get_all_dex_bytes, findings) -> None:
    for dex_name, dex_bytes in get_all_dex_bytes():
        try:
            dex = DEX(dex_bytes)
            for cls in dex.get_classes():
                cn = cls.get_name().lower()
                if any(kw in cn for kw in _LP_KEYWORDS):
                    findings.append({
                        "type": "lp_detection",
                        "color": "red",
                        "title": "Lucky Patcher Detection",
                        "description": "App may detect Lucky Patcher",
                        "details": [f"Class: {cls.get_name()}"],
                        "action": None,
                    })
                    return
        except Exception as e:
            logger.debug("LP scan failed %s: %s", dex_name, e)
            continue