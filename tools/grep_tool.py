"""Codebase search for the agent.

``grep_code`` runs a regex over text files under a directory (default: the
current working directory) and returns matching lines with file:line: text
prefixes — the agent's primary way to explore a project without dumping whole
files.
"""

from __future__ import annotations

import re
from pathlib import Path

# Directories that are never worth searching (either huge or not source).
_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "build",
    "dist",
    "release",
    ".idea",
    ".vscode",
    ".freebuff",
}

MAX_MATCH_LINES = 60  # results per call
MAX_FILE_SIZE = 2 * 1024 * 1024  # don't scan megabyte blobs line by line


def grep_code(pattern: str, path: str | None = None, max_results: int = 50) -> list[str]:
    """Search ``path`` (default: cwd) for lines matching ``pattern`` (regex)."""
    root = Path(path or ".")
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return ['{"error": "Invalid regex: %s"}' % exc]

    if not root.exists():
        return ['{"error": "Path not found: %s"}' % root]

    results: list[str] = []
    cap = min(max(max_results, 1), MAX_MATCH_LINES)

    def walk(directory: Path) -> None:
        if len(results) >= cap:
            return
        try:
            entries = sorted(directory.iterdir(), key=lambda e: e.name)
        except OSError:
            return
        for entry in entries:
            if len(results) >= cap:
                return
            name = entry.name
            if entry.is_dir():
                if name not in _SKIP_DIRS and not name.startswith("."):
                    walk(entry)
                continue
            if not entry.is_file() or name.startswith("."):
                continue
            try:
                if entry.stat().st_size > MAX_FILE_SIZE:
                    continue
                with entry.open("r", encoding="utf-8", errors="ignore") as fh:
                    for lineno, line in enumerate(fh, 1):
                        if len(results) >= cap:
                            return
                        if rx.search(line.rstrip("\n")):
                            results.append(
                                f"{entry}:{lineno}: {line.rstrip(chr(10))[:400]}"
                            )
            except OSError:
                continue

    walk(root)
    return results
