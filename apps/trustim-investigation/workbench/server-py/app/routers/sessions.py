from __future__ import annotations

import json
import re
from pathlib import Path

import aiofiles
from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..models.common import SuccessResponse
from ..models.session import Session, SessionSummary

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ---------------------------------------------------------------------------
# Helpers (ported from server/domains/sessions/service.ts)
# ---------------------------------------------------------------------------

_ID_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _sanitize_id(raw: str) -> str:
    return _ID_RE.sub("", raw)


def _safe_path(base: Path, filename: str) -> Path | None:
    resolved = (base / filename).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        return None
    return resolved


def _get_max_severity(nodes: dict[str, dict]) -> str:
    max_conf: float = 0
    has_sev = ""
    for node in nodes.values():
        conf = node.get("confidence", 0) or 0
        if conf > max_conf:
            max_conf = conf
        for tag in node.get("tags", []):
            if tag.startswith("SEV-"):
                if not has_sev or tag < has_sev:
                    has_sev = tag
    if has_sev:
        return has_sev
    if max_conf > 0.7:
        return "critical"
    if max_conf > 0.5:
        return "high"
    if max_conf > 0.3:
        return "medium"
    if max_conf > 0.1:
        return "low"
    return "benign"


def _summarize_session(data: dict[str, object]) -> SessionSummary | None:
    try:
        nodes = data.get("nodes", {})
        node_list = list(nodes.values())
        max_conf = max((n.get("confidence", 0) or 0 for n in node_list), default=0)
        completed_count = sum(1 for n in node_list if n.get("status") == "completed")
        has_sev = any(
            tag.startswith("SEV-")
            for n in node_list
            for tag in n.get("tags", [])
        )
        return SessionSummary(
            id=data["id"],
            name=data.get("name", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            node_count=len(node_list),
            max_severity=_get_max_severity(nodes),
            max_confidence=max_conf,
            completed_count=completed_count,
            has_sev=has_sev,
            skills_used=(data.get("skills_used") or [])[:3],
            starting_input_type=data.get("starting_input_type", "none"),
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=list[SessionSummary])
async def list_sessions():
    """Return lightweight summaries of all sessions, sorted newest-first."""
    sessions_dir = settings.sessions_dir
    if not sessions_dir.exists():
        return []

    summaries: list[SessionSummary] = []
    for fp in sessions_dir.glob("*.json"):
        try:
            async with aiofiles.open(fp, "r") as f:
                data = json.loads(await f.read())
            summary = _summarize_session(data)
            if summary:
                summaries.append(summary)
        except Exception:
            continue

    summaries.sort(key=lambda s: s.updated_at, reverse=True)
    return summaries


@router.get("/{session_id}", response_model=Session)
async def get_session(session_id: str):
    """Return a full session by ID."""
    safe_id = _sanitize_id(session_id)
    fp = _safe_path(settings.sessions_dir, f"{safe_id}.json")
    if not fp or not fp.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    async with aiofiles.open(fp, "r") as f:
        data = json.loads(await f.read())
    return data


@router.put("/{session_id}", response_model=SuccessResponse)
async def save_session(session_id: str, request: Request):
    """Save (create or update) a session."""
    safe_id = _sanitize_id(session_id)
    fp = _safe_path(settings.sessions_dir, f"{safe_id}.json")
    if not fp:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    body = await request.body()
    # Validate it's parseable JSON, but store it as-is to preserve all fields
    try:
        json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    settings.sessions_dir.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(fp, "w") as f:
        await f.write(body.decode("utf-8"))

    return SuccessResponse()


@router.delete("/{session_id}", response_model=SuccessResponse)
async def delete_session(session_id: str):
    """Delete a session file and its notebook."""
    safe_id = _sanitize_id(session_id)
    fp = _safe_path(settings.sessions_dir, f"{safe_id}.json")
    if not fp or not fp.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    fp.unlink()

    # Also remove associated notebook
    notebooks_dir = settings.sessions_dir.parent / "notebooks"
    nb_path = notebooks_dir / f"investigation-{safe_id[:8]}.ipynb"
    if nb_path.exists():
        nb_path.unlink()

    return SuccessResponse()
