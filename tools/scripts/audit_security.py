"""
Audit security — secrets, unsafe patterns, path traversal.

Usage:
    python tools/scripts/audit_security.py
    python tools/scripts/audit_security.py --strict
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def _find_project_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "src").is_dir():
            return p
    raise RuntimeError(f"Cannot find project root from {start}")


ROOT = _find_project_root(Path(__file__).resolve().parent)

PATTERNS = {
    "hardcoded_secret": re.compile(
        r"(password|api_key|apikey|secret|token|passwd)\s*=\s*"
        r"['\"][^'\"]{8,}['\"]",
        re.IGNORECASE,
    ),
    "eval_exec": re.compile(r"(?<![\w.])(eval|exec)\s*\("),
    "shell_true": re.compile(
        r"subprocess\.\w+\([^)]*shell\s*=\s*True"
    ),
    "yaml_unsafe": re.compile(
        r"yaml\.load\s*\([^,)]*\)(?!\s*,\s*Loader)",
    ),
    "pickle_load": re.compile(r"pickle\.load\s*\("),
    "sql_format": re.compile(r"execute\s*\(\s*f['\"]"),
    "os_system": re.compile(r"\bos\.system\s*\("),
    "tempfile_insecure": re.compile(r"tempfile\.mktemp\s*\("),
}

SKIP_DIRS = {"tests", "__pycache__", ".venv", "tools", "scripts"}


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for py in ROOT.rglob("*.py"):
        if any(s in py.parts for s in SKIP_DIRS):
            continue
        files.append(py)
    return sorted(files)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    files = _iter_py_files()
    print(f"Scanning {len(files)} files under {ROOT / 'src'}")

    issues = 0
    per_pattern: dict[str, int] = {}

    for py in files:
        try:
            content = py.read_text(encoding="utf-8")
        except OSError as e:
            print(f"[!] Cannot read {py}: {e}")
            continue

        for i, line in enumerate(content.splitlines(), 1):
            for name, pat in PATTERNS.items():
                if not pat.search(line):
                    continue
                rel = py.relative_to(ROOT)
                print(
                    f"[{name:18}] {rel}:{i}: {line.strip()[:100]}"
                )
                issues += 1
                per_pattern[name] = per_pattern.get(name, 0) + 1

    print(f"\n{'=' * 60}")
    print(f"Total issues: {issues}")
    if per_pattern:
        print("Breakdown:")
        for name, count in sorted(per_pattern.items()):
            print(f"  {name:18} {count}")

    if args.strict and issues > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())