"""LP-PC Suite — package root.

`src/` itself is normally added to `sys.path` (see `src/tests/conftest.py`),
so subpackages import as top-level `core`, `ui`, ... Importing them eagerly
from here would make `import src` fail when only the repo root is on the path.
Resolve the version lazily from either layout.
"""
from __future__ import annotations

__all__ = ["__version__"]


def _resolve_version() -> str:
    try:
        from core.version import VERSION
    except ImportError:
        from .core.version import VERSION
    return VERSION


def __getattr__(name: str) -> str:
    if name == "__version__":
        return _resolve_version()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
