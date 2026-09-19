"""Test core/regex_safe.py — ReDoS-safe regex helpers."""
import re

import pytest

from core.regex_safe import (
    _HAS_REGEX_LIB,
    _MAX_PATTERN_LEN,
    get_engine,
    is_safe_pattern,
    safe_finditer,
    safe_search,
    safe_sub,
)


# ============================================================
# is_safe_pattern
# ============================================================
class TestIsSafePattern:
    def test_simple_pattern_safe(self):
        safe, reason = is_safe_pattern(r"\d+")
        assert safe is True
        assert reason == ""

    def test_common_lvl_pattern_safe(self):
        safe, _ = is_safe_pattern(r'const-string\s+(\S+),\s*"test"')
        assert safe is True

    def test_unicode_pattern_safe(self):
        safe, _ = is_safe_pattern(r"[\u00C0-\u024F]+")
        assert safe is True

    def test_nested_plus_rejected(self):
        safe, reason = is_safe_pattern(r"(a+)+$")
        assert safe is False
        assert "nested quantifier" in reason

    def test_nested_star_rejected(self):
        safe, reason = is_safe_pattern(r"(a*)*b")
        assert safe is False
        assert "nested quantifier" in reason

    def test_nested_plus_then_star_rejected(self):
        safe, reason = is_safe_pattern(r"(a+)*")
        assert safe is False

    def test_pattern_too_long_rejected(self):
        safe, reason = is_safe_pattern("a" * (_MAX_PATTERN_LEN + 1))
        assert safe is False
        assert "quá dài" in reason

    def test_non_string_rejected(self):
        safe, reason = is_safe_pattern(None)  # type: ignore
        assert safe is False
        assert "string" in reason

    def test_long_alternation_rejected(self):
        # Alternation lặp quá dài → heuristic reject
        long_alt = "(" + "|".join(f"x{i}" for i in range(100)) + ")+"
        safe, reason = is_safe_pattern(long_alt)
        assert safe is False

    def test_short_alternation_ok(self):
        safe, _ = is_safe_pattern(r"(cat|dog)+")
        assert safe is True


# ============================================================
# safe_sub
# ============================================================
class TestSafeSub:
    def test_basic_substitution(self):
        new, ok = safe_sub(r"\d+", "N", "abc123def")
        assert ok is True
        assert new == "abcNdef"

    def test_no_match_returns_original(self):
        new, ok = safe_sub(r"\d+", "N", "abc")
        assert ok is True
        assert new == "abc"

    def test_unsafe_pattern_returns_original(self):
        logs = []
        new, ok = safe_sub(
            r"(a+)+$", "x", "aaaa", log_callback=logs.append
        )
        assert ok is False
        assert new == "aaaa"
        assert any("Reject" in l for l in logs)

    def test_invalid_syntax_returns_original(self):
        logs = []
        new, ok = safe_sub(
            r"[unclosed", "x", "content", log_callback=logs.append
        )
        assert ok is False
        assert new == "content"
        assert any("Syntax" in l for l in logs)

    def test_dotall_flag(self):
        new, ok = safe_sub(
            r"a.b", "X", "a\nb", flags=re.DOTALL,
        )
        assert ok is True
        assert new == "X"

    def test_multiline_replace(self):
        new, ok = safe_sub(
            r"foo", "bar", "foo\nfoo\nfoo",
        )
        assert ok is True
        assert new == "bar\nbar\nbar"

    def test_capture_groups(self):
        new, ok = safe_sub(
            r"(\w+)@(\w+)", r"\2.\1", "user@host"
        )
        assert ok is True
        assert new == "host.user"

    def test_callable_replacement(self):
        new, ok = safe_sub(
            r"\d+", lambda m: str(int(m.group(0)) * 2), "a1b2",
        )
        assert ok is True
        assert new == "a2b4"


# ============================================================
# safe_search
# ============================================================
class TestSafeSearch:
    def test_match_found(self):
        m = safe_search(r"\d+", "abc123")
        assert m is not None
        assert m.group(0) == "123"

    def test_no_match_returns_none(self):
        m = safe_search(r"\d+", "abc")
        assert m is None

    def test_unsafe_pattern_returns_none(self):
        m = safe_search(r"(a+)+$", "aaaa")
        assert m is None

    def test_invalid_regex_returns_none(self):
        m = safe_search(r"[unclosed", "content")
        assert m is None

    def test_flags_applied(self):
        m = safe_search(r"ABC", "abc", flags=re.IGNORECASE)
        assert m is not None


# ============================================================
# safe_finditer
# ============================================================
class TestSafeFinditer:
    def test_multiple_matches(self):
        matches = list(safe_finditer(r"\d+", "a1b22c333"))
        assert len(matches) == 3
        assert [m.group(0) for m in matches] == ["1", "22", "333"]

    def test_no_matches(self):
        matches = list(safe_finditer(r"\d+", "abc"))
        assert matches == []

    def test_unsafe_yields_nothing(self):
        matches = list(safe_finditer(r"(a+)+$", "aaaa"))
        assert matches == []

    def test_invalid_regex_yields_nothing(self):
        matches = list(safe_finditer(r"[unclosed", "content"))
        assert matches == []


# ============================================================
# get_engine
# ============================================================
def test_get_engine_returns_string():
    engine = get_engine()
    assert engine in ("re", "regex")


def test_has_regex_lib_is_bool():
    assert isinstance(_HAS_REGEX_LIB, bool)