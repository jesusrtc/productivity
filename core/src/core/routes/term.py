"""Project-scoped terminals backed by tmux + a PTY bridge over WebSocket.

Shape:
  browser xterm.js  <--WS-->  FastAPI  <--PTY-->  `tmux attach -t <name>`  <-->  claude

Why tmux + PTY (and not one or the other):
- **tmux** gives persistence. Closing the browser tab leaves `claude` running;
  the user can `tmux attach -t <name>` from iTerm at any time.
- **PTY** is the transport: forking a pseudo-terminal that execs `tmux attach`
  gives us clean ANSI + resize + streaming to pump over the WebSocket.

Session identity lives in TWO places:

- ``projects/<id>/project.json`` — durable. Stores the *logical*
  session list: ``{name, kind, claude_session_id?}``. This is the source of
  truth for "which sessions does this project know about" and for the
  Claude session UUIDs we need to ``--resume``. Survives server restarts.
- ``.lab/state/sessions/sessions.json`` — runtime. Maps the live tmux
  session name back to ``{project_id, logical_name, cwd, created_at}``.
  Re-created on session spawn, cleaned on session kill.

Tmux session naming (see ``_tmux_name_for`` / ``_parse_tmux_name``):
``neurona-<workspace>-<project>-<tab>-<hash6>``, where ``<workspace>`` is
the stable id from the workspace registry (``~/.lab/workspaces.toml``) —
NOT a hash of the workspace path — so a path change (USB remount, moved
checkout) no longer orphans every live session. ``<hash6>`` is a
deterministic 6-hex marker so the same workspace+project+tab always
produces the same name. Two older schemes (``lab-<label>-<digest8>-
<project>-<tab>`` and bare ``lab-<project>-<tab>``) are still recognized
for discovery/adoption so sessions spawned by a previous server build
aren't orphaned by this change. ``LAB_TMUX_PREFIX`` (tests / opt-out) keeps
the plain ``<prefix><project>-<tab>`` shape exactly as before.

Killing a session (the "X on a tab" flow) removes it from tmux + the runtime
file but **keeps** the project.json entry so a later re-open can
``claude --resume <claude_session_id>`` and pick up the conversation.

Most endpoints here are scoped to the ACTIVE workspace only — that's what
"the project I have open" means. Two exceptions span every REGISTERED
workspace (``~/.lab/workspaces.toml``), for the cross-workspace terminals
dashboard: ``GET /api/term/sessions`` with no ``project_id`` (each row
tagged ``workspace``), and ``DELETE /api/term/sessions/{name}`` (a session
named for any workspace is accepted and killed against its own workspace's
files). ``DELETE /api/term/sessions/project/{id}`` stays active-workspace
by default but takes an optional ``?workspace=`` to target another one. See
``_known_workspaces``.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import fcntl
import hashlib
import json
import logging
import os
import pty
import re
import shutil
import signal
import struct
import subprocess
import termios
import time
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from lab import settings as lab_settings

from core import fsguard


router = APIRouter()

log = logging.getLogger("core.term")


# ─── WebSocket send/close plumbing ──────────────────────────────────────────
#
# Any `await ws.send_text(...)` / `await ws.close()` can race with the client
# going away. Starlette/uvicorn surface the race as one of several exception
# types depending on the layer — `WebSocketDisconnect`, uvicorn's
# `ClientDisconnected`, `websockets.ConnectionClosed`, `RuntimeError` when
# we try to send after our own close already went out, and `OSError` when
# the underlying socket is gone. Catching each one individually scattered
# across every send site is noisy and easy to get wrong, so we funnel all
# sends through `_ws_send_text_safe` and all closes through `_ws_close_safe`
# which swallow that whole family and return a bool so callers can decide
# to bail.

try:
    from uvicorn.protocols.utils import ClientDisconnected as _ClientDisconnected
except Exception:  # pragma: no cover — defensive; uvicorn is a hard dep
    _ClientDisconnected = ConnectionError  # type: ignore[assignment,misc]

try:
    from websockets.exceptions import ConnectionClosed as _ConnectionClosed
except Exception:  # pragma: no cover
    _ConnectionClosed = ConnectionError  # type: ignore[assignment,misc]


_WS_SEND_RACE_ERRORS: tuple = (
    WebSocketDisconnect, _ClientDisconnected, _ConnectionClosed,
    RuntimeError, OSError,
)


async def _ws_send_text_safe(ws: WebSocket, payload: str) -> bool:
    """Send a text frame; swallow the client-gone-away family. Returns
    True on successful send, False if the client has already disconnected
    (caller should typically break out of its loop)."""
    try:
        await ws.send_text(payload)
        return True
    except _WS_SEND_RACE_ERRORS:
        return False
    except Exception:  # pragma: no cover — last-resort guard
        log.debug("ws send_text failed unexpectedly", exc_info=True)
        return False


async def _ws_close_safe(ws: WebSocket, code: int = 1000) -> None:
    """Close the WS; swallow the client-gone-away family and double-close
    runtime errors. Never raises."""
    try:
        await ws.close(code=code)
    except _WS_SEND_RACE_ERRORS:
        pass
    except Exception:  # pragma: no cover
        log.debug("ws close failed unexpectedly", exc_info=True)


# ─── paths + env ────────────────────────────────────────────────────────────

# Fixed literal marker for the current tmux naming scheme —
# ``neurona-<workspace>-<project>-<tab>-<hash6>``. Being a constant (not
# derived from the workspace path) it survives path changes, and doubles as
# a quick "yes, this is a lab-owned session" grep target.
_SESSION_PREFIX = "neurona-"

_WORKSPACE_LABEL_CACHE: dict[str, tuple[float, str]] = {}
_WORKSPACE_LABEL_TTL_S = 5.0


def _workspace_label_from_registry(resolved_root: Path) -> str | None:
    """Match ``resolved_root`` against ``~/.lab/workspaces.toml`` entries.

    Returns the entry's ``id`` — the stable handle a concurrent `lab
    workspace` rename/re-id operation may change, but which never changes
    just because the workspace's on-disk PATH moved (USB remount, moved
    checkout). Read fresh every call (the TTL cache above wraps the whole
    resolution, not just this step) so a registry edited out-of-process is
    picked up without a server restart.
    """
    try:
        from lab import paths
        data = paths.read_workspace_registry()
    except Exception:
        return None
    for row in data.get("workspaces") or []:
        raw_path = row.get("path")
        if not raw_path:
            continue
        try:
            entry_path = Path(str(raw_path)).expanduser().resolve()
        except OSError:
            continue
        if entry_path == resolved_root:
            wid = row.get("id")
            if wid:
                return str(wid)
    return None


def _workspace_label_from_lab_toml(resolved_root: Path) -> str | None:
    """Fallback: ``[workspace].name`` from the workspace's own ``lab.toml``."""
    toml_path = resolved_root / "lab.toml"
    if not toml_path.is_file():
        return None
    try:
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    workspace = data.get("workspace")
    if isinstance(workspace, dict):
        name = workspace.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _resolve_workspace_label(root: Path | None) -> str:
    """Stable short id for ``root``, used to namespace tmux session names.

    Resolution order: the workspace registry's ``id`` (matched by resolved
    path so it's independent of the path string itself — this is the fix
    for sessions silently orphaning on a path change), then
    ``[workspace].name`` from the workspace's own ``lab.toml``, then a
    sanitized root directory name as a last resort.

    Cached per resolved root path for a few seconds: cheap enough to re-read
    every call, but several tmux operations can fan out from one request and
    there's no reason to re-parse the registry for each of them.
    """
    if root is None:
        return "workspace"
    try:
        resolved = root.expanduser().resolve()
    except OSError:
        resolved = root.expanduser()
    key = str(resolved)
    now = time.monotonic()
    cached = _WORKSPACE_LABEL_CACHE.get(key)
    if cached and (now - cached[0]) < _WORKSPACE_LABEL_TTL_S:
        return cached[1]
    label = (
        _workspace_label_from_registry(resolved)
        or _workspace_label_from_lab_toml(resolved)
        or resolved.name
    )
    sanitized = _sanitize(label)
    _WORKSPACE_LABEL_CACHE[key] = (now, sanitized)
    return sanitized


def _new_scheme_prefix(root: Path | None) -> str:
    """Prefix of every CURRENT-scheme session name for this workspace."""
    return f"{_SESSION_PREFIX}{_resolve_workspace_label(root)}-"


def _legacy_namespaced_prefix(root: Path | None) -> str:
    """Reconstruct the pre-``neurona-`` namespaced prefix for ``root``.

    This reproduces the entire prefix algorithm the pre-``neurona-`` code
    used to compute on every call: ``lab-<dirname>-<sha1(resolved
    path)[:8]>-``. It embedded a hash of the workspace PATH, which is
    exactly why it broke on a path change — kept here only so already-live
    sessions from an older server build are still discovered instead of
    orphaned.
    """
    if root is None:
        return "lab-workspace-"
    try:
        resolved = root.expanduser().resolve()
    except OSError:
        resolved = root.expanduser()
    label = re.sub(r"[^A-Za-z0-9_-]+", "-", resolved.name).strip("-") or "workspace"
    digest = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:8]
    return f"lab-{label}-{digest}-"


def _tmux_discovery_prefixes(root: Path | None) -> list[str]:
    """All prefixes under which a tmux session could belong to this workspace.

    Includes the current fixed-``neurona-`` scheme plus the two schemes an
    older server build used, so already-live sessions from before this
    naming change are discovered/adopted instead of vanishing from the UI.
    With ``LAB_TMUX_PREFIX`` set (tests), there's only ever the one scheme.
    """
    env_prefix = os.environ.get("LAB_TMUX_PREFIX")
    if env_prefix:
        return [env_prefix]
    return [
        _new_scheme_prefix(root),
        _legacy_namespaced_prefix(root),
        "lab-",
    ]


# ─── multi-workspace session discovery ──────────────────────────────────────
#
# Dev servers (core.routes.servers) and a handful of terminal endpoints span
# every registered workspace, not just the active one — the dashboard needs
# to see and kill sessions that live in a workspace other than the one
# currently open. These helpers extend the single-root primitives above
# across every workspace in the registry.

def _known_workspaces(active_root: Path | None) -> list[dict]:
    """``[{"id": ..., "path": Path}, ...]`` for every registered workspace,
    plus ``active_root`` itself if it isn't already one of them (id
    defaults to the resolved directory name — same fallback
    ``core.routes.workspace`` and ``core.routes.servers`` use for a
    not-yet-registered current workspace). Read fresh on every call: the
    registry is a small TOML file and can change out-of-process (``lab
    workspace add`` et al.) without a server restart.
    """
    from lab import paths
    try:
        data = paths.read_workspace_registry()
    except Exception:
        data = {}
    rows: list[dict] = []
    seen: set[str] = set()
    for row in data.get("workspaces") or []:
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
        rows.append({"id": str(row.get("id") or root.name), "path": root})
    if active_root is not None:
        try:
            resolved = active_root.expanduser().resolve()
        except OSError:
            resolved = active_root
        if str(resolved) not in seen:
            rows.insert(0, {"id": resolved.name, "path": resolved})
    return rows


def _tmux_discovery_prefixes_all(workspaces: list[dict]) -> list[str]:
    """Union of ``_tmux_discovery_prefixes`` across every workspace in
    ``workspaces`` — lets the "list/kill anything" paths recognize a
    session spawned for ANY registered workspace, not just the active one.

    Cheap: each workspace contributes a couple of literal-prefix strings
    (no filesystem access), and the workspace-agnostic bare ``"lab-"``
    legacy prefix is included exactly once regardless of workspace count.
    Callers should compute ``workspaces`` once (e.g. via
    ``_known_workspaces``) and pass it in rather than re-reading the
    registry per call.
    """
    env_prefix = os.environ.get("LAB_TMUX_PREFIX")
    if env_prefix:
        return [env_prefix]
    prefixes: list[str] = []
    seen: set[str] = set()
    for ws in workspaces:
        for p in (_new_scheme_prefix(ws["path"]), _legacy_namespaced_prefix(ws["path"])):
            if p not in seen:
                seen.add(p)
                prefixes.append(p)
    prefixes.append("lab-")
    return prefixes


def _resolve_session_workspace_root(
    name: str, active_root: Path, workspaces: list[dict] | None = None,
) -> Path:
    """Which workspace's root a live tmux session name actually belongs to.

    The current + legacy-namespaced naming schemes both embed a
    workspace-specific segment (the registry label, or a hash of that
    workspace's old path) so they're unambiguous once tried against every
    known workspace's root. The oldest bare ``lab-<project>-<tab>`` scheme
    carries no workspace identity at all — those sessions fall back to the
    active workspace, exactly as this code has always behaved
    (single-workspace) before this change. ``LAB_TMUX_PREFIX`` test mode
    also always resolves to the active root (there's only ever one naming
    scheme in that mode, so no ambiguity to resolve).
    """
    if os.environ.get("LAB_TMUX_PREFIX"):
        return active_root
    for ws in (workspaces if workspaces is not None else _known_workspaces(active_root)):
        root = ws["path"]
        if name.startswith(_new_scheme_prefix(root)) or name.startswith(_legacy_namespaced_prefix(root)):
            return root
    return active_root


# If the lab server process itself happens to be launched FROM INSIDE a tmux
# session (e.g. `make start` run in a tmux pane), every `tmux ...` subprocess
# call below would inherit `$TMUX`/`$TMUX_PANE` from that parent shell — and
# tmux uses `$TMUX` to find its control socket. That silently redirects
# `list-sessions` / `new-session` / `has-session` etc. onto the CONTAINING
# session's server instead of the default one. A launchd-run instance (no
# controlling tmux) then talks to the *default* socket and can't see any of
# those sessions — they look gone, and reopening a project spawns fresh
# duplicates instead of finding them. Stripping `TMUX`/`TMUX_PANE` from every
# tmux child's env pins us to the default socket unconditionally, regardless
# of how the server process itself was launched.
_TMUX_ENV_STRIP_KEYS = ("TMUX", "TMUX_PANE")


def _tmux_child_env() -> dict[str, str]:
    """Environment for a tmux subprocess/exec: current env minus TMUX vars."""
    return {k: v for k, v in os.environ.items() if k not in _TMUX_ENV_STRIP_KEYS}


# Reserved pseudo-project ids.
#  * __cerebro__ — the personal knowledge-base view (cwd = content/)
#  * __self__    — the Lab framework checkout itself   (cwd = repo root)
#  * __logs__    — the embedded logs view              (cwd = logs/)
# They behave like regular projects otherwise: they show up in the project-
# tabs strip, can be closed (X), and reopened from the Home dashboard.
CEREBRO_PROJECT_ID = "__cerebro__"
SELF_PROJECT_ID = "__self__"
LOGS_PROJECT_ID = "__logs__"
# Per-repo pseudo project for the Code Search tab. The id is
# ``__cs_<repo>__`` where ``<repo>`` is a directory name under
# ``repositories/``. Used so each Code-Search repo has its own scoped
# terminal panel (cwd = repositories/<repo>) without needing a real
# project.json.
_CS_PREFIX = "__cs_"
_CS_SUFFIX = "__"


def _cs_repo_name(project_id: str) -> str | None:
    if not project_id.startswith(_CS_PREFIX) or not project_id.endswith(_CS_SUFFIX):
        return None
    name = project_id[len(_CS_PREFIX):-len(_CS_SUFFIX)]
    return name or None


def _sessions_file(root: Path) -> Path:
    from lab import paths
    return paths.sessions_file(root)


def _project_json(root: Path, project_id: str) -> Path:
    """Path of the metadata file for a project_id. Pseudo-projects store
    their sessions[] at a hidden file under content/ that shares
    project.json's shape."""
    if project_id == CEREBRO_PROJECT_ID:
        return root / "content" / ".cerebro-project.json"
    if project_id == SELF_PROJECT_ID:
        from lab import paths
        root = paths.find_framework_root()
        return root / "content" / ".self-project.json"
    if project_id == LOGS_PROJECT_ID:
        return root / "content" / ".logs-project.json"
    return root / "projects" / project_id / "project.json"


def _project_cwd(root: Path, project_id: str) -> Path:
    """Absolute cwd for a project_id.

    - ``__cerebro__``     → content/
    - ``__self__``        → monorepo root (so claude sees apps/, docs/, etc.)
    - ``__logs__``        → logs/
    - ``__cs_<repo>__``   → repositories/<repo> (Code Search per-repo terminal)
    """
    if project_id == CEREBRO_PROJECT_ID:
        return (root / "content").resolve()
    if project_id == SELF_PROJECT_ID:
        from lab import paths
        return paths.find_framework_root().resolve()
    if project_id == LOGS_PROJECT_ID:
        from lab import paths
        return paths.logs_dir(root).resolve()
    repo = _cs_repo_name(project_id)
    if repo:
        return (root / "repositories" / repo).resolve()
    return (root / "projects" / project_id).resolve()


# ─── runtime metadata (.sessions.json) ──────────────────────────────────────

def _load_meta(root: Path) -> dict:
    p = _sessions_file(root)
    legacy = root / "content" / ".sessions.json"
    if not p.is_file() and legacy.is_file():
        p = legacy
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, ValueError):
        return {}


def _save_meta(root: Path, meta: dict) -> None:
    p = _sessions_file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(meta, indent=2) + "\n")


# Workspace roots already warned about being unavailable (e.g. a registered
# workspace living on an unplugged external volume). The UI polls the session
# endpoints every few seconds, so warn once per root, not once per cycle.
_UNAVAILABLE_WARNED_ROOTS: set[str] = set()


def _warn_root_unavailable_once(root: Path, action: str, exc: OSError) -> None:
    key = str(root)
    if key in _UNAVAILABLE_WARNED_ROOTS:
        return
    _UNAVAILABLE_WARNED_ROOTS.add(key)
    log.warning(
        "workspace storage unavailable during %s for %s: %s",
        action, root, exc,
        extra={"event_type": "term.workspace.unavailable", "target": str(root)},
    )


# ─── durable metadata (project.json.sessions) ───────────────────────────────

def _load_project(root: Path, project_id: str) -> dict | None:
    p = _project_json(root, project_id)
    # Pre-rename migration: if the Cerebro file doesn't exist yet but the
    # old ``.knowledge-project.json`` does, rename it in place. One-shot.
    if project_id == CEREBRO_PROJECT_ID and not p.is_file():
        legacy = root / "content" / ".knowledge-project.json"
        if legacy.is_file():
            try:
                legacy.rename(p)
            except OSError:
                pass  # best effort; fall through
    if not p.is_file():
        # Pseudo-projects (Cerebro, Self, Logs) have no ``lab project new``
        # ceremony — bootstrap an empty shell so session IDs get persisted
        # on first use. Real projects still return None; creating their
        # project.json is the CLI's job.
        if project_id in (CEREBRO_PROJECT_ID, SELF_PROJECT_ID, LOGS_PROJECT_ID):
            return {}
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, ValueError):
        return None


def _save_project(root: Path, project_id: str, data: dict) -> None:
    p = _project_json(root, project_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")


def _get_project_sessions(root: Path, project_id: str) -> list[dict]:
    """Return the `sessions` array from project.json (empty if missing)."""
    data = _load_project(root, project_id)
    if not data:
        return []
    sessions = data.get("sessions")
    return sessions if isinstance(sessions, list) else []


def _project_session_by_name(root: Path, project_id: str) -> dict[str, dict]:
    """Saved sessions keyed by logical name."""
    return {
        s["name"]: s for s in _get_project_sessions(root, project_id)
        if isinstance(s, dict) and isinstance(s.get("name"), str)
    }


def _upsert_project_session(root: Path, project_id: str, entry: dict) -> None:
    """Insert or update an entry (keyed by ``name``) in project.json.sessions."""
    data = _load_project(root, project_id)
    if data is None:
        return  # project.json doesn't exist — skip silently; the session still
                # runs in tmux, just without durable storage.
    sessions = data.setdefault("sessions", [])
    if not isinstance(sessions, list):
        sessions = data["sessions"] = []
    for i, s in enumerate(sessions):
        if isinstance(s, dict) and s.get("name") == entry["name"]:
            sessions[i] = {**s, **entry}
            break
    else:
        sessions.append(entry)
    _save_project(root, project_id, data)


def _clean_optional_text(raw: str | None, *, max_len: int) -> str | None:
    if raw is None:
        return None
    text = " ".join(str(raw).strip().split())
    if not text:
        return None
    return text[:max_len]


_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+")


def _clean_pane_line(line: str) -> str:
    line = _ANSI_RE.sub("", line)
    line = _CONTROL_RE.sub("", line)
    return " ".join(line.strip().split())


def _infer_session_summary(name: str) -> str | None:
    """Best-effort hover summary from the visible tmux pane.

    This intentionally does not ask the agent to summarize itself; that would
    affect latency and sometimes mutate the conversation. A cached pane
    capture gives enough context for hover text without touching stdin.
    """
    now = time.monotonic()
    cached = _SUMMARY_CACHE.get(name)
    if cached and (now - cached[0]) < _SUMMARY_TTL_S:
        return cached[1] or None
    if not _tmux_available():
        return None
    try:
        proc = subprocess.run(
            ["tmux", "capture-pane", "-pt", name, "-S", "-120"],
            capture_output=True, text=True, timeout=1.0, env=_tmux_child_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    lines = [
        line for line in (_clean_pane_line(raw) for raw in proc.stdout.splitlines())
        if line and line not in ("$", ">", "%")
    ]
    if not lines:
        summary = ""
    else:
        tail = lines[-2:]
        summary = " / ".join(tail)
        if len(summary) > 240:
            summary = summary[:237].rstrip() + "..."
    _SUMMARY_CACHE[name] = (now, summary)
    return summary or None


# ─── registry recovery ──────────────────────────────────────────────────────
#
# .sessions.json is rebuildable state: every live tmux session is named
# ``<prefix><project>-<logical>`` and the durable half of its identity
# (kind / agent / claude_session_id) lives in project.json. If the runtime
# file is ever lost or corrupted, reconstruct it instead of leaving live
# sessions orphaned — orphans have project_id=None, which empties
# /api/term/projects-with-sessions and greys out every tab in the UI.

def _known_project_ids(root: Path) -> list[str]:
    ids = [CEREBRO_PROJECT_ID, SELF_PROJECT_ID, LOGS_PROJECT_ID]
    projects = root / "projects"
    if projects.is_dir():
        ids += [p.name for p in projects.iterdir() if p.is_dir()]
    repos = root / "repositories"
    if repos.is_dir():
        ids += [f"{_CS_PREFIX}{p.name}{_CS_SUFFIX}" for p in repos.iterdir() if p.is_dir()]
    return ids


def _split_project_tab_from_ids(project_ids: list[str], rest: str) -> tuple[str, str] | None:
    """Split ``<project>-<tab>`` against known project ids, longest first.

    Project ids can themselves contain ``-`` so the split point is
    ambiguous without this. The caller supplies project ids so dashboard
    scans can compute them once per workspace instead of re-walking the
    filesystem for every live tmux session.
    """
    for pid in sorted(set(project_ids), key=len, reverse=True):
        sane = _sanitize(pid)
        if rest.startswith(sane + "-") and len(rest) > len(sane) + 1:
            return pid, rest[len(sane) + 1:]
    return None


def _split_project_tab(root: Path, rest: str) -> tuple[str, str] | None:
    return _split_project_tab_from_ids(_known_project_ids(root), rest)


def _split_project_tab_hashed_from_ids(
    project_ids: list[str],
    workspace: str,
    rest: str,
) -> tuple[str, str] | None:
    """Split ``<project>-<tab>-<hash6>`` for the current naming scheme.

    Tolerates sessions missing the hash suffix (e.g. hand-created by a CLI
    or agent that followed the ``<project>-<tab>`` shape but didn't compute
    the marker): a trailing 6-hex segment is only treated as the hash when
    it verifies against the deterministic hash for that exact (project,
    tab) pair, so a tab name that innocently ends in 6 hex characters is
    never mistaken for one and chopped off.
    """
    for pid in sorted(set(project_ids), key=len, reverse=True):
        sane = _sanitize(pid)
        if not (rest.startswith(sane + "-") and len(rest) > len(sane) + 1):
            continue
        middle = rest[len(sane) + 1:]
        if "-" in middle:
            maybe_tab, _, maybe_hash = middle.rpartition("-")
            if maybe_tab and _HASH_HEX_RE.match(maybe_hash):
                if maybe_hash == _session_hash(workspace, sane, maybe_tab):
                    return pid, maybe_tab
        # No verified hash suffix — tolerate it; the whole remainder is the
        # tab. Still a valid nomenclature session, just hand-made.
        return pid, middle
    return None


def _split_project_tab_hashed(root: Path, workspace: str, rest: str) -> tuple[str, str] | None:
    return _split_project_tab_hashed_from_ids(_known_project_ids(root), workspace, rest)


def _parse_tmux_name(root: Path, name: str) -> tuple[str, str] | None:
    """Split a live tmux session name back into ``(project_id, logical_name)``.

    Recognizes three generations of naming, tried in order:
      1. Current: ``neurona-<workspace>-<project>-<tab>-<hash6>``.
      2. Namespaced legacy: ``lab-<label>-<digest8>-<project>-<tab>``.
      3. Bare legacy: ``lab-<project>-<tab>``.
    All three are tried so sessions spawned by an older server build (or by
    an agent/CLI running outside the server, following the convention) are
    still discovered and adopted instead of showing up as orphaned.

    With ``LAB_TMUX_PREFIX`` set, only the single legacy-shaped scheme under
    that literal prefix is recognized (test mode). Returns None for names we
    can't attribute (e.g. the UUID fallback for project-less terminals).
    """
    env_prefix = os.environ.get("LAB_TMUX_PREFIX")
    if env_prefix:
        if not name.startswith(env_prefix):
            return None
        return _split_project_tab(root, name[len(env_prefix):])

    new_prefix = _new_scheme_prefix(root)
    if name.startswith(new_prefix):
        workspace = new_prefix[len(_SESSION_PREFIX):-1]  # strip "neurona-" + trailing "-"
        parsed = _split_project_tab_hashed(root, workspace, name[len(new_prefix):])
        if parsed:
            return parsed

    legacy_ns = _legacy_namespaced_prefix(root)
    if name.startswith(legacy_ns):
        parsed = _split_project_tab(root, name[len(legacy_ns):])
        if parsed:
            return parsed

    if name.startswith("lab-"):
        parsed = _split_project_tab(root, name[len("lab-"):])
        if parsed:
            return parsed

    return None


def _parse_tmux_name_with_project_ids(
    root: Path,
    name: str,
    project_ids: list[str],
) -> tuple[str, str] | None:
    """Like ``_parse_tmux_name`` but uses a pre-scanned project id list."""
    env_prefix = os.environ.get("LAB_TMUX_PREFIX")
    if env_prefix:
        if not name.startswith(env_prefix):
            return None
        return _split_project_tab_from_ids(project_ids, name[len(env_prefix):])

    new_prefix = _new_scheme_prefix(root)
    if name.startswith(new_prefix):
        workspace = new_prefix[len(_SESSION_PREFIX):-1]
        parsed = _split_project_tab_hashed_from_ids(
            project_ids,
            workspace,
            name[len(new_prefix):],
        )
        if parsed:
            return parsed

    legacy_ns = _legacy_namespaced_prefix(root)
    if name.startswith(legacy_ns):
        parsed = _split_project_tab_from_ids(project_ids, name[len(legacy_ns):])
        if parsed:
            return parsed

    if name.startswith("lab-"):
        parsed = _split_project_tab_from_ids(project_ids, name[len("lab-"):])
        if parsed:
            return parsed

    return None


def _reconstruct_meta_entry(root: Path, name: str, created: int = 0) -> dict | None:
    """Best-effort runtime entry for a live session .sessions.json has no
    record of. The durable project.json entry wins where present; otherwise
    the logical name's leading word fills the gaps ("bash" → terminal,
    "codex" → codex agent, "server" → a managed dev-server tab spawned by
    ``core.routes.servers``, not a claude conversation)."""
    parsed = _parse_tmux_name(root, name)
    if not parsed:
        return None
    pid, logical = parsed
    base = logical.split("-")[0]
    entry: dict = {
        "project_id": pid,
        "logical_name": logical,
        "kind": "terminal" if base in ("bash", "terminal", "term", "shell", "server") else "claude",
        "agent": None,
        "cwd": str(_project_cwd(root, pid)),
        "created_at": created or int(time.time()),
        "recovered": True,
    }
    if entry["kind"] == "claude":
        entry["agent"] = base if base in lab_settings.VALID_AGENTS else "claude"
    for s in _get_project_sessions(root, pid):
        if isinstance(s, dict) and s.get("name") == logical:
            entry["kind"] = s.get("kind") or entry["kind"]
            entry["agent"] = s.get("agent") or entry["agent"]
            if s.get("claude_session_id"):
                entry["claude_session_id"] = s["claude_session_id"]
            break
    return entry


def _sync_meta(root: Path, live: list[dict] | None) -> dict:
    """Load .sessions.json reconciled against the live tmux listing.

    - ``live is None`` (listing failed) → return the registry untouched.
      Never prune on a failed listing: one transient tmux error would
      otherwise wipe every session's project mapping.
    - Prune entries whose tmux session is provably gone.
    - Rebuild entries for live sessions the registry has no record of.
    """
    meta = _load_meta(root)
    if live is None:
        log.warning(
            "tmux session listing unavailable; preserving terminal registry",
            extra={"event_type": "term.registry.unknown"},
        )
        return meta
    live_by_name = {s["name"]: s for s in live}
    changed = False
    for n in [n for n in meta if n not in live_by_name]:
        meta.pop(n)
        changed = True
        log.info(
            "terminal registry pruned dead tmux session %s",
            n,
            extra={"event_type": "term.registry.prune", "target": n},
        )
    for n, s in live_by_name.items():
        if n in meta:
            continue
        entry = _reconstruct_meta_entry(root, n, created=s.get("created", 0))
        if entry:
            meta[n] = entry
            changed = True
            log.info(
                "terminal registry recovered live tmux session %s",
                n,
                extra={
                    "event_type": "term.registry.recover",
                    "target": n,
                    "action": entry.get("project_id"),
                },
            )
    if changed:
        # Best-effort: the reconciled registry is still valid in memory, so
        # session listing must keep working even when the workspace's volume
        # can't take the write (unplugged drive → its stub dir under /Volumes
        # is root-owned and mkdir raises PermissionError). The save simply
        # retries on a later cycle once the volume is back.
        try:
            _save_meta(root, meta)
            _UNAVAILABLE_WARNED_ROOTS.discard(str(root))
        except OSError as exc:
            _warn_root_unavailable_once(root, "terminal registry save", exc)
    return meta


# ─── tmux helpers ───────────────────────────────────────────────────────────

def _tmux_available() -> bool:
    return shutil.which("tmux") is not None


def _tmux_list(prefixes: str | list[str]) -> list[dict] | None:
    """Return live tmux sessions whose names start with any of ``prefixes``.

    ``prefixes`` may be a single string (back-compat with callers that only
    know about one naming scheme) or a list (discovery across multiple
    schemes — see ``_tmux_discovery_prefixes``).

    Returns ``None`` when the listing itself FAILED — tmux binary missing,
    or ``tmux list-sessions`` errored for any reason other than "no server
    running" (which genuinely means zero sessions and maps to ``[]``).
    None means *unknown*, not *empty*: callers must never prune registry
    state on a failed listing — a single transient tmux error used to wipe
    every session's project mapping from .sessions.json (2026-06-10).
    """
    if not _tmux_available():
        return None
    if isinstance(prefixes, str):
        prefixes = [prefixes]
    proc = subprocess.run(
        ["tmux", "list-sessions", "-F",
         "#{session_name}|#{session_created}|#{session_attached}|#{session_windows}"],
        capture_output=True, text=True, env=_tmux_child_env(),
    )
    if proc.returncode != 0:
        err = (proc.stderr or "").lower()
        if "no server running" in err or "no sessions" in err:
            return []
        log.warning(
            "tmux list-sessions failed: %s",
            (proc.stderr or proc.stdout or "").strip()[:500],
            extra={"event_type": "term.tmux.list_failed"},
        )
        return None
    rows: list[dict] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        name = parts[0]
        if not any(name.startswith(p) for p in prefixes):
            continue
        rows.append({
            "name": name,
            "created": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0,
            "attached": parts[2] != "0" if len(parts) > 2 else False,
            "windows": int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1,
        })
    return rows


def _tmux_has_session(name: str) -> bool:
    if not _tmux_available():
        return False
    proc = subprocess.run(
        ["tmux", "has-session", "-t", name],
        capture_output=True, text=True, env=_tmux_child_env(),
    )
    return proc.returncode == 0


def _tmux_session_info(name: str) -> dict | None:
    """Single-session listing row (``created``/``attached``/``windows``),
    or ``None`` if the session isn't currently alive.

    Reuses ``_tmux_list`` (already the shape other listing endpoints pay
    for) filtered down to an exact name match, rather than adding a second
    tmux command shape. Fails closed like ``_tmux_has_session``: tmux
    missing or a failed listing both read as "not alive" here (callers
    that need to distinguish "genuinely empty" from "listing failed"
    should use ``_tmux_list`` directly, the way ``_sync_meta`` does).
    """
    for row in _tmux_list([name]) or []:
        if row["name"] == name:
            return row
    return None


def _configure_tmux_wheel_scrolling(session_name: str) -> None:
    """Enable mouse + route wheel-up like a normal terminal would.

    Wheel-up routing (mirrors tmux's stock WheelUpPane binding):

    - Pane's program enabled mouse reporting (``mouse_any_flag`` — Claude
      Code does) → ``send-keys -M`` passes the wheel event through so the
      app scrolls its own transcript, exactly like running it directly in
      iTerm. An earlier unconditional ``copy-mode -eu`` binding hijacked
      these events and paged through stale pane history instead — read as
      "scrolling shows previous commands".
    - Pane already in copy-mode → forward too (copy-mode consumes it).
    - Otherwise (plain shells, codex — no mouse reporting) → enter
      copy-mode and scroll by lines (``-e`` exits at the bottom; no ``-u``
      page-jump on entry).

    Two deliberate deviations from stock tmux:

    - No bare ``send-keys -M`` fallback for panes without mouse reporting —
      that shoved raw mouse-escape bytes into the shell buffer and bash
      readline ran random commands. The ``mouse_any_flag`` guard means -M
      only reaches programs that asked for (and can parse) mouse input.
    - ``alternate_on`` is dropped from the stock condition: for an
      alt-screen pane without mouse reporting tmux translates wheel into
      arrow keys, which recalls prompt history in agent TUIs — scrolling
      must never turn into arrow keys. Moot for lab-spawned sessions
      (``alternate-screen off`` below) but kept out defensively for
      adopted ones.

    Wheel-down needs no root binding: tmux forwards unbound mouse keys to
    panes that enabled mouse reporting, copy-mode's own table handles it
    while scrolled back, and it's silently dropped for plain shells.

    The binding is server-global (tmux offers no per-session root-table
    scope). Idempotent; safe to re-run on every session spawn.
    """
    if not _tmux_available():
        return
    env = _tmux_child_env()
    # Per-session mouse intercept.
    subprocess.run(
        ["tmux", "set-option", "-t", session_name, "mouse", "on"],
        capture_output=True, text=True, env=env,
    )
    # Keep altscreen-app output (git log's pager, less, man, etc.) in the
    # main buffer so it lands in scrollback after the app exits. Default
    # `alternate-screen on` wipes the pane back to pre-command state on
    # exit, which reads as "the terminal cleared my output."
    subprocess.run(
        ["tmux", "set-option", "-t", session_name, "alternate-screen", "off"],
        capture_output=True, text=True, env=env,
    )
    subprocess.run(
        ["tmux", "bind-key", "-T", "root", "WheelUpPane",
         "if-shell", "-F", "#{||:#{pane_in_mode},#{mouse_any_flag}}",
         "send-keys -M", "copy-mode -e"],
        capture_output=True, text=True, env=env,
    )
    # Wheel-down: let tmux's built-in copy-mode-vi/emacs table handle it.
    # Reset any prior root-table override so we don't inherit garbage from
    # an earlier run of this process.
    subprocess.run(
        ["tmux", "unbind-key", "-T", "root", "WheelDownPane"],
        capture_output=True, text=True, env=env,
    )


# ─── naming ─────────────────────────────────────────────────────────────────

# tmux session names disallow `.` and `:`; we also keep them URL-safe.
_NAME_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


def _sanitize(s: str) -> str:
    return _NAME_SAFE.sub("-", s).strip("-") or "x"


def _default_logical_name(kind: str) -> str:
    return "claude" if kind == "claude" else "bash"


def _agent_argv(agent: str) -> list[str]:
    """Launch argv for a non-Claude agent (codex / copilot).

    Resume/session bookkeeping is Claude-only for now, so these spawn a fresh
    session. Raises HTTPException if the CLI is missing so the UI can surface a
    clean "not installed" message instead of an opaque tmux failure.
    """
    if agent == "codex":
        if not shutil.which("codex"):
            raise HTTPException(
                status_code=400,
                detail="codex CLI not found on PATH — install it or pick a different agent in Settings.",
            )
        return ["codex"]
    if agent == "copilot":
        if shutil.which("copilot"):
            return ["copilot"]
        raise HTTPException(
            status_code=400,
            detail="GitHub Copilot CLI (`copilot`) not found on PATH — install it or pick a different agent in Settings.",
        )
    raise HTTPException(status_code=400, detail=f"unsupported agent: {agent}")


_HASH_HEX_RE = re.compile(r"^[0-9a-f]{6}$")


def _session_hash(workspace: str, project_sane: str, tab_sane: str) -> str:
    """Deterministic 6-hex marker appended to current-scheme session names.

    Hashes the SANITIZED project id + tab (not the raw pre-sanitize
    strings), since generation and parsing must agree byte-for-byte and the
    parser only ever sees the sanitized forms once split out of a live tmux
    name. The fixed ``neurona-`` literal is folded into the input too, so
    the digest space stays scoped to this specific naming scheme.
    """
    payload = f"{_SESSION_PREFIX}{workspace}/{project_sane}/{tab_sane}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:6]


def _tmux_name_for(project_id: str | None, logical_name: str,
                   root: Path | None = None) -> str:
    """Build the tmux session name.

    - ``LAB_TMUX_PREFIX`` set (tests / opt-out): ``<prefix><project>-<tab>``,
      exactly the pre-nomenclature format.
    - Otherwise: ``neurona-<workspace>-<project>-<tab>-<hash6>``, where
      ``<workspace>`` is the registry-stable workspace id (see
      ``_resolve_workspace_label``) and ``<hash6>`` is deterministic — the
      same workspace+project+tab always produces the same name.

    When no project is given (rare — standalone terminals) we fall back to a
    UUID so the name is globally unique.
    """
    env_prefix = os.environ.get("LAB_TMUX_PREFIX")
    if not project_id:
        if env_prefix:
            return env_prefix + uuid.uuid4().hex[:8]
        return _new_scheme_prefix(root) + uuid.uuid4().hex[:8]
    project_sane = _sanitize(project_id)
    tab_sane = _sanitize(logical_name)
    if env_prefix:
        return env_prefix + project_sane + "-" + tab_sane
    workspace = _resolve_workspace_label(root)
    digest = _session_hash(workspace, project_sane, tab_sane)
    return f"{_SESSION_PREFIX}{workspace}-{project_sane}-{tab_sane}-{digest}"


def _attach_command(name: str) -> str:
    """Exact command to attach to this tmux session from any terminal."""
    return f"tmux attach -t '{name}'"


def _pick_unique_logical_name(preferred: str, taken_logical_names: set[str]) -> str:
    """Return a logical_name that doesn't collide with a DIFFERENT live tab.

    ``taken_logical_names`` is the set of logical (tab) names already live
    for this project. Callers only reach this when they've already
    established that the preferred name belongs to a live tab and the
    caller explicitly wants a brand-new one (``start_fresh``) — this
    function's only job is picking the next free "-N" suffix, never
    renaming a tab away from a name it's entitled to reuse (that would be
    the "creates a new session for some reason" bug: silently uniquifying
    a resume/attach because the caller mis-detected a collision).
    """
    candidate = _sanitize(preferred)
    if candidate not in taken_logical_names:
        return candidate
    for n in range(2, 1000):
        alt = f"{candidate}-{n}"
        if alt not in taken_logical_names:
            return alt
    # Pathological fallback.
    return f"{candidate}-{uuid.uuid4().hex[:6]}"


# ─── API models ─────────────────────────────────────────────────────────────


class NewSession(BaseModel):
    project_id: str | None = None
    cwd: str | None = None
    # "claude" spawns `claude` with --permission-mode auto + --session-id
    # (generated UUID on first launch, saved to project.json, reused via
    # --resume on subsequent creates of the same name).
    # "terminal" spawns the user's $SHELL (or bash).
    kind: str = "claude"
    # Which agent CLI to launch for kind=="claude". None → resolve from the
    # project override / global default in .agents/config.json. One of
    # VALID_AGENTS (claude | codex | copilot).
    agent: str | None = None
    # Optional explicit logical name. Defaults: agent name / "bash".
    name: str | None = None
    # Only meaningful when kind == "claude". None → the workspace's
    # per-agent autopilot setting decides (claude defaults on; see
    # lab.settings.DEFAULTS["autopilot"]). Explicit true/false wins.
    auto: bool | None = None
    # When True, ignore any saved claude_session_id and start a brand-new
    # conversation (new UUID). Used by the manual "+ New Claude" picker.
    start_fresh: bool = False


# ─── endpoints ──────────────────────────────────────────────────────────────


# NOTE: every endpoint below that shells out to tmux (or touches the
# filesystem) is deliberately a *sync* ``def`` — FastAPI runs those in its
# thread pool. As ``async def`` they ran their blocking ``subprocess.run``
# calls ON the event loop, stalling every live terminal WebSocket for the
# duration of each tmux spawn (a few ms, several times per second under the
# UI's polling) — visible as typing-echo jitter.

def _sessions_for_root(root: Path, project_id: str | None) -> list[dict]:
    """One workspace's live session rows (optionally scoped to
    ``project_id``), with the runtime registry reconciled against the live
    tmux listing. Factored out of ``list_sessions`` so the "every
    workspace" path can reuse it per workspace without duplicating the
    tmux-list + meta-sync + row-shaping logic."""
    prefixes = _tmux_discovery_prefixes(root)
    listing = _tmux_list(prefixes)
    meta = _sync_meta(root, listing)
    live = {s["name"]: s for s in (listing or [])}

    rows: list[dict] = []
    saved_by_logical = _project_session_by_name(root, project_id) if project_id else {}
    for name, info in live.items():
        row = {**info, **meta.get(name, {}), "name": name, "attach_command": _attach_command(name)}
        if project_id and row.get("project_id") != project_id:
            continue
        logical = row.get("logical_name")
        saved = saved_by_logical.get(logical) if isinstance(logical, str) else None
        if saved:
            for key in ("label", "summary"):
                if saved.get(key):
                    row[key] = saved[key]
        if not row.get("summary"):
            inferred = _infer_session_summary(name)
            if inferred:
                row["summary"] = inferred
        rows.append(row)
    return rows


@router.get("/api/term/sessions")
def list_sessions(request: Request, project_id: str | None = None) -> list[dict]:
    """List live tmux sessions for a project (or all projects/workspaces).

    Scoped to ``project_id``: only the ACTIVE workspace's sessions — this
    is what the open project's tab strip means ("this project, in the
    workspace I'm looking at"), unchanged from before multi-workspace
    support. Unscoped: every REGISTERED workspace's sessions, each tagged
    with ``workspace`` (registry id) — this is what the cross-workspace
    terminals dashboard needs. A workspace whose path is missing/stalled
    is skipped for that cycle (fsguard 503, or an OSError from an
    unmounted/unreadable volume) rather than failing the whole request.

    Only returns sessions that are currently alive in tmux. Saved-but-dead
    sessions (stored in project.json) are surfaced separately via
    ``/api/term/sessions/saved``.
    """
    active_root: Path = request.app.state.index_cache.root

    if project_id:
        rows = _sessions_for_root(active_root, project_id)
        # Order preference: if the project has a saved ``sessions[]`` array
        # (in project.json), use that order as the source of truth — this
        # is what powers the "drag pills to reorder" UX. Sessions with no
        # saved entry (edge case: spawned out-of-band) get appended in
        # tmux-creation order.
        saved = _get_project_sessions(active_root, project_id)
        order: dict[str, int] = {
            s["name"]: i for i, s in enumerate(saved)
            if isinstance(s, dict) and "name" in s
        }
        def _key(row: dict) -> tuple[int, int]:
            logical = row.get("logical_name") or ""
            if logical in order:
                return (0, order[logical])
            # Unsaved rows sort after saved ones, newest-first within them.
            return (1, -row.get("created", 0))
        rows.sort(key=_key)
        return rows

    rows = []
    for ws in _known_workspaces(active_root):
        try:
            ws_rows = fsguard.guarded(ws["path"], _sessions_for_root, ws["path"], None)
        except HTTPException as exc:
            if exc.status_code != 503:
                raise
            continue
        except OSError as exc:
            # Same degradation as the fsguard 503 above: a workspace whose
            # volume is missing or unreadable is skipped this cycle instead
            # of failing the listing for every other workspace.
            _warn_root_unavailable_once(ws["path"], "session listing", exc)
            continue
        for r in ws_rows:
            r["workspace"] = ws["id"]
        rows.extend(ws_rows)
    rows.sort(key=lambda r: r.get("created", 0), reverse=True)
    return rows


class SessionOrder(BaseModel):
    project_id: str
    order: list[str]  # logical_names in the desired order


class SessionMetadata(BaseModel):
    project_id: str
    # Saved logical session name, not the tmux name. Display labels must not
    # rename tmux sessions because that would break attach/resume semantics.
    name: str
    label: str | None = None
    summary: str | None = None


class PastedImage(BaseModel):
    project_id: str
    data: str
    mime: str | None = None
    name: str | None = None
    session_name: str | None = None


_PASTE_IMAGE_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
}
_MAX_PASTE_IMAGE_BYTES = 25 * 1024 * 1024


def _decode_pasted_image(body: PastedImage) -> tuple[str, bytes]:
    raw = body.data or ""
    mime = (body.mime or "").lower().strip()
    data = raw
    if raw.startswith("data:"):
        header, sep, payload = raw.partition(",")
        if not sep:
            raise HTTPException(status_code=400, detail="invalid data URL")
        data = payload
        # data:image/png;base64,...
        meta = header[5:]
        declared = meta.split(";", 1)[0].lower().strip()
        if declared:
            mime = declared
    if mime not in _PASTE_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"unsupported image type: {mime or 'unknown'}")
    try:
        blob = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="invalid base64 image data")
    if not blob:
        raise HTTPException(status_code=400, detail="empty image")
    if len(blob) > _MAX_PASTE_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="image is too large")
    return mime, blob


@router.post("/api/term/sessions/order")
def set_session_order(body: SessionOrder, request: Request) -> dict:
    """Reorder the project's saved sessions[] so /api/term/sessions reflects
    the new pill order. Any saved session not listed is appended in its
    original relative order."""
    root: Path = request.app.state.index_cache.root
    data = _load_project(root, body.project_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"project {body.project_id!r} not found")
    current = data.get("sessions") if isinstance(data.get("sessions"), list) else []
    by_name = {s["name"]: s for s in current if isinstance(s, dict) and "name" in s}
    new_list: list[dict] = []
    seen: set[str] = set()
    for name in body.order:
        if name in by_name and name not in seen:
            new_list.append(by_name[name])
            seen.add(name)
    # Append anything not mentioned, preserving relative order.
    for s in current:
        n = s.get("name") if isinstance(s, dict) else None
        if n and n not in seen:
            new_list.append(s)
            seen.add(n)
    data["sessions"] = new_list
    _save_project(root, body.project_id, data)
    _invalidate_project_term_caches()
    return {"ok": True, "order": [s.get("name") for s in new_list]}


@router.patch("/api/term/sessions/metadata")
def update_session_metadata(body: SessionMetadata, request: Request) -> dict:
    """Persist a user-facing label/summary for a saved logical session."""
    root: Path = request.app.state.index_cache.root
    data = _load_project(root, body.project_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"project {body.project_id!r} not found")
    sessions = data.get("sessions") if isinstance(data.get("sessions"), list) else []
    entry = None
    for s in sessions:
        if isinstance(s, dict) and s.get("name") == body.name:
            entry = s
            break
    if entry is None:
        raise HTTPException(status_code=404, detail=f"session {body.name!r} not found")

    fields = getattr(body, "model_fields_set", None)
    if fields is None:
        fields = getattr(body, "__fields_set__", set())
    if "label" in fields:
        label = _clean_optional_text(body.label, max_len=80)
        if label:
            entry["label"] = label
        else:
            entry.pop("label", None)
    if "summary" in fields:
        summary = _clean_optional_text(body.summary, max_len=320)
        if summary:
            entry["summary"] = summary
        else:
            entry.pop("summary", None)

    data["sessions"] = sessions
    _save_project(root, body.project_id, data)

    tmux_name = _tmux_name_for(body.project_id, body.name, root)
    meta = _load_meta(root)
    if tmux_name in meta:
        if "label" in fields:
            if entry.get("label"):
                meta[tmux_name]["label"] = entry["label"]
            else:
                meta[tmux_name].pop("label", None)
        if "summary" in fields:
            if entry.get("summary"):
                meta[tmux_name]["summary"] = entry["summary"]
            else:
                meta[tmux_name].pop("summary", None)
        _save_meta(root, meta)

    log.info(
        "terminal session metadata updated",
        extra={
            "event_type": "term.session.metadata",
            "action": body.project_id,
            "target": body.name,
        },
    )
    return {"ok": True, "session": entry}


@router.post("/api/term/paste-image")
def paste_image(body: PastedImage, request: Request) -> dict:
    """Save a pasted clipboard image under the terminal cwd and return a path.

    The browser then inserts that relative path into the active PTY. Keeping
    image handling as an explicit paste-time HTTP call avoids touching the
    latency-critical websocket byte path used by normal typing and text paste.
    """
    root: Path = request.app.state.index_cache.root
    if not body.project_id:
        raise HTTPException(status_code=400, detail="project_id is required")
    cwd = _project_cwd(root, body.project_id)
    if not cwd.is_dir():
        raise HTTPException(status_code=400, detail=f"cwd not a directory: {cwd}")
    mime, blob = _decode_pasted_image(body)
    ext = _PASTE_IMAGE_TYPES[mime]
    target_dir = cwd / ".lab" / "terminal-pastes"
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"{stamp}-{uuid.uuid4().hex[:8]}.{ext}"
    target = target_dir / filename
    target.write_bytes(blob)
    rel = Path(".lab") / "terminal-pastes" / filename
    log.info(
        "terminal pasted image saved",
        extra={
            "event_type": "term.paste_image",
            "action": body.project_id,
            "target": str(rel),
        },
    )
    return {
        "ok": True,
        "path": rel.as_posix(),
        "absolute_path": str(target),
        "mime": mime,
        "bytes": len(blob),
    }


# ─── Status (working vs idle) ───────────────────────────────────────────────
#
# Claude Code's TUI prints an "esc to interrupt" hint on the working line
# while a request is in flight. Its absence means the session is at its
# prompt — either freshly idle or awaiting a [y/n]-style approval. We match
# that string (and a couple of related hints) to classify each session.
#
# Results are cached briefly so the 3s-poll from the browser + the
# per-request cost of spawning `tmux capture-pane` stay modest.

# Multiple signals that Claude is mid-turn. Any one of them is enough;
# we match against the last ~40 lines of tmux capture-pane output.
#
# Why not just "esc to interrupt"? The hint isn't always visible — on
# narrow terminals it can wrap off-screen, and during subagent work
# (Task tool running a research loop) Claude sometimes only paints the
# subagent status line with its timer while the interrupt hint sits on
# a line tmux may drop from a compact capture.
_WORKING_HINTS_RE = re.compile(
    r"("
    # Explicit interrupt hints
    r"esc to interrupt"
    r"|ctrl[- ]?c to interrupt"
    r"|ctrl[- ]?b to run in bg"
    # Working indicator with elapsed-time timer: `…(1m 36s`, `…(36s`
    # (unicode ellipsis or three ASCII dots). The space between `…` and
    # the paren is optional.
    r"|(?:…|\.\.\.)\s*\(\d+[smh]"
    # "thought for 27s" — present on the working indicator line even if
    # the interrupt hint wrapped away
    r"|thought for \d+\s*[smh]"
    # Token counters next to the timer: "↑ 138 tokens" / "↓ 1.1k tokens"
    # — only printed while a turn is active
    r"|[↑↓]\s*\d+(?:\.\d+)?\s*[kKmM]?\s*tokens"
    r")",
    re.IGNORECASE,
)

_STATUS_CACHE: dict[str, tuple[float, str]] = {}
_STATUS_TTL_S = 8.0
_SUMMARY_CACHE: dict[str, tuple[float, str]] = {}
_SUMMARY_TTL_S = 60.0
_PROJECTS_CACHE_TTL_S = 8.0
_PROJECTS_ATTENTION_CACHE: tuple[float, list[str]] | None = None
_PROJECTS_WITH_SESSIONS_CACHE: tuple[float, list[str]] | None = None


def _invalidate_project_term_caches() -> None:
    global _PROJECTS_ATTENTION_CACHE, _PROJECTS_WITH_SESSIONS_CACHE
    _PROJECTS_ATTENTION_CACHE = None
    _PROJECTS_WITH_SESSIONS_CACHE = None


def _fresh_project_cache(cache: tuple[float, list[str]] | None) -> list[str] | None:
    if not cache:
        return None
    ts, value = cache
    if time.monotonic() - ts >= _PROJECTS_CACHE_TTL_S:
        return None
    return list(value)


def _classify_pane(name: str) -> str:
    """Return 'working' | 'idle' | 'unknown' by scanning the pane's last lines."""
    now = time.monotonic()
    cached = _STATUS_CACHE.get(name)
    if cached and (now - cached[0]) < _STATUS_TTL_S:
        return cached[1]
    if not _tmux_available():
        return "unknown"
    proc = subprocess.run(
        ["tmux", "capture-pane", "-pt", name, "-S", "-40"],
        capture_output=True, text=True, env=_tmux_child_env(),
    )
    if proc.returncode != 0:
        status = "unknown"
    elif _WORKING_HINTS_RE.search(proc.stdout):
        status = "working"
    else:
        status = "idle"
    _STATUS_CACHE[name] = (now, status)
    return status


@router.get("/api/term/sessions/status")
def session_status(request: Request, project_id: str | None = None) -> list[dict]:
    """Per-session live status. Claude sessions → ``working`` | ``idle``;
    terminal sessions → ``n/a`` (they never "wait" on the user in a way we
    can distinguish from interactive use).
    """
    root: Path = request.app.state.index_cache.root
    prefixes = _tmux_discovery_prefixes(root)
    live = _tmux_list(prefixes)
    meta = _sync_meta(root, live)
    out: list[dict] = []
    for s in live or []:
        info = meta.get(s["name"]) or {}
        pid = info.get("project_id")
        if project_id and pid != project_id:
            continue
        kind = (info.get("kind") or "claude").lower()
        agent = (info.get("agent") or "claude").lower()
        # Only the Claude agent has a UI we can classify; codex/copilot/terminal → n/a.
        status = _classify_pane(s["name"]) if (kind == "claude" and agent == "claude") else "n/a"
        out.append({
            "name": s["name"],
            "logical_name": info.get("logical_name"),
            "project_id": pid,
            "kind": kind,
            "agent": info.get("agent"),
            "status": status,
        })
    return out


@router.get("/api/term/projects-attention")
def projects_attention(request: Request) -> list[str]:
    """Projects that need the user's attention.

    Definition: the project has at least one live Claude session AND none
    of its Claude sessions is currently ``working``. This is the
    "everything's waiting for you" signal the UI uses to highlight the
    project tab.

    Held (snoozed) projects are excluded — if the user intentionally
    parked the project, its idle Claude session is *expected* and
    shouldn't pulse. Once the hold expires, the project rejoins the
    attention set normally.
    """
    global _PROJECTS_ATTENTION_CACHE
    cached = _fresh_project_cache(_PROJECTS_ATTENTION_CACHE)
    if cached is not None:
        return cached

    root: Path = request.app.state.index_cache.root
    prefixes = _tmux_discovery_prefixes(root)
    listing = _tmux_list(prefixes)
    meta = _sync_meta(root, listing)
    live_names = {s["name"] for s in (listing or [])}
    by_project: dict[str, list[str]] = {}
    for name, info in meta.items():
        if name not in live_names:
            continue
        # Only Claude-agent sessions drive the "waiting for you" signal — we
        # can't classify codex/copilot panes, so they shouldn't pulse the tab.
        if (info.get("kind") or "claude").lower() != "claude":
            continue
        if (info.get("agent") or "claude").lower() != "claude":
            continue
        pid = info.get("project_id")
        if not pid:
            continue
        by_project.setdefault(pid, []).append(name)

    # Read held project ids from the index cache. A hold "suppresses"
    # attention while `until` is still in the future; once it passes, the
    # project falls back into the normal attention flow (the UI also gets
    # a "ready-for-review" signal from the Snoozed tab).
    held_ids: set[str] = set()
    try:
        now_iso = datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds")
        idx = request.app.state.index_cache.get()
        for p in idx.get("projects", []):
            h = p.get("hold")
            if not h or not h.get("until"):
                continue
            if str(h["until"]) > now_iso:
                held_ids.add(p["id"])
    except Exception:
        pass

    attention: list[str] = []
    for pid, names in by_project.items():
        if pid in held_ids:
            continue
        statuses = [_classify_pane(n) for n in names]
        # Attention: at least one claude, none of them working.
        if statuses and not any(s == "working" for s in statuses):
            attention.append(pid)
    _PROJECTS_ATTENTION_CACHE = (time.monotonic(), list(attention))
    return attention


@router.get("/api/term/sessions/saved")
def list_saved_sessions(request: Request, project_id: str) -> list[dict]:
    """List sessions saved in the project's project.json (may or may not be live)."""
    root: Path = request.app.state.index_cache.root
    return _get_project_sessions(root, project_id)


@router.get("/api/term/projects-with-sessions")
def projects_with_sessions(request: Request) -> list[str]:
    """Project IDs that currently have at least one live tmux session.

    Drives the topbar tab strip (tabs == projects with active sessions).
    Code Search per-repo pseudo-projects (``__cs_<repo>__``) are
    filtered out — they aren't standalone tabs, they're driven by the
    single ``🔍 code-search`` pseudo-tab and the in-tab repo picker.
    """
    global _PROJECTS_WITH_SESSIONS_CACHE
    cached = _fresh_project_cache(_PROJECTS_WITH_SESSIONS_CACHE)
    if cached is not None:
        return cached

    root: Path = request.app.state.index_cache.root
    prefixes = _tmux_discovery_prefixes(root)
    listing = _tmux_list(prefixes)
    meta = _sync_meta(root, listing)
    live_names = {s["name"] for s in (listing or [])}
    ids: list[str] = []
    for name in live_names:
        info = meta.get(name) or {}
        pid = info.get("project_id")
        if not pid or pid in ids:
            continue
        if _cs_repo_name(pid):
            continue
        ids.append(pid)
    _PROJECTS_WITH_SESSIONS_CACHE = (time.monotonic(), list(ids))
    return ids


@router.post("/api/term/sessions")
def create_session(body: NewSession, request: Request) -> dict:
    """Create (or re-attach / resume) a named session.

    Behavior:
    - If a live tmux session with the computed name exists: return it as-is.
    - Else: spawn a new tmux session. For kind == "claude", use the saved
      claude_session_id (via ``--resume``) if project.json has one and
      ``start_fresh`` is False; otherwise generate a new UUID and record it
      in project.json via ``--session-id``.
    """
    if not _tmux_available():
        raise HTTPException(status_code=500, detail="tmux not installed. Run: brew install tmux")

    kind = (body.kind or "claude").lower()
    if kind not in ("claude", "terminal"):
        raise HTTPException(status_code=400, detail=f"unknown kind: {kind}")

    root: Path = request.app.state.index_cache.root

    # For agent sessions (kind=="claude"), resolve which CLI to launch:
    # explicit body.agent → project override → global default.
    agent: str | None = None
    if kind == "claude":
        agent = (body.agent or lab_settings.resolve_agent(root, body.project_id)).lower()
        if agent not in lab_settings.VALID_AGENTS:
            raise HTTPException(status_code=400, detail=f"unknown agent: {agent!r}")

    # Resolve cwd.
    if body.cwd:
        cwd = Path(body.cwd).resolve()
    elif body.project_id:
        cwd = _project_cwd(root, body.project_id)
    else:
        cwd = root.resolve()
    if not cwd.is_dir():
        raise HTTPException(status_code=400, detail=f"cwd not a directory: {cwd}")

    # Discover every live session that could belong to this workspace under
    # ANY generation of the naming scheme (current + the two pre-nomenclature
    # ones), and reconcile the runtime registry against it. This is what
    # lets us recognize "this project's codex tab is already live" even when
    # the live session's actual tmux name uses an older scheme than the one
    # `_tmux_name_for` would compute today — that mismatch used to spawn a
    # same-tab duplicate on every reopen after a naming-scheme or
    # workspace-path change instead of attaching to what was already there.
    listing = _tmux_list(_tmux_discovery_prefixes(root))
    meta = _sync_meta(root, listing)
    live_by_name = {s["name"]: s for s in (listing or [])}

    # Default the logical name to the agent (claude/codex/copilot) so different
    # agents get distinct tmux sessions/tabs within the same project.
    preferred = body.name or (agent if kind == "claude" else _default_logical_name(kind))
    preferred_sane = _sanitize(preferred)

    # Live logical (tab) names already running for this project, and — if
    # one of them IS the tab we're about to (re)open — its live tmux name +
    # runtime entry, regardless of which naming scheme produced that name.
    live_logical_names: set[str] = set()
    existing_for_tab: tuple[str, dict] | None = None
    for name, info in meta.items():
        if name not in live_by_name or info.get("project_id") != body.project_id:
            continue
        logical_live = info.get("logical_name")
        if not logical_live:
            continue
        live_logical_names.add(logical_live)
        if logical_live == preferred_sane:
            existing_for_tab = (name, info)

    # Default POST is idempotent: if this tab already has a live session —
    # under ANY naming scheme — attach to it instead of spawning a
    # duplicate. Only `start_fresh` forces a brand-new session (with a "-N"
    # suffix so it coexists with the original).
    if existing_for_tab and not body.start_fresh:
        name, info = existing_for_tab
        row = {"name": name, **info, "already_running": True,
               "attach_command": _attach_command(name)}
        if body.project_id:
            saved = _project_session_by_name(root, body.project_id).get(
                info.get("logical_name") or preferred_sane
            )
            if saved:
                for key in ("label", "summary"):
                    if saved.get(key):
                        row[key] = saved[key]
        log.info(
            "terminal session already running",
            extra={
                "event_type": "term.session.already_running",
                "action": body.project_id,
                "target": name,
            },
        )
        return row

    logical = preferred_sane
    if existing_for_tab and body.start_fresh:
        # The preferred tab IS live (that's `existing_for_tab`) but the
        # caller explicitly asked for a fresh one — bump to the next free
        # logical name. A name that's merely sanitized-equal to a DIFFERENT
        # live tab never reaches this branch — see the loop above, which
        # only sets `existing_for_tab` for an exact logical-name match — so
        # this never renames a tab away from a name it's entitled to reuse.
        logical = _pick_unique_logical_name(preferred_sane, live_logical_names)
    tmux_name = _tmux_name_for(body.project_id, logical, root)

    # Final authoritative guard: a tmux session with this exact computed
    # name already exists (race with a concurrent create, a leftover from a
    # prior crash, or the deterministic hash landing on a name reused from
    # an earlier run) — adopt it rather than erroring or trying to spawn a
    # duplicate (which tmux itself would refuse anyway).
    if _tmux_has_session(tmux_name):
        entry = meta.get(tmux_name) or _reconstruct_meta_entry(root, tmux_name) or {
            "project_id": body.project_id,
            "logical_name": logical,
            "kind": kind,
            "agent": agent,
            "cwd": str(cwd),
            "created_at": int(time.time()),
        }
        meta[tmux_name] = entry
        _save_meta(root, meta)
        _invalidate_project_term_caches()
        log.info(
            "terminal session adopted (already live under computed name)",
            extra={
                "event_type": "term.session.adopted",
                "action": body.project_id,
                "target": tmux_name,
            },
        )
        return {"name": tmux_name, **entry, "already_running": True,
                "attach_command": _attach_command(tmux_name)}

    # Build the command line.
    auto_applied = False
    resumed_from = None
    claude_session_id = None
    if kind == "claude" and agent == "claude":
        parts = ["claude"]
        wants_auto = (
            body.auto
            if body.auto is not None
            else lab_settings.resolve_autopilot(root, "claude")
        )
        if wants_auto:
            parts.extend(lab_settings.AUTOPILOT_FLAGS["claude"])
            auto_applied = True
        # Look up a saved claude_session_id for this project+name.
        existing_id = None
        if body.project_id and not body.start_fresh:
            for s in _get_project_sessions(root, body.project_id):
                if isinstance(s, dict) and s.get("name") == logical and s.get("kind") == "claude":
                    existing_id = s.get("claude_session_id")
                    break
        if existing_id:
            parts.extend(["--resume", existing_id])
            claude_session_id = existing_id
            resumed_from = existing_id
        else:
            claude_session_id = str(uuid.uuid4())
            parts.extend(["--session-id", claude_session_id])
        cmd_argv = parts
    elif kind == "claude":
        # codex / copilot — fresh session (resume is Claude-only for now).
        cmd_argv = _agent_argv(agent)
        if lab_settings.resolve_autopilot(root, agent):
            cmd_argv = cmd_argv + list(lab_settings.AUTOPILOT_FLAGS.get(agent, ()))
            auto_applied = True
    else:
        # kind == "terminal"
        shell = os.environ.get("SHELL") or shutil.which("bash") or "/bin/sh"
        cmd_argv = [shell, "-l"]

    # Spawn tmux. We pass argv via shell so tmux can parse it; simpler for
    # claude's flag expansion and matches what users see in `tmux ls`.
    cmd_str = " ".join(_shell_quote(a) for a in cmd_argv)
    proc = subprocess.run(
        ["tmux", "new-session", "-d", "-s", tmux_name, "-c", str(cwd), cmd_str],
        capture_output=True, text=True, env=_tmux_child_env(),
    )
    if proc.returncode != 0:
        log.error(
            "tmux new-session failed for %s: %s",
            tmux_name,
            (proc.stderr or proc.stdout or "").strip()[:500],
            extra={
                "event_type": "term.session.create_failed",
                "action": body.project_id,
                "target": tmux_name,
            },
        )
        raise HTTPException(status_code=500, detail=(proc.stderr or proc.stdout).strip() or "tmux failed")

    # Mouse wheel → tmux copy-mode scrollback (no send-keys fallback).
    _configure_tmux_wheel_scrolling(tmux_name)

    # Record runtime metadata.
    meta = _load_meta(root)
    meta[tmux_name] = {
        "project_id": body.project_id,
        "logical_name": logical,
        "kind": kind,
        "agent": agent,
        "cwd": str(cwd),
        "cmd": cmd_str,
        "auto": auto_applied,
        "claude_session_id": claude_session_id,
        "resumed_from": resumed_from,
        "created_at": int(time.time()),
    }
    _save_meta(root, meta)
    _invalidate_project_term_caches()

    # Record durable entry (claude session id survives restart).
    if body.project_id:
        entry: dict = {"name": logical, "kind": kind}
        if agent:
            entry["agent"] = agent
        if claude_session_id:
            entry["claude_session_id"] = claude_session_id
        _upsert_project_session(root, body.project_id, entry)
        saved = _project_session_by_name(root, body.project_id).get(logical)
        if saved:
            for key in ("label", "summary"):
                if saved.get(key):
                    meta[tmux_name][key] = saved[key]
            if saved.get("label") or saved.get("summary"):
                _save_meta(root, meta)
        _invalidate_project_term_caches()

    log.info(
        "terminal session spawned",
        extra={
            "event_type": "term.session.spawn",
            "action": body.project_id,
            "target": tmux_name,
        },
    )
    return {"name": tmux_name, **meta[tmux_name], "attach_command": _attach_command(tmux_name)}


@router.delete("/api/term/sessions/{name}")
def kill_session(name: str, request: Request, purge: bool = False) -> dict:
    """Kill a live session. The saved entry in project.json stays unless
    ``purge``.

    Accepts a session named for ANY registered workspace, not just the
    active one (the cross-workspace terminals dashboard needs to kill
    sessions it lists from other workspaces) — the name is resolved back
    to its owning workspace root so the runtime registry / servers
    desired-state hook below operate on the right workspace's files.
    """
    active_root: Path = request.app.state.index_cache.root
    workspaces = _known_workspaces(active_root)
    prefixes = _tmux_discovery_prefixes_all(workspaces)
    if not any(name.startswith(p) for p in prefixes):
        raise HTTPException(status_code=400, detail="invalid session name")

    root = _resolve_session_workspace_root(name, active_root, workspaces)
    meta = _load_meta(root)
    info = meta.get(name) or {}
    project_id = info.get("project_id")
    logical_name = info.get("logical_name")

    if _tmux_available():
        subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True, text=True,
                       env=_tmux_child_env())
    meta.pop(name, None)
    _save_meta(root, meta)
    _invalidate_project_term_caches()

    if logical_name == "server" and project_id:
        # A managed dev-server tab was killed through the generic terminal
        # kill flow (not /api/servers/{id}/stop) — mark it desired=stopped so
        # the servers supervisor doesn't resurrect it on its next tick.
        # Imported lazily to avoid a module import cycle (servers.py imports
        # term at module scope; term.py must not import servers at module
        # scope).
        from core.routes import servers as servers_mod
        try:
            servers_mod.set_desired(root, project_id, "stopped")
        except Exception:  # pragma: no cover — best effort, never blocks the kill
            log.warning("failed to mark server desired=stopped for %s", project_id, exc_info=True)

    if purge and project_id and logical_name:
        data = _load_project(root, project_id)
        if data and isinstance(data.get("sessions"), list):
            data["sessions"] = [s for s in data["sessions"]
                                if not (isinstance(s, dict) and s.get("name") == logical_name)]
            _save_project(root, project_id, data)
            _invalidate_project_term_caches()

    log.info(
        "terminal session killed",
        extra={
            "event_type": "term.session.kill",
            "action": project_id,
            "target": name,
        },
    )
    return {"ok": True, "purged": purge}


@router.delete("/api/term/sessions/project/{project_id}")
def kill_project_sessions(
    project_id: str, request: Request, purge: bool = False, workspace: str | None = None,
) -> dict:
    """Kill EVERY live session belonging to ``project_id``. Powers the tab X.

    Scoped to the active workspace by default — unchanged behavior for the
    project tab strip's "X" button. Pass ``?workspace=<id>`` to target a
    different registered workspace instead (the cross-workspace terminals
    dashboard needs this since the same project id can exist in more than
    one workspace).
    """
    active_root: Path = request.app.state.index_cache.root
    if workspace is not None:
        root = None
        for ws in _known_workspaces(active_root):
            if ws["id"] == workspace:
                root = ws["path"]
                break
        if root is None:
            raise HTTPException(status_code=404, detail=f"workspace {workspace!r} not found")
    else:
        root = active_root

    prefixes = _tmux_discovery_prefixes(root)
    meta = _load_meta(root)
    killed: list[str] = []
    killed_server = False
    for name in list(meta.keys()):
        info = meta.get(name) or {}
        if info.get("project_id") != project_id:
            continue
        if not any(name.startswith(p) for p in prefixes):
            continue
        if _tmux_available():
            subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True, text=True,
                           env=_tmux_child_env())
        meta.pop(name, None)
        killed.append(name)
        if info.get("logical_name") == "server":
            killed_server = True
    _save_meta(root, meta)
    _invalidate_project_term_caches()

    if killed_server:
        # See the matching comment in kill_session() above.
        from core.routes import servers as servers_mod
        try:
            servers_mod.set_desired(root, project_id, "stopped")
        except Exception:  # pragma: no cover — best effort, never blocks the kill
            log.warning("failed to mark server desired=stopped for %s", project_id, exc_info=True)

    if purge:
        data = _load_project(root, project_id)
        if data and isinstance(data.get("sessions"), list):
            data["sessions"] = []
            _save_project(root, project_id, data)
            _invalidate_project_term_caches()
    log.info(
        "terminal project sessions killed",
        extra={
            "event_type": "term.session.kill_project",
            "action": project_id,
            "target": ",".join(killed),
        },
    )
    return {"ok": True, "killed": killed, "purged": purge}


def _shell_quote(s: str) -> str:
    """Minimal POSIX shell quoting — we control inputs so we don't need shlex."""
    if not s:
        return "''"
    if re.match(r"^[A-Za-z0-9@%+=:,./_-]+$", s):
        return s
    return "'" + s.replace("'", "'\\''") + "'"


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    """Tell the PTY its window geometry. xterm.js sends this on resize."""
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except OSError:
        pass


# Tmux session names the WS endpoint is willing to look at. The creation
# side already sanitizes via `_sanitize`, but the WS path is taking its
# `name` straight from the URL — so guard against traversal / injection
# even though the only consumer today is `subprocess.run(["tmux", "-t",
# name])` (argv, not shell). Matches tmux's own charset: letters, digits,
# underscore, hyphen. Explicitly excludes `.`, `:`, `/` which tmux itself
# rejects and which would be hazardous.
_VALID_WS_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


def _clamp_dim(raw: str | None, default: int, lo: int, hi: int) -> int:
    try:
        v = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


@router.websocket("/ws/term/{name}")
async def term_ws(websocket: WebSocket, name: str) -> None:
    """Bridge a browser xterm.js to `tmux attach -t <name>` via a PTY.

    The client SHOULD pass its fitted geometry as ``?cols=N&rows=N`` so the
    PTY is born at the right size. Without it we'd attach at a default
    80x24, tmux would instantly reflow the whole session to 80x24 (full
    TUI redraw at the wrong size — mangled output, wrapped status lines),
    then reflow AGAIN when the client's first resize lands ~100-300ms
    later. The leftovers of that double redraw were visible as a corrupted
    pane on every reconnect.

    Wire protocol (text frames, JSON):
      client -> server:  {"type":"input","data":"..."}
                         {"type":"resize","cols":N,"rows":N}
                         {"type":"detach"}
      server -> client:  {"type":"data","data":"..."}        # PTY bytes (utf-8)
                         {"type":"exit"}                      # tmux attach exited
    """
    root: Path = websocket.app.state.index_cache.root
    prefixes = _tmux_discovery_prefixes(root)
    loop = asyncio.get_running_loop()
    path_info = f"/ws/term/{name}"
    init_cols = _clamp_dim(websocket.query_params.get("cols"), 80, 2, 1000)
    init_rows = _clamp_dim(websocket.query_params.get("rows"), 24, 2, 500)
    await websocket.accept()
    log.info(
        "WS terminal %s connected",
        name,
        extra={"path_info": path_info, "event_type": "ws.connect"},
    )

    # Gate 1: static name validation + tmux availability. Check in an
    # executor because _tmux_has_session spawns a subprocess; don't block
    # the event loop (under load, blocking here widens the window in which
    # the client can drop before we even send the "no-session" frame).
    name_ok = bool(_VALID_WS_NAME.match(name)) and any(name.startswith(p) for p in prefixes)
    tmux_up = name_ok and _tmux_available()
    has_session = False
    if tmux_up:
        try:
            has_session = await loop.run_in_executor(
                None, _tmux_has_session, name,
            )
        except Exception:  # pragma: no cover
            has_session = False

    if not (name_ok and tmux_up and has_session):
        log.warning(
            "WS terminal %s rejected: no session",
            name,
            extra={"path_info": path_info, "event_type": "ws.reject"},
        )
        # Session doesn't exist (normal "tmux session ended" case). Send
        # the exit frame and close; both calls are race-safe — if the
        # client already dropped, we swallow it at DEBUG rather than
        # propagating a traceback through starlette.
        await _ws_send_text_safe(
            websocket,
            json.dumps({"type": "exit", "reason": "no-session"}),
        )
        await _ws_close_safe(websocket)
        return

    # Fork a PTY and exec `tmux attach` in the child. The window size is
    # set on BOTH sides of the fork (slave in the child before exec, master
    # in the parent) so tmux can never observe the transient default size —
    # it must see the client's real geometry from its very first read.
    pid, fd = pty.fork()
    if pid == 0:
        env = {**_tmux_child_env(), "TERM": "xterm-256color"}
        _set_winsize(0, init_rows, init_cols)  # stdin == PTY slave post-fork
        try:
            os.execvpe("tmux", ["tmux", "attach", "-t", name], env)
        except Exception:  # pragma: no cover
            os._exit(1)

    _set_winsize(fd, init_rows, init_cols)
    log.info(
        "WS terminal %s attached %dx%d",
        name,
        init_cols,
        init_rows,
        extra={"path_info": path_info, "event_type": "ws.attach"},
    )

    # Latency-critical byte path. The PTY master fd is registered directly
    # with the event loop (kqueue/epoll) instead of round-tripping every
    # chunk through the default thread-pool executor — no thread handoff
    # between "tmux produced bytes" and "WS frame goes out". The fd is
    # non-blocking so the reader callback can drain everything available
    # and bail on EAGAIN.
    os.set_blocking(fd, False)

    _READ_SIZE = 65536
    out_q: asyncio.Queue[bytes | None] = asyncio.Queue()
    reader_registered = False

    def _on_pty_readable() -> None:
        # Runs on the event loop. Drain what's available; never block.
        while True:
            try:
                chunk = os.read(fd, _READ_SIZE)
            except BlockingIOError:
                return
            except (OSError, ValueError):
                # EIO: tmux attach exited and the slave side closed.
                chunk = b""
            if not chunk:
                try:
                    loop.remove_reader(fd)
                except (OSError, ValueError):
                    pass
                out_q.put_nowait(None)
                return
            out_q.put_nowait(chunk)
            if len(chunk) < _READ_SIZE:
                return

    try:
        loop.add_reader(fd, _on_pty_readable)
        reader_registered = True
    except (NotImplementedError, OSError):  # pragma: no cover — darwin/linux
        reader_registered = False

    async def pump_pty_to_ws() -> None:
        # Queue → WS. Frames are decoded incrementally so a multi-byte
        # UTF-8 char split across reads never renders as U+FFFD. While a
        # send is in flight, newly-arrived chunks pile up in the queue and
        # get coalesced into the next frame — burst replay (tmux attach)
        # becomes a handful of big frames instead of hundreds of small ones,
        # while a lone keystroke echo still goes out immediately.
        import codecs
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        if not reader_registered:
            # Fallback pump for loops without add_reader support.
            os.set_blocking(fd, True)
            while True:
                try:
                    data = await loop.run_in_executor(None, os.read, fd, _READ_SIZE)
                except (OSError, ValueError):
                    break
                if not data:
                    break
                ok = await _ws_send_text_safe(
                    websocket,
                    json.dumps({"type": "data", "data": decoder.decode(data)}),
                )
                if not ok:
                    break
            return
        eof = False
        while not eof:
            chunk = await out_q.get()
            if chunk is None:
                break
            parts = [chunk]
            while True:
                try:
                    nxt = out_q.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if nxt is None:
                    eof = True
                    break
                parts.append(nxt)
            text = decoder.decode(b"".join(parts))
            if not text:
                continue
            ok = await _ws_send_text_safe(
                websocket,
                json.dumps({"type": "data", "data": text}),
            )
            if not ok:
                break

    reader_task = asyncio.create_task(pump_pty_to_ws())

    async def _pty_write(data: bytes) -> bool:
        """Write to the non-blocking PTY master. Big pastes can overrun the
        kernel's PTY input buffer (~16KB on macOS); on EAGAIN we wait for
        writability instead of dropping bytes or busy-looping."""
        view = memoryview(data)
        while view.nbytes:
            try:
                n = os.write(fd, view)
                view = view[n:]
            except BlockingIOError:
                writable = asyncio.Event()
                try:
                    loop.add_writer(fd, writable.set)
                except (NotImplementedError, OSError):
                    await asyncio.sleep(0.01)
                    continue
                try:
                    await writable.wait()
                finally:
                    try:
                        loop.remove_writer(fd)
                    except (OSError, ValueError):
                        pass
            except OSError:
                return False
        return True

    try:
        while True:
            msg = await websocket.receive_text()
            try:
                ctrl = json.loads(msg)
            except (json.JSONDecodeError, ValueError):
                continue
            t = ctrl.get("type")
            if t == "input":
                data = ctrl.get("data", "")
                if isinstance(data, str):
                    if not await _pty_write(data.encode("utf-8")):
                        # PTY went away under us (tmux exited). Bail so
                        # the finally block runs cleanup.
                        break
            elif t == "resize":
                _set_winsize(fd, int(ctrl.get("rows", 24)), int(ctrl.get("cols", 80)))
            elif t == "detach":
                break
    except _WS_SEND_RACE_ERRORS:
        # Any flavor of "client is gone" — WSDisconnect,
        # ClientDisconnected, ConnectionClosed, OSError from a torn-down
        # socket. Fall through to cleanup without a traceback.
        pass
    except Exception:
        log.exception(
            "WS terminal %s failed",
            name,
            extra={"path_info": path_info, "event_type": "ws.error"},
        )
        raise
    finally:
        # Cleanup order matters: unhook the fd from the loop and stop the
        # pump first so they can't race with us on the same fd, then tear
        # down tmux attach + fd, then best-effort send "exit" and close.
        if reader_registered:
            try:
                loop.remove_reader(fd)
            except (OSError, ValueError):
                pass
        reader_task.cancel()
        try:
            await reader_task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            os.kill(pid, signal.SIGHUP)
        except ProcessLookupError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.waitpid(pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            pass
        await _ws_send_text_safe(websocket, json.dumps({"type": "exit"}))
        await _ws_close_safe(websocket)
        log.info(
            "WS terminal %s disconnected",
            name,
            extra={"path_info": path_info, "event_type": "ws.disconnect"},
        )
