"""Root detection + LP detection — kết quả definitive Yes/No."""
from __future__ import annotations

import logging

from androguard.core.dex import DEX

logger = logging.getLogger(__name__)

_ROOT_KEYWORDS = (
    "root", "magisk", "supersu", "busybox",
    "isdevicerooted", "checkroot",
)

# FIX: Thêm cả slash variant vì class name trong DEX dùng '/' (Lcom/chelpu/...)
# Keyword matching sẽ normalize cả 'com.chelpu' và 'com/chelpu'
_LP_KEYWORDS = (
    "luckypatcher",
    "lucky_patcher",
    "com.chelpu",   # dot form (package name)
    "com/chelpu",   # slash form (DEX internal)
)


def check_root_detection(get_all_dex_bytes, findings) -> None:
    """
    Scan DEX tìm root detection code.
    Luôn emit 1 finding: Yes (đỏ) hoặc No (xám).
    """
    for dex_name, dex_bytes in get_all_dex_bytes():
        try:
            dex = DEX(dex_bytes)
            for cls in dex.get_classes():
                for method in cls.get_methods():
                    mn = method.get_name().lower()
                    if any(kw in mn for kw in _ROOT_KEYWORDS):
                        findings.append({
                            "type": "root_detection",
                            "color": "red",
                            "title": "Root Detection",
                            "description": (
                                f"Yes — method '{method.get_name()}' "
                                f"in class '{cls.get_name()}'"
                            ),
                            "details": [
                                f"Class: {cls.get_name()}",
                                f"Method: {method.get_name()}",
                            ],
                            "action": None,
                        })
                        return
        except Exception as e:
            logger.debug("root scan failed %s: %s", dex_name, e)
            continue

    # Không tìm thấy → No (definitive)
    findings.append({
        "type": "root_detection",
        "color": None,
        "title": "Root Detection",
        "description": "No — no root detection code found",
        "details": [],
        "action": None,
    })


def check_lp_detection(get_all_dex_bytes, findings) -> None:
    """
    Scan DEX tìm Lucky Patcher detection.
    Luôn emit 1 finding: Yes (đỏ) hoặc No (xám).
    """
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
                        "description": f"Yes — class '{cls.get_name()}'",
                        "details": [f"Class: {cls.get_name()}"],
                        "action": None,
                    })
                    return
        except Exception as e:
            logger.debug("LP scan failed %s: %s", dex_name, e)
            continue

    findings.append({
        "type": "lp_detection",
        "color": None,
        "title": "Lucky Patcher Detection",
        "description": "No — no LP detection code found",
        "details": [],
        "action": None,
    })