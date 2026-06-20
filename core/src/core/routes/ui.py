"""UI state endpoints.

Small catch-all for per-monorepo UI preferences that need to persist across
browsers / machines (so localStorage isn't the right place). Today that's
just the tab-strip order; future: pinned projects, theme per-project, etc.

State lives in ``content/.ui-state.json``. The watcher's self-write guard
already ignores dotfiles under ``content/`` that start with ``.`` — writes
here don't trigger index rebuilds.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


router = APIRouter()


def _state_file(root: Path) -> Path:
    return root / "content" / ".ui-state.json"


def _load(root: Path) -> dict:
    p = _state_file(root)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, ValueError):
        return {}


def _save(root: Path, data: dict) -> None:
    p = _state_file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")


@router.get("/api/ui/tab-order")
async def get_tab_order(request: Request) -> list[str]:
    root: Path = request.app.state.index_cache.root
    order = _load(root).get("tab_order", [])
    return order if isinstance(order, list) else []


class TabOrder(BaseModel):
    order: list[str]


@router.post("/api/ui/tab-order")
async def set_tab_order(body: TabOrder, request: Request) -> dict:
    if not isinstance(body.order, list):
        raise HTTPException(status_code=400, detail="order must be a list")
    root: Path = request.app.state.index_cache.root
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
