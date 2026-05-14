import json
import os
import re
import subprocess
from pathlib import Path


def _monorepo_root() -> Path:
    """Best-effort monorepo root.

    Honors ``LAB_ROOT`` (so tests can point at a fixture tree). Otherwise falls
    back to the package's filesystem location: this module lives at
    ``<root>/apps/server/src/server/diff_parser.py``, so the root is four
    levels above the package dir.
    """
    env_root = os.environ.get("LAB_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parents[4]


def _projects_dir() -> Path:
    return _monorepo_root() / "content" / "projects"


def get_branch(repo: str) -> str:
    """Get current branch name."""
    if not os.path.isdir(repo):
        return "unknown"
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, cwd=repo,
    )
    return result.stdout.strip()


def _exclude_pathspecs(exclude_paths: list[str] | None) -> list[str]:
    """Convert plain path prefixes into git pathspec excludes.

    Given ``["repositories", "apps/darwin-backups/downloads"]`` returns
    the pathspec tail ``["--", ".", ":(exclude)repositories", ...]`` that
    git log/diff/status/... accept to narrow the set of tracked paths.

    Returns an empty list when there's nothing to exclude, so callers can
    splat the result into their argv unconditionally.
    """
    if not exclude_paths:
        return []
    return ["--", "."] + [f":(exclude){p}" for p in exclude_paths if p]


def get_commits(repo: str, count: int = 50,
                exclude_paths: list[str] | None = None) -> list[dict]:
    """Get commits: on base branch shows last N commits, on feature branch shows commits since branching.

    ``exclude_paths`` narrows the log to commits that *touched* files
    outside those prefixes. Used by the Productivity self-view to ignore
    ``repositories/`` churn.
    """
    if not os.path.isdir(repo):
        return []
    branch = get_branch(repo)
    base = _get_base_branch(repo)
    on_base = branch in (base, "master", "main", "trunk")

    if on_base:
        cmd = ["git", "log", f"-{count}", "--format=%H%n%h%n%s%n%an%n%ar%n---"]
    else:
        cmd = ["git", "log", f"{base}..HEAD", f"-{count}", "--format=%H%n%h%n%s%n%an%n%ar%n---"]
    cmd += _exclude_pathspecs(exclude_paths)

    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=repo,
    )
    commits = []
    lines = result.stdout.strip().split("\n")
    i = 0
    while i + 4 < len(lines):
        commits.append({
            "sha": lines[i],
            "short_sha": lines[i + 1],
            "message": lines[i + 2],
            "author": lines[i + 3],
            "date": lines[i + 4],
        })
        i += 6  # skip the --- separator
    return commits


def get_commit_diff(repo: str, sha: str) -> dict:
    """Get diff for a specific commit (vs its parent)."""
    if not os.path.isdir(repo):
        return {"files": [], "repo": repo, "branch": "unknown", "type": "commit", "sha": sha}
    result = subprocess.run(
        ["git", "diff", f"{sha}~1", sha],
        capture_output=True, text=True, cwd=repo,
    )
    files = _parse_unified_diff(result.stdout)
    for f in files:
        adds = sum(1 for h in f["hunks"] for l in h["lines"] if l["type"] == "add")
        dels = sum(1 for h in f["hunks"] for l in h["lines"] if l["type"] == "delete")
        f["additions"] = adds
        f["deletions"] = dels
    return {
        "files": files,
        "repo": repo,
        "branch": get_branch(repo),
        "type": "commit",
        "sha": sha,
    }


def _get_base_branch(repo: str) -> str:
    """Find the base branch: try master, then main."""
    for branch in ("master", "main"):
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch],
            capture_output=True, text=True, cwd=repo,
        )
        if result.returncode == 0:
            return branch
    return "master"


def get_diff(repo: str, diff_type: str,
             exclude_paths: list[str] | None = None) -> dict:
    """Get parsed diff for a repo.

    diff_type: 'uncommitted' (vs HEAD) or 'branch' (vs base branch)
    exclude_paths: path prefixes to omit from the diff and the untracked list.
    """
    if not os.path.isdir(repo):
        return {"files": [], "repo": repo, "branch": "unknown", "base_branch": None, "type": diff_type, "error": "Directory not found"}

    branch = get_branch(repo)
    base = _get_base_branch(repo)
    on_base = branch in (base, "master", "main", "trunk")

    if diff_type == "uncommitted":
        cmd = ["git", "diff", "HEAD"]
    elif on_base:
        # On master/main: "branch" diff is same as uncommitted
        cmd = ["git", "diff", "HEAD"]
    else:
        # On feature branch: compare working tree against base branch
        # This includes: committed since base + staged + unstaged
        cmd = ["git", "diff", base]
    cmd += _exclude_pathspecs(exclude_paths)

    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=repo,
    )
    raw = result.stdout

    # Also get untracked files (new files not yet tracked by git)
    ut_cmd = ["git", "ls-files", "--others", "--exclude-standard"]
    ut_cmd += _exclude_pathspecs(exclude_paths)
    ut_result = subprocess.run(
        ut_cmd, capture_output=True, text=True, cwd=repo,
    )
    untracked_files = [f for f in ut_result.stdout.strip().splitlines() if f]

    files = _parse_unified_diff(raw)

    # Add untracked files as "all lines added"
    for fname in untracked_files:
        fpath = os.path.join(repo, fname)
        try:
            with open(fpath) as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            content = ""
        lines_list = content.splitlines()
        hunk_lines = []
        for i, line in enumerate(lines_list, 1):
            hunk_lines.append({
                "type": "add",
                "old_num": None,
                "new_num": i,
                "content": line,
            })
        files.append({
            "filename": fname,
            "status": "added",
            "hunks": [{
                "old_start": 0,
                "old_count": 0,
                "new_start": 1,
                "new_count": len(lines_list),
                "lines": hunk_lines,
            }] if hunk_lines else [],
        })

    # Compute per-file stats
    for f in files:
        adds = sum(1 for h in f["hunks"] for l in h["lines"] if l["type"] == "add")
        dels = sum(1 for h in f["hunks"] for l in h["lines"] if l["type"] == "delete")
        f["additions"] = adds
        f["deletions"] = dels

    return {
        "files": files,
        "repo": repo,
        "branch": get_branch(repo),
        "base_branch": _get_base_branch(repo) if diff_type == "branch" else None,
        "type": diff_type,
    }


def parse_notebook(filepath: str) -> list[dict]:
    """Parse an ipynb file into a list of cells with rendered content."""
    try:
        with open(filepath) as f:
            nb = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []

    cells = []
    for cell in nb.get("cells", []):
        cell_type = cell.get("cell_type", "code")
        source = "".join(cell.get("source", []))

        # Parse outputs for code cells
        outputs = []
        for out in cell.get("outputs", []):
            out_type = out.get("output_type", "")
            if out_type == "stream":
                outputs.append({"type": "text", "content": "".join(out.get("text", []))})
            elif out_type in ("execute_result", "display_data"):
                data = out.get("data", {})
                if "image/png" in data:
                    outputs.append({"type": "image", "content": data["image/png"]})
                elif "text/html" in data:
                    outputs.append({"type": "html", "content": "".join(data["text/html"])})
                elif "text/plain" in data:
                    outputs.append({"type": "text", "content": "".join(data["text/plain"])})
            elif out_type == "error":
                tb = "\n".join(out.get("traceback", []))
                # Strip ANSI codes
                tb = re.sub(r'\x1b\[[0-9;]*m', '', tb)
                outputs.append({"type": "error", "content": tb})

        cells.append({
            "cell_type": cell_type,
            "source": source,
            "outputs": outputs,
            "execution_count": cell.get("execution_count"),
            # Carry the cell's metadata through so the UI can sniff
            # markers like ``lab_pending`` (used by the nb_exec endpoint
            # to flag a running placeholder) and paint a distinct frame.
            "metadata": cell.get("metadata") or {},
        })

    return cells


def get_notebook_diff(repo: str, filepath: str, diff_type: str) -> dict:
    """Compare notebook cells between current and base version."""
    current_path = os.path.join(repo, filepath)
    current_cells = parse_notebook(current_path)

    # Get base version
    if diff_type == "uncommitted":
        base_ref = "HEAD"
    else:
        base_ref = _get_base_branch(repo)

    try:
        result = subprocess.run(
            ["git", "show", f"{base_ref}:{filepath}"],
            capture_output=True, text=True, cwd=repo,
        )
        if result.returncode == 0:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.ipynb', delete=False) as tmp:
                tmp.write(result.stdout)
                tmp_path = tmp.name
            base_cells = parse_notebook(tmp_path)
            os.unlink(tmp_path)
        else:
            base_cells = []
    except Exception:
        base_cells = []

    # Simple cell-by-cell comparison
    max_len = max(len(current_cells), len(base_cells))
    diff_cells = []
    for i in range(max_len):
        cur = current_cells[i] if i < len(current_cells) else None
        base = base_cells[i] if i < len(base_cells) else None

        if cur and not base:
            diff_cells.append({"status": "added", "cell": cur, "index": i})
        elif base and not cur:
            diff_cells.append({"status": "deleted", "cell": base, "index": i})
        elif cur["source"] != base["source"]:
            diff_cells.append({"status": "modified", "cell": cur, "base_cell": base, "index": i})
        else:
            # Check if outputs changed
            cur_out = json.dumps(cur.get("outputs", []))
            base_out = json.dumps(base.get("outputs", []))
            if cur_out != base_out:
                diff_cells.append({"status": "output_changed", "cell": cur, "base_cell": base, "index": i})
            else:
                diff_cells.append({"status": "unchanged", "cell": cur, "index": i})

    return {
        "cells": diff_cells,
        "total_cells": len(current_cells),
        "changed_cells": sum(1 for c in diff_cells if c["status"] != "unchanged"),
    }


def get_file_tree(repo: str) -> list[dict]:
    """Get full file tree of a repo as nested structure.

    Returns list of nodes: {name, path, type: 'file'|'dir', children: [...]}
    Excludes .git directory.
    """
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True, text=True, cwd=repo,
    )
    paths = [p for p in result.stdout.strip().splitlines() if p]

    # Also include untracked files
    ut_result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True, text=True, cwd=repo,
    )
    untracked = [p for p in ut_result.stdout.strip().splitlines() if p]
    all_paths = sorted(set(paths + untracked))

    root: list[dict] = []
    dir_map: dict[str, list] = {"": root}

    for filepath in all_paths:
        parts = filepath.split("/")
        # Ensure all parent dirs exist
        for i in range(1, len(parts)):
            dir_path = "/".join(parts[:i])
            parent_path = "/".join(parts[:i-1])
            if dir_path not in dir_map:
                node = {"name": parts[i-1], "path": dir_path, "type": "dir", "children": []}
                dir_map[dir_path] = node["children"]
                dir_map[parent_path].append(node)
        # Add file
        parent_path = "/".join(parts[:-1])
        dir_map[parent_path].append({
            "name": parts[-1],
            "path": filepath,
            "type": "file",
        })

    return root


def _discover_monorepo_projects() -> list[dict]:
    """Scan <monorepo>/content/projects/*/project.json and return project dicts.

    Shape matches what the UI expects:
      {"name": str, "is_project": bool, "path": str, "repos": [str]}

    `repos` is derived from `project.json.worktrees` (new schema: list of
    {mp, dir, branch}). The `dir` entry is assumed to be either an absolute
    path or a path relative to the monorepo root.
    """
    projects_dir = _projects_dir()
    if not projects_dir.is_dir():
        return []

    mono_root = _monorepo_root()
    out: list[dict] = []
    for proj_dir in sorted(projects_dir.iterdir()):
        if not proj_dir.is_dir():
            continue
        # Support both new (project.json) and legacy hidden (.project.json)
        pj = proj_dir / "project.json"
        if not pj.is_file():
            pj = proj_dir / ".project.json"
        if not pj.is_file():
            continue
        try:
            data = json.loads(pj.read_text())
        except (json.JSONDecodeError, ValueError):
            continue

        # New schema: worktrees = [{mp, dir, branch}, ...]
        # Legacy schema: repos = [<abs-path>, ...] (flat list of paths)
        #
        # ``dir`` from `lab project add` is the worktree's *basename* (e.g.
        # "im-test-davi-vision"), meant to be relative to this project's
        # folder. We try that first, then fall back to monorepo-root for
        # older entries that stored a full "content/projects/…/…" path.
        repos: list[str] = []
        worktrees = data.get("worktrees") or []

        def _resolve_worktree(d: str) -> str | None:
            p = Path(d)
            if p.is_absolute():
                return str(p) if p.is_dir() else None
            candidates = [
                (proj_dir / p).resolve(),   # basename relative to project
                (mono_root / p).resolve(),  # full path relative to root
            ]
            for c in candidates:
                if c.is_dir() and (c / ".git").exists() or c.is_dir():
                    return str(c)
            # Last resort: return the project-relative form even if missing,
            # so the UI at least shows *something* the user can diagnose.
            return str((proj_dir / p).resolve())

        if isinstance(worktrees, list):
            for wt in worktrees:
                if isinstance(wt, dict):
                    d = wt.get("dir") or wt.get("path")
                    if not d:
                        continue
                    resolved = _resolve_worktree(d)
                    if resolved:
                        repos.append(resolved)
                elif isinstance(wt, str):
                    resolved = _resolve_worktree(wt)
                    if resolved:
                        repos.append(resolved)
        legacy_repos = data.get("repos") or []
        if isinstance(legacy_repos, list):
            for r in legacy_repos:
                if isinstance(r, str):
                    repos.append(r)

        name = data.get("id") or data.get("name") or proj_dir.name
        out.append({
            "name": name,
            "is_project": True,
            "path": str(proj_dir),
            "repos": repos,
            "tab_open": bool(data.get("tab_open", False)),
        })

    return out


def get_registered_repos() -> list[dict]:
    """Return project dicts the UI expects.

    Primary source: auto-discovered projects from
    ``<monorepo>/content/projects/*/project.json``.

    Fallback: ``/tmp/gdiff-repos.json`` (the legacy registry), when no
    monorepo projects are found or the monorepo layout is absent.

    Each entry:
      {"name": str, "is_project": bool, "path": str, "repos": [str]}
    """
    monorepo_projects = _discover_monorepo_projects()
    if monorepo_projects:
        return monorepo_projects

    try:
        with open("/tmp/gdiff-repos.json") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    if not data:
        return []

    # Handle old format: flat list of path strings
    if isinstance(data[0], str):
        return [
            {
                "name": os.path.basename(p),
                "is_project": False,
                "path": p,
                "repos": [p],
            }
            for p in data
        ]

    return data


def _parse_unified_diff(raw: str) -> list[dict]:
    """Parse unified diff output into structured file diffs."""
    files = []
    current_file = None
    current_hunk = None

    for line in raw.splitlines():
        # New file diff
        if line.startswith("diff --git"):
            if current_file is not None:
                if current_hunk is not None:
                    current_file["hunks"].append(current_hunk)
                files.append(current_file)
            # Extract filename from "diff --git a/foo b/foo"
            parts = line.split(" b/", 1)
            fname = parts[1] if len(parts) > 1 else ""
            current_file = {"filename": fname, "status": "modified", "hunks": []}
            current_hunk = None
            continue

        if current_file is None:
            continue

        # Detect file status
        if line.startswith("new file"):
            current_file["status"] = "added"
            continue
        if line.startswith("deleted file"):
            current_file["status"] = "deleted"
            continue
        if line.startswith("rename from"):
            current_file["status"] = "renamed"
            continue

        # Hunk header
        hunk_match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if hunk_match:
            if current_hunk is not None:
                current_file["hunks"].append(current_hunk)
            current_hunk = {
                "old_start": int(hunk_match.group(1)),
                "old_count": int(hunk_match.group(2) or 1),
                "new_start": int(hunk_match.group(3)),
                "new_count": int(hunk_match.group(4) or 1),
                "lines": [],
            }
            old_num = int(hunk_match.group(1))
            new_num = int(hunk_match.group(3))
            continue

        if current_hunk is None:
            continue

        # Diff lines
        if line.startswith("+"):
            current_hunk["lines"].append({
                "type": "add",
                "old_num": None,
                "new_num": new_num,
                "content": line[1:],
            })
            new_num += 1
        elif line.startswith("-"):
            current_hunk["lines"].append({
                "type": "delete",
                "old_num": old_num,
                "new_num": None,
                "content": line[1:],
            })
            old_num += 1
        elif line.startswith(" "):
            current_hunk["lines"].append({
                "type": "context",
                "old_num": old_num,
                "new_num": new_num,
                "content": line[1:],
            })
            old_num += 1
            new_num += 1
        # Skip "\ No newline at end of file" and other noise

    # Flush last file/hunk
    if current_file is not None:
        if current_hunk is not None:
            current_file["hunks"].append(current_hunk)
        files.append(current_file)

    return files
