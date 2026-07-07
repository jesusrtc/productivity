"""Per-project dev-server management.

A workspace project opts in by having a ``Makefile`` at its project root
with a ``server-start`` target. Convention (see ``docs/SERVERS.md``):

  server-start:       # required — foreground, blocks
  <recipe>

  server-stop:        # optional — best-effort cleanup
  <recipe>

  SERVER_PORT = 8006             # optional
  SERVER_HEALTH_URL = http://... # optional; defaults to 127.0.0.1:<port>/

"Starting" a server means spawning a detached tmux session (default socket,
same naming scheme as the terminal UI — see ``core.routes.term``) that runs
``make server-start`` in the foreground. The session then shows up in the
normal terminal UI as a "server" tab. "Stopping" runs the optional
``server-stop`` target best-effort, then kills the tmux session.

A background supervisor thread ticks periodically, checks liveness (tmux
has-session) + health (HTTP GET on the optional health URL), and restarts
any project whose desired state is "running" but whose session died or
whose health check has been failing.

Desired state (running vs. stopped) is persisted per-workspace at
``<root>/.lab/state/servers.json`` so it survives server restarts.

Servers are managed across EVERY registered workspace (``~/.lab/
workspaces.toml``), not just the active one: ``GET /api/servers`` returns
rows from all of them (each carrying ``workspace``), the supervisor ticks
all of them every interval, and start/stop/restart take an explicit
``{workspace}`` path segment (see ``_known_workspaces``). A workspace whose
path is currently missing or stalled is skipped for that cycle rather than
failing the whole request — mirrors ``core.routes.workspace``'s
per-workspace degradation in ``list_workspace_projects``.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from lab import paths, storage
from lab.model import ModelError, validate_id

from core import fsguard
from core.routes import term as term_routes
from core.routes import workspace as workspace_routes


router = APIRouter()

log = logging.getLogger("core.servers")


def _validate_project_id(project_id: str) -> None:
    try:
        validate_id(project_id)
    except ModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _root_key(root: Path) -> str:
    try:
        return str(Path(root).expanduser().resolve())
    except OSError:
        return str(root)


_WORKSPACE_ID_CACHE_TTL_S = 15.0
_workspace_id_cache: dict[str, tuple[float, str]] = {}


def _workspace_id(root: Path) -> str:
    """Registered workspace id for ``root`` (directory name as fallback),
    cached briefly — the registry is a tiny toml but the dashboard polls
    every few seconds."""
    key = _root_key(root)
    now = time.monotonic()
    cached = _workspace_id_cache.get(key)
    if cached and (now - cached[0]) < _WORKSPACE_ID_CACHE_TTL_S:
        return cached[1]
    try:
        rows = list(paths.read_workspace_registry().get("workspaces") or [])
    except Exception:
        rows = []
    wid = workspace_routes._workspace_id_for(Path(key), rows)
    _workspace_id_cache[key] = (now, wid)
    return wid


def _known_workspaces(active_root: Path | None) -> list[dict]:
    """``[{"id": ..., "path": Path}, ...]`` for every registered workspace,
    plus ``active_root`` itself if it isn't already one of them.

    This is what makes dev servers span every registered workspace instead
    of just the active one. The not-yet-registered-current-workspace
    fallback mirrors ``_workspace_id``/``core.routes.workspace``'s
    ``_workspace_id_for`` (id defaults to the resolved directory name), so
    servers still work before a workspace has been formally registered —
    the shape most of this test suite's fixture workspace is in. Read
    fresh on every call: the registry is a small TOML file and can change
    out-of-process (``lab workspace add`` et al.) without a server restart.
    """
    try:
        rows = list(paths.read_workspace_registry().get("workspaces") or [])
    except Exception:
        rows = []
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        raw = row.get("path")
        if not raw:
            continue
        try:
            root = Path(str(raw)).expanduser().resolve()
        except OSError:
            continue
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        out.append({"id": str(row.get("id") or root.name), "path": root})
    if active_root is not None:
        try:
            resolved = active_root.expanduser().resolve()
        except OSError:
            resolved = active_root
        if str(resolved) not in seen:
            out.insert(0, {"id": workspace_routes._workspace_id_for(resolved, rows), "path": resolved})
    return out


def _resolve_workspace_root(workspace_id: str, active_root: Path | None) -> Path | None:
    for ws in _known_workspaces(active_root):
        if ws["id"] == workspace_id:
            return ws["path"]
    return None


def _require_workspace_root(workspace_id: str, active_root: Path | None) -> Path:
    """404 for an unknown workspace id, or one whose path isn't reachable
    right now (missing mount, unplugged drive, a stalled volume that times
    out rather than answering). From the API caller's perspective both read
    as "can't act on this workspace right now", so a stall degrades to 404
    here rather than surfacing fsguard's 503."""
    root = _resolve_workspace_root(workspace_id, active_root)
    if root is None:
        raise HTTPException(status_code=404, detail=f"workspace {workspace_id!r} not found")
    try:
        available = fsguard.guarded(root, root.is_dir)
    except HTTPException as exc:
        if exc.status_code != 503:
            raise
        raise HTTPException(
            status_code=404,
            detail=f"workspace {workspace_id!r} is not available right now: {exc.detail}",
        ) from exc
    if not available:
        raise HTTPException(status_code=404, detail=f"workspace {workspace_id!r} path not found: {root}")
    return root


# ─── Makefile parsing ───────────────────────────────────────────────────────

_MAKEFILE_SERVER_START_RE = re.compile(r"^server-start:", re.MULTILINE)
_MAKEFILE_SERVER_STOP_RE = re.compile(r"^server-stop:", re.MULTILINE)
_MAKEFILE_PORT_RE = re.compile(r"^SERVER_PORT\s*[:?]?=\s*(\d+)", re.MULTILINE)
_MAKEFILE_HEALTH_URL_RE = re.compile(r"^SERVER_HEALTH_URL\s*[:?]?=\s*(\S+)", re.MULTILINE)


def _parse_makefile(text: str) -> dict:
    has_start = bool(_MAKEFILE_SERVER_START_RE.search(text))
    has_stop = bool(_MAKEFILE_SERVER_STOP_RE.search(text))

    port: int | None = None
    m = _MAKEFILE_PORT_RE.search(text)
    if m:
        try:
            port = int(m.group(1))
        except ValueError:
            port = None

    health_url: str | None = None
    m = _MAKEFILE_HEALTH_URL_RE.search(text)
    if m:
        health_url = m.group(1).strip()
    elif port is not None:
        health_url = f"http://127.0.0.1:{port}/"

    return {"has_start": has_start, "has_stop": has_stop, "port": port, "health_url": health_url}


def _scan_server_projects(root: Path) -> list[dict]:
    """Blocking scan of ``root/projects/*/Makefile`` for server-managed
    projects. Runs inside ``fsguard.guarded`` — never call directly against
    a live workspace path outside that wrapper."""
    projects_dir = root / "projects"
    if not projects_dir.is_dir():
        return []
    found: list[dict] = []
    for pdir in sorted(projects_dir.iterdir()):
        if not pdir.is_dir() or pdir.name.startswith("."):
            continue
        makefile = pdir / "Makefile"
        if not makefile.is_file():
            continue
        try:
            text = makefile.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        info = _parse_makefile(text)
        if not info["has_start"]:
            continue
        info["project_id"] = pdir.name
        found.append(info)
    return found


_DISCOVERY_CACHE_TTL_S = 8.0
_discovery_cache_lock = threading.Lock()
_discovery_cache: dict[str, tuple[float, list[dict]]] = {}


def _discover_server_projects(root: Path) -> list[dict]:
    """Server-managed projects for ``root``, cached for a few seconds."""
    key = _root_key(root)
    now = time.monotonic()
    with _discovery_cache_lock:
        cached = _discovery_cache.get(key)
        if cached and (now - cached[0]) < _DISCOVERY_CACHE_TTL_S:
            return [dict(r) for r in cached[1]]
    rows = fsguard.guarded(root, _scan_server_projects, root)
    with _discovery_cache_lock:
        _discovery_cache[key] = (now, rows)
    return [dict(r) for r in rows]


def _find_server_project(root: Path, project_id: str) -> dict | None:
    for row in _discover_server_projects(root):
        if row["project_id"] == project_id:
            return row
    return None


def _discover_all_server_rows(active_root: Path | None) -> list[tuple[str, Path, dict]]:
    """``(workspace_id, root, discovery_row)`` across every available
    registry workspace, sorted by ``(workspace_id, project_id)``.

    A workspace whose path is missing or its volume stalled this cycle
    (fsguard 503 from ``_discover_server_projects``) is silently skipped —
    mirrors ``core.routes.workspace``'s per-workspace degradation in
    ``list_workspace_projects`` so one dead mount never blanks every other
    workspace's rows.
    """
    out: list[tuple[str, Path, dict]] = []
    for ws in _known_workspaces(active_root):
        root = ws["path"]
        try:
            found = _discover_server_projects(root)
        except HTTPException as exc:
            if exc.status_code != 503:
                raise
            continue
        for row in found:
            out.append((ws["id"], root, row))
    out.sort(key=lambda t: (t[0], t[2]["project_id"]))
    return out


# ─── desired-state persistence ──────────────────────────────────────────────

def _servers_state_file(root: Path) -> Path:
    return paths.workspace_state_dir(root) / "servers.json"


def _load_desired_state(root: Path) -> dict:
    try:
        data = storage.read_json(_servers_state_file(root))
    except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_desired_state(root: Path, data: dict) -> None:
    storage.write_json(_servers_state_file(root), data)


def set_desired(root: Path, project_id: str, desired: str) -> None:
    """Persist the desired run state ("running"/"stopped") for a project.

    Public (no leading underscore) because ``core.routes.term`` calls this
    after killing a "server" tab session so the supervisor doesn't
    resurrect a session the user explicitly closed.
    """
    data = _load_desired_state(root)
    data[project_id] = {
        "desired": desired,
        "updated": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
    }
    _save_desired_state(root, data)


def _get_desired(root: Path, project_id: str) -> str:
    entry = _load_desired_state(root).get(project_id)
    if isinstance(entry, dict) and entry.get("desired") in ("running", "stopped"):
        return entry["desired"]
    return "stopped"


# ─── tmux + health ───────────────────────────────────────────────────────────

_SERVER_TAB_NAME = "server"


def _session_name_for(root: Path, project_id: str) -> str:
    return term_routes._tmux_name_for(project_id, _SERVER_TAB_NAME, root)


_HEALTH_TIMEOUT_S = 2.0


def _check_health(url: str | None, timeout: float = _HEALTH_TIMEOUT_S) -> bool:
    """GET ``url``; ANY HTTP response (including 4xx/5xx) counts as healthy.
    Connection refused / timeout / DNS failure -> unhealthy."""
    if not url:
        return False
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def _spawn_server_session(root: Path, project_id: str, project_dir: Path) -> str:
    """Start the tmux session running ``make server-start`` (no-op if
    already alive). Returns the session name. Raises HTTPException(409) on
    a hard tmux failure, HTTPException(500) if tmux isn't installed."""
    if not term_routes._tmux_available():
        raise HTTPException(status_code=500, detail="tmux not installed. Run: brew install tmux")
    session_name = _session_name_for(root, project_id)
    if term_routes._tmux_has_session(session_name):
        return session_name
    proc = subprocess.run(
        ["tmux", "new-session", "-d", "-s", session_name, "-c", str(project_dir), "make server-start"],
        capture_output=True, text=True, env=term_routes._tmux_child_env(),
    )
    if proc.returncode != 0:
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        message = err or out or "tmux new-session failed"
        if out and err and out != err:
            message = f"{err}\n{out}"
        raise HTTPException(status_code=409, detail=message)
    log.info(
        "server session spawned",
        extra={"event_type": "servers.spawn", "action": project_id, "target": session_name},
    )
    return session_name


def _stop_server_session(root: Path, project_id: str, project_dir: Path, has_stop: bool) -> str:
    """Best-effort ``make server-stop`` (if the target exists) then
    ``tmux kill-session``. Returns the session name. Raises
    HTTPException(504) if ``make server-stop`` times out; a nonzero exit
    code from ``server-stop`` itself is ignored (best effort)."""
    session_name = _session_name_for(root, project_id)
    if has_stop:
        try:
            subprocess.run(
                ["make", "server-stop"], cwd=str(project_dir), timeout=20,
                capture_output=True, text=True, env=term_routes._tmux_child_env(),
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="make server-stop timed out after 20s")
    if term_routes._tmux_available():
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            capture_output=True, text=True, env=term_routes._tmux_child_env(),
        )
    log.info(
        "server session stopped",
        extra={"event_type": "servers.stop", "action": project_id, "target": session_name},
    )
    return session_name


def _restart_project(root: Path, project_id: str, project_dir: Path, row: dict) -> None:
    """Stop then start. Raises HTTPException on a hard failure from either
    step (surfaced to the API caller as 409/504/500)."""
    try:
        _stop_server_session(root, project_id, project_dir, bool(row.get("has_stop")))
    finally:
        # Reset the cached liveness/started_at BEFORE respawning so the new
        # session gets a fresh "starting" grace window instead of inheriting
        # whatever `started_at` the previous run had.
        _refresh_status(root, project_id, row)
    _spawn_server_session(root, project_id, project_dir)


# ─── status cache ────────────────────────────────────────────────────────────
#
# Keyed by (resolved workspace root, project_id) so a workspace switch never
# mixes up two different workspaces' projects that happen to share an id.

_STATUS_LOCK = threading.Lock()
_STATUS: dict[tuple[str, str], dict] = {}

_STARTING_GRACE_S = 20.0


def _default_status_entry() -> dict:
    return {
        "healthy": None,
        "alive": False,
        "last_check": 0.0,
        "state": "stopped",
        "restarts": 0,
        "started_at": None,
        "consecutive_unhealthy": 0,
        "consecutive_restart_failures": 0,
        "last_restart_attempt": None,
        "session_created": None,
    }


def _derive_state(alive: bool, healthy: bool | None, health_url: str | None,
                  started_at: float | None, now_mono: float) -> str:
    if not alive:
        # No lab-managed session, but something answers on the health URL:
        # a server someone started by hand ("external") — visible and
        # stoppable from the dashboard, never auto-restarted.
        return "external" if healthy else "stopped"
    if not health_url or healthy:
        return "running"
    if started_at is not None and (now_mono - started_at) < _STARTING_GRACE_S:
        return "starting"
    return "unhealthy"


def _refresh_status(root: Path, project_id: str, row: dict) -> dict:
    """Compute liveness/health for one project and update the shared status
    cache (never performs a restart). Returns a copy of the updated entry.
    Used both by the supervisor tick and by GET /api/servers's bounded
    inline refresh for stale/missing rows."""
    session_name = _session_name_for(root, project_id)
    session_info = term_routes._tmux_session_info(session_name)
    alive = session_info is not None
    health_url = row.get("health_url")
    # Checked even without a live session so hand-started servers surface
    # as "external". A dead port with no session stays healthy=None ("no
    # health info"), not False — there's nothing there to be unhealthy.
    healthy = _check_health(health_url) if health_url else None
    if not alive and healthy is False:
        healthy = None
    now_mono = time.monotonic()
    key = (_root_key(root), project_id)
    with _STATUS_LOCK:
        entry = _STATUS.setdefault(key, _default_status_entry())
        if not alive:
            entry["started_at"] = None
            entry["consecutive_unhealthy"] = 0
            entry["session_created"] = None
        else:
            if entry["started_at"] is None:
                entry["started_at"] = now_mono
            entry["session_created"] = session_info.get("created") or None
        if alive and health_url:
            entry["consecutive_unhealthy"] = 0 if healthy else entry["consecutive_unhealthy"] + 1
        entry["alive"] = alive
        entry["healthy"] = healthy
        entry["last_check"] = time.time()
        entry["state"] = _derive_state(alive, healthy, health_url, entry["started_at"], now_mono)
        if entry["state"] == "running":
            entry["consecutive_restart_failures"] = 0
        return dict(entry)


def _row_for(root: Path, project_id: str, row: dict, entry: dict) -> dict:
    session_name = _session_name_for(root, project_id)
    port = row.get("port")
    status = entry["state"]
    # Human-facing URL, non-null whenever the server is actually listening
    # (managed or external) — the dashboard's "Open" button gates on this.
    url = f"http://localhost:{port}/" if (port is not None and status in ("running", "external")) else None
    return {
        "project_id": project_id,
        "workspace": _workspace_id(root),
        "path": str(root / "projects" / project_id),
        "has_stop": bool(row.get("has_stop")),
        "port": port,
        "health_url": row.get("health_url"),
        "url": url,
        "desired": _get_desired(root, project_id),
        "status": status,
        "healthy": entry["healthy"],
        "session_name": session_name,
        "session_created": entry.get("session_created"),
        "attach_command": f"tmux attach -t '{session_name}'",
        "last_check": entry["last_check"],
        "restarts": entry["restarts"],
    }


# ─── supervisor ──────────────────────────────────────────────────────────────

def _supervisor_interval_s() -> float:
    try:
        return max(1.0, float(os.environ.get("LAB_SERVER_SUPERVISOR_INTERVAL", "10")))
    except ValueError:
        return 10.0


def _supervisor_restart(root: Path, project_id: str, project_dir: Path, row: dict) -> bool:
    """Best-effort restart for the supervisor — never raises."""
    try:
        _restart_project(root, project_id, project_dir, row)
        return True
    except Exception:
        log.warning(
            "supervisor restart failed for %s", project_id, exc_info=True,
            extra={"event_type": "servers.supervisor.restart_failed", "action": project_id},
        )
        return False


def _supervisor_tick_impl(root: Path) -> None:
    rows = _discover_server_projects(root)
    desired_map = _load_desired_state(root)
    now_mono = time.monotonic()

    for row in rows:
        project_id = row["project_id"]
        entry = _refresh_status(root, project_id, row)
        desired = (desired_map.get(project_id) or {}).get("desired", "stopped")

        # "external" means the port is already answering without a lab
        # session — spawning `make server-start` on top of it would just
        # crash-loop on the busy port, so leave it alone.
        needs_restart = desired == "running" and entry["state"] != "external" and (
            not entry["alive"]
            or (bool(row.get("health_url")) and entry["consecutive_unhealthy"] >= 2)
        )

        key = (_root_key(root), project_id)
        if needs_restart:
            with _STATUS_LOCK:
                e = _STATUS[key]
                backed_off = (
                    e["consecutive_restart_failures"] >= 3
                    and e["last_restart_attempt"] is not None
                    and (now_mono - e["last_restart_attempt"]) < 60
                )
                if backed_off:
                    needs_restart = False
                else:
                    e["last_restart_attempt"] = now_mono
                    e["restarts"] += 1

        if not needs_restart:
            continue

        project_dir = root / "projects" / project_id
        ok = _supervisor_restart(root, project_id, project_dir, row)
        entry2 = _refresh_status(root, project_id, row)
        if not ok or not entry2["alive"]:
            with _STATUS_LOCK:
                _STATUS[key]["consecutive_restart_failures"] += 1


def supervisor_tick(root: Path) -> None:
    """Run one supervisor pass for ``root``.

    Never raises — a bad tick (a stalled workspace volume, a project whose
    Makefile went missing mid-scan, ...) must not kill the daemon thread.
    A workspace whose path is currently unavailable (fsguard 503 — missing
    mount, stalled volume) is skipped quietly at DEBUG rather than logged
    as an ERROR on every tick: with multiple workspaces ticked every
    interval, an unmounted USB drive is an expected steady state, not a
    bug. Any other failure is still logged loudly. Tests call this
    directly without any thread involved.
    """
    try:
        _supervisor_tick_impl(root)
    except HTTPException as exc:
        if exc.status_code == 503:
            log.debug(
                "server supervisor: workspace unavailable this tick: %s", root,
                extra={"event_type": "servers.supervisor.workspace_unavailable"},
            )
            return
        log.exception(
            "server supervisor tick failed for %s", root,
            extra={"event_type": "servers.supervisor.tick_failed"},
        )
    except Exception:
        log.exception(
            "server supervisor tick failed for %s", root,
            extra={"event_type": "servers.supervisor.tick_failed"},
        )


_SUPERVISOR_THREAD: threading.Thread | None = None
_SUPERVISOR_STOP = threading.Event()


def _supervisor_loop(get_root) -> None:
    interval = _supervisor_interval_s()
    while not _SUPERVISOR_STOP.is_set():
        try:
            active_root = get_root()
            for ws in _known_workspaces(active_root):
                supervisor_tick(ws["path"])
        except Exception:  # pragma: no cover — defensive; supervisor_tick already guards
            log.exception("server supervisor loop iteration failed")
        interval = _supervisor_interval_s()
        _SUPERVISOR_STOP.wait(interval)


def start_supervisor(app) -> None:
    """Start the background supervisor daemon thread for ``app``.

    Gated behind ``LAB_SERVER_SUPERVISOR`` (default on; set to "0" to
    disable — tests always disable it via conftest). Safe to call more than
    once; a second call is a no-op while the thread is alive.
    """
    global _SUPERVISOR_THREAD
    if os.environ.get("LAB_SERVER_SUPERVISOR", "1") == "0":
        return
    if _SUPERVISOR_THREAD is not None and _SUPERVISOR_THREAD.is_alive():
        return

    _SUPERVISOR_STOP.clear()

    def _get_root() -> Path | None:
        cache = getattr(app.state, "index_cache", None)
        return cache.root if cache is not None else None

    thread = threading.Thread(
        target=_supervisor_loop, args=(_get_root,),
        daemon=True, name="lab-server-supervisor",
    )
    _SUPERVISOR_THREAD = thread
    thread.start()


def stop_supervisor() -> None:
    _SUPERVISOR_STOP.set()


# ─── API ─────────────────────────────────────────────────────────────────────
#
# Every endpoint below is a plain sync `def` — like term.py, anything that
# shells out to tmux/make or touches the filesystem must run in FastAPI's
# threadpool rather than blocking the event loop.

@router.get("/api/servers")
def list_servers(request: Request) -> dict:
    active_root: Path = request.app.state.index_cache.root
    stale_after = _supervisor_interval_s() * 2
    now_wall = time.time()

    out = []
    for workspace_id, root, row in _discover_all_server_rows(active_root):
        project_id = row["project_id"]
        key = (_root_key(root), project_id)
        with _STATUS_LOCK:
            cached = _STATUS.get(key)
            entry = dict(cached) if cached else None
        if entry is None or (now_wall - entry["last_check"]) > stale_after:
            entry = _refresh_status(root, project_id, row)
        out.append(_row_for(root, project_id, row, entry))
    return {"servers": out}


@router.post("/api/servers/{workspace}/{project_id}/start")
def start_server(workspace: str, project_id: str, request: Request) -> dict:
    _validate_project_id(project_id)
    active_root: Path = request.app.state.index_cache.root
    root = _require_workspace_root(workspace, active_root)
    row = _find_server_project(root, project_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"project {project_id!r} has no server-start Makefile target in workspace {workspace!r}",
        )

    set_desired(root, project_id, "running")
    project_dir = root / "projects" / project_id
    _spawn_server_session(root, project_id, project_dir)
    entry = _refresh_status(root, project_id, row)
    return _row_for(root, project_id, row, entry)


@router.post("/api/servers/{workspace}/{project_id}/stop")
def stop_server(workspace: str, project_id: str, request: Request) -> dict:
    _validate_project_id(project_id)
    active_root: Path = request.app.state.index_cache.root
    root = _require_workspace_root(workspace, active_root)
    row = _find_server_project(root, project_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"project {project_id!r} has no server-start Makefile target in workspace {workspace!r}",
        )

    set_desired(root, project_id, "stopped")
    project_dir = root / "projects" / project_id
    _stop_server_session(root, project_id, project_dir, bool(row.get("has_stop")))
    entry = _refresh_status(root, project_id, row)
    return _row_for(root, project_id, row, entry)


@router.post("/api/servers/{workspace}/{project_id}/restart")
def restart_server(workspace: str, project_id: str, request: Request) -> dict:
    _validate_project_id(project_id)
    active_root: Path = request.app.state.index_cache.root
    root = _require_workspace_root(workspace, active_root)
    row = _find_server_project(root, project_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"project {project_id!r} has no server-start Makefile target in workspace {workspace!r}",
        )

    set_desired(root, project_id, "running")
    project_dir = root / "projects" / project_id
    _restart_project(root, project_id, project_dir, row)
    entry = _refresh_status(root, project_id, row)
    return _row_for(root, project_id, row, entry)
