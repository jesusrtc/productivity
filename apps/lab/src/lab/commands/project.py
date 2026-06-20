from __future__ import annotations

import re
import shutil
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

import click

from lab import mp as mp_mod
from lab import paths, storage
from lab.commands._helpers import require_valid_id as _require_valid_id
from lab.model import ModelError, Priority, Project, ProjectStatus
from lab.util import split_csv


_DURATION_RE = re.compile(r"^\s*(\d+)\s*([mhdw])\s*$", re.IGNORECASE)


def _now_local() -> datetime:
    """Timezone-aware now in the local zone (so ``isoformat`` includes offset)."""
    return datetime.now(tz=timezone.utc).astimezone()


def _parse_duration_to_until(spec: str, *, now: datetime | None = None) -> str:
    """Convert ``2h``/``3d``/``1w``/``45m`` to an ISO timestamp."""
    m = _DURATION_RE.match(spec)
    if not m:
        raise click.ClickException(
            f"--for {spec!r}: expected N followed by m/h/d/w (e.g. 2h, 3d, 1w)"
        )
    qty = int(m.group(1))
    unit = m.group(2).lower()
    seconds = {"m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]
    base = now or _now_local()
    return (base + _timedelta(seconds * qty)).isoformat(timespec="seconds")


def _timedelta(secs: int):
    # Local helper to avoid yet another import at module top.
    from datetime import timedelta
    return timedelta(seconds=secs)


def _parse_until_to_iso(spec: str) -> str:
    """Normalize a user-supplied ``--until`` to an ISO timestamp.

    Accepts bare dates (``YYYY-MM-DD`` → end-of-day local) and ISO datetimes.
    """
    spec = spec.strip()
    # Bare date → 23:59 local so "until tomorrow" means "all of tomorrow".
    if re.match(r"^\d{4}-\d{2}-\d{2}$", spec):
        d = date.fromisoformat(spec)
        local_tz = _now_local().tzinfo
        dt = datetime(d.year, d.month, d.day, 23, 59, 0, tzinfo=local_tz)
        return dt.isoformat(timespec="seconds")
    # Otherwise trust isoformat (accept trailing Z).
    try:
        dt = datetime.fromisoformat(spec.replace("Z", "+00:00"))
    except ValueError as exc:
        raise click.ClickException(f"--until {spec!r}: not a valid date/datetime") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_now_local().tzinfo)
    return dt.isoformat(timespec="seconds")


def _ensure_mp_cloned(root: Path, mp: str) -> None:
    """Best-effort clone of a single MP via `mint clone`. Silent on success,
    verbose-ish on failure (the caller re-checks and raises if missing)."""
    mp_root = root / "repositories"
    mp_root.mkdir(exist_ok=True)
    dest = mp_root / mp
    if dest.is_dir() and (dest / ".git").exists():
        return
    proc = subprocess.run(
        ["mint", "clone", mp],
        cwd=str(mp_root), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
        click.echo(f"  (mint clone failed: {' | '.join(tail)})")


_PROJECT_SETTABLE = {
    "description", "status", "priority", "due", "loe", "tags", "labels", "name",
    "agent", "model",
}


def _iter_project_files(root: Path):
    projects_root = root / "projects"
    if not projects_root.is_dir():
        return
    for child in sorted(projects_root.iterdir()):
        pjson = child / "project.json"
        if pjson.is_file():
            yield pjson


@click.group(name="project")
def project_group() -> None:
    """Project lifecycle commands."""


@project_group.command("new")
@click.argument("project_id")
@click.option("--desc", "description", default="", help="Short description")
@click.option("--priority", type=click.Choice([p.value for p in Priority]), default=None)
@click.option("--due", default=None, help="Due date YYYY-MM-DD")
@click.option("--tags", default="", help="Comma-separated tags")
@click.option("--labels", default="", help="Comma-separated MP labels")
def new(project_id: str, description: str, priority: str | None, due: str | None,
        tags: str, labels: str) -> None:
    """Create a new project under projects/<id>/."""
    root = paths.find_monorepo_root()
    try:
        project = Project.from_dict({
            "id": project_id,
            "name": project_id,
            "description": description,
            "status": "active",
            "priority": priority,
            "due": due,
            "tags": split_csv(tags),
            "labels": split_csv(labels),
        })
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc

    pdir = paths.project_dir(root, project.id)
    if pdir.exists():
        raise click.ClickException(f"project {project.id!r} already exists at {pdir}")

    # Atomic creation: if any step fails, remove the partial directory.
    try:
        (pdir / "docs").mkdir(parents=True)
        (pdir / "notes").mkdir()
        (pdir / "assets").mkdir()

        storage.write_json(paths.project_file(root, project.id), project.to_dict())
        storage.write_json(paths.tasks_file(root, project.id), {"next_id": 1, "tasks": []})
    except Exception:
        if pdir.exists():
            shutil.rmtree(pdir, ignore_errors=True)
        raise

    click.echo(f"created {project.id} at {pdir}")


@project_group.command("ls")
@click.option("--status", type=click.Choice([s.value for s in ProjectStatus]), default=None)
@click.option("--tag", "tag_filter", default=None)
@click.option("--label", "label_filter", default=None)
def ls(status: str | None, tag_filter: str | None, label_filter: str | None) -> None:
    """List projects (default: all)."""
    root = paths.find_monorepo_root()
    rows = []
    for pjson in _iter_project_files(root):
        data = storage.read_json(pjson)
        if status and data.get("status") != status:
            continue
        if tag_filter and tag_filter not in (data.get("tags") or []):
            continue
        if label_filter and label_filter not in (data.get("labels") or []):
            continue
        rows.append(data)

    if not rows:
        click.echo("no projects")
        return

    width_id = max(len(r["id"]) for r in rows)
    for r in rows:
        priority = r.get("priority") or "--"
        due = r.get("due") or "--"
        desc = (r.get("description") or "").strip().split("\n")[0][:60]
        click.echo(f"{r['id']:<{width_id}}  {r['status']:<8}  {priority:<2}  {due:<10}  {desc}")


@project_group.command("status")
@click.argument("project_id", required=False)
def status(project_id: str | None) -> None:
    """Print a summary of a project (uses PWD if no id given)."""
    from lab.commands._helpers import resolve_project_id
    root = paths.find_monorepo_root()
    pid = resolve_project_id(project_id)

    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    data = storage.read_json(pjson)

    tjson = paths.tasks_file(root, pid)
    task_counts = {"todo": 0, "in_progress": 0, "blocked": 0, "done": 0}
    if tjson.is_file():
        for t in storage.read_json(tjson).get("tasks", []):
            s = t.get("status")
            if s in task_counts:
                task_counts[s] += 1

    click.echo(f"{data['id']}  ({data['status']})")
    if data.get("description"):
        for line in data["description"].splitlines():
            click.echo(f"  {line}")
    click.echo(
        f"  tasks: todo={task_counts['todo']} in_progress={task_counts['in_progress']} "
        f"blocked={task_counts['blocked']} done={task_counts['done']}"
    )
    if data.get("priority"):
        click.echo(f"  priority: {data['priority']}")
    if data.get("due"):
        click.echo(f"  due: {data['due']}")
    if data.get("tags"):
        click.echo(f"  tags: {', '.join(data['tags'])}")
    if data.get("labels"):
        click.echo(f"  labels: {', '.join(data['labels'])}")


@project_group.command("set")
@click.argument("project_id")
@click.argument("field")
@click.argument("value")
def set_field(project_id: str, field: str, value: str) -> None:
    """Update a single field on a project (validated)."""
    pid = _require_valid_id(project_id)
    if field not in _PROJECT_SETTABLE:
        raise click.ClickException(
            f"{field} is not settable. Allowed: {sorted(_PROJECT_SETTABLE)}"
        )
    root = paths.find_monorepo_root()
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    data = storage.read_json(pjson)

    if field in {"tags", "labels"}:
        data[field] = split_csv(value)
    elif field == "loe":
        if value in {"", "null", "none"}:
            data[field] = None
        else:
            try:
                data[field] = float(value)
            except ValueError as exc:
                raise click.ClickException(f"loe: {value!r} is not a number") from exc
    elif field in {"priority", "due", "status", "agent", "model"}:
        data[field] = value if value not in {"", "null", "none"} else None
    else:
        data[field] = value

    data["updated"] = date.today().isoformat()

    try:
        Project.from_dict(data)
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc

    storage.write_json(pjson, data)
    click.echo(f"{pid}.{field} = {data[field]!r}")


@project_group.command("hold")
@click.argument("project_id", required=False)
@click.option("--for", "duration", default=None,
              help="Duration offset (e.g. 2h, 3d, 1w). Mutually exclusive with --until.")
@click.option("--until", "until", default=None,
              help="Absolute YYYY-MM-DD or ISO datetime. Mutually exclusive with --for.")
@click.option("--reason", default="", help="Short label describing what you're waiting on.")
@click.option("--url", "url", default="", help="Optional URL to check (PR, doc, slack, ...).")
def hold(project_id: str | None, duration: str | None, until: str | None,
         reason: str, url: str) -> None:
    """Soft-snooze a project until ``--for`` / ``--until``.

    The project stays visible on the dashboard but is sorted out of the
    active set. Once the ``until`` timestamp passes it resurfaces in the
    "Ready for review" strip with the reason + URL you saved.
    """
    from lab.commands._helpers import resolve_project_id
    if (duration is None) == (until is None):
        raise click.ClickException("exactly one of --for or --until is required")
    pid = resolve_project_id(project_id)
    root = paths.find_monorepo_root()
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")

    now = _now_local()
    until_iso = _parse_duration_to_until(duration, now=now) if duration else _parse_until_to_iso(until)

    data = storage.read_json(pjson)
    hold_doc = {
        "until": until_iso,
        "reason": reason.strip(),
        "url": url.strip(),
        "set_at": now.isoformat(timespec="seconds"),
    }
    # Drop empty optional keys for cleaner JSON.
    hold_doc = {k: v for k, v in hold_doc.items() if v not in ("", None)}
    data["hold"] = hold_doc
    data["updated"] = date.today().isoformat()

    try:
        Project.from_dict(data)
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc

    storage.write_json(pjson, data)
    click.echo(f"held {pid} until {until_iso}"
               + (f" · {reason}" if reason else "")
               + (f" · {url}" if url else ""))


@project_group.command("unhold")
@click.argument("project_id", required=False)
def unhold(project_id: str | None) -> None:
    """Clear an active hold (remove the ``hold`` field)."""
    from lab.commands._helpers import resolve_project_id
    pid = resolve_project_id(project_id)
    root = paths.find_monorepo_root()
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    data = storage.read_json(pjson)
    if not data.get("hold"):
        click.echo(f"{pid}: no hold to clear")
        return
    data["hold"] = None
    data["updated"] = date.today().isoformat()
    storage.write_json(pjson, data)
    click.echo(f"cleared hold on {pid}")


@project_group.command("holds")
def holds_cmd() -> None:
    """List every project currently on hold (active + expired)."""
    root = paths.find_monorepo_root()
    rows: list[tuple[str, dict]] = []
    for pjson in _iter_project_files(root):
        data = storage.read_json(pjson)
        h = data.get("hold")
        if h:
            rows.append((data["id"], h))
    if not rows:
        click.echo("no holds")
        return
    now = _now_local()
    width_id = max(len(pid) for pid, _ in rows)
    for pid, h in sorted(rows, key=lambda r: r[1].get("until", "")):
        until = h.get("until", "")
        state = "ready" if until and until < now.isoformat(timespec="seconds") else "held"
        reason = h.get("reason") or ""
        url = h.get("url") or ""
        extra = f" · {reason}" if reason else ""
        extra += f" · {url}" if url else ""
        click.echo(f"{pid:<{width_id}}  [{state:<5}]  until {until}{extra}")


@project_group.command("archive")
@click.argument("project_id")
def archive(project_id: str) -> None:
    """Set status to archived (hidden from default dashboard)."""
    pid = _require_valid_id(project_id)
    root = paths.find_monorepo_root()
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    data = storage.read_json(pjson)
    data["status"] = "archived"
    data["updated"] = date.today().isoformat()

    try:
        Project.from_dict(data)
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc

    storage.write_json(pjson, data)
    click.echo(f"archived {pid}")


@project_group.command("rm")
@click.argument("project_id")
@click.option("--yes", is_flag=True, help="Skip confirmation")
def rm(project_id: str, yes: bool) -> None:
    """Delete a project folder permanently. Worktrees, if any, must be removed first (later plan)."""
    pid = _require_valid_id(project_id)
    root = paths.find_monorepo_root()
    pdir = paths.project_dir(root, pid)
    if not pdir.is_dir():
        raise click.ClickException(f"project {pid!r} not found")

    if not yes:
        click.confirm(
            f"Permanently delete {pdir}? This cannot be undone.",
            abort=True,
        )

    shutil.rmtree(pdir)
    click.echo(f"removed {pid}")


@project_group.command("migrate-worktrees")
@click.option("--id", "project_id", default=None,
              help="Only migrate this project; default: every project.")
@click.option("--dry-run", is_flag=True, default=False)
def migrate_worktrees(project_id: str | None, dry_run: bool) -> None:
    """Move flat-layout worktrees into each project's ``worktrees/`` subfolder.

    Older projects stored worktrees directly under the project dir
    (``projects/<p>/<prefix>-<obj>``). New layout nests them
    under a dedicated ``worktrees/`` sibling. Uses ``git worktree move``
    so the MP-side admin state stays consistent, then rewrites
    ``project.json.worktrees[].dir`` to the new relative path.

    Skips entries already at ``worktrees/*``. Safe to re-run.
    """
    root = paths.find_monorepo_root()
    projects_root = root / "projects"
    if not projects_root.is_dir():
        click.echo("no projects yet.")
        return
    ids = [project_id] if project_id else [
        p.name for p in sorted(projects_root.iterdir())
        if p.is_dir() and (p / "project.json").is_file()
    ]
    moved = skipped = failed = 0
    for pid in ids:
        pjson = paths.project_file(root, pid)
        data = storage.read_json(pjson)
        worktrees = data.get("worktrees") or []
        if not isinstance(worktrees, list) or not worktrees:
            continue
        pdir = paths.project_dir(root, pid)
        changed = False
        for wt in worktrees:
            if not isinstance(wt, dict):
                continue
            current = wt.get("dir", "")
            if not current or "/" in current:
                skipped += 1
                continue  # already subfolder form (or empty)
            src = pdir / current
            dst_rel = f"worktrees/{current}"
            dst = pdir / dst_rel
            mp = wt.get("mp", "")
            mp_dir = root / "repositories" / mp
            if not src.is_dir():
                click.echo(f"  ✗ {pid}/{current}: source dir missing, skipping")
                skipped += 1
                continue
            if dst.exists():
                click.echo(f"  ✗ {pid}/{current}: dest already exists at {dst_rel}")
                failed += 1
                continue
            click.echo(f"  ↻ {pid}: {current} → {dst_rel}")
            if dry_run:
                moved += 1
                continue
            (pdir / "worktrees").mkdir(exist_ok=True)
            try:
                subprocess.run(
                    ["git", "-C", str(mp_dir), "worktree", "move", str(src), str(dst)],
                    check=True, capture_output=True, text=True,
                )
            except subprocess.CalledProcessError as exc:
                msg = (exc.stderr or exc.stdout or str(exc)).strip()
                click.echo(f"  ✗ {pid}/{current}: {msg}")
                failed += 1
                continue
            wt["dir"] = dst_rel
            changed = True
            moved += 1
        if changed and not dry_run:
            storage.write_json(pjson, data)
    verb = "would move" if dry_run else "moved"
    click.echo(f"{verb} {moved}, skipped {skipped}, failed {failed}")


@project_group.command("add")
@click.argument("project_id")
@click.argument("mp")
@click.option("--branch", default=None, help="Override computed branch name")
def add(project_id: str, mp: str, branch: str | None) -> None:
    """Create a git worktree of MP at projects/<project>/<mp-prefix>-<objective>/."""
    pid = _require_valid_id(project_id)
    root = paths.find_monorepo_root()
    pdir = paths.project_dir(root, pid)
    if not pdir.is_dir():
        raise click.ClickException(f"project {pid!r} not found")

    mp_dir = root / "repositories" / mp
    # Missing MP clone? Try to bootstrap from repositories.list before
    # bailing out. This makes `lab project add` Just Work for a fresh repo
    # checkout — no "oh you forgot to run pull-repos" surprise.
    if not mp_dir.is_dir() or not (mp_dir / ".git").exists():
        click.echo(f"repositories/{mp} not found — pulling first…")
        _ensure_mp_cloned(root, mp)
        if not mp_dir.is_dir() or not (mp_dir / ".git").exists():
            raise click.ClickException(
                f"MP {mp!r} still not at repositories/{mp} — check `repositories.list` "
                f"and your mint auth, then try `lab repo pull --only {mp}` directly"
            )

    prefix = mp_mod.prefix_for(mp)
    if not prefix:
        raise click.ClickException(
            f"no prefix for {mp!r} — set with `lab repo prefix {mp} <short>`"
        )

    objective = mp_mod.objective_from(pid)
    # Worktrees live under a dedicated subfolder so they don't clutter the
    # project's doc tree (docs/, notes/, assets/, ...). Stored path is
    # relative to the project dir — resolved by the server at render time.
    worktrees_root = pdir / "worktrees"
    worktrees_root.mkdir(exist_ok=True)
    worktree_dir = worktrees_root / f"{prefix}-{objective}"
    branch_name = branch or f"jcortes/{objective}"

    if worktree_dir.exists():
        raise click.ClickException(f"worktree already at {worktree_dir}")

    # Ensure the branch exists in the MP (create from master if not)
    try:
        subprocess.run(
            ["git", "-C", str(mp_dir), "rev-parse", "--verify", branch_name],
            check=True, capture_output=True,
        )
        # Branch exists — add worktree tracking it
        subprocess.run(
            ["git", "-C", str(mp_dir), "worktree", "add", str(worktree_dir), branch_name],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError:
        # Branch doesn't exist — create it from master
        try:
            subprocess.run(
                ["git", "-C", str(mp_dir), "worktree", "add", "-b", branch_name,
                 str(worktree_dir), "master"],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as exc:
            msg = (exc.stderr or exc.stdout or str(exc)).strip()
            raise click.ClickException(f"git worktree add failed: {msg}") from exc

    # Update project.json.worktrees
    pjson = paths.project_file(root, pid)
    data = storage.read_json(pjson)
    data.setdefault("worktrees", [])
    data["worktrees"].append({
        "mp": mp,
        "dir": f"worktrees/{worktree_dir.name}",
        "branch": branch_name,
    })
    data["updated"] = date.today().isoformat()
    storage.write_json(pjson, data)

    click.echo(f"added worktree worktrees/{worktree_dir.name} on {branch_name}")


@project_group.command("remove")
@click.argument("project_id")
@click.argument("mp")
@click.option("--force", "-f", is_flag=True, default=False,
              help="Pass --force to `git worktree remove` (drops uncommitted changes).")
def remove(project_id: str, mp: str, force: bool) -> None:
    """Remove a worktree (git worktree remove + project.json update). Does NOT delete the branch."""
    pid = _require_valid_id(project_id)
    root = paths.find_monorepo_root()
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    data = storage.read_json(pjson)
    worktrees = data.get("worktrees", [])
    entry = next((w for w in worktrees if w.get("mp") == mp), None)
    if not entry:
        raise click.ClickException(f"no worktree for MP {mp!r} in project {pid!r}")

    worktree_path = paths.project_dir(root, pid) / entry["dir"]
    mp_dir = root / "repositories" / mp
    if worktree_path.exists() and mp_dir.is_dir():
        cmd = ["git", "-C", str(mp_dir), "worktree", "remove", str(worktree_path)]
        if force:
            cmd.append("--force")
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            msg = (exc.stderr or exc.stdout or str(exc)).strip()
            hint = "" if force else "  (retry with --force to discard uncommitted changes)"
            raise click.ClickException(f"git worktree remove failed: {msg}{hint}") from exc

    data["worktrees"] = [w for w in worktrees if w.get("mp") != mp]
    data["updated"] = date.today().isoformat()
    storage.write_json(pjson, data)
    click.echo(f"removed worktree for {mp}")
