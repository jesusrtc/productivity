"""Distinguish an initial Git worktree checkout from subsequent file updates."""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path


# The sidebar's longest time selector is 24 hours. Older checkout timestamps
# cannot pollute it, so avoid Git scans for long-established worktrees.
_RECENT_WINDOW_SECONDS = 24 * 60 * 60
_REFLOG_ENTRY = re.compile(
    rb"([0-9a-f]{40}|[0-9a-f]{64}) ([0-9a-f]{40}|[0-9a-f]{64}) .+ "
    rb"([0-9]+) [+-][0-9]{4}(?:\t(.*))?\n?$"
)


def checkout_baseline(root: Path) -> tuple[str, float | None] | None:
    """Read the original checkout's commit and completion time, if preserved.

    A linked worktree has its own HEAD reflog. Git creates its zero-to-commit
    entry, populates files through reset --hard, then records that reset. Read
    only those first two records: later commits/resets must not move the cutoff.
    Detached HEAD may omit the no-op reset record; use initial content as the
    baseline in that case. Missing/expired creation records keep normal mtimes.
    Git's ordering is in builtin/worktree.c:checkout_worktree and
    builtin/reset.c:cmd_reset (write_locked_index precedes reset_refs).
    """
    marker = root / ".git"
    try:
        if not marker.is_file():
            return None
        with marker.open("r") as stream:
            pointer = stream.readline(4096).strip()
        if not pointer.startswith("gitdir: "):
            return None
        git_dir = (root / pointer[8:]).resolve()
        if not (git_dir / "commondir").is_file():
            return None  # Separate git directories and submodules aren't worktrees.
        with (git_dir / "logs/HEAD").open("rb") as stream:
            first = _REFLOG_ENTRY.fullmatch(stream.readline(4096))
            second = _REFLOG_ENTRY.fullmatch(stream.readline(4096))
        if not first or set(first[1]) != {ord("0")}:
            return None
        initial = first[2]
        # Reflogs have second precision. Content differences below keep edits
        # made during this same second (even already committed) visible.
        end = None
        if second and second[1] == initial and second[2] == initial and second[4] == b"reset: moving to HEAD":
            end = float(second[3]) + 1
        if (end or float(first[3]) + 1) < time.time() - _RECENT_WINDOW_SECONDS:
            return None
        return initial.decode("ascii"), end
    except (OSError, ValueError, UnicodeError):
        return None


def mark_checkout_files(root: Path, baseline: tuple[str, float | None], entries: list[tuple[str, dict]]) -> None:
    """Tag untouched checkout files without changing their real timestamps."""
    initial, end = baseline
    candidates = [(path, entry) for path, entry in entries
                  if end is None or entry.get("mtime", end) < end]
    if not candidates:
        return

    def git_paths(*args: str) -> set[str]:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), *args],
            capture_output=True, check=True, timeout=3,
        )
        return set(result.stdout.decode("utf-8", errors="surrogateescape").split("\0"))

    try:
        original_paths = git_paths("ls-tree", "-r", "--name-only", "-z", initial)
        changed = git_paths(
            "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
            "--name-only", "-z", initial, "--",
        )
    except (OSError, subprocess.SubprocessError):
        return  # Uncertain data should never hide a user's edit.
    for path, entry in candidates:
        if path in original_paths and path not in changed:
            entry["checkout_generated"] = True
