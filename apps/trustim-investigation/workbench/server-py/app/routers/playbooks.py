from __future__ import annotations

import json
import random
import re
import string
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
from fastapi import APIRouter, HTTPException

from ..config import settings
from ..models.common import SuccessResponse
from ..models.playbook import (
    Playbook,
    PlaybookEdge,
    PlaybookExecution,
    PlaybookNode,
)

router = APIRouter(tags=["playbooks"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ID_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _sanitize_id(raw: str) -> str:
    return _ID_RE.sub("", raw)


def _safe_path(base: Path, filename: str) -> Path | None:
    resolved = (base / filename).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        return None
    return resolved


def _compute_entry_node_ids(
    nodes: list[PlaybookNode], edges: list[PlaybookEdge]
) -> list[str]:
    """Return IDs of nodes with no incoming edges."""
    targets = {e.target for e in edges}
    return [n.id for n in nodes if n.id not in targets]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _random_suffix(length: int = 4) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


# ---------------------------------------------------------------------------
# File helpers (async)
# ---------------------------------------------------------------------------


async def _load_playbook(pb_id: str) -> dict | None:
    fp = _safe_path(settings.playbooks_dir, f"{pb_id}.json")
    if not fp or not fp.exists():
        return None
    try:
        async with aiofiles.open(fp, "r") as f:
            return json.loads(await f.read())
    except Exception:
        return None


async def _load_all_playbooks() -> list[dict]:
    d = settings.playbooks_dir
    if not d.exists():
        return []
    results: list[dict] = []
    for fp in sorted(d.glob("*.json")):
        try:
            async with aiofiles.open(fp, "r") as f:
                results.append(json.loads(await f.read()))
        except Exception:
            continue
    return results


async def _save_playbook(pb_id: str, data: dict) -> bool:
    fp = _safe_path(settings.playbooks_dir, f"{pb_id}.json")
    if not fp:
        return False
    settings.playbooks_dir.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(fp, "w") as f:
        await f.write(json.dumps(data, indent=2))
    return True


async def _delete_playbook(pb_id: str) -> None:
    fp = _safe_path(settings.playbooks_dir, f"{pb_id}.json")
    if fp and fp.exists():
        fp.unlink()


# ---------------------------------------------------------------------------
# Routes — Playbooks CRUD
# ---------------------------------------------------------------------------


@router.get("/playbooks", response_model=list[Playbook])
async def list_playbooks():
    return await _load_all_playbooks()


@router.get("/playbooks/{playbook_id}", response_model=Playbook)
async def get_playbook(playbook_id: str):
    data = await _load_playbook(_sanitize_id(playbook_id))
    if not data:
        raise HTTPException(status_code=404, detail="Not found")
    return data


class _PlaybookCreate(Playbook):
    """Body for creating a playbook — id/version/timestamps are server-set."""
    id: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@router.post("/playbooks", response_model=Playbook)
async def create_playbook(body: _PlaybookCreate):
    now = _now_iso()
    pb_id = f"pb-{int(datetime.now(timezone.utc).timestamp() * 1000)}-{_random_suffix()}"
    data = body.model_dump()
    data.update(
        id=pb_id,
        version=1,
        created_at=now,
        updated_at=now,
    )
    nodes = [PlaybookNode(**n) if isinstance(n, dict) else n for n in (data.get("nodes") or [])]
    edges = [PlaybookEdge(**e) if isinstance(e, dict) else e for e in (data.get("edges") or [])]
    data["entry_node_ids"] = _compute_entry_node_ids(nodes, edges)
    if not await _save_playbook(pb_id, data):
        raise HTTPException(status_code=400, detail="Invalid")
    return data


@router.put("/playbooks/{playbook_id}", response_model=Playbook)
async def update_playbook(playbook_id: str, body: _PlaybookCreate):
    safe_id = _sanitize_id(playbook_id)
    existing = await _load_playbook(safe_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Not found")
    updates = body.model_dump(exclude_unset=True)
    merged = {**existing, **updates}
    merged["id"] = existing["id"]
    merged["created_at"] = existing.get("created_at", "")
    merged["version"] = (existing.get("version") or 0) + 1
    merged["updated_at"] = _now_iso()
    nodes = [PlaybookNode(**n) if isinstance(n, dict) else n for n in (merged.get("nodes") or [])]
    edges = [PlaybookEdge(**e) if isinstance(e, dict) else e for e in (merged.get("edges") or [])]
    merged["entry_node_ids"] = _compute_entry_node_ids(nodes, edges)
    await _save_playbook(safe_id, merged)
    return merged


@router.delete("/playbooks/{playbook_id}", response_model=SuccessResponse)
async def delete_playbook_route(playbook_id: str):
    await _delete_playbook(_sanitize_id(playbook_id))
    return SuccessResponse()


# ---------------------------------------------------------------------------
# Routes — Playbook run (stub)
# ---------------------------------------------------------------------------


from pydantic import BaseModel, Field


class RunPlaybookBody(BaseModel):
    session_id: str = Field(alias="sessionId")
    inputs: dict = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


@router.post("/playbooks/{playbook_id}/run", response_model=PlaybookExecution)
async def run_playbook(playbook_id: str, body: RunPlaybookBody):
    safe_id = _sanitize_id(playbook_id)
    pb = await _load_playbook(safe_id)
    if not pb:
        raise HTTPException(status_code=404, detail="Not found")
    if not body.session_id:
        raise HTTPException(status_code=400, detail="sessionId required")
    return PlaybookExecution(
        id="exec-pending",
        playbook_id=pb["id"],
        session_id=body.session_id,
        status="running",
        started_at=_now_iso(),
    )


# ---------------------------------------------------------------------------
# Routes — Playbook Executions (stubs — runner not ported yet)
# ---------------------------------------------------------------------------


@router.get("/playbook-executions", response_model=list[PlaybookExecution])
async def list_executions():
    return []


@router.get("/playbook-executions/{exec_id}", response_model=PlaybookExecution)
async def get_execution(exec_id: str):
    raise HTTPException(status_code=404, detail="Not found")


@router.delete("/playbook-executions/{exec_id}", response_model=SuccessResponse)
async def cancel_execution(exec_id: str):
    return SuccessResponse()
