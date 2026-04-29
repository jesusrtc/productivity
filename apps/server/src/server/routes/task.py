from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Query, Request


router = APIRouter()


@router.get("/api/tasks")
async def list_tasks(request: Request,
                     status: str | None = None,
                     priority: str | None = None,
                     tag: str | None = None,
                     label: str | None = None) -> list[dict]:
    idx = request.app.state.index_cache.get()
    rows = idx["tasks"]
    if status == "open":
        rows = [r for r in rows if r.get("status") != "done"]
    elif status:
        rows = [r for r in rows if r.get("status") == status]
    if priority:
        wanted = {p.strip() for p in priority.split(",") if p.strip()}
        rows = [r for r in rows if r.get("priority") in wanted]
    if tag:
        rows = [r for r in rows if tag in (r.get("tags") or [])]
    if label:
        rows = [r for r in rows if label in (r.get("labels") or [])]
    return rows


@router.get("/api/tasks/due")
async def list_tasks_due(request: Request, days: int = Query(..., ge=1)) -> list[dict]:
    horizon = date.today() + timedelta(days=days)
    idx = request.app.state.index_cache.get()
    out: list[dict] = []
    for r in idx["tasks"]:
        due = r.get("due")
        if not due:
            continue
        if date.fromisoformat(due) <= horizon:
            out.append(r)
    return out
