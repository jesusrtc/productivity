import json
import os
import re
import subprocess
from pathlib import Path


def _monorepo_root(root: str | Path | None = None) -> Path:
    """Best-effort monorepo root.

    Honors an explicit root, ``LAB_WORKSPACE``, then ``LAB_ROOT`` (so tests can
    point at a fixture tree). Otherwise falls back to the package's filesystem location: this module lives at
    ``<root>/core/src/core/diff_parser.py``, so the root is three
    levels above the package dir.
    """
    if root is not None:
        return Path(root)
    env_workspace = os.environ.get("LAB_WORKSPACE")
    if env_workspace:
        return Path(env_workspace)
    env_root = os.environ.get("LAB_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parents[3]


def _projects_dir(root: str | Path | None = None) -> Path:
    return _monorepo_root(root) / "projects"


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

    Given ``["repositories", "tmp/downloads"]`` returns
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
        ["git", "show", "--format=", "--no-color", "--find-renames", sha],
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


def parse_notebook_output(out: dict) -> dict | None:
    """Convert one nbformat output into the stable shape consumed by the UI.

    Keeping this public lets live kernel events and persisted notebook reads use
    exactly the same MIME preference and error cleanup rules.
    """
    out_type = out.get("output_type", "")
    parsed: dict | None = None
    if out_type == "stream":
        parsed = {
            "type": "text",
            "content": "".join(out.get("text", [])),
            "stream_name": out.get("name", "stdout"),
        }
    elif out_type in ("execute_result", "display_data"):
        data = out.get("data", {})
        if "image/png" in data:
            parsed = {"type": "image", "content": data["image/png"]}
        elif "text/html" in data:
            parsed = {"type": "html", "content": "".join(data["text/html"])}
        elif "image/svg+xml" in data:
            # SVG is trusted kernel output, just like text/html. It is common
            # for lightweight chart helpers and should render without first
            # rasterizing to PNG.
            parsed = {"type": "html", "content": "".join(data["image/svg+xml"])}
        elif "text/plain" in data:
            parsed = {"type": "text", "content": "".join(data["text/plain"])}
    elif out_type == "error":
        tb = "\n".join(out.get("traceback", []))
        # Strip ANSI codes.
        tb = re.sub(r'\x1b\[[0-9;]*m', '', tb)
        parsed = {"type": "error", "content": tb}

    display_id = (out.get("transient") or {}).get("display_id")
    if parsed is not None and display_id:
        parsed["display_id"] = str(display_id)
    return parsed


def _parse_notebook_payload(nb: dict) -> list[dict]:
    cells = []
    for cell in nb.get("cells", []):
        cell_type = cell.get("cell_type", "code")
        source = "".join(cell.get("source", []))

        # Parse outputs for code cells
        outputs = []
        for out in cell.get("outputs", []):
            parsed = parse_notebook_output(out)
            if parsed is not None:
                outputs.append(parsed)

        cells.append({
            # nbformat 4.5 cell ids are stable across insertions/deletions and
            # let the notebook UI and agent API target the same cell without
            # racing on a positional index.
            "id": cell.get("id"),
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


def parse_notebook_content(content: str) -> list[dict]:
    """Parse notebook JSON text into the cell shape used by the UI."""
    try:
        payload = json.loads(content)
    except (TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    return _parse_notebook_payload(payload if isinstance(payload, dict) else {})


def parse_notebook(filepath: str) -> list[dict]:
    """Parse an ipynb file into a list of cells with rendered content."""
    try:
        with open(filepath) as f:
            nb = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    return _parse_notebook_payload(nb if isinstance(nb, dict) else {})


def diff_notebook_cells(base_cells: list[dict], current_cells: list[dict]) -> dict:
    """Return a positional, cell-aware notebook diff for two revisions."""
    max_len = max(len(current_cells), len(base_cells))
    diff_cells = []
    for i in range(max_len):
        cur = current_cells[i] if i < len(current_cells) else None
        base = base_cells[i] if i < len(base_cells) else None

        if cur and not base:
            diff_cells.append({"status": "added", "cell": cur, "index": i})
        elif base and not cur:
            diff_cells.append({"status": "deleted", "cell": base, "index": i})
        elif cur["cell_type"] != base["cell_type"] or cur["source"] != base["source"]:
            diff_cells.append({"status": "modified", "cell": cur, "base_cell": base, "index": i})
        else:
            # Execution counts and rich outputs are reviewable notebook state
            # even when the source itself did not change.
            cur_output = json.dumps({
                "execution_count": cur.get("execution_count"),
                "outputs": cur.get("outputs", []),
            }, sort_keys=True)
            base_output = json.dumps({
                "execution_count": base.get("execution_count"),
                "outputs": base.get("outputs", []),
            }, sort_keys=True)
            if cur_output != base_output:
                diff_cells.append({
                    "status": "output_changed",
                    "cell": cur,
                    "base_cell": base,
                    "index": i,
                })
            else:
                diff_cells.append({"status": "unchanged", "cell": cur, "index": i})

    return {
        "cells": diff_cells,
        "before_cells": len(base_cells),
        "after_cells": len(current_cells),
        "total_cells": len(current_cells),
        "changed_cells": sum(1 for cell in diff_cells if cell["status"] != "unchanged"),
    }


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
            base_cells = parse_notebook_content(result.stdout)
        else:
            base_cells = []
    except Exception:
        base_cells = []

    return diff_notebook_cells(base_cells, current_cells)


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
        node = {
            "name": parts[-1],
            "path": filepath,
            "type": "file",
        }
        disk_path = Path(repo) / filepath
        if disk_path.is_symlink():
            node["is_symlink"] = True
            try:
                node["symlink_target"] = os.readlink(disk_path)
            except OSError:
                pass
        dir_map[parent_path].append(node)

    return root


def _discover_monorepo_projects(root: str | Path | None = None) -> list[dict]:
    """Scan <monorepo>/projects/*/project.json and return project dicts.

    Shape matches what the UI expects:
      {"name": str, "is_project": bool, "path": str, "repos": [str]}

    `repos` is derived from `project.json.worktrees` (new schema: list of
    {mp, dir, branch}). The `dir` entry is assumed to be either an absolute
    path or a path relative to the monorepo root.
    """
    projects_dir = _projects_dir(root)
    if not projects_dir.is_dir():
        return []

    mono_root = _monorepo_root(root)
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
        # older entries that stored a full "projects/…/…" path.
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

        project_id = data.get("id") or proj_dir.name
        display_name = data.get("name")
        if not isinstance(display_name, str) or not display_name.strip():
            display_name = project_id
        out.append({
            # ``name`` remains the stable project id for backward-compatible
            # API consumers. ``display_name`` is presentation-only and may
            # change without renaming the project directory or terminal ids.
            "name": project_id,
            "display_name": display_name,
            "is_project": True,
            "path": str(proj_dir),
            "repos": repos,
            "tab_open": bool(data.get("tab_open", False)),
        })

    return out


def get_registered_repos(root: str | Path | None = None) -> list[dict]:
    """Return project dicts the UI expects.

    Primary source: auto-discovered projects from
    ``<monorepo>/projects/*/project.json``.

    Fallback: ``/tmp/gdiff-repos.json`` (the legacy registry), when no
    monorepo projects are found or the monorepo layout is absent.

    Each entry:
      {"name": str, "display_name": str, "is_project": bool,
       "path": str, "repos": [str]}
    """
    monorepo_projects = _discover_monorepo_projects(root)
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


def parse_unified_diff(raw: str) -> list[dict]:
    """Parse unified-diff text and attach GitHub-style per-file stats.

    ``_parse_unified_diff`` is also used by the live git-diff helpers above.
    This public wrapper is for stored ``.diff``/``.patch`` documents and
    other callers that already have the raw patch text in memory.
    """
    files = _parse_unified_diff(raw)
    for file in files:
        file["additions"] = sum(
            1 for hunk in file["hunks"] for line in hunk["lines"]
            if line["type"] == "add"
        )
        file["deletions"] = sum(
            1 for hunk in file["hunks"] for line in hunk["lines"]
            if line["type"] == "delete"
        )
    return files
