"""Workspace-scoped terminals backed by tmux + a PTY bridge over WebSocket.

Shape:
  browser xterm.js  <--WS-->  FastAPI  <--PTY-->  `tmux attach -t <name>`  <-->  claude

Why tmux + PTY (and not one or the other):
- **tmux** gives persistence. Closing the browser tab leaves `claude` running;
  the user can `tmux attach -t <name>` from iTerm at any time.
- **PTY** is the transport: forking a pseudo-terminal that execs `tmux attach`
  gives us clean ANSI + resize + streaming to pump over the WebSocket.

Session identity lives in TWO places:

- ``workspaces/<id>/workspace.json`` — durable. Stores the *logical*
  session list: ``{name, kind, claude_session_id?, agent_session_id?}``. This is the source of
  truth for "which sessions does this workspace know about" and for the
  Claude session UUIDs we need to ``--resume``. Survives server restarts.
- ``.lab/state/sessions/sessions.json`` — runtime. Maps the live tmux
  session name back to ``{workspace_id, logical_name, cwd, created_at}``.
  Re-created on session spawn, cleaned on session kill.

Tmux session naming (see ``_tmux_name_for`` / ``_parse_tmux_name``):
``neurona-<workspace>-<tab>-<hash6>``. Vault ownership is deliberately
not exposed in the human-facing name; it remains in runtime metadata and
is folded into the deterministic hash so same-named workspaces in different
vaults cannot collide. Older vault-prefixed and ``lab-`` schemes
are still recognized for discovery/adoption, so this change never requires
killing or renaming a live session. ``LAB_TMUX_PREFIX`` (tests / opt-out)
keeps the plain ``<prefix><workspace>-<tab>`` shape exactly as before.

Killing a session (the "X on a tab" flow) removes it from tmux + the runtime
file but **keeps** the workspace.json entry so a later re-open can
``claude --resume <claude_session_id>`` and pick up the conversation.

Workspace-scoped endpoints default to the ACTIVE vault for backward
compatibility and accept an optional ``vault`` id so several vaults
can stay open at once. Two operations span every REGISTERED vault
(``~/.lab/vaults.toml``): ``GET /api/term/sessions`` with no
``workspace_id`` (each row tagged ``vault``), and
``DELETE /api/term/sessions/{name}`` (a session named for any vault is
accepted and killed against its owning vault's files). See
``_known_vaults``.
"""
from __future__ import annotations

from lab import naming

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
import sqlite3
import struct
import subprocess
import termios
import time
import tomllib
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
import yaml

from lab import paths as lab_paths
from lab import settings as lab_settings
from lab import tmux_sockets

from core import auth, fsguard
from core import vault_config


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

# Fixed literal marker for Lab-owned tmux sessions. Current names use
# ``neurona-<workspace>-<tab>-<hash6>``; the immediately preceding generation
# inserted ``<vault>-`` after this marker and remains discoverable.
_SESSION_PREFIX = "neurona-"

_VAULT_LABEL_CACHE: dict[str, tuple[float, str]] = {}
_VAULT_LABEL_TTL_S = 5.0


def _vault_label_from_registry(resolved_root: Path) -> str | None:
    """Match ``resolved_root`` against ``~/.lab/vaults.toml`` entries.

    Returns the entry's ``id`` — the stable handle a concurrent `lab
    vault` rename/re-id operation may change, but which never changes
    just because the vault's on-disk PATH moved (USB remount, moved
    checkout). Read fresh every call (the TTL cache above wraps the whole
    resolution, not just this step) so a registry edited out-of-process is
    picked up without a server restart.
    """
    try:
        assistant = lab_paths.assistant_root()
        if assistant is not None and assistant == resolved_root:
            return "assistant"
        data = lab_paths.read_vault_registry()
    except Exception:
        return None
    for row in data.get("vaults") or []:
        raw_path = row.get("path")
        if not raw_path:
            continue
        try:
            entry_path = Path(str(raw_path)).expanduser().resolve()
        except OSError:
            continue
        if entry_path == resolved_root:
            vault_id = row.get("id")
            if vault_id:
                return str(vault_id)
    return None


def _vault_label_from_lab_toml(resolved_root: Path) -> str | None:
    """Fallback: ``[vault].name`` from the vault's own ``lab.toml``."""
    toml_path = resolved_root / "lab.toml"
    if not toml_path.is_file():
        return None
    try:
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    vault = data.get("vault", data.get("workspace"))
    if isinstance(vault, dict):
        name = vault.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _resolve_vault_label(root: Path | None) -> str:
    """Stable short id for ``root``, used to namespace tmux session names.

    Resolution order: the vault registry's ``id`` (matched by resolved
    path so it's independent of the path string itself — this is the fix
    for sessions silently orphaning on a path change), then
    ``[vault].name`` from the vault's own ``lab.toml``, then a
    sanitized root directory name as a last resort.

    Cached per resolved root path for a few seconds: cheap enough to re-read
    every call, but several tmux operations can fan out from one request and
    there's no reason to re-parse the registry for each of them.
    """
    if root is None:
        return "vault"
    try:
        resolved = root.expanduser().resolve()
    except OSError:
        resolved = root.expanduser()
    key = str(resolved)
    now = time.monotonic()
    cached = _VAULT_LABEL_CACHE.get(key)
    if cached and (now - cached[0]) < _VAULT_LABEL_TTL_S:
        return cached[1]
    label = (
        _vault_label_from_registry(resolved)
        or _vault_label_from_lab_toml(resolved)
        or resolved.name
    )
    sanitized = _sanitize(label)
    _VAULT_LABEL_CACHE[key] = (now, sanitized)
    return sanitized


def _new_scheme_prefix(root: Path | None = None) -> str:
    """Vault-neutral prefix of every current-scheme session name."""
    return _SESSION_PREFIX


def _legacy_vault_prefix(root: Path | None) -> str:
    """Prefix used by the previous ``neurona-<vault>-...`` scheme."""
    return f"{_SESSION_PREFIX}{_resolve_vault_label(root)}-"


def _legacy_namespaced_prefix(root: Path | None) -> str:
    """Reconstruct the pre-``neurona-`` namespaced prefix for ``root``.

    This reproduces the entire prefix algorithm the pre-``neurona-`` code
    used to compute on every call: ``lab-<dirname>-<sha1(resolved
    path)[:8]>-``. It embedded a hash of the vault PATH, which is
    exactly why it broke on a path change — kept here only so already-live
    sessions from an older server build are still discovered instead of
    orphaned.
    """
    if root is None:
        return "lab-vault-"
    try:
        resolved = root.expanduser().resolve()
    except OSError:
        resolved = root.expanduser()
    label = re.sub(r"[^A-Za-z0-9_-]+", "-", resolved.name).strip("-") or "vault"
    digest = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:8]
    return f"lab-{label}-{digest}-"


def _tmux_discovery_prefixes(root: Path | None) -> list[str]:
    """All prefixes under which a tmux session could belong to this vault.

    Includes the vault-neutral current scheme plus all schemes an older
    server build used, so already-live sessions from before this
    naming change are discovered/adopted instead of vanishing from the UI.
    With ``LAB_TMUX_PREFIX`` set (tests), there's only ever the one scheme.
    """
    env_prefix = os.environ.get("LAB_TMUX_PREFIX")
    if env_prefix:
        return [env_prefix]
    return [
        _new_scheme_prefix(root),
        _legacy_vault_prefix(root),
        _legacy_namespaced_prefix(root),
        "lab-",
    ]


# ─── multi-vault session discovery ──────────────────────────────────────
#
# Dev servers (core.routes.servers) and a handful of terminal endpoints span
# every registered vault, not just the active one — the dashboard needs
# to see and kill sessions that live in a vault other than the one
# currently open. These helpers extend the single-root primitives above
# across every vault in the registry.

def _known_vaults(active_root: Path | None) -> list[dict]:
    """``[{"id": ..., "path": Path}, ...]`` for every registered vault,
    plus ``active_root`` itself if it isn't already one of them (id
    defaults to the resolved directory name — same fallback
    ``core.routes.vault`` and ``core.routes.servers`` use for a
    not-yet-registered current vault). Read fresh on every call: the
    registry is a small TOML file and can change out-of-process (``lab
    vault add`` et al.) without a server restart.
    """
    try:
        data = lab_paths.read_vault_registry()
    except Exception:
        data = {}
    rows: list[dict] = []
    seen: set[str] = set()
    for row in data.get("vaults") or []:
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
            seen.add(str(resolved))
    # A client owns one Assistant database across every vault. Treat it
    # as a terminal-only pseudo-vault without registering it as a normal
    # Vault tab.
    try:
        assistant = lab_paths.assistant_root()
    except Exception:
        assistant = None
    if assistant is not None and assistant.is_dir() and str(assistant) not in seen:
        rows.append({"id": ASSISTANT_VAULT_ID, "path": assistant})
    return rows


def _vault_root_for(active_root: Path, vault: str | None) -> Path:
    """Resolve an optional registered vault id without changing global state."""
    if not vault:
        return active_root
    for row in _known_vaults(active_root):
        if row["id"] == vault:
            return row["path"]
    raise HTTPException(status_code=404, detail=f"vault {vault!r} not found")


def _vault_id_for_root(active_root: Path, root: Path) -> str:
    resolved = root.expanduser().resolve()
    for row in _known_vaults(active_root):
        if row["path"].expanduser().resolve() == resolved:
            return str(row["id"])
    return resolved.name


def _require_root_access(connection: Request | WebSocket, active_root: Path, root: Path) -> dict:
    return auth.require_vault(connection, _vault_id_for_root(active_root, root))


def _require_workspace_access(
    connection: Request | WebSocket, active_root: Path, root: Path, workspace_id: str | None,
) -> dict:
    if workspace_id == ASSISTANT_WORKSPACE_ID:
        return auth.require_admin(connection)
    user = _require_root_access(connection, active_root, root)
    if workspace_id in {SELF_WORKSPACE_ID, CEREBRO_WORKSPACE_ID, LOGS_WORKSPACE_ID} or _cs_repo_name(workspace_id or ""):
        if not auth.is_admin(user):
            raise HTTPException(status_code=403, detail="admin access required")
    return user


def _tmux_discovery_prefixes_all(vaults: list[dict]) -> list[str]:
    """Union of ``_tmux_discovery_prefixes`` across every vault in
    ``vaults`` — lets the "list/kill anything" paths recognize a
    session spawned for ANY registered vault, not just the active one.

    Cheap: each vault contributes a couple of literal-prefix strings
    (no filesystem access), and the vault-agnostic bare ``"lab-"``
    legacy prefix is included exactly once regardless of vault count.
    Callers should compute ``vaults`` once (e.g. via
    ``_known_vaults``) and pass it in rather than re-reading the
    registry per call.
    """
    env_prefix = os.environ.get("LAB_TMUX_PREFIX")
    if env_prefix:
        return [env_prefix]
    prefixes: list[str] = []
    seen: set[str] = set()
    for vault_row in vaults:
        for p in (
            _new_scheme_prefix(),
            _legacy_vault_prefix(vault_row["path"]),
            _legacy_namespaced_prefix(vault_row["path"]),
        ):
            if p not in seen:
                seen.add(p)
                prefixes.append(p)
    prefixes.append("lab-")
    return prefixes


def _resolve_session_vault_root(
    name: str, active_root: Path, vaults: list[dict] | None = None,
) -> Path:
    """Which vault's root a live tmux session name actually belongs to.

    Current names omit a visible vault segment, so ownership is resolved
    first from each vault's runtime registry and then by verifying the
    vault-specific hash. Previous ``neurona-<vault>-...`` and
    namespaced ``lab-`` names remain directly attributable. The oldest bare
    ``lab-<workspace>-<tab>`` form falls back to the active vault.
    """
    if os.environ.get("LAB_TMUX_PREFIX"):
        return active_root
    known = vaults if vaults is not None else _known_vaults(active_root)
    for vault_row in known:
        try:
            if name in _load_meta(vault_row["path"]):
                return vault_row["path"]
        except OSError:
            continue
    for vault_row in known:
        root = vault_row["path"]
        if _parse_current_tmux_name(root, name) is not None:
            return root
        if name.startswith(_legacy_vault_prefix(root)) or name.startswith(_legacy_namespaced_prefix(root)):
            return root
    return active_root


# If the lab server process itself happens to be launched FROM INSIDE a tmux
# session (e.g. `make start` run in a tmux pane), every `tmux ...` subprocess
# call below would inherit `$TMUX`/`$TMUX_PANE` from that parent shell — and
# tmux uses `$TMUX` to find its control socket. That silently redirects
# `list-sessions` / `new-session` / `has-session` etc. onto the CONTAINING
# session's server instead of the default one. A launchd-run instance (no
# controlling tmux) then talks to the *default* socket and can't see any of
# those sessions — they look gone, and reopening a workspace spawns fresh
# duplicates instead of finding them. Stripping `TMUX`/`TMUX_PANE` from every
# tmux child's env pins us to the default socket unconditionally, regardless
# of how the server process itself was launched.
_TMUX_ENV_STRIP_KEYS = ("TMUX", "TMUX_PANE")


def _tmux_child_env() -> dict[str, str]:
    """Environment for a tmux subprocess/exec: current env minus TMUX vars."""
    return {k: v for k, v in os.environ.items() if k not in _TMUX_ENV_STRIP_KEYS}


# Reserved pseudo-workspace ids.
#  * __cerebro__ — the personal knowledge-base view (cwd = content/)
#  * __self__    — the Lab framework checkout itself   (cwd = repo root)
#  * __logs__    — the embedded logs view              (cwd = logs/)
#  * __vault__ — the active vault view         (cwd = vault root)
#  * __assistant__ — the client-owned global task database
# They behave like regular workspaces for terminal lifecycle and durable session
# state; each view decides independently whether its topbar tab is closable.
CEREBRO_WORKSPACE_ID = "__cerebro__"
SELF_WORKSPACE_ID = "__self__"
LOGS_WORKSPACE_ID = "__logs__"
VAULT_WORKSPACE_ID = "__vault__"
ASSISTANT_WORKSPACE_ID = "__assistant__"
ASSISTANT_VAULT_ID = "__assistant__"
# Per-repo pseudo workspace for the Code Search tab. The id is
# ``__cs_<repo>__`` where ``<repo>`` is a directory name under
# ``repositories/``. Used so each Code-Search repo has its own scoped
# terminal panel (cwd = repositories/<repo>) without needing a real
# workspace.json.
_CS_PREFIX = "__cs_"
_CS_SUFFIX = "__"


def _cs_repo_name(workspace_id: str) -> str | None:
    if not workspace_id.startswith(_CS_PREFIX) or not workspace_id.endswith(_CS_SUFFIX):
        return None
    name = workspace_id[len(_CS_PREFIX):-len(_CS_SUFFIX)]
    return name or None


def _sessions_file(root: Path) -> Path:
    from lab import paths
    return paths.sessions_file(root)


def _workspace_json(root: Path, workspace_id: str) -> Path:
    """Path of the metadata file for a workspace_id. Pseudo-workspaces store
    their sessions[] at a hidden file under content/ that shares
    workspace.json's shape."""
    if workspace_id == CEREBRO_WORKSPACE_ID:
        return naming.pseudo_metadata_file(root, "cerebro")
    if workspace_id == SELF_WORKSPACE_ID:
        from lab import paths
        root = paths.find_framework_root()
        return naming.pseudo_metadata_file(root, "self")
    if workspace_id == LOGS_WORKSPACE_ID:
        return naming.pseudo_metadata_file(root, "logs")
    if workspace_id == VAULT_WORKSPACE_ID:
        return naming.pseudo_metadata_file(root, "vault")
    if workspace_id == ASSISTANT_WORKSPACE_ID:
        return naming.workspace_metadata_file(root / ".lab")
    return naming.workspace_metadata_file(naming.workspaces_dir(root) / workspace_id)


def _workspace_cwd(root: Path, workspace_id: str) -> Path:
    """Absolute cwd for a workspace_id.

    - ``__cerebro__``     → content/
    - ``__self__``        → monorepo root (so claude sees apps/, docs/, etc.)
    - ``__logs__``        → logs/
    - ``__vault__``   → the active vault root (Vault tab terminal)
    - ``__assistant__``   → the client-owned Assistant database root
    - ``__cs_<repo>__``   → repositories/<repo> (Code Search per-repo terminal)
    """
    if workspace_id == CEREBRO_WORKSPACE_ID:
        return (root / "content").resolve()
    if workspace_id == VAULT_WORKSPACE_ID:
        return root.resolve()
    if workspace_id == ASSISTANT_WORKSPACE_ID:
        return root.resolve()
    if workspace_id == SELF_WORKSPACE_ID:
        from lab import paths
        return paths.find_framework_root().resolve()
    if workspace_id == LOGS_WORKSPACE_ID:
        from lab import paths
        return paths.logs_dir(root).resolve()
    repo = _cs_repo_name(workspace_id)
    if repo:
        return (root / "repositories" / repo).resolve()
    return (naming.workspaces_dir(root) / workspace_id).resolve()


# ─── runtime metadata (.sessions.json) ──────────────────────────────────────

def _load_meta(root: Path) -> dict:
    p = _sessions_file(root)
    legacy = root / "content" / ".sessions.json"
    if not p.is_file() and legacy.is_file():
        p = legacy
    if not p.is_file():
        return {}
    try:
        return naming.runtime_metadata(json.loads(p.read_text()))
    except (json.JSONDecodeError, ValueError):
        return {}


def _save_meta(root: Path, meta: dict) -> None:
    p = _sessions_file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(meta, indent=2) + "\n")


# Vault roots already warned about being unavailable (e.g. a registered
# vault living on an unplugged external volume). The UI polls the session
# endpoints every few seconds, so warn once per root, not once per cycle.
_UNAVAILABLE_WARNED_ROOTS: set[str] = set()


def _warn_root_unavailable_once(root: Path, action: str, exc: OSError) -> None:
    key = str(root)
    if key in _UNAVAILABLE_WARNED_ROOTS:
        return
    _UNAVAILABLE_WARNED_ROOTS.add(key)
    log.warning(
        "vault storage unavailable during %s for %s: %s",
        action, root, exc,
        extra={"event_type": "term.vault.unavailable", "target": str(root)},
    )


# ─── durable metadata (workspace.json.sessions) ───────────────────────────────

def _load_workspace(root: Path, workspace_id: str) -> dict | None:
    p = _workspace_json(root, workspace_id)
    # Pre-rename migration: if the Cerebro file doesn't exist yet but the
    # old ``.knowledge-workspace.json`` does, rename it in place. One-shot.
    if workspace_id == CEREBRO_WORKSPACE_ID and not p.is_file():
        legacy = root / "content" / ".knowledge-workspace.json"
        if legacy.is_file():
            try:
                legacy.rename(p)
            except OSError:
                pass  # best effort; fall through
    if not p.is_file():
        # Pseudo-workspaces have no ``lab workspace new``
        # ceremony — bootstrap an empty shell so session IDs get persisted
        # on first use. Real workspaces still return None; creating their
        # workspace.json is the CLI's job.
        if workspace_id in (
            CEREBRO_WORKSPACE_ID,
            SELF_WORKSPACE_ID,
            LOGS_WORKSPACE_ID,
            VAULT_WORKSPACE_ID,
            ASSISTANT_WORKSPACE_ID,
        ):
            return {}
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, ValueError):
        return None


def _save_workspace(root: Path, workspace_id: str, data: dict) -> None:
    p = _workspace_json(root, workspace_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")


def _get_workspace_sessions(root: Path, workspace_id: str) -> list[dict]:
    """Return the `sessions` array from workspace.json (empty if missing)."""
    data = _load_workspace(root, workspace_id)
    if not data:
        return []
    sessions = data.get("sessions")
    return sessions if isinstance(sessions, list) else []


def _workspace_session_by_name(root: Path, workspace_id: str) -> dict[str, dict]:
    """Saved sessions keyed by logical name."""
    return {
        s["name"]: s for s in _get_workspace_sessions(root, workspace_id)
        if isinstance(s, dict) and isinstance(s.get("name"), str)
    }


def _upsert_workspace_session(root: Path, workspace_id: str, entry: dict) -> None:
    """Insert or update an entry (keyed by ``name``) in workspace.json.sessions."""
    data = _load_workspace(root, workspace_id)
    if data is None:
        return  # workspace.json doesn't exist — skip silently; the session still
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
    _save_workspace(root, workspace_id, data)


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


def _infer_session_summary(name: str, tmux_socket: str) -> str | None:
    """Best-effort hover summary from the visible tmux pane.

    This intentionally does not ask the agent to summarize itself; that would
    affect latency and sometimes mutate the conversation. A cached pane
    capture gives enough context for hover text without touching stdin.
    """
    now = time.monotonic()
    cache_key = f"{tmux_socket}\0{name}"
    cached = _SUMMARY_CACHE.get(cache_key)
    if cached and (now - cached[0]) < _SUMMARY_TTL_S:
        return cached[1] or None
    if not _tmux_available():
        return None
    try:
        proc = subprocess.run(
            _tmux_command(tmux_socket, "capture-pane", "-pt", name, "-S", "-120"),
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
    _SUMMARY_CACHE[cache_key] = (now, summary)
    return summary or None


_AGENT_METADATA_TTL_S = 5.0
_AGENT_METADATA_CACHE: dict[
    str, tuple[float, object, tuple[str | None, str | None, list[str]]]
] = {}
_CLAUDE_TRANSCRIPT_CACHE: dict[
    str, tuple[int, int, int, str | None, str | None, list[str], bool]
] = {}
# Cache both the TTYs that were inspected and the subset that resolved to a
# live Codex thread.  A pane TTY can legitimately have no Codex process; if
# we only cache successful resolutions, one such terminal turns every poll
# into another ps + SQLite scan instead of a cache hit.
_CODEX_METADATA_CACHE: tuple[
    float, set[str], dict[str, tuple[str, str, str | None, list[str]]]
] | None = None
_CODEX_PROCESS_UUID_RE = re.compile(r"^pid:(\d+):")
_AGENT_IMAGE_TAG_RE = re.compile(r"<image\b[^>]*>.*?</image>", re.DOTALL | re.I)
_AGENT_IMAGE_REF_RE = re.compile(r"\[Image\s+#\d+\]", re.I)
_AGENT_IMAGE_PATH_RE = re.compile(
    r"(?:^|\s)\.lab/terminal-pastes/\S+\.(?:png|jpe?g|webp)\b", re.I,
)
_COPILOT_PLACEHOLDER_TITLES = {
    "copilot", "github copilot", "new session", "session initialization",
}


def _message_content_text(content) -> str | None:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts = []
    for item in content:
        if not isinstance(item, dict) or item.get("type") not in ("text", "input_text"):
            continue
        value = item.get("text")
        if isinstance(value, str):
            parts.append(value)
    return "\n".join(parts) or None


def _clean_agent_task(raw: str | None, *, max_len: int = 280) -> str | None:
    if not isinstance(raw, str):
        return None
    text = _AGENT_IMAGE_TAG_RE.sub(" ", raw)
    text = _AGENT_IMAGE_REF_RE.sub(" ", text)
    text = _AGENT_IMAGE_PATH_RE.sub(" ", text)
    text = "\n".join(
        " ".join(line.split())
        for line in text.strip().splitlines()
        if line.strip()
    )
    if not text or text in ("[Request interrupted by user]", "Request interrupted by user"):
        return None
    if (
        text.startswith("# AGENTS.md instructions for ")
        or text.startswith("Base directory for this skill:")
        or text.startswith("<environment_context>")
    ):
        return None
    if len(text) > max_len:
        return text[: max_len - 3].rstrip() + "..."
    return text


def _clean_agent_requests(raw_requests) -> list[str]:
    if isinstance(raw_requests, str):
        raw_requests = [raw_requests]
    if not isinstance(raw_requests, (list, tuple)):
        return []
    requests = []
    for raw in raw_requests:
        request = _clean_agent_task(raw)
        if request:
            requests.append(request)
    return requests


def _request_clears_session(raw: str | None) -> bool:
    if not isinstance(raw, str):
        return False
    text = raw.strip().lower()
    return text == "/clear" or bool(re.match(
        r"^<command-name>\s*/clear\s*</command-name>(?:\s|<|$)", text,
    ))


def _agent_file_fingerprint(*paths: Path) -> tuple[tuple[str, int, int], ...]:
    fingerprint = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        fingerprint.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(fingerprint)


def _cached_agent_metadata(
    key: str, fingerprint: object, loader,
) -> tuple[str | None, str | None, list[str]]:
    now = time.monotonic()
    cached = _AGENT_METADATA_CACHE.get(key)
    if cached and (
        now - cached[0] < _AGENT_METADATA_TTL_S or cached[1] == fingerprint
    ):
        return cached[2]
    try:
        name, objective, requests = loader()
        value = (
            _clean_optional_text(name, max_len=100),
            _clean_agent_task(objective),
            _clean_agent_requests(requests),
        )
    except (
        OSError, TypeError, ValueError, json.JSONDecodeError, sqlite3.Error,
        yaml.YAMLError,
    ):
        value = (None, None, [])
    _AGENT_METADATA_CACHE[key] = (now, fingerprint, value)
    return value


def _claude_session_metadata(
    session_id: str, cwd: str,
) -> tuple[str | None, str | None, list[str]]:
    """Read Claude's title, live AI recap, and post-clear user requests."""
    workspace_slug = re.sub(r"[^A-Za-z0-9]", "-", str(Path(cwd).resolve()))
    workspace_dir = Path.home() / ".claude" / "projects" / workspace_slug
    transcript = workspace_dir / f"{session_id}.jsonl"

    index_path = workspace_dir / "sessions-index.json"

    def load() -> tuple[str | None, str | None, list[str]]:
        title = None
        objective = None
        requests = []
        cleared = False
        if transcript.is_file():
            stat = transcript.stat()
            cached_transcript = _CLAUDE_TRANSCRIPT_CACHE.get(str(transcript))
            start = 0
            if cached_transcript:
                (
                    cached_inode, cached_size, cached_mtime, title, objective,
                    cached_requests, cleared,
                ) = cached_transcript
                if (
                    cached_inode == stat.st_ino
                    and (
                        stat.st_size > cached_size
                        or (
                            stat.st_size == cached_size
                            and stat.st_mtime_ns == cached_mtime
                        )
                    )
                ):
                    start = cached_size
                    requests = list(cached_requests)
                else:
                    title = None
                    objective = None
                    requests = []
                    cleared = False
            with transcript.open("rb") as handle:
                handle.seek(start)
                data = handle.read()
                end = handle.tell()
                final_stat = os.fstat(handle.fileno())
            for raw in data.splitlines():
                try:
                    event = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                candidate = event.get("customTitle") or event.get("aiTitle")
                if isinstance(candidate, str) and candidate.strip():
                    title = candidate
                if (
                    event.get("type") == "system"
                    and event.get("subtype") == "away_summary"
                ):
                    objective = _clean_agent_task(event.get("content"))
                message = event.get("message")
                if (
                    event.get("type") == "user"
                    and event.get("isSidechain") is not True
                    and event.get("userType") in (None, "external")
                    and not event.get("toolUseResult")
                    and not event.get("sourceToolAssistantUUID")
                    and isinstance(message, dict)
                ):
                    raw_task = _message_content_text(message.get("content"))
                    if _request_clears_session(raw_task):
                        requests = []
                        objective = None
                        title = None
                        cleared = True
                        continue
                    candidate_task = _clean_agent_task(raw_task)
                    if candidate_task:
                        requests.append(candidate_task)
                        # An away recap only describes the conversation up to
                        # the point it was emitted. A later user turn makes it
                        # stale, so requests become the source of truth again.
                        objective = None
            _CLAUDE_TRANSCRIPT_CACHE[str(transcript)] = (
                final_stat.st_ino, end, final_stat.st_mtime_ns, title,
                objective, list(requests), cleared,
            )

        if index_path.is_file() and not cleared and (not title or not requests):
            payload = json.loads(index_path.read_text())
            entries = payload.get("entries") if isinstance(payload, dict) else None
            for entry in entries if isinstance(entries, list) else []:
                if isinstance(entry, dict) and entry.get("sessionId") == session_id:
                    title = title or entry.get("name") or entry.get("summary")
                    fallback = entry.get("firstPrompt") or entry.get("summary")
                    if not requests and fallback:
                        requests.append(fallback)
                    break
        if not objective and title and len(requests) == 1:
            objective = title
        return title, objective, requests

    return _cached_agent_metadata(
        f"claude:{session_id}",
        _agent_file_fingerprint(transcript, index_path),
        load,
    )


def _copilot_session_metadata(
    session_id: str,
) -> tuple[str | None, str | None, list[str]]:
    """Read Copilot's saved name, checkpoint recap, and post-clear requests."""
    home = Path(os.environ.get("COPILOT_HOME") or (Path.home() / ".copilot"))
    session_dir = home / "session-state" / session_id
    vault = session_dir / "workspace.yaml"
    events = session_dir / "events.jsonl"
    store = home / "session-store.db"

    def load() -> tuple[str | None, str | None, list[str]]:
        title = None
        vault_summary = None
        user_named = False
        summary_count = 0
        if vault.is_file():
            payload = yaml.safe_load(vault.read_text())
            if isinstance(payload, dict):
                candidates = [payload]
                nested = payload.get("workspace")
                if isinstance(nested, dict):
                    candidates.append(nested)
                for candidate in candidates:
                    if not title:
                        title = candidate.get("name") or candidate.get("summary")
                    if not vault_summary:
                        vault_summary = candidate.get("summary")
                    user_named = user_named or candidate.get("user_named") is True
                    summary_count = max(
                        summary_count, int(candidate.get("summary_count") or 0),
                    )
        all_requests = []
        cleared = False
        if events.is_file():
            for raw in events.read_bytes().splitlines():
                try:
                    event = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                event_data = event.get("data")
                if event.get("type") != "user.message" or not isinstance(event_data, dict):
                    continue
                raw_task = event_data.get("content")
                if _request_clears_session(raw_task):
                    all_requests = []
                    cleared = True
                    continue
                candidate_task = _clean_agent_task(raw_task)
                if candidate_task:
                    all_requests.append(candidate_task)
        normalized_title = re.sub(r"\s+", " ", str(title or "").strip().lower())
        if cleared:
            title = None
        if not user_named and normalized_title in _COPILOT_PLACEHOLDER_TITLES:
            title = None

        objective = None
        if store.is_file() and not cleared:
            try:
                with closing(sqlite3.connect(
                    f"file:{store}?mode=ro", uri=True, timeout=0.2,
                )) as conn:
                    row = conn.execute(
                        """
                        SELECT title, overview
                        FROM checkpoints
                        WHERE session_id = ?
                        ORDER BY checkpoint_number DESC, id DESC
                        LIMIT 1
                        """,
                        (session_id,),
                    ).fetchone()
                    if row:
                        objective = row[0] or row[1]
                    if not objective and summary_count:
                        row = conn.execute(
                            "SELECT summary FROM sessions WHERE id = ?",
                            (session_id,),
                        ).fetchone()
                        if row:
                            objective = row[0]
            except sqlite3.Error:
                # Older Copilot builds may not have global checkpoint tables.
                pass
        if not objective and summary_count and not cleared:
            objective = vault_summary
        if (
            not user_named
            and re.sub(r"\s+", " ", str(objective or "").strip().lower())
            in _COPILOT_PLACEHOLDER_TITLES
        ):
            objective = None
        if not objective and title and not cleared and len(all_requests) == 1:
            objective = title
        return title, objective, all_requests

    return _cached_agent_metadata(
        f"copilot:{session_id}",
        _agent_file_fingerprint(
            vault, events, store, Path(f"{store}-wal"),
        ),
        load,
    )


def _tty_key(raw: str | None) -> str:
    return (raw or "").removeprefix("/dev/").strip()


def _codex_session_metadata_by_tty(
    ttys: set[str], cwds: set[str] | None = None,
) -> dict[str, tuple[str, str, str | None, list[str]]]:
    """Map TTYs to ``(thread id, display name, AI recap, requests)``.

    Codex's log index records a process UUID containing the native PID and
    the active top-level thread ID. Joining that with the thread index and
    each process's controlling TTY gives an exact per-pane mapping, including
    after `/new` switches a long-lived TUI process to another conversation.
    """
    global _CODEX_METADATA_CACHE
    wanted = {_tty_key(tty) for tty in ttys if _tty_key(tty)}
    if not wanted:
        return {}
    now = time.monotonic()
    if (
        _CODEX_METADATA_CACHE
        and now - _CODEX_METADATA_CACHE[0] < _AGENT_METADATA_TTL_S
        and wanted.issubset(_CODEX_METADATA_CACHE[1])
    ):
        return {
            tty: value for tty, value in _CODEX_METADATA_CACHE[2].items()
            if tty in wanted
        }

    logs_path = Path.home() / ".codex" / "logs_2.sqlite"
    threads_path = Path.home() / ".codex" / "state_5.sqlite"
    if not logs_path.is_file() or not threads_path.is_file():
        _CODEX_METADATA_CACHE = (now, wanted, {})
        return {}
    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid=,tty="], capture_output=True, text=True,
            timeout=1.0,
        )
        if proc.returncode != 0:
            return {}
        pid_tty: dict[int, str] = {}
        for line in proc.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[0].isdigit():
                tty = _tty_key(fields[1])
                if tty in wanted:
                    pid_tty[int(fields[0])] = tty
        if not pid_tty:
            _CODEX_METADATA_CACHE = (now, wanted, {})
            return {}

        directories = sorted(cwd for cwd in (cwds or set()) if cwd)
        cwd_where = ""
        cwd_params: list[str] = []
        if directories:
            cwd_where = f" AND cwd IN ({','.join('?' for _ in directories)})"
            cwd_params = directories
        with closing(sqlite3.connect(
            f"file:{threads_path}?mode=ro", uri=True, timeout=0.2,
        )) as conn:
            thread_rows = conn.execute(
                f"""
                SELECT id, title, name, preview
                FROM threads
                WHERE archived = 0 AND source = 'cli'{cwd_where}
                ORDER BY updated_at DESC
                LIMIT 500
                """,
                cwd_params,
            ).fetchall()
        threads = {str(row[0]): row for row in thread_rows}
        if not threads:
            _CODEX_METADATA_CACHE = (now, wanted, {})
            return {}
        thread_ids = list(threads)
        placeholders = ",".join("?" for _ in thread_ids)
        with closing(sqlite3.connect(
            f"file:{logs_path}?mode=ro", uri=True, timeout=0.2,
        )) as conn:
            candidates = conn.execute(
                f"""
                SELECT process_uuid, thread_id, MAX(ts) AS last_seen
                FROM logs
                WHERE thread_id IN ({placeholders})
                GROUP BY process_uuid, thread_id
                """,
                thread_ids,
            ).fetchall()
        best: dict[str, tuple[int, str, str]] = {}
        live_process_uuids: set[str] = set()
        for process_uuid, thread_id, last_seen in candidates:
            match = _CODEX_PROCESS_UUID_RE.match(str(process_uuid))
            thread = threads.get(str(thread_id))
            if not match or not thread:
                continue
            tty = pid_tty.get(int(match.group(1)))
            if not tty:
                continue
            live_process_uuids.add(str(process_uuid))
            display = _clean_optional_text(thread[2] or thread[1], max_len=100)
            if not display:
                continue
            current = best.get(tty)
            if current is None or int(last_seen or 0) > current[0]:
                best[tty] = (
                    int(last_seen or 0), str(thread_id), display,
                )

        # Slash commands such as `/clear` and `/new` start a fresh Codex
        # thread before it has a user event. That empty thread is logged by
        # the TUI's shell snapshot, but it is not projected into `threads`
        # yet. Prefer a newer snapshot even when its thread row is absent so
        # the prior conversation's requests disappear immediately.
        if best and live_process_uuids:
            process_placeholders = ",".join("?" for _ in live_process_uuids)
            earliest_known = min(row[0] for row in best.values())
            with closing(sqlite3.connect(
                f"file:{logs_path}?mode=ro", uri=True, timeout=0.2,
            )) as conn:
                starts = conn.execute(
                    f"""
                    SELECT process_uuid, thread_id, ts AS started_at
                    FROM logs
                    WHERE ts > ?
                      AND target = 'codex_core::shell_snapshot'
                      AND thread_id IS NOT NULL
                      AND process_uuid IN ({process_placeholders})
                    ORDER BY ts DESC
                    """,
                    [earliest_known, *sorted(live_process_uuids)],
                ).fetchall()
            for process_uuid, thread_id, started_at in starts:
                match = _CODEX_PROCESS_UUID_RE.match(str(process_uuid))
                tty = pid_tty.get(int(match.group(1))) if match else None
                if not tty:
                    continue
                started = int(started_at or 0)
                current = best.get(tty)
                if current is not None and started > current[0]:
                    thread = threads.get(str(thread_id))
                    display = _clean_optional_text(
                        (thread[2] or thread[1]) if thread else None,
                        max_len=100,
                    ) or ""
                    best[tty] = (started, str(thread_id), display)

        tasks: dict[str, list[str]] = {}
        cleared_threads: set[str] = set()
        live_thread_ids = sorted({row[1] for row in best.values()})
        history_path = Path.home() / ".codex" / "thread_history_1.sqlite"
        task_rows = []
        if live_thread_ids and history_path.is_file():
            live_placeholders = ",".join("?" for _ in live_thread_ids)
            try:
                with closing(sqlite3.connect(
                    f"file:{history_path}?mode=ro", uri=True, timeout=0.2,
                )) as conn:
                    task_rows = conn.execute(
                        f"""
                        SELECT thread_id, item_json, rollout_ordinal
                        FROM thread_items
                        WHERE item_type = 'userMessage'
                          AND thread_id IN ({live_placeholders})
                        ORDER BY thread_id, rollout_ordinal
                        """,
                        live_thread_ids,
                    ).fetchall()
            except sqlite3.Error:
                # Older Codex builds may have no projection DB/table yet.
                # Keep the session name and fall back to the thread preview.
                pass
        for thread_id, item_json, _rollout_ordinal in task_rows:
            try:
                item = json.loads(item_json)
            except (TypeError, json.JSONDecodeError):
                continue
            raw_task = _message_content_text(item.get("content"))
            if _request_clears_session(raw_task):
                tasks[str(thread_id)] = []
                cleared_threads.add(str(thread_id))
                continue
            task = _clean_agent_task(raw_task)
            if task:
                tasks.setdefault(str(thread_id), []).append(task)
        resolved = {}
        for tty, row in best.items():
            if row[1] not in threads:
                resolved[tty] = (row[1], "", None, [])
                continue
            requests = tasks[row[1]] if row[1] in tasks else (
                _clean_agent_requests([threads[row[1]][3]])
            )
            generated_name = _clean_optional_text(
                threads[row[1]][2], max_len=100,
            )
            was_cleared = row[1] in cleared_threads
            objective = (
                generated_name if len(requests) == 1 and not was_cleared else None
            )
            display = "" if was_cleared else row[2]
            resolved[tty] = (row[1], display, objective, requests)
        _CODEX_METADATA_CACHE = (now, wanted, resolved)
        return resolved
    except (OSError, sqlite3.Error, subprocess.SubprocessError):
        return {}


def _enrich_agent_session_names(rows: list[dict]) -> None:
    codex_ttys = {
        str(row.get("pane_tty")) for row in rows
        if row.get("agent") == "codex" and row.get("pane_tty")
    }
    codex_cwds = {
        str(row.get("cwd")) for row in rows
        if row.get("agent") == "codex" and row.get("cwd")
    }
    codex_metadata = _codex_session_metadata_by_tty(codex_ttys, codex_cwds)
    for row in rows:
        agent = row.get("agent")
        session_id = row.get("agent_session_id") or row.get("claude_session_id")
        display = None
        objective = None
        requests = []
        if agent == "codex":
            metadata = codex_metadata.get(_tty_key(row.get("pane_tty")))
            if metadata:
                session_id, display, objective, requests = metadata
        elif agent == "claude" and isinstance(session_id, str):
            display, objective, requests = _claude_session_metadata(
                session_id, str(row.get("cwd") or ""),
            )
        elif agent == "copilot" and isinstance(session_id, str):
            display, objective, requests = _copilot_session_metadata(session_id)
        if isinstance(session_id, str) and session_id:
            row["agent_session_id"] = session_id
        if display:
            row["agent_session_name"] = display
        objective = _clean_agent_task(objective)
        if objective:
            row["agent_session_objective"] = objective
        requests = _clean_agent_requests(requests)
        if requests:
            row["agent_session_requests"] = requests
        summary = objective or (requests[-1] if requests else None)
        if summary:
            # Keep the scalar during the API transition and for older clients.
            row["agent_session_summary"] = summary


# ─── registry recovery ──────────────────────────────────────────────────────
#
# .sessions.json is rebuildable state: every live tmux session is named
# ``<prefix><workspace>-<logical>`` and the durable half of its identity
# (kind / agent / claude_session_id) lives in workspace.json. If the runtime
# file is ever lost or corrupted, reconstruct it instead of leaving live
# sessions orphaned — orphans have workspace_id=None, which empties
# /api/term/workspaces-with-sessions and greys out every tab in the UI.

def _known_workspace_ids(root: Path) -> list[str]:
    ids = [
        CEREBRO_WORKSPACE_ID,
        SELF_WORKSPACE_ID,
        LOGS_WORKSPACE_ID,
        VAULT_WORKSPACE_ID,
        "__workspace__",  # Legacy vault terminal scope; keep live tmux names discoverable.
    ]
    workspaces = naming.workspaces_dir(root)
    if workspaces.is_dir():
        ids += [p.name for p in workspaces.iterdir() if p.is_dir()]
    repos = root / "repositories"
    if repos.is_dir():
        ids += [f"{_CS_PREFIX}{p.name}{_CS_SUFFIX}" for p in repos.iterdir() if p.is_dir()]
    return ids


def _split_workspace_tab_from_ids(workspace_ids: list[str], rest: str) -> tuple[str, str] | None:
    """Split ``<workspace>-<tab>`` against known workspace ids, longest first.

    Workspace ids can themselves contain ``-`` so the split point is
    ambiguous without this. The caller supplies workspace ids so dashboard
    scans can compute them once per vault instead of re-walking the
    filesystem for every live tmux session.
    """
    for pid in sorted(set(workspace_ids), key=len, reverse=True):
        sane = _sanitize(pid)
        if rest.startswith(sane + "-") and len(rest) > len(sane) + 1:
            return pid, rest[len(sane) + 1:]
    return None


def _split_workspace_tab(root: Path, rest: str) -> tuple[str, str] | None:
    return _split_workspace_tab_from_ids(_known_workspace_ids(root), rest)


def _split_workspace_tab_hashed_from_ids(
    workspace_ids: list[str],
    vault: str,
    rest: str,
) -> tuple[str, str] | None:
    """Split ``<workspace>-<tab>-<hash6>`` for the current naming scheme.

    Tolerates sessions missing the hash suffix (e.g. hand-created by a CLI
    or agent that followed the ``<workspace>-<tab>`` shape but didn't compute
    the marker): a trailing 6-hex segment is only treated as the hash when
    it verifies against the deterministic hash for that exact (workspace,
    tab) pair, so a tab name that innocently ends in 6 hex characters is
    never mistaken for one and chopped off.
    """
    for pid in sorted(set(workspace_ids), key=len, reverse=True):
        sane = _sanitize(pid)
        if not (rest.startswith(sane + "-") and len(rest) > len(sane) + 1):
            continue
        middle = rest[len(sane) + 1:]
        if "-" in middle:
            maybe_tab, _, maybe_hash = middle.rpartition("-")
            if maybe_tab and _HASH_HEX_RE.match(maybe_hash):
                if maybe_hash == _session_hash(vault, sane, maybe_tab):
                    return pid, maybe_tab
        # No verified hash suffix — tolerate it; the whole remainder is the
        # tab. Still a valid nomenclature session, just hand-made.
        return pid, middle
    return None


def _split_workspace_tab_hashed(root: Path, vault: str, rest: str) -> tuple[str, str] | None:
    return _split_workspace_tab_hashed_from_ids(_known_workspace_ids(root), vault, rest)


def _split_current_workspace_tab_from_ids(
    workspace_ids: list[str], vault: str, rest: str,
) -> tuple[str, str] | None:
    """Strictly split a vault-neutral current name.

    The visible name no longer carries a vault id, so the deterministic
    suffix must verify for ``vault``. A hash belonging to another root
    is rejected instead of being misread as part of the logical tab name.
    """
    for pid in sorted(set(workspace_ids), key=len, reverse=True):
        sane = _sanitize(pid)
        if not (rest.startswith(sane + "-") and len(rest) > len(sane) + 1):
            continue
        middle = rest[len(sane) + 1:]
        maybe_tab, sep, maybe_hash = middle.rpartition("-")
        if not sep or not maybe_tab or not _HASH_HEX_RE.match(maybe_hash):
            continue
        if maybe_hash == _session_hash(vault, sane, maybe_tab):
            return pid, maybe_tab
    return None


def _parse_current_tmux_name(
    root: Path, name: str, workspace_ids: list[str] | None = None,
) -> tuple[str, str] | None:
    if not name.startswith(_SESSION_PREFIX):
        return None
    return _split_current_workspace_tab_from_ids(
        workspace_ids if workspace_ids is not None else _known_workspace_ids(root),
        _resolve_vault_label(root),
        name[len(_SESSION_PREFIX):],
    )


def _parse_tmux_name(root: Path, name: str) -> tuple[str, str] | None:
    """Split a live tmux session name back into ``(workspace_id, logical_name)``.

    Recognizes four generations of naming, tried in order:
      1. Current: ``neurona-<workspace>-<tab>-<hash6>``.
      2. Previous: ``neurona-<vault>-<workspace>-<tab>-<hash6>``.
      3. Namespaced legacy: ``lab-<label>-<digest8>-<workspace>-<tab>``.
      4. Bare legacy: ``lab-<workspace>-<tab>``.
    All are tried so sessions spawned by an older server build (or by
    an agent/CLI running outside the server, following the convention) are
    still discovered and adopted instead of showing up as orphaned.

    With ``LAB_TMUX_PREFIX`` set, only the single legacy-shaped scheme under
    that literal prefix is recognized (test mode). Returns None for names we
    can't attribute (e.g. the UUID fallback for workspace-less terminals).
    """
    env_prefix = os.environ.get("LAB_TMUX_PREFIX")
    if env_prefix:
        if not name.startswith(env_prefix):
            return None
        return _split_workspace_tab(root, name[len(env_prefix):])

    parsed = _parse_current_tmux_name(root, name)
    if parsed:
        return parsed

    vault_prefix = _legacy_vault_prefix(root)
    if name.startswith(vault_prefix):
        vault = _resolve_vault_label(root)
        parsed = _split_workspace_tab_hashed(root, vault, name[len(vault_prefix):])
        if parsed:
            return parsed

    legacy_ns = _legacy_namespaced_prefix(root)
    if name.startswith(legacy_ns):
        parsed = _split_workspace_tab(root, name[len(legacy_ns):])
        if parsed:
            return parsed

    if name.startswith("lab-"):
        parsed = _split_workspace_tab(root, name[len("lab-"):])
        if parsed:
            return parsed

    return None


def _parse_tmux_name_with_workspace_ids(
    root: Path,
    name: str,
    workspace_ids: list[str],
) -> tuple[str, str] | None:
    """Like ``_parse_tmux_name`` but uses a pre-scanned workspace id list."""
    env_prefix = os.environ.get("LAB_TMUX_PREFIX")
    if env_prefix:
        if not name.startswith(env_prefix):
            return None
        return _split_workspace_tab_from_ids(workspace_ids, name[len(env_prefix):])

    parsed = _parse_current_tmux_name(root, name, workspace_ids)
    if parsed:
        return parsed

    vault_prefix = _legacy_vault_prefix(root)
    if name.startswith(vault_prefix):
        vault = _resolve_vault_label(root)
        parsed = _split_workspace_tab_hashed_from_ids(
            workspace_ids,
            vault,
            name[len(vault_prefix):],
        )
        if parsed:
            return parsed

    legacy_ns = _legacy_namespaced_prefix(root)
    if name.startswith(legacy_ns):
        parsed = _split_workspace_tab_from_ids(workspace_ids, name[len(legacy_ns):])
        if parsed:
            return parsed

    if name.startswith("lab-"):
        parsed = _split_workspace_tab_from_ids(workspace_ids, name[len("lab-"):])
        if parsed:
            return parsed

    return None


def _reconstruct_meta_entry(
    root: Path,
    name: str,
    created: int = 0,
    tmux_socket: str = tmux_sockets.DEFAULT_SOCKET,
) -> dict | None:
    """Best-effort runtime entry for a live session .sessions.json has no
    record of. The durable workspace.json entry wins where present; otherwise
    the logical name's leading word fills the gaps ("bash" → terminal,
    "codex" → codex agent, "server" → a managed dev-server tab spawned by
    ``core.routes.servers``, not a claude conversation)."""
    parsed = _parse_tmux_name(root, name)
    if not parsed:
        return None
    pid, logical = parsed
    if pid == "__workspace__":
        pid = VAULT_WORKSPACE_ID
    base = logical.split("-")[0]
    entry: dict = {
        "workspace_id": pid,
        "logical_name": logical,
        "kind": "terminal" if base in ("bash", "terminal", "term", "shell", "server") else "claude",
        "agent": None,
        "cwd": str(_workspace_cwd(root, pid)),
        "created_at": created or int(time.time()),
        "tmux_socket": tmux_socket,
        "recovered": True,
    }
    if entry["kind"] == "claude":
        entry["agent"] = base if base in lab_settings.VALID_AGENTS else "claude"
    for s in _get_workspace_sessions(root, pid):
        if isinstance(s, dict) and s.get("name") == logical:
            entry["kind"] = s.get("kind") or entry["kind"]
            entry["agent"] = s.get("agent") or entry["agent"]
            if s.get("claude_session_id"):
                entry["claude_session_id"] = s["claude_session_id"]
            if s.get("agent_session_id"):
                entry["agent_session_id"] = s["agent_session_id"]
            for key in ("label", "summary", "linked_file", "linked_scope"):
                if s.get(key):
                    entry[key] = s[key]
            break
    return entry


def _sync_meta(root: Path, live: list[dict] | None) -> dict:
    """Load .sessions.json reconciled against the live tmux listing.

    - ``live is None`` (listing failed) → return the registry untouched.
      Never prune on a failed listing: one transient tmux error would
      otherwise wipe every session's workspace mapping.
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
    # The current ``neurona-`` prefix is shared by every vault. Keep
    # only sessions already owned by this registry or whose deterministic
    # hash/name parses for this root; otherwise each vault scan would
    # adopt every other vault's sessions into its own sessions.json.
    live = [
        row for row in live
        if row.get("name") in meta or _parse_tmux_name(root, str(row.get("name") or "")) is not None
    ]
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
            socket_name = str(
                s.get("tmux_socket") or tmux_sockets.DEFAULT_SOCKET
            )
            if meta[n].get("tmux_socket") != socket_name:
                meta[n]["tmux_socket"] = socket_name
                changed = True
            continue
        entry = _reconstruct_meta_entry(
            root,
            n,
            created=s.get("created", 0),
            tmux_socket=str(
                s.get("tmux_socket") or tmux_sockets.DEFAULT_SOCKET
            ),
        )
        if entry:
            meta[n] = entry
            changed = True
            log.info(
                "terminal registry recovered live tmux session %s",
                n,
                extra={
                    "event_type": "term.registry.recover",
                    "target": n,
                    "action": entry.get("workspace_id"),
                },
            )
    if changed:
        # Best-effort: the reconciled registry is still valid in memory, so
        # session listing must keep working even when the vault's volume
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


def _tmux_command(socket_name: str, *args: str) -> list[str]:
    """Build a socket-aware tmux argv without changing default commands."""
    return tmux_sockets.command(socket_name, *args)


def _active_tmux_socket() -> str:
    return tmux_sockets.active_socket()


def _tmux_server_alive(socket_name: str) -> bool:
    """Whether an already-seeded tmux server is reachable."""
    if not _tmux_available():
        return False
    proc = subprocess.run(
        _tmux_command(socket_name, "show-options", "-gv", "exit-empty"),
        capture_output=True,
        text=True,
        env=_tmux_child_env(),
    )
    return proc.returncode == 0


def _is_lab_tmux_name(name: str) -> bool:
    prefix = os.environ.get("LAB_TMUX_PREFIX")
    if prefix:
        return name.startswith(prefix)
    return name.startswith(_SESSION_PREFIX) or name.startswith("lab-")


def _tmux_list(
    prefixes: str | list[str], *, prune_draining: bool = True,
) -> list[dict] | None:
    """Return live tmux sessions whose names start with any of ``prefixes``.

    ``prefixes`` may be a single string (back-compat with callers that only
    know about one naming scheme) or a list (discovery across multiple
    schemes — see ``_tmux_discovery_prefixes``).

    Returns ``None`` when the listing itself FAILED — tmux binary missing,
    or ``tmux list-sessions`` errored for any reason other than "no server
    running" (which genuinely means zero sessions and maps to ``[]``).
    None means *unknown*, not *empty*: callers must never prune registry
    state on a failed listing — a single transient tmux error used to wipe
    every session's workspace mapping from .sessions.json (2026-06-10).
    """
    if not _tmux_available():
        return None
    if isinstance(prefixes, str):
        prefixes = [prefixes]
    rows: list[dict] = []
    lab_rows_by_socket: dict[str, int] = {}
    generations = tmux_sockets.generations()
    for generation in generations:
        socket_name = str(generation["name"])
        proc = subprocess.run(
            _tmux_command(
                socket_name,
                "list-sessions",
                "-F",
                (
                    "#{session_name}|#{session_created}|#{session_attached}|"
                    "#{session_windows}|#{pane_tty}|#{pane_pid}"
                ),
            ),
            capture_output=True,
            text=True,
            env=_tmux_child_env(),
        )
        if proc.returncode != 0:
            err = (proc.stderr or "").lower()
            if tmux_sockets.is_no_server_error(err):
                lab_rows_by_socket[socket_name] = 0
                continue
            log.warning(
                "tmux list-sessions failed on socket %s: %s",
                socket_name,
                (proc.stderr or proc.stdout or "").strip()[:500],
                extra={
                    "event_type": "term.tmux.list_failed",
                    "target": socket_name,
                },
            )
            return None

        lab_count = 0
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("|")
            name = parts[0]
            if _is_lab_tmux_name(name):
                lab_count += 1
            if not any(name.startswith(p) for p in prefixes):
                continue
            rows.append({
                "name": name,
                "created": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0,
                "attached": parts[2] != "0" if len(parts) > 2 else False,
                "windows": int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1,
                "pane_tty": parts[4] if len(parts) > 4 else "",
                "pane_pid": int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 0,
                "tmux_socket": socket_name,
            })
        lab_rows_by_socket[socket_name] = lab_count

    empty_draining = {
        str(row["name"])
        for row in generations
        if row.get("status") == "draining"
        and lab_rows_by_socket.get(str(row["name"])) == 0
    }
    if empty_draining and prune_draining:
        try:
            tmux_sockets.prune_drained(empty_draining)
        except OSError:
            log.warning("failed to prune drained tmux socket state", exc_info=True)
    return rows


def _tmux_has_session(name: str, socket_name: str | None = None) -> bool:
    if not _tmux_available():
        return False
    sockets = [socket_name] if socket_name else tmux_sockets.socket_names()
    for candidate in sockets:
        proc = subprocess.run(
            _tmux_command(str(candidate), "has-session", "-t", name),
            capture_output=True,
            text=True,
            env=_tmux_child_env(),
        )
        if proc.returncode == 0:
            return True
    return False


def _tmux_find_session_socket(
    name: str,
    preferred_socket: str | None = None,
) -> str | None:
    if not _tmux_available():
        return None
    sockets = tmux_sockets.socket_names()
    if preferred_socket in sockets:
        sockets = [str(preferred_socket)] + [
            socket_name for socket_name in sockets
            if socket_name != preferred_socket
        ]
    # Preserve the historical one-argument helper call in steady state.
    # Besides keeping monkeypatched integrations compatible, this makes the
    # normal one-socket path exactly one has-session subprocess.
    if len(sockets) == 1:
        return sockets[0] if _tmux_has_session(name) else None
    for socket_name in sockets:
        if _tmux_has_session(name, socket_name):
            return socket_name
    return None


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


def _configure_tmux_wheel_scrolling(
    session_name: str,
    socket_name: str = tmux_sockets.DEFAULT_SOCKET,
) -> None:
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
        _tmux_command(socket_name, "set-option", "-t", session_name, "mouse", "on"),
        capture_output=True, text=True, env=env,
    )
    # Keep altscreen-app output (git log's pager, less, man, etc.) in the
    # main buffer so it lands in scrollback after the app exits. Default
    # `alternate-screen on` wipes the pane back to pre-command state on
    # exit, which reads as "the terminal cleared my output."
    subprocess.run(
        _tmux_command(
            socket_name,
            "set-option",
            "-t",
            session_name,
            "alternate-screen",
            "off",
        ),
        capture_output=True, text=True, env=env,
    )
    subprocess.run(
        _tmux_command(
            socket_name,
            "bind-key",
            "-T",
            "root",
            "WheelUpPane",
            "if-shell",
            "-F",
            "#{||:#{pane_in_mode},#{mouse_any_flag}}",
            "send-keys -M",
            "copy-mode -e",
        ),
        capture_output=True, text=True, env=env,
    )
    # Wheel-down: let tmux's built-in copy-mode-vi/emacs table handle it.
    # Reset any prior root-table override so we don't inherit garbage from
    # an earlier run of this process.
    subprocess.run(
        _tmux_command(
            socket_name,
            "unbind-key",
            "-T",
            "root",
            "WheelDownPane",
        ),
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

    These spawn a fresh session (Copilot's caller-owned UUID is appended by the
    create route). Raises HTTPException if the CLI is missing so the UI can
    surface a clean "not installed" message instead of an opaque tmux failure.
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


def _session_hash(vault: str, workspace_sane: str, tab_sane: str) -> str:
    """Deterministic 6-hex marker appended to current-scheme session names.

    Vault ownership stays in this hash even though it is no longer a
    visible name segment. Hashing sanitized values keeps generation and
    parsing byte-for-byte consistent.
    """
    payload = f"{_SESSION_PREFIX}{vault}/{workspace_sane}/{tab_sane}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:6]


def _tmux_name_for(workspace_id: str | None, logical_name: str,
                   root: Path | None = None) -> str:
    """Build the tmux session name.

    - ``LAB_TMUX_PREFIX`` set (tests / opt-out): ``<prefix><workspace>-<tab>``,
      exactly the pre-nomenclature format.
    - Otherwise: ``neurona-<workspace>-<tab>-<hash6>``. The vault's stable
      registry id is folded into ``<hash6>`` rather than exposed in the
      visible name, so identical workspace/tab pairs in different vaults
      remain collision-free.

    When no workspace is given (rare — standalone terminals) we fall back to a
    UUID so the name is globally unique.
    """
    env_prefix = os.environ.get("LAB_TMUX_PREFIX")
    if not workspace_id:
        if env_prefix:
            return env_prefix + uuid.uuid4().hex[:8]
        return _new_scheme_prefix() + uuid.uuid4().hex[:8]
    workspace_sane = _sanitize(workspace_id)
    tab_sane = _sanitize(logical_name)
    if env_prefix:
        return env_prefix + workspace_sane + "-" + tab_sane
    vault = _resolve_vault_label(root)
    digest = _session_hash(vault, workspace_sane, tab_sane)
    return f"{_SESSION_PREFIX}{workspace_sane}-{tab_sane}-{digest}"


def _legacy_vault_tmux_name_for(
    workspace_id: str, logical_name: str, root: Path | None,
) -> str:
    """Exact name emitted by the preceding vault-visible generation."""
    vault = _resolve_vault_label(root)
    workspace_sane = _sanitize(workspace_id)
    tab_sane = _sanitize(logical_name)
    digest = _session_hash(vault, workspace_sane, tab_sane)
    return f"{_SESSION_PREFIX}{vault}-{workspace_sane}-{tab_sane}-{digest}"


def _attach_command(
    name: str,
    socket_name: str = tmux_sockets.DEFAULT_SOCKET,
) -> str:
    """Exact command to attach to this tmux session from any terminal."""
    if socket_name != tmux_sockets.DEFAULT_SOCKET:
        return f"tmux -L '{socket_name}' attach -t '{name}'"
    return f"tmux attach -t '{name}'"


def _pick_unique_logical_name(preferred: str, taken_logical_names: set[str]) -> str:
    """Return a logical_name that doesn't collide with a DIFFERENT live tab.

    ``taken_logical_names`` is the set of logical (tab) names already live
    for this workspace. Callers only reach this when they've already
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


class LinkedScope(BaseModel):
    # Sidebar identity is independent of the process cwd and optional file link.
    base_root: str = Field(min_length=1, max_length=4096)
    project_root: str = Field(min_length=1, max_length=4096)
    root: str = Field(min_length=1, max_length=4096)
    worktree: str | None = Field(default=None, max_length=4096)
    label: str = Field(default="Root", max_length=512)
    color: str = Field(default="#6e7681", pattern=r"^#[0-9a-fA-F]{6}$")
    config_scope: str = Field(default="", max_length=4096)


class NewSession(BaseModel):
    workspace_id: str | None = None
    vault: str | None = None
    cwd: str | None = None
    linked_scope: LinkedScope | None = None
    # "claude" spawns `claude` with --permission-mode auto + --session-id
    # (generated UUID on first launch, saved to workspace.json, reused via
    # --resume on subsequent creates of the same name).
    # "terminal" spawns the user's $SHELL (or bash).
    kind: str = "claude"
    # Which agent CLI to launch for kind=="claude". None → resolve from the
    # workspace override / global default in .agents/config.json. One of
    # VALID_AGENTS (claude | codex | copilot).
    agent: str | None = None
    # Optional explicit logical name. Defaults: agent name / "bash".
    name: str | None = None
    # Only meaningful when kind == "claude". None → the vault's
    # per-agent autopilot setting decides (claude defaults on; see
    # lab.settings.DEFAULTS["autopilot"]). Explicit true/false wins.
    auto: bool | None = None
    # When True, ignore any saved claude_session_id and start a brand-new
    # conversation (new UUID). Used by the manual "+ New Claude" picker.
    start_fresh: bool = False


class AttachSession(BaseModel):
    workspace_id: str
    vault: str | None = None
    name: str


# ─── endpoints ──────────────────────────────────────────────────────────────


# NOTE: every endpoint below that shells out to tmux (or touches the
# filesystem) is deliberately a *sync* ``def`` — FastAPI runs those in its
# thread pool. As ``async def`` they ran their blocking ``subprocess.run``
# calls ON the event loop, stalling every live terminal WebSocket for the
# duration of each tmux spawn (a few ms, several times per second under the
# UI's polling) — visible as typing-echo jitter.

def _sessions_for_root(
    root: Path, workspace_id: str | None, *, include_agent_details: bool = True,
) -> list[dict]:
    """One vault's live session rows (optionally scoped to
    ``workspace_id``), with the runtime registry reconciled against the live
    tmux listing. Factored out of ``list_sessions`` so the "every
    vault" path can reuse it per vault without duplicating the
    tmux-list + meta-sync + row-shaping logic."""
    prefixes = _tmux_discovery_prefixes(root)
    listing = _tmux_list(prefixes)
    meta = _sync_meta(root, listing)
    # _sync_meta filters the vault-neutral ``neurona-`` listing down to
    # sessions attributable to this root. Runtime metadata is therefore the
    # ownership boundary for the rows returned here.
    live = {s["name"]: s for s in (listing or []) if s["name"] in meta}

    rows: list[dict] = []
    saved_by_logical = _workspace_session_by_name(root, workspace_id) if workspace_id else {}
    for name, info in live.items():
        row = {**info, **meta.get(name, {}), "name": name}
        socket_name = str(
            row.get("tmux_socket") or tmux_sockets.DEFAULT_SOCKET
        )
        row["tmux_socket"] = socket_name
        row["attach_command"] = _attach_command(name, socket_name)
        if workspace_id and row.get("workspace_id") != workspace_id:
            continue
        logical = row.get("logical_name")
        saved = saved_by_logical.get(logical) if isinstance(logical, str) else None
        if saved:
            for key in ("label", "summary", "linked_file", "linked_scope"):
                if saved.get(key):
                    row[key] = saved[key]
        rows.append(row)
    # Agent titles/tasks and capture-pane summaries are useful in the active
    # workspace's terminal UI, but the unscoped endpoint is polled every five
    # seconds by the dashboard/top tabs and consumes none of those fields.
    # Avoid ps, SQLite and one tmux capture per row on that global hot path.
    if include_agent_details:
        _enrich_agent_session_names(rows)
        for row in rows:
            if row.get("summary"):
                continue
            agent_summary = row.get("agent_session_summary")
            if agent_summary:
                row["summary"] = agent_summary
                continue
            inferred = _infer_session_summary(
                str(row.get("name") or ""),
                str(row.get("tmux_socket") or tmux_sockets.DEFAULT_SOCKET),
            )
            if inferred:
                row["summary"] = inferred
    return rows


@router.get("/api/term/sessions")
def list_sessions(
    request: Request, workspace_id: str | None = None, vault: str | None = None,
) -> list[dict]:
    """List live tmux sessions for a workspace (or all workspaces/vaults).

    Scoped to ``workspace_id``: sessions in the requested ``vault`` (or
    the active vault when omitted). Unscoped: every REGISTERED
    vault's sessions, each tagged with ``vault`` (registry id) —
    this is what the cross-vault terminals dashboard needs. A vault
    whose path is missing/stalled is skipped for that cycle (fsguard 503,
    or an OSError from an unmounted/unreadable volume) rather than failing
    the whole request.

    Only returns sessions that are currently alive in tmux. Saved-but-dead
    sessions (stored in workspace.json) are surfaced separately via
    ``/api/term/sessions/saved``.
    """
    active_root = auth.request_root(request)

    if workspace_id:
        root = _vault_root_for(active_root, vault)
        _require_workspace_access(request, active_root, root, workspace_id)
        rows = _sessions_for_root(root, workspace_id)
        # Order preference: if the workspace has a saved ``sessions[]`` array
        # (in workspace.json), use that order as the source of truth — this
        # is what powers the "drag pills to reorder" UX. Sessions with no
        # saved entry (edge case: spawned out-of-band) get appended in
        # tmux-creation order.
        saved = _get_workspace_sessions(root, workspace_id)
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
    user = auth.require_user(request)
    for vault_row in _known_vaults(active_root):
        if not auth.can_access_vault(user, str(vault_row["id"])):
            continue
        try:
            ws_rows = fsguard.guarded(
                vault_row["path"], _sessions_for_root, vault_row["path"], None,
                include_agent_details=False,
            )
        except HTTPException as exc:
            if exc.status_code != 503:
                raise
            continue
        except OSError as exc:
            # Same degradation as the fsguard 503 above: a vault whose
            # volume is missing or unreadable is skipped this cycle instead
            # of failing the listing for every other vault.
            _warn_root_unavailable_once(vault_row["path"], "session listing", exc)
            continue
        for r in ws_rows:
            r["vault"] = vault_row["id"]
        rows.extend(ws_rows)
    rows.sort(key=lambda r: r.get("created", 0), reverse=True)
    return rows


@router.get("/api/term/sessions/attachable")
def list_attachable_sessions(
    request: Request, workspace_id: str, vault: str | None = None,
) -> list[dict]:
    """List live tmux sessions for the attach-session picker.

    Unlike the normal session list, admins also see otherwise-unregistered
    sessions on Lab's active/draining tmux sockets. Registered sessions are
    enriched with their owning vault/workspace so the client can group the
    picker. Non-admins only see sessions already registered in vaults they
    can access; importing an arbitrary host session remains admin-only, just
    like the attach endpoint itself.
    """
    active_root = auth.request_root(request)
    target_root = _vault_root_for(active_root, vault)
    user = _require_workspace_access(
        request, active_root, target_root, workspace_id,
    )
    target_vault = _vault_id_for_root(active_root, target_root)

    registered: dict[tuple[str, str], dict] = {}
    # A tmux client is not what makes a session "attached" in this picker.
    # The useful distinction is whether Lab already has a terminal tab for
    # it.  Map both registered sessions and the sources behind grouped
    # aliases to the Lab tab that represents them.
    tabs_by_source: dict[str, dict] = {}
    for vault_row in _known_vaults(active_root):
        vault_id = str(vault_row["id"])
        if not auth.can_access_vault(user, vault_id):
            continue
        try:
            ws_rows = fsguard.guarded(
                vault_row["path"], _sessions_for_root, vault_row["path"], None,
                include_agent_details=False,
            )
        except HTTPException as exc:
            if exc.status_code != 503:
                raise
            continue
        except OSError as exc:
            _warn_root_unavailable_once(
                vault_row["path"], "attachable session listing", exc,
            )
            continue

        workspace_names: dict[str, str] = {}
        for row in ws_rows:
            owner_workspace = str(row.get("workspace_id") or "")
            if owner_workspace not in workspace_names:
                workspace_doc = _load_workspace(vault_row["path"], owner_workspace)
                workspace_names[owner_workspace] = str(
                    (workspace_doc or {}).get("name") or owner_workspace
                )
            enriched = {
                **row,
                "vault": vault_id,
                "workspace_name": workspace_names[owner_workspace],
            }
            socket_name = str(
                enriched.get("tmux_socket") or tmux_sockets.DEFAULT_SOCKET
            )
            registered[(socket_name, str(enriched["name"]))] = enriched
            tab = {
                "session_name": str(enriched["name"]),
                "workspace_id": owner_workspace,
                "workspace_name": workspace_names[owner_workspace],
                "vault": vault_id,
            }
            tabs_by_source.setdefault(str(enriched["name"]), tab)
            if enriched.get("kind") == "attached" and enriched.get("source_session"):
                tabs_by_source.setdefault(str(enriched["source_session"]), tab)

    # This scan includes unregistered sessions, so it must not prune a
    # draining socket merely because that socket has no Lab-owned sessions.
    live = _tmux_list([""], prune_draining=False)
    if live is None:
        raise HTTPException(
            status_code=503,
            detail="tmux sessions are temporarily unavailable",
        )

    rows: list[dict] = []
    seen_names: set[str] = set()
    for live_row in live:
        name = str(live_row.get("name") or "")
        # The attach endpoint currently identifies a source by name, not by
        # socket. If a rolling generation happens to contain the same name,
        # show the active generation's first match only so the picker cannot
        # imply a socket choice the attach operation does not support.
        if (
            not name
            or name in seen_names
            or len(name) > 200
            or not _VALID_WS_NAME.fullmatch(name)
        ):
            continue
        seen_names.add(name)
        socket_name = str(
            live_row.get("tmux_socket") or tmux_sockets.DEFAULT_SOCKET
        )
        row = registered.get((socket_name, name))
        if row is None:
            if not auth.is_admin(user):
                continue
            row = {
                **live_row,
                "name": name,
                "logical_name": name,
                "workspace_id": None,
                "workspace_name": "Unassigned",
                "vault": None,
                "kind": "tmux",
                "agent": None,
                "tmux_socket": socket_name,
                "attach_command": _attach_command(name, socket_name),
            }
        else:
            row = {**row}
            # Grouped aliases are implementation details of an existing Lab
            # tab.  Their original source is listed instead and carries that
            # tab's status, avoiding duplicate rows for the same terminal.
            if row.get("kind") == "attached":
                continue
        tab = tabs_by_source.get(name)
        row["has_ui_tab"] = tab is not None
        if tab:
            row["tab_session_name"] = tab["session_name"]
            row["tab_workspace_id"] = tab["workspace_id"]
            row["tab_workspace_name"] = tab["workspace_name"]
            row["tab_vault"] = tab["vault"]
            row["tab_in_current_workspace"] = (
                tab["vault"] == target_vault
                and tab["workspace_id"] == workspace_id
            )
        else:
            row["tab_in_current_workspace"] = False
        # Preserve the narrower legacy meaning for cached clients: this was
        # always "already added to the picker target", not "has any Lab tab".
        row["already_added"] = row["tab_in_current_workspace"]
        row["current_workspace"] = (
            row.get("vault") == target_vault
            and row.get("workspace_id") == workspace_id
        )
        rows.append(row)

    return rows


class SessionOrder(BaseModel):
    workspace_id: str
    vault: str | None = None
    order: list[str]  # logical_names in the desired order


class LinkedFile(BaseModel):
    root: str
    path: str


class SessionMetadata(BaseModel):
    workspace_id: str
    vault: str | None = None
    # Saved logical session name, not the tmux name. Display labels must not
    # rename tmux sessions because that would break attach/resume semantics.
    name: str
    label: str | None = None
    summary: str | None = None
    # A terminal has one primary file. Several terminals may independently
    # point at the same file (for example, one Codex and one Copilot tab).
    linked_file: LinkedFile | None = None
    linked_scope: LinkedScope | None = None


class PastedImage(BaseModel):
    workspace_id: str
    vault: str | None = None
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
    """Reorder the workspace's saved sessions[] so /api/term/sessions reflects
    the new pill order. Any saved session not listed is appended in its
    original relative order."""
    active_root = auth.request_root(request)
    root = _vault_root_for(active_root, body.vault)
    _require_workspace_access(request, active_root, root, body.workspace_id)
    data = _load_workspace(root, body.workspace_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"workspace {body.workspace_id!r} not found")
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
    _save_workspace(root, body.workspace_id, data)
    _invalidate_workspace_term_caches()
    return {"ok": True, "order": [s.get("name") for s in new_list]}


@router.patch("/api/term/sessions/metadata")
def update_session_metadata(body: SessionMetadata, request: Request) -> dict:
    """Persist user-facing metadata for a saved logical session."""
    active_root = auth.request_root(request)
    root = _vault_root_for(active_root, body.vault)
    _require_workspace_access(request, active_root, root, body.workspace_id)
    data = _load_workspace(root, body.workspace_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"workspace {body.workspace_id!r} not found")
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
    if "linked_file" in fields:
        if body.linked_file is None:
            entry.pop("linked_file", None)
        else:
            file_root = str(body.linked_file.root or "").strip()
            file_path = str(body.linked_file.path or "").strip()
            if not file_root or not file_path:
                raise HTTPException(
                    status_code=400,
                    detail="linked_file requires non-empty root and path",
                )
            if len(file_root) > 4096 or len(file_path) > 4096:
                raise HTTPException(status_code=400, detail="linked_file path is too long")
            entry["linked_file"] = {"root": file_root, "path": file_path}

    if "linked_scope" in fields:
        if body.linked_scope is None:
            entry.pop("linked_scope", None)
        else:
            entry["linked_scope"] = body.linked_scope.model_dump()

    data["sessions"] = sessions
    _save_workspace(root, body.workspace_id, data)

    tmux_name = _tmux_name_for(body.workspace_id, body.name, root)
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
        if "linked_file" in fields:
            if entry.get("linked_file"):
                meta[tmux_name]["linked_file"] = entry["linked_file"]
            else:
                meta[tmux_name].pop("linked_file", None)
        if "linked_scope" in fields:
            if entry.get("linked_scope"):
                meta[tmux_name]["linked_scope"] = entry["linked_scope"]
            else:
                meta[tmux_name].pop("linked_scope", None)
        _save_meta(root, meta)
    _invalidate_workspace_term_caches()

    log.info(
        "terminal session metadata updated",
        extra={
            "event_type": "term.session.metadata",
            "action": body.workspace_id,
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
    active_root = auth.request_root(request)
    root = _vault_root_for(active_root, body.vault)
    _require_workspace_access(request, active_root, root, body.workspace_id)
    if not body.workspace_id:
        raise HTTPException(status_code=400, detail="workspace_id is required")
    cwd = _workspace_cwd(root, body.workspace_id)
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
            "action": body.workspace_id,
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


# ─── Session-derived summary + workspace-list caches ─────────────────────────
_SUMMARY_CACHE: dict[str, tuple[float, str]] = {}
_SUMMARY_TTL_S = 60.0
_WORKSPACES_CACHE_TTL_S = 8.0
_WORKSPACES_WITH_SESSIONS_CACHE: tuple[float, list[str]] | None = None


def _invalidate_workspace_term_caches() -> None:
    global _WORKSPACES_WITH_SESSIONS_CACHE
    _WORKSPACES_WITH_SESSIONS_CACHE = None


def _fresh_workspace_cache(cache: tuple[float, list[str]] | None) -> list[str] | None:
    if not cache:
        return None
    ts, value = cache
    if time.monotonic() - ts >= _WORKSPACES_CACHE_TTL_S:
        return None
    return list(value)


@router.get("/api/term/sessions/saved")
def list_saved_sessions(
    request: Request, workspace_id: str, vault: str | None = None,
) -> list[dict]:
    """List sessions saved in the workspace's workspace.json (may or may not be live)."""
    active_root = auth.request_root(request)
    root = _vault_root_for(active_root, vault)
    _require_workspace_access(request, active_root, root, workspace_id)
    return _get_workspace_sessions(root, workspace_id)


@router.get("/api/term/workspaces-with-sessions")
def workspaces_with_sessions(request: Request) -> list[str]:
    """Workspace IDs that currently have at least one live tmux session.

    Drives the topbar tab strip (tabs == workspaces with active sessions).
    Code Search per-repo pseudo-workspaces (``__cs_<repo>__``) are
    filtered out — they aren't standalone tabs, they're driven by the
    single ``🔍 code-search`` pseudo-tab and the in-tab repo picker.
    """
    global _WORKSPACES_WITH_SESSIONS_CACHE
    user = auth.require_user(request)
    if not auth.is_admin(user):
        active_root = auth.request_root(request)
        ids: list[str] = []
        for vault_row in _known_vaults(active_root):
            if not auth.can_access_vault(user, str(vault_row["id"])):
                continue
            listing = _tmux_list(_tmux_discovery_prefixes(vault_row["path"]))
            meta = _sync_meta(vault_row["path"], listing)
            for name in {item["name"] for item in (listing or [])}:
                workspace_id = (meta.get(name) or {}).get("workspace_id")
                if not workspace_id or workspace_id in ids or str(workspace_id).startswith("__"):
                    continue
                ids.append(workspace_id)
        return ids
    cached = _fresh_workspace_cache(_WORKSPACES_WITH_SESSIONS_CACHE)
    if cached is not None:
        return cached

    root = auth.request_root(request)
    prefixes = _tmux_discovery_prefixes(root)
    listing = _tmux_list(prefixes)
    meta = _sync_meta(root, listing)
    live_names = {s["name"] for s in (listing or [])}
    ids: list[str] = []
    for name in live_names:
        info = meta.get(name) or {}
        pid = info.get("workspace_id")
        if not pid or pid in ids:
            continue
        if _cs_repo_name(pid):
            continue
        ids.append(pid)
    _WORKSPACES_WITH_SESSIONS_CACHE = (time.monotonic(), list(ids))
    return ids


@router.post("/api/term/sessions/attach")
def attach_session(body: AttachSession, request: Request) -> dict:
    """Expose an existing tmux session as a safe Lab-owned grouped alias.

    The alias shares the source session's windows and panes, so browser input
    and output are the same session. Killing the Lab alias does not kill the
    original session. No nested tmux client, proxy process, or byte-path
    forwarding is introduced.
    """
    if not _tmux_available():
        raise HTTPException(status_code=500, detail="tmux not installed. Run: brew install tmux")

    source_name = (body.name or "").strip()
    if len(source_name) > 200 or not _VALID_WS_NAME.fullmatch(source_name):
        raise HTTPException(
            status_code=400,
            detail="invalid tmux session name; use letters, digits, underscores, or hyphens",
        )

    active_root = auth.request_root(request)
    root = _vault_root_for(active_root, body.vault)
    user = _require_workspace_access(request, active_root, root, body.workspace_id)
    cwd = _workspace_cwd(root, body.workspace_id)
    if not cwd.is_dir():
        raise HTTPException(status_code=400, detail=f"workspace directory not found: {cwd}")

    # A registered Lab session retains its vault access boundary. An
    # otherwise-unregistered host tmux session may contain anything, so only
    # an admin can import it into Lab by name.
    owner: tuple[Path, dict] | None = None
    for vault_row in _known_vaults(active_root):
        try:
            candidate = (_load_meta(vault_row["path"]).get(source_name) or {})
        except OSError:
            continue
        if candidate:
            owner = (vault_row["path"], candidate)
            break
    if owner:
        _require_workspace_access(
            request,
            active_root,
            owner[0],
            owner[1].get("workspace_id"),
        )
    elif not auth.is_admin(user):
        raise HTTPException(
            status_code=403,
            detail="admin access is required to attach an unregistered tmux session",
        )

    meta = _load_meta(root)
    for alias_name, info in meta.items():
        if (
            info.get("workspace_id") == body.workspace_id
            and info.get("kind") == "attached"
            and info.get("source_session") == source_name
        ):
            alias_socket = _tmux_find_session_socket(
                alias_name,
                str(info.get("tmux_socket") or "") or None,
            )
            if alias_socket:
                info["tmux_socket"] = alias_socket
                return {
                    "name": alias_name,
                    **info,
                    "already_running": True,
                    "attach_command": _attach_command(alias_name, alias_socket),
                }

    taken_logical = {
        str(info.get("logical_name"))
        for info in meta.values()
        if info.get("workspace_id") == body.workspace_id and info.get("logical_name")
    }
    logical = _pick_unique_logical_name(_sanitize(source_name), taken_logical)

    # Rotation and new-session creation use the same lock. This prevents a
    # source found on the draining generation from being pruned between the
    # lookup and creation of its grouped alias.
    with tmux_sockets.state_lock():
        source_socket = _tmux_find_session_socket(source_name)
        if not source_socket:
            raise HTTPException(
                status_code=404,
                detail=f"tmux session {source_name!r} was not found on a Lab socket",
            )
        alias_name = _tmux_name_for(body.workspace_id, logical, root)
        while _tmux_find_session_socket(alias_name):
            taken_logical.add(logical)
            logical = _pick_unique_logical_name(_sanitize(source_name), taken_logical)
            alias_name = _tmux_name_for(body.workspace_id, logical, root)
        proc = subprocess.run(
            _tmux_command(
                source_socket,
                "new-session",
                "-d",
                "-t",
                source_name,
                "-s",
                alias_name,
            ),
            capture_output=True,
            text=True,
            env=_tmux_child_env(),
        )
    if proc.returncode != 0:
        raise HTTPException(
            status_code=409,
            detail=(proc.stderr or proc.stdout or "tmux could not attach the session").strip(),
        )

    _configure_tmux_wheel_scrolling(alias_name, source_socket)
    entry = {
        "workspace_id": body.workspace_id,
        "logical_name": logical,
        "kind": "attached",
        "agent": None,
        "cwd": str(cwd),
        "cmd": _attach_command(source_name, source_socket),
        "source_session": source_name,
        "created_at": int(time.time()),
        "tmux_socket": source_socket,
    }
    meta = _load_meta(root)
    meta[alias_name] = entry
    _save_meta(root, meta)
    _upsert_workspace_session(root, body.workspace_id, {
        "name": logical,
        "kind": "attached",
        "source_session": source_name,
    })
    _invalidate_workspace_term_caches()
    log.info(
        "existing tmux session attached through grouped alias",
        extra={
            "event_type": "term.session.attach_existing",
            "action": body.workspace_id,
            "target": alias_name,
        },
    )
    return {
        "name": alias_name,
        **entry,
        "attach_command": _attach_command(alias_name, source_socket),
    }


@router.post("/api/term/sessions")
def create_session(body: NewSession, request: Request) -> dict:
    """Create (or re-attach / resume) a named session.

    Behavior:
    - If a live tmux session with the computed name exists: return it as-is.
    - Else: spawn a new tmux session. For kind == "claude", use the saved
      claude_session_id (via ``--resume``) if workspace.json has one and
      ``start_fresh`` is False; otherwise generate a new UUID and record it
      in workspace.json via ``--session-id``.
    """
    if not _tmux_available():
        raise HTTPException(status_code=500, detail="tmux not installed. Run: brew install tmux")

    kind = (body.kind or "claude").lower()
    if kind not in ("claude", "terminal"):
        raise HTTPException(status_code=400, detail=f"unknown kind: {kind}")

    active_root = auth.request_root(request)
    root = _vault_root_for(active_root, body.vault)
    _require_workspace_access(request, active_root, root, body.workspace_id)

    # For agent sessions (kind=="claude"), resolve which CLI to launch:
    # explicit body.agent → workspace override → global default. The result
    # must be enabled for this vault (vault.json agents.supported):
    # an explicit request for a disabled agent errors; a default that fell
    # out of the enabled set silently clamps to the first enabled agent.
    agent: str | None = None
    if kind == "claude":
        agent = (body.agent or lab_settings.resolve_agent(root, body.workspace_id)).lower()
        if agent not in lab_settings.VALID_AGENTS:
            raise HTTPException(status_code=400, detail=f"unknown agent: {agent!r}")
        supported = vault_config.supported_agents(root)
        if agent not in supported:
            if body.agent:
                raise HTTPException(
                    status_code=400,
                    detail=f"agent {agent!r} is not enabled for this vault "
                           "(Vault tab → Agents)",
                )
            agent = supported[0]

    # Restores reuse their saved scope; new terminals capture the sidebar scope.
    saved_scope = None
    if body.workspace_id and not body.start_fresh:
        saved_session = _workspace_session_by_name(root, body.workspace_id).get(
            _sanitize(body.name or agent or "bash"), {}
        )
        saved_scope = saved_session.get("linked_scope")
    linked_scope = body.linked_scope.model_dump() if body.linked_scope else saved_scope
    # Resolve cwd.
    if body.cwd:
        cwd = Path(body.cwd).resolve()
    elif linked_scope:
        cwd = Path(linked_scope["root"]).resolve()
    elif body.workspace_id:
        cwd = _workspace_cwd(root, body.workspace_id)
    else:
        cwd = root.resolve()
    if not cwd.is_dir():
        raise HTTPException(status_code=400, detail=f"cwd not a directory: {cwd}")

    # Discover every live session that could belong to this vault under
    # ANY generation of the naming scheme (current + the two pre-nomenclature
    # ones), and reconcile the runtime registry against it. This is what
    # lets us recognize "this workspace's codex tab is already live" even when
    # the live session's actual tmux name uses an older scheme than the one
    # `_tmux_name_for` would compute today — that mismatch used to spawn a
    # same-tab duplicate on every reopen after a naming-scheme or
    # vault-path change instead of attaching to what was already there.
    listing = _tmux_list(_tmux_discovery_prefixes(root))
    meta = _sync_meta(root, listing)
    live_by_name = {s["name"]: s for s in (listing or [])}

    # Default the logical name to the agent (claude/codex/copilot) so different
    # agents get distinct tmux sessions/tabs within the same workspace.
    preferred = body.name or (agent if kind == "claude" else _default_logical_name(kind))
    preferred_sane = _sanitize(preferred)

    # Live logical (tab) names already running for this workspace, and — if
    # one of them IS the tab we're about to (re)open — its live tmux name +
    # runtime entry, regardless of which naming scheme produced that name.
    live_logical_names: set[str] = set()
    existing_for_tab: tuple[str, dict] | None = None
    for name, info in meta.items():
        if name not in live_by_name or info.get("workspace_id") != body.workspace_id:
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
        socket_name = str(
            info.get("tmux_socket") or tmux_sockets.DEFAULT_SOCKET
        )
        row = {"name": name, **info, "already_running": True,
               "tmux_socket": socket_name,
               "attach_command": _attach_command(name, socket_name)}
        if body.workspace_id:
            saved = _workspace_session_by_name(root, body.workspace_id).get(
                info.get("logical_name") or preferred_sane
            )
            if saved:
                for key in ("label", "summary", "linked_file", "linked_scope"):
                    if saved.get(key):
                        row[key] = saved[key]
        log.info(
            "terminal session already running",
            extra={
                "event_type": "term.session.already_running",
                "action": body.workspace_id,
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
    tmux_name = _tmux_name_for(body.workspace_id, logical, root)

    # Final authoritative guard: a tmux session with this exact computed
    # name already exists (race with a concurrent create, a leftover from a
    # prior crash, or the deterministic hash landing on a name reused from
    # an earlier run) — adopt it rather than erroring or trying to spawn a
    # duplicate (which tmux itself would refuse anyway).
    existing_socket = _tmux_find_session_socket(tmux_name)
    if existing_socket:
        entry = (
            meta.get(tmux_name)
            or _reconstruct_meta_entry(
                root,
                tmux_name,
                tmux_socket=existing_socket,
            )
            or {
                "workspace_id": body.workspace_id,
                "logical_name": logical,
                "kind": kind,
                "agent": agent,
                "cwd": str(cwd),
                "created_at": int(time.time()),
            }
        )
        entry["tmux_socket"] = existing_socket
        meta[tmux_name] = entry
        _save_meta(root, meta)
        _invalidate_workspace_term_caches()
        log.info(
            "terminal session adopted (already live under computed name)",
            extra={
                "event_type": "term.session.adopted",
                "action": body.workspace_id,
                "target": tmux_name,
            },
        )
        return {"name": tmux_name, **entry, "already_running": True,
                "attach_command": _attach_command(tmux_name, existing_socket)}

    # Build the command line.
    auto_applied = False
    resumed_from = None
    claude_session_id = None
    agent_session_id = None
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
        # Look up a saved claude_session_id for this workspace+name.
        existing_id = None
        if body.workspace_id and not body.start_fresh:
            for s in _get_workspace_sessions(root, body.workspace_id):
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
        agent_session_id = claude_session_id
        cmd_argv = parts
    elif kind == "claude":
        # codex / copilot — fresh session (resume is Claude-only for now).
        # Same `auto` contract as claude: an explicit request wins,
        # otherwise the vault's per-agent autopilot setting decides.
        cmd_argv = _agent_argv(agent)
        if agent == "copilot":
            # Copilot accepts a caller-owned UUID. Keeping it in Lab's
            # registry lets the session-list endpoint read its generated
            # name from ~/.copilot/session-state/<uuid>/workspace.yaml.
            agent_session_id = str(uuid.uuid4())
            cmd_argv = cmd_argv + ["--session-id", agent_session_id]
        wants_auto = (
            body.auto
            if body.auto is not None
            else lab_settings.resolve_autopilot(root, agent)
        )
        if wants_auto:
            cmd_argv = cmd_argv + list(lab_settings.AUTOPILOT_FLAGS.get(agent, ()))
            auto_applied = True
    else:
        # kind == "terminal"
        shell = os.environ.get("SHELL") or shutil.which("bash") or "/bin/sh"
        cmd_argv = [shell, "-l"]

    # Spawn tmux. We pass argv via shell so tmux can parse it; simpler for
    # claude's flag expansion and matches what users see in `tmux ls`.
    cmd_str = " ".join(_shell_quote(a) for a in cmd_argv)
    # Serialize just the routing decision + spawn with CLI rotation. This
    # prevents a terminal created concurrently with a handoff from landing
    # on the just-retired socket. The lock is never touched by terminal I/O.
    with tmux_sockets.state_lock():
        socket_name = _active_tmux_socket()
        if (
            socket_name != tmux_sockets.DEFAULT_SOCKET
            and not _tmux_server_alive(socket_name)
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"terminal socket {socket_name!r} is no longer running; "
                    "run `lab terminal rotate` directly from iTerm"
                ),
            )
        proc = subprocess.run(
            _tmux_command(
                socket_name,
                "new-session",
                "-d",
                "-s",
                tmux_name,
                "-c",
                str(cwd),
                cmd_str,
            ),
            capture_output=True,
            text=True,
            env=_tmux_child_env(),
        )
    if proc.returncode != 0:
        log.error(
            "tmux new-session failed for %s: %s",
            tmux_name,
            (proc.stderr or proc.stdout or "").strip()[:500],
            extra={
                "event_type": "term.session.create_failed",
                "action": body.workspace_id,
                "target": tmux_name,
            },
        )
        raise HTTPException(status_code=500, detail=(proc.stderr or proc.stdout).strip() or "tmux failed")

    # Mouse wheel → tmux copy-mode scrollback (no send-keys fallback).
    _configure_tmux_wheel_scrolling(tmux_name, socket_name)

    # Record runtime metadata.
    meta = _load_meta(root)
    meta[tmux_name] = {
        "workspace_id": body.workspace_id,
        "logical_name": logical,
        "kind": kind,
        "agent": agent,
        "cwd": str(cwd),
        "cmd": cmd_str,
        "auto": auto_applied,
        "claude_session_id": claude_session_id,
        "agent_session_id": agent_session_id,
        "resumed_from": resumed_from,
        "created_at": int(time.time()),
        "tmux_socket": socket_name,
    }
    _save_meta(root, meta)
    _invalidate_workspace_term_caches()

    # Record durable provider identity (Claude resumes it; Copilot uses it for
    # display-name lookup even though reopening still starts a fresh session).
    if body.workspace_id:
        entry: dict = {"name": logical, "kind": kind}
        if linked_scope:
            entry["linked_scope"] = linked_scope
        if agent:
            entry["agent"] = agent
        if claude_session_id:
            entry["claude_session_id"] = claude_session_id
        if agent_session_id and agent != "claude":
            entry["agent_session_id"] = agent_session_id
        _upsert_workspace_session(root, body.workspace_id, entry)
        saved = _workspace_session_by_name(root, body.workspace_id).get(logical)
        if saved:
            for key in ("label", "summary", "linked_file", "linked_scope"):
                if saved.get(key):
                    meta[tmux_name][key] = saved[key]
            if any(saved.get(key) for key in ("label", "summary", "linked_file", "linked_scope")):
                _save_meta(root, meta)
        _invalidate_workspace_term_caches()

    log.info(
        "terminal session spawned",
        extra={
            "event_type": "term.session.spawn",
            "action": body.workspace_id,
            "target": tmux_name,
        },
    )
    return {
        "name": tmux_name,
        **meta[tmux_name],
        "attach_command": _attach_command(tmux_name, socket_name),
    }


@router.delete("/api/term/sessions/{name}")
def kill_session(name: str, request: Request, purge: bool = False) -> dict:
    """Kill a live session. The saved entry in workspace.json stays unless
    ``purge``.

    Accepts a session named for ANY registered vault, not just the
    active one (the cross-vault terminals dashboard needs to kill
    sessions it lists from other vaults) — the name is resolved back
    to its owning vault root so the runtime registry / servers
    desired-state hook below operate on the right vault's files.
    """
    active_root = auth.request_root(request)
    vaults = _known_vaults(active_root)
    prefixes = _tmux_discovery_prefixes_all(vaults)
    if not any(name.startswith(p) for p in prefixes):
        raise HTTPException(status_code=400, detail="invalid session name")

    root = _resolve_session_vault_root(name, active_root, vaults)
    meta = _load_meta(root)
    info = meta.get(name) or {}
    workspace_id = info.get("workspace_id")
    logical_name = info.get("logical_name")
    _require_workspace_access(request, active_root, root, workspace_id)

    if _tmux_available():
        socket_name = str(
            info.get("tmux_socket")
            or _tmux_find_session_socket(name)
            or tmux_sockets.DEFAULT_SOCKET
        )
        subprocess.run(
            _tmux_command(socket_name, "kill-session", "-t", name),
            capture_output=True,
            text=True,
            env=_tmux_child_env(),
        )
    meta.pop(name, None)
    _save_meta(root, meta)
    _invalidate_workspace_term_caches()

    if logical_name == "server" and workspace_id:
        # A managed dev-server tab was killed through the generic terminal
        # kill flow (not /api/servers/{id}/stop) — mark it desired=stopped so
        # the servers supervisor doesn't resurrect it on its next tick.
        # Imported lazily to avoid a module import cycle (servers.py imports
        # term at module scope; term.py must not import servers at module
        # scope).
        from core.routes import servers as servers_mod
        try:
            servers_mod.set_desired(root, workspace_id, "stopped")
        except Exception:  # pragma: no cover — best effort, never blocks the kill
            log.warning("failed to mark server desired=stopped for %s", workspace_id, exc_info=True)

    if purge and workspace_id and logical_name:
        data = _load_workspace(root, workspace_id)
        if data and isinstance(data.get("sessions"), list):
            data["sessions"] = [s for s in data["sessions"]
                                if not (isinstance(s, dict) and s.get("name") == logical_name)]
            _save_workspace(root, workspace_id, data)
            _invalidate_workspace_term_caches()

    log.info(
        "terminal session killed",
        extra={
            "event_type": "term.session.kill",
            "action": workspace_id,
            "target": name,
        },
    )
    return {"ok": True, "purged": purge}


@router.delete("/api/term/sessions/workspace/{workspace_id}")
def kill_workspace_sessions(
    workspace_id: str, request: Request, purge: bool = False, vault: str | None = None,
) -> dict:
    """Kill EVERY live session belonging to ``workspace_id``. Powers the tab X.

    Scoped to the active vault by default — unchanged behavior for the
    workspace tab strip's "X" button. Pass ``?vault=<id>`` to target a
    different registered vault instead (the cross-vault terminals
    dashboard needs this since the same workspace id can exist in more than
    one vault).
    """
    active_root = auth.request_root(request)
    if vault is not None:
        root = None
        for vault_row in _known_vaults(active_root):
            if vault_row["id"] == vault:
                root = vault_row["path"]
                break
        if root is None:
            raise HTTPException(status_code=404, detail=f"vault {vault!r} not found")
    else:
        root = active_root
    _require_workspace_access(request, active_root, root, workspace_id)

    prefixes = _tmux_discovery_prefixes(root)
    meta = _load_meta(root)
    killed: list[str] = []
    killed_server = False
    for name in list(meta.keys()):
        info = meta.get(name) or {}
        if info.get("workspace_id") != workspace_id:
            continue
        if not any(name.startswith(p) for p in prefixes):
            continue
        if _tmux_available():
            socket_name = str(
                info.get("tmux_socket")
                or _tmux_find_session_socket(name)
                or tmux_sockets.DEFAULT_SOCKET
            )
            subprocess.run(
                _tmux_command(socket_name, "kill-session", "-t", name),
                capture_output=True,
                text=True,
                env=_tmux_child_env(),
            )
        meta.pop(name, None)
        killed.append(name)
        if info.get("logical_name") == "server":
            killed_server = True
    _save_meta(root, meta)
    _invalidate_workspace_term_caches()

    if killed_server:
        # See the matching comment in kill_session() above.
        from core.routes import servers as servers_mod
        try:
            servers_mod.set_desired(root, workspace_id, "stopped")
        except Exception:  # pragma: no cover — best effort, never blocks the kill
            log.warning("failed to mark server desired=stopped for %s", workspace_id, exc_info=True)

    if purge:
        data = _load_workspace(root, workspace_id)
        if data and isinstance(data.get("sessions"), list):
            data["sessions"] = []
            _save_workspace(root, workspace_id, data)
            _invalidate_workspace_term_caches()
    log.info(
        "terminal workspace sessions killed",
        extra={
            "event_type": "term.session.kill_workspace",
            "action": workspace_id,
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


def _term_ws_context(websocket: WebSocket, name: str) -> tuple[list[str], str | None] | None:
    """Resolve and authorize a connection off the shared event loop."""
    if auth.user_from_connection(websocket) is None:
        return None
    active_root: Path = websocket.app.state.index_cache.root
    vaults = _known_vaults(active_root)
    root = _resolve_session_vault_root(name, active_root, vaults)
    session_meta = _load_meta(root).get(name) or {}
    _require_workspace_access(
        websocket, active_root, root, session_meta.get("workspace_id"),
    )
    return _tmux_discovery_prefixes(root), session_meta.get("tmux_socket")


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
    # Vault discovery, permission checks, and metadata reads can touch slow
    # disks. They must not pause every already-connected terminal's byte loop.
    try:
        context = await asyncio.to_thread(_term_ws_context, websocket, name)
    except HTTPException as exc:
        await websocket.close(code=4403 if exc.status_code == 403 else 4404)
        return
    if context is None:
        await websocket.close(code=4401)
        return
    prefixes, known_socket = context
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
    tmux_socket: str | None = None
    if tmux_up:
        try:
            tmux_socket = await loop.run_in_executor(
                None,
                _tmux_find_session_socket,
                name,
                str(known_socket) if known_socket else None,
            )
        except Exception:  # pragma: no cover
            tmux_socket = None

    if not (name_ok and tmux_up and tmux_socket):
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
    attach_argv = _tmux_command(str(tmux_socket), "attach", "-t", name)
    pid, fd = pty.fork()
    if pid == 0:
        env = {**_tmux_child_env(), "TERM": "xterm-256color"}
        _set_winsize(0, init_rows, init_cols)  # stdin == PTY slave post-fork
        try:
            os.execvpe(
                "tmux",
                attach_argv,
                env,
            )
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
