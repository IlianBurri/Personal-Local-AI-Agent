"""Git awareness for the agent.

``git_status`` gives the model the repository state (branch, working-tree
changes, recent commits) so it can reason about what to do before editing
files. Read-only: it never stages, commits, or mutates anything.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_MAX_COMMITS = 5


def git_status(path: str | None = None) -> dict:
    """Return branch, dirty-file list, and recent commits for a git repo."""
    cwd = str(Path(path or ".").resolve())
    result = {"branch": None, "changes": [], "recent_commits": []}

    def run(args: list[str]) -> str | None:
        try:
            proc = subprocess.run(
                ["git", "-C", cwd, *args],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        # rstrip only newlines: porcelain status lines keep their leading
        # space (" M file") which callers need.
        return proc.stdout.rstrip("\n")

    branch = run(["rev-parse", "--abbrev-ref", "HEAD"])
    if branch is None:
        return {"error": "Not a git repository (or git is unavailable)"}
    result["branch"] = branch

    status = run(["status", "--porcelain"])
    if status:
        for line in status.splitlines():
            if len(result["changes"]) >= 50:
                result["changes"].append("... (more)")
                break
            result["changes"].append(line)

    log = run(
        [
            "log",
            f"--max-count={_MAX_COMMITS}",
            "--pretty=format:%h %ad %s",
            "--date=short",
        ]
    )
    if log:
        result["recent_commits"] = log.splitlines()
    return result
