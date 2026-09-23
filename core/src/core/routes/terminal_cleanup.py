"""Explicit, reviewed cleanup of detached Lab terminals older than seven days."""
from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core import agent_activity, auth, document_terminals, fsguard
from core.routes import term, ui
from lab import paths, tmux_sockets
from lab.workspace_identity import operation_lease

router = APIRouter()
log = logging.getLogger(__name__)
INACTIVE_SECONDS = 7 * 24 * 60 * 60
_LOCK = threading.RLock()


def mark_access(name: str, socket: str | None) -> None:
    if not socket:
        return
    try:
        # Commands accepting a pane target need the trailing colon: =name
        # alone can silently resolve an empty format context in tmux.
        subprocess.run(term._tmux_command(socket, "set-option", "-t", "=" + name + ":",
                                         "@lab_last_access", str(int(time.time()))),
                       capture_output=True, env=term._tmux_child_env(), timeout=3)
    except (OSError, subprocess.SubprocessError):
        log.debug("Could not record terminal detach time", exc_info=True)


def _roots(active_root: Path) -> list[dict]:
    roots = term._known_vaults(active_root)
    framework = paths.find_framework_root().resolve()
    if not any(row["path"].resolve() == framework for row in roots):
        roots.append({"id": "__self__", "path": framework})
    return roots


def _last_used(row: dict) -> int:
    return max(int(row.get(key) or 0) for key in
               ("created", "activity", "last_attached", "last_access"))


def _eligible(row: dict, now: float) -> bool:
    logical = str(row.get("logical_name") or "")
    return bool(row.get("activity_known") and row.get("tmux_id")
                and row.get("created", 0) > 0 and not row.get("attached")
                and row.get("workspace_id") and logical
                and logical != "server" and not logical.startswith("server-")
                and _last_used(row) < now - INACTIVE_SECONDS)


def _root_rows(root: Path, listing: list[dict], meta: dict, registered: set[str]) -> list[dict]:
    # Read-only discovery: opening the modal must not allocate identities or
    # prune runtime registries. Existing registries win over legacy recovery.
    workspaces = {}
    rows = []
    documents = None
    for live in listing:
        if live["name"] in registered and live["name"] not in meta:
            continue
        info = meta.get(live["name"]) or term._reconstruct_meta_entry(
            root, live["name"], live["created"], live["tmux_socket"])
        if not info:
            continue
        row = {**info, **live}  # live timestamps/socket must win over metadata
        workspace = row.get("workspace_id")
        if not workspace:
            continue
        if workspace not in workspaces:
            workspaces[workspace] = term._load_workspace(root, workspace) or {}
        data = workspaces[workspace]
        row["workspace_name"] = {
            "__self__": "Home", "__assistant__": "Assistant", "__vault__": "Vault",
            "__cerebro__": "Cerebro", "__logs__": "Logs",
        }.get(workspace, data.get("name") or workspace.removeprefix("__cs_").removesuffix("__"))
        saved = next((s for s in data.get("sessions", []) if isinstance(s, dict)
                      and s.get("name") == row.get("logical_name")), {})
        row["label"] = saved.get("label") or row.get("label") or row.get("logical_name")
        if row.get("document_key"):
            if documents is None:
                documents = document_terminals._load(root)
            entry = dict(documents.get(row["document_key"]) or {})
            document_terminals._merge_input(entry)
            if entry.get("unsent_input"):
                continue
            row["last_access"] = max(row.get("last_access", 0), int(entry.get("last_used", 0)))
        rows.append(row)
    return rows


def _scan(active_root: Path) -> tuple[list[dict], list[str]]:
    roots = _roots(active_root)
    listing = term._tmux_list(term._tmux_discovery_prefixes_all(roots),
                              prune_draining=False, activity=True)
    if listing is None:
        raise HTTPException(503, "Could not inspect tmux sessions. Nothing was stopped.")
    candidates, warnings, seen = [], [], set()
    registries, registered = {}, set()
    for vault in roots:
        try:
            meta = fsguard.guarded(vault["path"], term._load_meta, vault["path"])
            registries[vault["id"]] = meta
            registered.update(meta)
        except (OSError, ValueError, HTTPException):
            warnings.append(f"Could not inspect {vault['id']}; its sessions are excluded.")
    now = time.time()
    for vault in roots:
        root = vault["path"]
        if vault["id"] not in registries:
            continue
        try:
            rows = fsguard.guarded(root, _root_rows, root, listing, registries[vault["id"]], registered)
        except (OSError, ValueError, HTTPException):
            warnings.append(f"Could not inspect {vault['id']}; its sessions are excluded.")
            continue
        for row in rows:
            key = (row["tmux_socket"], row["name"])
            if key in seen:
                continue
            seen.add(key)
            if not _eligible(row, now):
                continue
            row.update(root=root, vault=vault["id"], last_used=_last_used(row))
            candidates.append(row)
    # This explicit scan stays off the normal polling/input paths.
    term._enrich_agent_session_names(candidates)
    agent_activity.enrich(candidates)
    candidates = [row for row in candidates if
                  row.get("agent_activity", {}).get("state") not in {"working", "waiting"}]
    for row in candidates:
        identity = [row[key] for key in ("vault", "workspace_id", "name", "tmux_socket",
                                        "tmux_id", "created", "pane_pid", "last_used")]
        row["id"] = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    return candidates, warnings


def _public(row: dict) -> dict:
    return {key: row.get(key) for key in
            ("id", "name", "label", "logical_name", "vault", "workspace_id", "workspace_name",
             "last_used", "tmux_socket")}


@router.get("/api/term/cleanup")
def candidates(request: Request) -> dict:
    auth.require_admin(request)
    rows, warnings = _scan(request.app.state.index_cache.root)
    groups = {}
    for row in rows:
        # Home sessions may be registered in several vaults; show one Home.
        key = "home" if row["workspace_id"] == term.SELF_WORKSPACE_ID else json.dumps(
            [row["vault"], row["workspace_id"]])
        group = groups.setdefault(key, {"id": key, "workspace_id": row["workspace_id"],
                                       "vault": row["vault"], "name": row["workspace_name"],
                                       "sessions": []})
        group["sessions"].append(_public(row))
    for group in groups.values():
        group["sessions"].sort(key=lambda s: (s["last_used"], s["name"]))
    return {"days": 7, "groups": sorted(groups.values(), key=lambda g: (g["name"].casefold(), g["vault"])),
            "warnings": warnings, "count": len(rows)}


class CleanupRequest(BaseModel):
    candidates: list[str] = Field(min_length=1, max_length=2000)


def _disable_autospawn(root: Path, workspace: str) -> None:
    data = ui._load(root)
    disabled = set(ui._terminal_autospawn_disabled(data))
    disabled.add(workspace)
    data["terminal_autospawn_disabled"] = sorted(disabled)
    ui._save(root, data)


def _stop(row: dict) -> bool:
    # Evaluate freshness inside tmux's command queue, immediately before kill.
    # Exact targets and the server's session ID protect against name reuse.
    checks = [f"#{{==:#{{session_id}},{row['tmux_id']}}}",
              f"#{{==:#{{session_created}},{row['created']}}}",
              f"#{{==:#{{pane_pid}},{row['pane_pid']}}}",
              "#{==:#{session_attached},0}"]
    for value in ("#{session_activity}", "#{session_last_attached}",
                  "#{?@lab_last_access,#{@lab_last_access},0}"):
        checks.append(f"#{{<=:{value},{row['last_used']}}}")
    condition = checks[0]
    for check in checks[1:]:
        condition = "#{&&:" + condition + "," + check + "}"
    target = "=" + row["name"]
    result = subprocess.run(term._tmux_command(
        row["tmux_socket"], "if-shell", "-F", "-t", target + ":", condition,
        "kill-session -t " + term._shell_quote(target),
        "display-message -p lab-cleanup-skipped"),
        capture_output=True, text=True, env=term._tmux_child_env(), timeout=5)
    if result.returncode:
        raise RuntimeError("tmux could not stop this session; refresh and try again")
    return "lab-cleanup-skipped" not in result.stdout


def _remove_saved(row: dict) -> None:
    root, workspace, name = row["root"], row["workspace_id"], row["name"]
    meta = term._load_meta(root)
    meta.pop(name, None)
    term._save_meta(root, meta)
    if row.get("document_key"):
        entries = document_terminals._load(root)
        entry = entries.get(row["document_key"])
        if entry and entry.get("name") == name:
            document_terminals._retire(root, entry, None)
            document_terminals._save(root, entries)
    else:
        data = term._load_workspace(root, workspace)
        if data and isinstance(data.get("sessions"), list):
            data["sessions"] = [s for s in data["sessions"] if not
                                (isinstance(s, dict) and s.get("name") == row["logical_name"])]
            term._save_workspace(root, workspace, data)
    term._invalidate_workspace_term_caches()


@router.post("/api/term/cleanup")
def cleanup(body: CleanupRequest, request: Request) -> dict:
    auth.require_admin(request)
    killed, skipped, errors = [], [], []
    active_root = request.app.state.index_cache.root
    with _LOCK, document_terminals._LOCK:
        rows, warnings = _scan(active_root)
        current = {row["id"]: row for row in rows}
        for candidate_id in dict.fromkeys(body.candidates):
            row = current.get(candidate_id)
            if not row:
                skipped.append({"id": candidate_id, "reason": "Session changed, became active, or is no longer available."})
                continue
            try:
                with operation_lease(row["root"], row["workspace_id"]), tmux_sockets.state_lock():
                    # Persist suppression before any kill, including recovery
                    # initiated by other open browsers. Purge only reviewed tabs.
                    roots = _roots(active_root) if row["workspace_id"] == term.SELF_WORKSPACE_ID else [{"path": row["root"]}]
                    for root in roots:
                        _disable_autospawn(root["path"], row["workspace_id"])
                    if not _stop(row):
                        skipped.append({"id": candidate_id, "reason": "Session was accessed during cleanup."})
                        continue
                    killed.append(_public(row))
                    _remove_saved(row)
                    log.info("Inactive terminal stopped", extra={"event_type": "term.session.cleanup",
                                                                "target": row["name"], "action": row["workspace_id"]})
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, HTTPException) as exc:
                log.warning("Terminal cleanup failed for %s", row["name"], exc_info=True)
                errors.append({"id": candidate_id, "name": row["name"],
                               "reason": str(getattr(exc, "detail", exc))})
    return {"killed": killed, "skipped": skipped, "errors": errors, "warnings": warnings}
