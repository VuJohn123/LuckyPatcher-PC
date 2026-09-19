"""
ReDoS-safe regex helpers — dùng chung cho mọi patcher cần xử lý
pattern từ user/file ngoài (custom_patch, ads_blocklist, smart_pattern).

Cơ chế:
  - `regex` lib (nếu có): native timeout.
  - Fallback stdlib `re`: heuristic pattern validator (chặn nested quantifier,
    pattern quá dài, catastrophic backtracking patterns).
"""
from __future__ import annotations

import logging
import re
from typing import Callable

logger = logging.getLogger(__name__)

try:
    import regex as _re_engine  # type: ignore
    _HAS_REGEX_LIB = True
except ImportError:
    _re_engine = re  # type: ignore
    _HAS_REGEX_LIB = False

_MAX_PATTERN_LEN = 1000
_DEFAULT_TIMEOUT = 2.0


# ============================================================
# HEURISTIC VALIDATOR (fallback khi không có regex lib)
# ============================================================
# Các pattern gây catastrophic backtracking phổ biến:
_NESTED_QUANT_RE = re.compile(r"\([^()]*[*+][^()]*\)[*+]")
_OVERLAP_ALT_RE = re.compile(r"\((?:[^|()]+\|)+[^|()]+\)[*+]")


def is_safe_pattern(pattern: str) -> tuple[bool, str]:
    """
    Return (is_safe, reason).

    Từ chối:
      - pattern quá dài (>1000 chars)
      - nested quantifier (a+)+, (a*)+, (a+)*
      - overlapping alternation (a|a)+ (chỉ heuristic)
    """
    if not isinstance(pattern, str):
        return False, "pattern không phải string"
    if len(pattern) > _MAX_PATTERN_LEN:
        return False, (
            f"pattern quá dài ({len(pattern)} > {_MAX_PATTERN_LEN})"
        )

    m = _NESTED_QUANT_RE.search(pattern)
    if m:
        return False, f"nested quantifier {m.group()!r}"

    # Chỉ cảnh báo cho pattern cực dài có alternation lặp
    if len(pattern) > 200:
        m2 = _OVERLAP_ALT_RE.search(pattern)
        if m2:
            return False, f"overlapping alternation {m2.group()!r}"

    return True, ""


# ============================================================
# SAFE SUB / SEARCH / FINDITER
# ============================================================
def safe_sub(
    pattern: str,
    repl,
    content: str,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    flags: int = 0,
    log_callback: Callable | None = None,
) -> tuple[str, bool]:
    """Return (new_content, success)."""
    is_safe, reason = is_safe_pattern(pattern)
    if not is_safe:
        if log_callback:
            log_callback(f"[!] [RegexSafe] Reject: {reason}")
        return content, False

    if _HAS_REGEX_LIB:
        try:
            new = _re_engine.sub(
                pattern, repl, content, timeout=timeout, flags=flags,
            )
            return new, True
        except getattr(_re_engine, "TimeoutError", TimeoutError) as e:
            if log_callback:
                log_callback(
                    f"[!] [RegexSafe] Timeout {timeout}s: {e}"
                )
            return content, False
        except _re_engine.error as e:
            if log_callback:
                log_callback(f"[!] [RegexSafe] Syntax: {e}")
            return content, False
    else:
        try:
            new = re.sub(pattern, repl, content, flags=flags)
            return new, True
        except re.error as e:
            if log_callback:
                log_callback(f"[!] [RegexSafe] Syntax: {e}")
            return content, False


def safe_search(
    pattern: str,
    content: str,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    flags: int = 0,
):
    """Return match hoặc None nếu fail/timeout."""
    is_safe, _ = is_safe_pattern(pattern)
    if not is_safe:
        return None

    if _HAS_REGEX_LIB:
        try:
            return _re_engine.search(
                pattern, content, timeout=timeout, flags=flags,
            )
        except Exception:
            return None
    else:
        try:
            return re.search(pattern, content, flags=flags)
        except re.error:
            return None


def safe_finditer(
    pattern: str,
    content: str,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    flags: int = 0,
):
    """Yield matches — return empty iterator nếu pattern nguy hiểm."""
    is_safe, _ = is_safe_pattern(pattern)
    if not is_safe:
        return

    if _HAS_REGEX_LIB:
        try:
            yield from _re_engine.finditer(
                pattern, content, timeout=timeout, flags=flags,
            )
        except Exception:
            return
    else:
        try:
            yield from re.finditer(pattern, content, flags=flags)
        except re.error:
            return


def get_engine() -> str:
    return "regex" if _HAS_REGEX_LIB else "re"