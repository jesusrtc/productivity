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
- ``content/.sessions.json`` — runtime. Maps the live tmux session name
  (``lab-<project>-<logical>``) back to ``{project_id, logical_name, cwd,
  created_at}``. Re-created on session spawn, cleaned on session kill.

Killing a session (the "X on a tab" flow) removes it from tmux + the runtime
file but **keeps** the project.json entry so a later re-open can
``claude --resume <claude_session_id>`` and pick up the conversation.
"""
from __future__ import annotations

import asyncio
import fcntl
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
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from lab import settings as lab_settings


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

def _tmux_prefix() -> str:
    """Prefix for every tmux session we spawn. Env override isolates tests."""
    return os.environ.get("LAB_TMUX_PREFIX", "lab-")


# Reserved pseudo-project ids.
#  * __cerebro__ — the personal knowledge-base view (cwd = content/)
#  * __self__    — the productivity monorepo itself    (cwd = repo root)
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
    return root / "content" / ".sessions.json"


def _project_json(root: Path, project_id: str) -> Path:
    """Path of the metadata file for a project_id. Pseudo-projects store
    their sessions[] at a hidden file under content/ that shares
    project.json's shape."""
    if project_id == CEREBRO_PROJECT_ID:
        return root / "content" / ".cerebro-project.json"
    if project_id == SELF_PROJECT_ID:
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
        return root.resolve()
    if project_id == LOGS_PROJECT_ID:
        return (root / "logs").resolve()
    repo = _cs_repo_name(project_id)
    if repo:
        return (root / "repositories" / repo).resolve()
    return (root / "projects" / project_id).resolve()


# ─── runtime metadata (.sessions.json) ──────────────────────────────────────

def _load_meta(root: Path) -> dict:
    p = _sessions_file(root)
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


def _parse_tmux_name(root: Path, name: str) -> tuple[str, str] | None:
    """Split ``<prefix><project>-<logical>`` back into (project_id, logical_name).

    Project ids can themselves contain ``-`` so the split point is ambiguous;
    match against the known project ids, longest first. Returns None for
    names we can't attribute (e.g. the UUID fallback for project-less
    terminals)."""
    prefix = _tmux_prefix()
    if not name.startswith(prefix):
        return None
    rest = name[len(prefix):]
    for pid in sorted(_known_project_ids(root), key=len, reverse=True):
        sane = _sanitize(pid)
        if rest.startswith(sane + "-") and len(rest) > len(sane) + 1:
            return pid, rest[len(sane) + 1:]
    return None


def _reconstruct_meta_entry(root: Path, name: str, created: int = 0) -> dict | None:
    """Best-effort runtime entry for a live session .sessions.json has no
    record of. The durable project.json entry wins where present; otherwise
    the logical name's leading word fills the gaps ("bash" → terminal,
    "codex" → codex agent)."""
    parsed = _parse_tmux_name(root, name)
    if not parsed:
        return None
    pid, logical = parsed
    base = logical.split("-")[0]
    entry: dict = {
        "project_id": pid,
        "logical_name": logical,
        "kind": "terminal" if base in ("bash", "terminal", "term", "shell") else "claude",
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
        return meta
    live_by_name = {s["name"]: s for s in live}
    changed = False
    for n in [n for n in meta if n not in live_by_name]:
        meta.pop(n)
        changed = True
    for n, s in live_by_name.items():
        if n in meta:
            continue
        entry = _reconstruct_meta_entry(root, n, created=s.get("created", 0))
        if entry:
            meta[n] = entry
            changed = True
    if changed:
        _save_meta(root, meta)
    return meta


# ─── tmux helpers ───────────────────────────────────────────────────────────

def _tmux_available() -> bool:
    return shutil.which("tmux") is not None


def _tmux_list(prefix: str) -> list[dict] | None:
    """Return live tmux sessions whose names start with ``prefix``.

    Returns ``None`` when the listing itself FAILED — tmux binary missing,
    or ``tmux list-sessions`` errored for any reason other than "no server
    running" (which genuinely means zero sessions and maps to ``[]``).
    None means *unknown*, not *empty*: callers must never prune registry
    state on a failed listing — a single transient tmux error used to wipe
    every session's project mapping from .sessions.json (2026-06-10).
    """
    if not _tmux_available():
        return None
    proc = subprocess.run(
        ["tmux", "list-sessions", "-F",
         "#{session_name}|#{session_created}|#{session_attached}|#{session_windows}"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or "").lower()
        if "no server running" in err or "no sessions" in err:
            return []
        return None
    rows: list[dict] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        name = parts[0]
        if not name.startswith(prefix):
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
        capture_output=True, text=True,
    )
    return proc.returncode == 0


def _configure_tmux_wheel_scrolling(session_name: str) -> None:
    """Enable mouse + bind wheel-up to tmux copy-mode. No fallback.

    The previous binding used ``send-keys -M`` as a fallback for non-alt
    panes — which shoved raw mouse-escape bytes into the shell buffer, and
    bash readline parsed them as keybindings (running random commands,
    clearing the screen). Drop the fallback entirely: wheel-up ALWAYS
    enters tmux copy-mode + pages up; wheel-down is left at tmux default
    (scrolls copy-mode down; no-op otherwise — doesn't inject anything).

    The binding is server-global (tmux offers no per-session root-table
    scope). Idempotent; safe to re-run on every session spawn.
    """
    if not _tmux_available():
        return
    # Per-session mouse intercept.
    subprocess.run(
        ["tmux", "set-option", "-t", session_name, "mouse", "on"],
        capture_output=True, text=True,
    )
    # Keep altscreen-app output (git log's pager, less, man, etc.) in the
    # main buffer so it lands in scrollback after the app exits. Default
    # `alternate-screen on` wipes the pane back to pre-command state on
    # exit, which reads as "the terminal cleared my output."
    subprocess.run(
        ["tmux", "set-option", "-t", session_name, "alternate-screen", "off"],
        capture_output=True, text=True,
    )
    # Unconditionally enter copy-mode + scroll up one page on wheel-up.
    # No -M fallback so no bytes are injected into any pane's stdin.
    subprocess.run(
        ["tmux", "bind-key", "-T", "root", "WheelUpPane",
         "copy-mode", "-eu"],
        capture_output=True, text=True,
    )
    # Wheel-down: let tmux's built-in copy-mode-vi/emacs table handle it.
    # Reset any prior root-table override so we don't inherit garbage from
    # an earlier run of this process.
    subprocess.run(
        ["tmux", "unbind-key", "-T", "root", "WheelDownPane"],
        capture_output=True, text=True,
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


def _tmux_name_for(project_id: str | None, logical_name: str) -> str:
    """Build the tmux session name. Format: ``<prefix><project>-<logical>``.

    When no project is given (rare — standalone terminals) we fall back to a
    UUID so the name is globally unique.
    """
    if not project_id:
        return _tmux_prefix() + uuid.uuid4().hex[:8]
    return _tmux_prefix() + _sanitize(project_id) + "-" + _sanitize(logical_name)


def _pick_unique_logical_name(root: Path, project_id: str, preferred: str,
                              live_names: set[str]) -> str:
    """Return a logical_name that doesn't collide with a live tmux session.

    The saved-in-project.json case is allowed to collide: reusing a name is
    exactly how ``--resume`` finds its claude_session_id.
    """
    candidate = _sanitize(preferred)
    if _tmux_name_for(project_id, candidate) not in live_names:
        return candidate
    # Live collision — pick the next available "-N" suffix.
    for n in range(2, 1000):
        alt = f"{candidate}-{n}"
        if _tmux_name_for(project_id, alt) not in live_names:
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
    # Only meaningful when kind == "claude".
    auto: bool = True
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

@router.get("/api/term/sessions")
def list_sessions(request: Request, project_id: str | None = None) -> list[dict]:
    """List live tmux sessions for a project (or all projects).

    Only returns sessions that are currently alive in tmux. Saved-but-dead
    sessions (stored in project.json) are surfaced separately via
    ``/api/term/sessions/saved``.
    """
    root: Path = request.app.state.index_cache.root
    prefix = _tmux_prefix()
    listing = _tmux_list(prefix)
    meta = _sync_meta(root, listing)
    live = {s["name"]: s for s in (listing or [])}

    rows: list[dict] = []
    for name, info in live.items():
        row = {**info, **meta.get(name, {}), "name": name}
        if project_id and row.get("project_id") != project_id:
            continue
        rows.append(row)

    # Order preference: if the caller scoped to one project AND that project
    # has a saved ``sessions[]`` array (in project.json), use that order as
    # the source of truth — this is what powers the "drag pills to reorder"
    # UX. Sessions with no saved entry (edge case: spawned out-of-band) get
    # appended in tmux-creation order.
    if project_id:
        saved = _get_project_sessions(root, project_id)
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
    else:
        rows.sort(key=lambda r: r.get("created", 0), reverse=True)
    return rows


class SessionOrder(BaseModel):
    project_id: str
    order: list[str]  # logical_names in the desired order


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
        capture_output=True, text=True,
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
    prefix = _tmux_prefix()
    live = _tmux_list(prefix)
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
    prefix = _tmux_prefix()
    listing = _tmux_list(prefix)
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
    prefix = _tmux_prefix()
    listing = _tmux_list(prefix)
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

    prefix = _tmux_prefix()
    live_names = {s["name"] for s in (_tmux_list(prefix) or [])}

    # Default the logical name to the agent (claude/codex/copilot) so different
    # agents get distinct tmux sessions/tabs within the same project.
    preferred = body.name or (agent if kind == "claude" else _default_logical_name(kind))
    preferred_tmux = _tmux_name_for(body.project_id, preferred)

    # Default POST is idempotent: if the preferred name is already live, we
    # just return that session. Only `start_fresh` forces a brand-new session
    # (with a "-N" suffix so it coexists with the original).
    if preferred_tmux in live_names and not body.start_fresh:
        meta = _load_meta(root)
        return {"name": preferred_tmux, **(meta.get(preferred_tmux) or {}),
                "already_running": True}

    logical = preferred
    if preferred_tmux in live_names and body.start_fresh:
        logical = _pick_unique_logical_name(root, body.project_id or "",
                                             preferred, live_names)
    tmux_name = _tmux_name_for(body.project_id, logical)

    # Build the command line.
    auto_applied = False
    resumed_from = None
    claude_session_id = None
    if kind == "claude" and agent == "claude":
        parts = ["claude"]
        if body.auto:
            parts.extend(["--permission-mode", "auto"])
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
    else:
        # kind == "terminal"
        shell = os.environ.get("SHELL") or shutil.which("bash") or "/bin/sh"
        cmd_argv = [shell, "-l"]

    # Spawn tmux. We pass argv via shell so tmux can parse it; simpler for
    # claude's flag expansion and matches what users see in `tmux ls`.
    cmd_str = " ".join(_shell_quote(a) for a in cmd_argv)
    proc = subprocess.run(
        ["tmux", "new-session", "-d", "-s", tmux_name, "-c", str(cwd), cmd_str],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
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
        _invalidate_project_term_caches()

    return {"name": tmux_name, **meta[tmux_name]}


@router.delete("/api/term/sessions/{name}")
def kill_session(name: str, request: Request, purge: bool = False) -> dict:
    """Kill a live session. The saved entry in project.json stays unless ``purge``."""
    prefix = _tmux_prefix()
    if not name.startswith(prefix):
        raise HTTPException(status_code=400, detail="invalid session name")
    root: Path = request.app.state.index_cache.root

    meta = _load_meta(root)
    info = meta.get(name) or {}
    project_id = info.get("project_id")
    logical_name = info.get("logical_name")

    if _tmux_available():
        subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True, text=True)
    meta.pop(name, None)
    _save_meta(root, meta)
    _invalidate_project_term_caches()

    if purge and project_id and logical_name:
        data = _load_project(root, project_id)
        if data and isinstance(data.get("sessions"), list):
            data["sessions"] = [s for s in data["sessions"]
                                if not (isinstance(s, dict) and s.get("name") == logical_name)]
            _save_project(root, project_id, data)
            _invalidate_project_term_caches()

    return {"ok": True, "purged": purge}


@router.delete("/api/term/sessions/project/{project_id}")
def kill_project_sessions(project_id: str, request: Request, purge: bool = False) -> dict:
    """Kill EVERY live session belonging to ``project_id``. Powers the tab X."""
    root: Path = request.app.state.index_cache.root
    prefix = _tmux_prefix()
    meta = _load_meta(root)
    killed: list[str] = []
    for name in list(meta.keys()):
        info = meta.get(name) or {}
        if info.get("project_id") != project_id:
            continue
        if not name.startswith(prefix):
            continue
        if _tmux_available():
            subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True, text=True)
        meta.pop(name, None)
        killed.append(name)
    _save_meta(root, meta)
    _invalidate_project_term_caches()
    if purge:
        data = _load_project(root, project_id)
        if data and isinstance(data.get("sessions"), list):
            data["sessions"] = []
            _save_project(root, project_id, data)
            _invalidate_project_term_caches()
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
    prefix = _tmux_prefix()
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
    name_ok = bool(_VALID_WS_NAME.match(name)) and name.startswith(prefix)
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
        env = {**os.environ, "TERM": "xterm-256color"}
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
