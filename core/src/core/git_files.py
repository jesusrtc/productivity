"""Git membership for Recently updated, without changing the Files view."""
from pathlib import Path
import subprocess


def metadata_paths(root: Path) -> list[Path]:
    """Git directories can live outside a linked worktree's visible folder."""
    marker = root / ".git"
    try:
        if marker.is_dir():
            return [marker]
        pointer = marker.read_text().strip()
        if not pointer.startswith("gitdir: "):
            return []
        directory = (root / pointer[8:]).resolve()
        common = directory / "commondir"
        return [directory, (directory / common.read_text().strip()).resolve()] if common.is_file() else [directory]
    except (OSError, UnicodeError):
        return []


def tracked_paths(root: Path | str) -> set[str]:
    """Return indexed paths, excluding paths matched by Git's ignore rules.

    Run once per repository, including nested repositories and linked worktrees.
    NUL-separated output preserves spaces and newlines in filenames. If Git is
    unavailable, no file can be confirmed as tracked.
    """
    def paths(*args: str) -> set[str]:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), "ls-files", "-z",
             "--cached", *args, "--", "."],
            capture_output=True, check=True, timeout=5,
        )
        return set(result.stdout.decode("utf-8", errors="surrogateescape").split("\0")) - {""}

    try:
        return paths() - paths("--ignored", "--exclude-standard")
    except (OSError, subprocess.SubprocessError):
        return set()


def tracked_subset(root: Path | str, candidates: list[str]) -> set[str]:
    """Check a small Git diff without matching ignore rules against the whole index.

    Git comparisons already yield indexed paths (plus deleted paths). Limit
    index lookup and --no-index ignore checks to those candidates. Fall back
    to the full membership pass for large changes to bound argv/pathspec cost.
    """
    if not candidates:
        return set()
    if len(candidates) > 128 or sum(len(path) for path in candidates) > 16000:
        return tracked_paths(root).intersection(candidates)
    indexed = subprocess.run(
        ["git", "--no-optional-locks", "--literal-pathspecs", "-C", str(root),
         "ls-files", "--cached", "-z", "--", *candidates],
        capture_output=True, check=True, timeout=5,
    )
    paths = set(indexed.stdout.decode("utf-8", errors="surrogateescape").split("\0")) - {""}
    if not paths:
        return set()
    ignored = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(root), "check-ignore", "--no-index", "-z", "--stdin"],
        input=("\0".join(paths) + "\0").encode("utf-8", errors="surrogateescape"),
        capture_output=True, timeout=5,
    )
    if ignored.returncode not in (0, 1):
        raise subprocess.CalledProcessError(ignored.returncode, ignored.args, stderr=ignored.stderr)
    return paths - set(ignored.stdout.decode("utf-8", errors="surrogateescape").split("\0"))
