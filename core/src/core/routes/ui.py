"""UI state endpoints.

Small catch-all for per-monorepo UI preferences that need to persist across
browsers / machines (so localStorage isn't the right place). Today that's
the tab-strip order, pseudo-tab open state, and per-workspace terminal
auto-spawn suppression; future: pinned workspaces, theme per-workspace, etc.

State lives in vault-local ``.lab/state/ui-state.json`` so switching
vaults does not reuse stale frontend state.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core import auth

router = APIRouter()

_PSEUDO_TAB_IDS = {"__logs__", "__self__"}


def _pseudo_tab_ids() -> set[str]:
    return set(_PSEUDO_TAB_IDS)


def _state_file(root: Path) -> Path:
    from lab import paths
    return paths.ui_state_file(root)


def _load(root: Path) -> dict:
    p = _state_file(root)
    legacy = root / "content" / ".ui-state.json"
    if not p.is_file() and legacy.is_file():
        p = legacy
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text())
        disabled = data.get("terminal_autospawn_disabled")
        if isinstance(disabled, list):
            data["terminal_autospawn_disabled"] = ["__vault__" if value == "__workspace__" else value for value in disabled]
        return data
    except (json.JSONDecodeError, ValueError):
        return {}


def _save(root: Path, data: dict) -> None:
    p = _state_file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")


@router.get("/api/ui/tab-order")
def get_tab_order(request: Request) -> list[str]:
    root = auth.request_root(request)
    order = _load(root).get("tab_order", [])
    return order if isinstance(order, list) else []


class TabOrder(BaseModel):
    order: list[str]


@router.post("/api/ui/tab-order")
def set_tab_order(body: TabOrder, request: Request) -> dict:
    if not isinstance(body.order, list):
        raise HTTPException(status_code=400, detail="order must be a list")
    root = auth.request_root(request)
    data = _load(root)
    # Deduplicate while preserving first occurrence.
    seen: set[str] = set()
    deduped: list[str] = []
    for pid in body.order:
        if not isinstance(pid, str) or pid in seen:
            continue
        seen.add(pid)
        deduped.append(pid)
    data["tab_order"] = deduped
    _save(root, data)
    return {"ok": True, "order": deduped}


def _open_pseudo_tabs(data: dict, *, include_defaults: bool = False) -> list[str]:
    raw = data.get("pseudo_tabs_open", [])
    allowed = _pseudo_tab_ids()
    if not isinstance(raw, list):
        raw = []
    seen: set[str] = set()
    out: list[str] = []
    for tab_id in raw:
        if not isinstance(tab_id, str):
            continue
        if tab_id not in allowed or tab_id in seen:
            continue
        seen.add(tab_id)
        out.append(tab_id)
    if include_defaults and "__self__" in allowed and "__self__" not in seen:
        out.append("__self__")
    return out


@router.get("/api/ui/pseudo-tabs")
def get_pseudo_tabs(request: Request) -> list[str]:
    root = auth.request_root(request)
    return _open_pseudo_tabs(_load(root), include_defaults=True)


class PseudoTabState(BaseModel):
    tab_id: str
    open: bool


@router.post("/api/ui/pseudo-tabs")
def set_pseudo_tab(body: PseudoTabState, request: Request) -> dict:
    if body.tab_id not in _pseudo_tab_ids():
        raise HTTPException(status_code=400, detail=f"unknown pseudo tab: {body.tab_id!r}")
    root = auth.request_root(request)
    data = _load(root)
    open_tabs = _open_pseudo_tabs(data)
    if body.open and body.tab_id not in open_tabs:
        open_tabs.append(body.tab_id)
    elif not body.open:
        open_tabs = [tab_id for tab_id in open_tabs if tab_id != body.tab_id]
    data["pseudo_tabs_open"] = open_tabs
    _save(root, data)
    return {"ok": True, "open": _open_pseudo_tabs(data, include_defaults=True)}


def _terminal_autospawn_disabled(data: dict) -> list[str]:
    raw = data.get("terminal_autospawn_disabled", [])
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for workspace_id in raw:
        if not isinstance(workspace_id, str) or not workspace_id or workspace_id in seen:
            continue
        seen.add(workspace_id)
        out.append(workspace_id)
    return out


def _vault_root(request: Request, vault: str | None) -> Path:
    active_root = auth.request_root(request)
    if not vault:
        return active_root
    from core.routes.term import _vault_root_for
    return _vault_root_for(active_root, vault)


@router.get("/api/ui/term-autospawn")
def get_term_autospawn(
    workspace_id: str, request: Request, vault: str | None = None,
) -> dict:
    root = _vault_root(request, vault)
    disabled = set(_terminal_autospawn_disabled(_load(root)))
    return {"workspace_id": workspace_id, "enabled": workspace_id not in disabled}


class TermAutoSpawnState(BaseModel):
    workspace_id: str
    enabled: bool
    vault: str | None = None


@router.post("/api/ui/term-autospawn")
def set_term_autospawn(body: TermAutoSpawnState, request: Request) -> dict:
    if not body.workspace_id:
        raise HTTPException(status_code=400, detail="workspace_id is required")
    root = _vault_root(request, body.vault)
    data = _load(root)
    disabled = set(_terminal_autospawn_disabled(data))
    if body.enabled:
        disabled.discard(body.workspace_id)
    else:
        disabled.add(body.workspace_id)
    data["terminal_autospawn_disabled"] = sorted(disabled)
    _save(root, data)
    return {"ok": True, "workspace_id": body.workspace_id, "enabled": body.enabled}
