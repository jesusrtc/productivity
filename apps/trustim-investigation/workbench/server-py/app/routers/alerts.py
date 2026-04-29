from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import APIRouter, HTTPException, Query

from ..config import settings
from ..models.alert import Alert, AlertFilters, AlertSummary
from ..models.common import SuccessResponse

router = APIRouter(prefix="/alerts", tags=["alerts"])

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


def _normalize_summary(data: dict) -> AlertSummary:
    return AlertSummary(
        id=data.get("id", ""),
        external_id=data.get("external_id"),
        title=data.get("title", ""),
        status=data.get("status", "new"),
        severity=data.get("severity", "medium"),
        source=data.get("source", "manual"),
        alert_type=data.get("alert_type", ""),
        assignee=data.get("assignee"),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        session_count=len(data.get("session_ids") or []),
        ioc_count=len(data.get("iocs") or []),
        related_count=len(data.get("related_alert_ids") or []),
        tags=data.get("tags") or [],
    )


def _filter_alerts(
    alerts: list[AlertSummary], filters: AlertFilters
) -> list[AlertSummary]:
    result = alerts
    if filters.status:
        result = [a for a in result if a.status in filters.status]
    if filters.severity:
        result = [a for a in result if a.severity in filters.severity]
    if filters.source:
        result = [a for a in result if a.source in filters.source]
    if filters.alert_type:
        result = [a for a in result if a.alert_type == filters.alert_type]
    if filters.assignee:
        result = [a for a in result if a.assignee == filters.assignee]
    if filters.search:
        q = filters.search.lower()
        result = [
            a
            for a in result
            if q in a.title.lower() or q in a.alert_type.lower()
        ]
    if filters.date_from:
        result = [a for a in result if a.created_at >= filters.date_from]
    if filters.date_to:
        result = [a for a in result if a.created_at <= filters.date_to]
    return result


async def _load_all_alerts() -> list[dict]:
    alerts_dir = settings.alerts_dir
    if not alerts_dir.exists():
        return []
    alerts: list[dict] = []
    for fp in alerts_dir.glob("*.json"):
        try:
            async with aiofiles.open(fp, "r") as f:
                alerts.append(json.loads(await f.read()))
        except Exception:
            continue
    return alerts


async def _load_alert(alert_id: str) -> dict | None:
    fp = _safe_path(settings.alerts_dir, f"{alert_id}.json")
    if not fp or not fp.exists():
        return None
    try:
        async with aiofiles.open(fp, "r") as f:
            return json.loads(await f.read())
    except Exception:
        return None


async def _save_alert(alert_id: str, data: dict) -> None:
    fp = _safe_path(settings.alerts_dir, f"{alert_id}.json")
    if not fp:
        raise ValueError("Invalid ID")
    settings.alerts_dir.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(fp, "w") as f:
        await f.write(json.dumps(data, indent=2))


def _get_related_alerts(alert: dict, all_alerts: list[dict]) -> list[dict]:
    alert_iocs = {
        f"{i['type']}:{i['value']}" for i in (alert.get("iocs") or [])
    }
    alert_type = alert.get("alert_type", "")
    alert_date = 0.0
    try:
        alert_date = datetime.fromisoformat(
            alert.get("created_at", "")
        ).timestamp()
    except Exception:
        pass
    seven_days = 7 * 24 * 60 * 60

    scored: list[tuple[int, dict]] = []
    for other in all_alerts:
        if other.get("id") == alert.get("id"):
            continue
        score = 0
        other_iocs = [
            f"{i['type']}:{i['value']}" for i in (other.get("iocs") or [])
        ]
        for ioc in other_iocs:
            if ioc in alert_iocs:
                score += 3
        if other.get("alert_type") == alert_type and alert_type:
            score += 2
        try:
            other_date = datetime.fromisoformat(
                other.get("created_at", "")
            ).timestamp()
            if abs(other_date - alert_date) < seven_days:
                score += 1
        except Exception:
            pass
        if (
            other.get("incident_id")
            and other.get("incident_id") == alert.get("incident_id")
        ):
            score += 5
        if score > 0:
            scored.append((score, other))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:10]]


# ---------------------------------------------------------------------------
# Sync stub routes (BEFORE /:id to avoid FastAPI treating "sync" as an ID)
# ---------------------------------------------------------------------------


class _SyncStatus(SuccessResponse):
    running: bool = False
    last_sync: str | None = None
    alert_count: int = 0


class _SyncResult(SuccessResponse):
    new_alerts: int = 0
    updated_alerts: int = 0


@router.get("/sync/status", response_model=_SyncStatus)
async def get_sync_status():
    return _SyncStatus()


@router.post("/sync", response_model=_SyncResult)
async def run_sync():
    return _SyncResult()


@router.post("/sync/start", response_model=_SyncStatus)
async def start_sync():
    return _SyncStatus()


@router.post("/sync/stop", response_model=_SyncStatus)
async def stop_sync():
    return _SyncStatus()


# ---------------------------------------------------------------------------
# CRUD routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[AlertSummary])
async def list_alerts(
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    alert_type: Optional[str] = Query(None),
    assignee: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    all_data = await _load_all_alerts()
    summaries = [_normalize_summary(a) for a in all_data]
    filters = AlertFilters(
        status=status.split(",") if status else None,
        severity=severity.split(",") if severity else None,
        source=source.split(",") if source else None,
        alert_type=alert_type,
        assignee=assignee,
        search=search,
        date_from=date_from,
        date_to=date_to,
    )
    filtered = _filter_alerts(summaries, filters)
    filtered.sort(key=lambda a: a.created_at, reverse=True)
    return filtered


@router.get("/{alert_id}/related", response_model=list[AlertSummary])
async def get_related(alert_id: str):
    safe_id = _sanitize_id(alert_id)
    alert = await _load_alert(safe_id)
    if not alert:
        return []
    all_alerts = await _load_all_alerts()
    related = _get_related_alerts(alert, all_alerts)
    return [_normalize_summary(r) for r in related]


@router.get("/{alert_id}", response_model=Alert)
async def get_alert(alert_id: str):
    safe_id = _sanitize_id(alert_id)
    alert = await _load_alert(safe_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("", response_model=Alert)
async def create_alert(body: Alert):
    now = datetime.utcnow().isoformat() + "Z"
    alert_id = _sanitize_id(body.id or f"alert-{int(time.time() * 1000)}")
    data = body.model_dump()
    data.update(
        id=alert_id,
        created_at=now,
        updated_at=now,
        session_ids=data.get("session_ids") or [],
        related_alert_ids=data.get("related_alert_ids") or [],
    )
    try:
        await _save_alert(alert_id, data)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID")
    return data


@router.patch("/{alert_id}", response_model=Alert)
async def update_alert(alert_id: str, body: dict):
    safe_id = _sanitize_id(alert_id)
    existing = await _load_alert(safe_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Alert not found")
    updated = {
        **existing,
        **body,
        "id": existing["id"],
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    try:
        await _save_alert(existing["id"], updated)
    except ValueError:
        raise HTTPException(status_code=500, detail="Failed to update alert")
    return updated


@router.delete("/{alert_id}", response_model=SuccessResponse)
async def delete_alert(alert_id: str):
    safe_id = _sanitize_id(alert_id)
    fp = _safe_path(settings.alerts_dir, f"{safe_id}.json")
    if fp and fp.exists():
        fp.unlink()
    return SuccessResponse()
