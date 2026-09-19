"""
Audit code quality — find TODO/FIXME/bare except/print spam.

Usage:
    python tools/scripts/audit_quality.py
    python tools/scripts/audit_quality.py --strict
"""
from __future__ import annotations

import argparse
import ast
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
    "TODO/FIXME": re.compile(r"\b(TODO|FIXME|XXX|HACK)\b"),
    "bare_except": re.compile(r"except\s*:"),
    "eval_exec": re.compile(r"(?<![\w.])(eval|exec)\s*\("),
    "shell_true": re.compile(r"shell\s*=\s*True"),
}

SKIP_DIRS = {"tests", "__pycache__", ".venv", "venv", "tools", "scripts"}

# Files allowed to call print() — CLI entry, diagnostics
CLI_PRINT_FILES = {
    "main.py",
    "run_gui.py",
    "gui.py",
}

# print() with these markers is legit
PRINT_WHITELIST_MARKERS = (
    "log_callback",     # callback default
    "sink",             # loguru sink
    "[tid:",            # trace prefix output
    "argparse",         # CLI
)


def _has_abstract_decorator(lines: list[str], idx: int) -> bool:
    """Check if line idx is inside a method decorated with @abstractmethod."""
    for j in range(idx - 1, max(idx - 6, -1), -1):
        stripped = lines[j].strip()
        if stripped.startswith("@abstractmethod"):
            return True
        if stripped.startswith("def ") or stripped.startswith("class "):
            break
    return False


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

        lines = content.splitlines()
        in_docstring = False
        is_cli_file = py.name in CLI_PRINT_FILES

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            triple_count = stripped.count('"""') + stripped.count("'''")
            was_in = in_docstring
            if triple_count % 2 == 1:
                in_docstring = not in_docstring
            if was_in or in_docstring:
                continue

            # --- print_spam (special rules) ---
            if re.match(r"^\s*print\(", line):
                if is_cli_file:
                    continue
                if any(m in line for m in PRINT_WHITELIST_MARKERS):
                    continue
                rel = py.relative_to(ROOT)
                print(
                    f"[{'print_spam':20}] {rel}:{i}: "
                    f"{line.strip()[:100]}"
                )
                issues += 1
                per_pattern["print_spam"] = (
                    per_pattern.get("print_spam", 0) + 1
                )
                continue

            # --- stub (NotImplementedError) ---
            if re.search(r"raise\s+NotImplementedError", line):
                if _has_abstract_decorator(lines, i - 1):
                    continue
                rel = py.relative_to(ROOT)
                print(
                    f"[{'stub':20}] {rel}:{i}: "
                    f"{line.strip()[:100]}"
                )
                issues += 1
                per_pattern["stub"] = per_pattern.get("stub", 0) + 1
                continue

            # --- Other patterns ---
            for name, pat in PATTERNS.items():
                if not pat.search(line):
                    continue
                rel = py.relative_to(ROOT)
                print(
                    f"[{name:20}] {rel}:{i}: {line.strip()[:100]}"
                )
                issues += 1
                per_pattern[name] = per_pattern.get(name, 0) + 1

    print(f"\n{'=' * 60}")
    print(f"Total issues: {issues}")
    if per_pattern:
        print("Breakdown:")
        for name, count in sorted(per_pattern.items()):
            print(f"  {name:20} {count}")

    if args.strict and issues > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())