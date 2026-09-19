"""
i18n — Đa ngôn ngữ cho LP-PC Suite.

Cơ chế:
  - Load từ `assets/i18n/<lang>.json` (nested dict).
  - Fallback: `en.json` → source string (không dịch).
  - Env override: `LP_LANG=vi|en|...` (default "vi").
  - Runtime switch: `set_language("en")` + emit `language_changed`.

Usage:
    from core.i18n import t, set_language, get_language

    t("main_window.title")             # → "LP-PC Suite v4"
    t("sidebar.apps")                  # → "Ứng dụng đã cài"
    t("status.loaded", count=5)        # → "Đã tải 5 ứng dụng"

Fallback chain:
    1. current lang → key
    2. en → key
    3. return key (source string)
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from threading import RLock

logger = logging.getLogger(__name__)

_LANG_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "i18n"
_DEFAULT_LANG = "vi"
_FALLBACK_LANG = "en"

_current_lang: str = os.environ.get("LP_LANG", _DEFAULT_LANG)
_translations: dict[str, dict] = {}
_lock = RLock()


# ============================================================
# LOAD
# ============================================================
def _load_lang(lang: str) -> dict:
    """Load translations từ JSON. Return {} nếu fail."""
    path = _LANG_DIR / f"{lang}.json"
    if not path.exists():
        logger.debug("Missing translation file: %s", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Load %s failed: %s", path, e)
        return {}


def _ensure_loaded(lang: str) -> None:
    with _lock:
        if lang not in _translations:
            _translations[lang] = _load_lang(lang)


# ============================================================
# PUBLIC
# ============================================================
def get_language() -> str:
    return _current_lang


def set_language(lang: str) -> None:
    global _current_lang
    with _lock:
        _current_lang = lang
        _ensure_loaded(lang)
    logger.info("Language set to: %s", lang)


def available_languages() -> list[str]:
    """Return list of lang codes có file JSON."""
    if not _LANG_DIR.exists():
        return ["vi", "en"]
    codes = sorted(
        p.stem for p in _LANG_DIR.glob("*.json")
    )
    return codes or ["vi", "en"]


def t(key: str, **fmt) -> str:
    """
    Translate key. Support nested key bằng dấu ".":
        "main_window.title"
    Format placeholders: t("loaded", count=5) → "...5..."

    Fallback: current lang → en → key.
    """
    _ensure_loaded(_current_lang)
    if _current_lang != _FALLBACK_LANG:
        _ensure_loaded(_FALLBACK_LANG)

    # Try current lang
    value = _lookup(_translations.get(_current_lang, {}), key)
    if value is None:
        value = _lookup(_translations.get(_FALLBACK_LANG, {}), key)
    if value is None:
        value = key

    # Format placeholders
    if fmt:
        try:
            return value.format(**fmt)
        except (KeyError, ValueError):
            return value
    return value


def _lookup(data: dict, key: str):
    """Lookup nested key. Return None nếu không có."""
    parts = key.split(".")
    current = data
    for p in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(p)
        if current is None:
            return None
    return current if isinstance(current, str) else None