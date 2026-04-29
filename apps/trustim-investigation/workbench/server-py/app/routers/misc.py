from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from ..config import settings
from ..models.common import SuccessResponse

router = APIRouter(tags=["misc"])


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ===================================================================
# Templates CRUD
# ===================================================================


class TemplateSummary(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    created_at: str = ""


class CreateTemplateBody(BaseModel):
    id: str = ""
    name: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class CreateTemplateResponse(BaseModel):
    ok: bool = True
    id: str


@router.get("/templates", response_model=list[TemplateSummary])
async def list_templates():
    d = settings.templates_dir
    d.mkdir(parents=True, exist_ok=True)
    results: list[TemplateSummary] = []
    for fp in d.glob("*.json"):
        try:
            async with aiofiles.open(fp, "r") as f:
                data = json.loads(await f.read())
            results.append(TemplateSummary(
                id=data.get("id", ""),
                name=data.get("name", ""),
                description=data.get("description", ""),
                skills=data.get("skills", []),
                created_at=data.get("created_at", ""),
            ))
        except Exception:
            continue
    return results


@router.post("/templates", response_model=CreateTemplateResponse)
async def create_template(body: CreateTemplateBody):
    d = settings.templates_dir
    d.mkdir(parents=True, exist_ok=True)
    tpl_id = _sanitize_id(body.id or f"tpl-{int(datetime.now(timezone.utc).timestamp() * 1000)}")
    data = body.model_dump()
    data["id"] = tpl_id
    data["created_at"] = _now_iso()
    fp = _safe_path(d, f"{tpl_id}.json")
    if not fp:
        raise HTTPException(status_code=400, detail="Invalid ID")
    async with aiofiles.open(fp, "w") as f:
        await f.write(json.dumps(data, indent=2))
    return CreateTemplateResponse(id=tpl_id)


@router.delete("/templates/{template_id}", response_model=SuccessResponse)
async def delete_template(template_id: str):
    fp = _safe_path(settings.templates_dir, f"{_sanitize_id(template_id)}.json")
    if fp and fp.exists():
        fp.unlink()
    return SuccessResponse()


# ===================================================================
# Queries (cross-session query reuse)
# ===================================================================


class QueryEntry(BaseModel):
    query: str
    label: str = "Query"
    session: str = ""
    confidence: float = 0
    timestamp: str = ""


@router.get("/queries", response_model=list[QueryEntry])
async def list_queries():
    d = settings.sessions_dir
    if not d.exists():
        return []

    files = sorted(d.glob("*.json"))[-20:]  # last 20 sessions
    queries: list[QueryEntry] = []

    for fp in files:
        try:
            async with aiofiles.open(fp, "r") as f:
                data = json.loads(await f.read())
            for node in (data.get("nodes") or {}).values():
                q = node.get("query")
                if q and node.get("status") == "completed" and "select" in q.lower():
                    queries.append(QueryEntry(
                        query=q,
                        label=node.get("label", "Query"),
                        session=data.get("name", fp.name),
                        confidence=node.get("confidence", 0) or 0,
                        timestamp=node.get("timestamp", ""),
                    ))
        except Exception:
            continue

    # Deduplicate by normalized query, sort by recency
    seen: set[str] = set()
    unique: list[QueryEntry] = []
    queries.sort(key=lambda q: q.timestamp, reverse=True)
    for q in queries:
        key = re.sub(r"\s+", " ", q.query).strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(q)
        if len(unique) >= 50:
            break

    return unique


# ===================================================================
# Export
# ===================================================================


class ExportAllResponse(BaseModel):
    exported_at: str
    session_count: int
    sessions: list[dict[str, Any]]


@router.get("/export/all", response_model=ExportAllResponse)
async def export_all():
    d = settings.sessions_dir
    if not d.exists():
        return ExportAllResponse(exported_at=_now_iso(), session_count=0, sessions=[])

    sessions: list[dict] = []
    for fp in d.glob("*.json"):
        try:
            async with aiofiles.open(fp, "r") as f:
                sessions.append(json.loads(await f.read()))
        except Exception:
            continue

    return ExportAllResponse(
        exported_at=_now_iso(),
        session_count=len(sessions),
        sessions=sessions,
    )


@router.post("/export/json")
async def export_json(body: dict[str, Any]):
    content = json.dumps(body, indent=2)
    filename = f"investigation-{body.get('id', 'export')}.json"
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ===================================================================
# Seed Demo
# ===================================================================


class SeedDemoResponse(BaseModel):
    ok: bool = True
    seeded: dict[str, int] = Field(default_factory=dict)


@router.post("/seed-demo", response_model=SeedDemoResponse)
async def seed_demo():
    now = _now_iso()
    yesterday = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() - 86400, tz=timezone.utc
    ).isoformat()
    two_days_ago = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() - 2 * 86400, tz=timezone.utc
    ).isoformat()
    seeded: dict[str, int] = {"alerts": 0, "playbooks": 0}

    # Seed demo alerts (only if none exist)
    alerts_dir = settings.alerts_dir
    alerts_dir.mkdir(parents=True, exist_ok=True)
    existing_alerts = list(alerts_dir.glob("*.json"))
    if len(existing_alerts) == 0:
        demo_alerts = [
            {
                "id": "demo-alert-1",
                "title": "Registration spike from disposable .xyz domains",
                "description": "Cold registration volume increased 340% from .xyz and .icu TLDs in the last 24h. Top domain: ghksc.xyz with 527 registrations. Possible automated account creation campaign.",
                "status": "new", "severity": "high", "source": "iris", "alert_type": "registration_spike",
                "created_at": yesterday, "updated_at": yesterday, "session_ids": [], "related_alert_ids": ["demo-alert-2"], "tags": ["auto-detected", "fake-accounts"],
                "iocs": [{"type": "domain", "value": "ghksc.xyz"}, {"type": "domain", "value": "mailnesia.com"}, {"type": "ip", "value": "185.220.101.34"}, {"type": "ip", "value": "45.134.225.17"}],
                "metadata": {"iris_plan": "trust-incident-auto-alert", "wow_pct": 34.2},
            },
            {
                "id": "demo-alert-2",
                "title": "SwiftShader device fingerprint clustering",
                "description": "Anomalous canvas hash clustering detected. 89 accounts sharing identical SwiftShader WebGL renderer with matching canvas hashes. RTT >200ms suggests proxy usage.",
                "status": "new", "severity": "medium", "source": "iris", "alert_type": "fake_account",
                "created_at": yesterday, "updated_at": yesterday, "session_ids": [], "related_alert_ids": ["demo-alert-1"], "tags": ["device-fingerprint"],
                "iocs": [{"type": "device_hash", "value": "canvas:a3f8b2c1d4"}, {"type": "ip", "value": "185.220.101.34"}],
                "metadata": {"members_affected": 89},
            },
            {
                "id": "demo-alert-3",
                "title": "ATO credential washing via MITM proxy",
                "description": "MITM phishing rule (Evilginx) activations spiked 5x in the last 6 hours. 23 unique member IDs with password_result=PASS and MITM rule hit.",
                "status": "investigating", "severity": "critical", "source": "iris", "alert_type": "ato",
                "created_at": two_days_ago, "updated_at": yesterday, "session_ids": [], "related_alert_ids": [], "tags": ["ato", "phishing", "evilginx"],
                "iocs": [{"type": "ip", "value": "91.215.85.12"}, {"type": "ip", "value": "91.215.85.13"}, {"type": "member_id", "value": "123456789"}],
                "metadata": {"activated_rules": ["IMIR: MITM ATO", "Incident Response: ColorFish ATO"], "member_count": 23},
            },
            {
                "id": "demo-alert-4",
                "title": "Guest scraping volume increase \u2014 block filter bypass",
                "description": "Denial event volume from block filter rules increased 22% WoW. New user agent patterns detected bypassing existing rules.",
                "status": "new", "severity": "medium", "source": "iris", "alert_type": "guest_scraping",
                "created_at": now, "updated_at": now, "session_ids": [], "related_alert_ids": [], "tags": ["scraping"],
                "iocs": [{"type": "user_agent", "value": "Mozilla/5.0 (compatible; DataBot/2.0)"}],
                "metadata": {"denial_count_today": 145000, "wow_pct": 22.1},
            },
            {
                "id": "demo-alert-5",
                "title": "Challenge abuse \u2014 VoIP solve rate anomaly",
                "description": "Phone challenge solve rate from VoIP numbers jumped to 98.7% (baseline 62%). Possible IRSF or solver service.",
                "status": "new", "severity": "high", "source": "iris", "alert_type": "challenge_abuse",
                "created_at": now, "updated_at": now, "session_ids": [], "related_alert_ids": [], "tags": ["challenge", "voip", "irsf"],
                "iocs": [],
                "metadata": {"solve_rate": 98.7, "baseline": 62.0, "voip_count": 341},
            },
        ]
        for alert in demo_alerts:
            fp = _safe_path(alerts_dir, f"{alert['id']}.json")
            if fp:
                async with aiofiles.open(fp, "w") as f:
                    await f.write(json.dumps(alert, indent=2))
        seeded["alerts"] = len(demo_alerts)

    # Seed demo playbooks (only if none exist)
    playbooks_dir = settings.playbooks_dir
    playbooks_dir.mkdir(parents=True, exist_ok=True)
    existing_playbooks = list(playbooks_dir.glob("*.json"))
    if len(existing_playbooks) == 0:
        yesterday_date = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() - 86400, tz=timezone.utc
        ).strftime("%Y-%m-%d")
        demo_playbooks = [
            {
                "id": "pb-reg-spike", "name": "Registration Spike Triage",
                "description": "Automated registration spike investigation: email domains -> IP clustering -> device fingerprints -> restriction check -> SEV assessment.",
                "category": "registration_spike", "version": 1, "created_at": now, "updated_at": now,
                "inputs": [{"name": "DATE", "type": "date", "description": "Investigation date", "required": True, "default": yesterday_date}],
                "nodes": [
                    {"id": "n1", "ref_id": "registration-events", "ref_type": "automation", "label": "Email domain analysis", "inputs": {"DATE": "{{input.DATE}}"}, "input_refs": {}, "position": {"x": 250, "y": 0}},
                    {"id": "n2", "ref_id": "registration-events", "ref_type": "automation", "label": "IP clustering", "inputs": {"DATE": "{{input.DATE}}"}, "input_refs": {}, "position": {"x": 100, "y": 150}},
                    {"id": "n3", "ref_id": "device-fingerprint", "ref_type": "automation", "label": "Device fingerprints", "inputs": {"DATE": "{{input.DATE}}"}, "input_refs": {}, "position": {"x": 400, "y": 150}},
                    {"id": "n4", "ref_id": "", "ref_type": "prompt", "label": "Analyze findings", "inputs": {}, "input_refs": {}, "body": "Analyze the registration spike findings from email domains, IP clusters, and device fingerprints. Determine if this is coordinated abuse.", "position": {"x": 250, "y": 300}},
                    {"id": "n5", "ref_id": "", "ref_type": "prompt", "label": "SEV Assessment", "inputs": {}, "input_refs": {}, "body": "Run SEV assessment based on accumulated findings. Check T7D WoW thresholds.", "position": {"x": 250, "y": 450}},
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n4"},
                    {"id": "e2", "source": "n2", "target": "n4"},
                    {"id": "e3", "source": "n3", "target": "n4"},
                    {"id": "e4", "source": "n4", "target": "n5"},
                ],
                "entry_node_ids": ["n1", "n2", "n3"],
            },
            {
                "id": "pb-ato-triage", "name": "ATO Investigation",
                "description": "Account takeover investigation: login scoring -> MITM rule check -> credential washing detection -> self-report correlation -> SEV.",
                "category": "ato", "version": 1, "created_at": now, "updated_at": now,
                "inputs": [{"name": "DATE", "type": "date", "description": "Investigation date", "required": True, "default": yesterday_date}],
                "nodes": [
                    {"id": "n1", "ref_id": "login-score-events", "ref_type": "automation", "label": "Login score analysis", "inputs": {"DATE": "{{input.DATE}}"}, "input_refs": {}, "position": {"x": 250, "y": 0}},
                    {"id": "n2", "ref_id": "rule-performance", "ref_type": "automation", "label": "MITM rule activations", "inputs": {"DATE": "{{input.DATE}}"}, "input_refs": {}, "position": {"x": 250, "y": 150}},
                    {"id": "n3", "ref_id": "", "ref_type": "prompt", "label": "Assess ATO impact", "inputs": {}, "input_refs": {}, "body": "Assess the scope of the ATO campaign based on login scoring and rule activations.", "position": {"x": 250, "y": 300}},
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n2"},
                    {"id": "e2", "source": "n2", "target": "n3"},
                ],
                "entry_node_ids": ["n1"],
            },
            {
                "id": "pb-scraping", "name": "Scraping Investigation",
                "description": "Guest/member scraping triage: denial events -> block filter rules -> IP analysis -> impact.",
                "category": "guest_scraping", "version": 1, "created_at": now, "updated_at": now,
                "inputs": [{"name": "DAYS", "type": "number", "description": "Lookback days", "required": False, "default": "7"}],
                "nodes": [
                    {"id": "n1", "ref_id": "site-traffic", "ref_type": "automation", "label": "Denial event volume", "inputs": {}, "input_refs": {}, "position": {"x": 250, "y": 0}},
                    {"id": "n2", "ref_id": "scraping-events", "ref_type": "automation", "label": "Block filter analysis", "inputs": {}, "input_refs": {}, "position": {"x": 250, "y": 150}},
                    {"id": "n3", "ref_id": "", "ref_type": "prompt", "label": "Summarize scraping", "inputs": {}, "input_refs": {}, "body": "Summarize scraping findings and recommend rule changes.", "position": {"x": 250, "y": 300}},
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n2"},
                    {"id": "e2", "source": "n2", "target": "n3"},
                ],
                "entry_node_ids": ["n1"],
            },
        ]
        for pb in demo_playbooks:
            fp = _safe_path(playbooks_dir, f"{pb['id']}.json")
            if fp:
                async with aiofiles.open(fp, "w") as f:
                    await f.write(json.dumps(pb, indent=2))
        seeded["playbooks"] = len(demo_playbooks)

    return SeedDemoResponse(seeded=seeded)


# ===================================================================
# IOCs
# ===================================================================


class IocEntry(BaseModel):
    value: str
    type: str
    sessions: list[str] = Field(default_factory=list)
    firstSeen: str = ""
    lastSeen: str = ""


class IocListResponse(BaseModel):
    count: int
    iocs: list[IocEntry]


class IocAddBody(BaseModel):
    iocs: list[dict[str, str]]
    session_id: str = Field(alias="sessionId")

    model_config = {"populate_by_name": True}


class IocAddResponse(BaseModel):
    ok: bool = True
    added: int = 0
    total: int = 0


class IocCheckResponse(BaseModel):
    found: bool = False
    matches: list[IocEntry] = Field(default_factory=list)


async def _load_ioc_db() -> dict[str, dict]:
    try:
        async with aiofiles.open(settings.ioc_db_path, "r") as f:
            return json.loads(await f.read())
    except Exception:
        return {}


async def _save_ioc_db(db: dict[str, dict]) -> None:
    async with aiofiles.open(settings.ioc_db_path, "w") as f:
        await f.write(json.dumps(db))


@router.get("/iocs", response_model=IocListResponse)
async def list_iocs():
    db = await _load_ioc_db()
    entries = sorted(db.values(), key=lambda e: len(e.get("sessions", [])), reverse=True)
    return IocListResponse(count=len(entries), iocs=entries[:200])


@router.post("/iocs", response_model=IocAddResponse)
async def add_iocs(body: IocAddBody):
    db = await _load_ioc_db()
    now = _now_iso()
    added = 0
    for ioc in body.iocs[:500]:
        key = f"{ioc.get('type', '')}:{ioc.get('value', '')}"
        if key in db:
            if body.session_id not in db[key].get("sessions", []):
                db[key].setdefault("sessions", []).append(body.session_id)
                db[key]["lastSeen"] = now
        else:
            db[key] = {
                "value": ioc.get("value", ""),
                "type": ioc.get("type", ""),
                "sessions": [body.session_id],
                "firstSeen": now,
                "lastSeen": now,
            }
            added += 1
    await _save_ioc_db(db)
    return IocAddResponse(added=added, total=len(db))


@router.get("/iocs/check", response_model=IocCheckResponse)
async def check_ioc(value: str = Query(default="")):
    if not value:
        return IocCheckResponse()
    db = await _load_ioc_db()
    matches = [e for e in db.values() if e.get("value") == value]
    return IocCheckResponse(found=len(matches) > 0, matches=matches)


# ===================================================================
# Notebooks
# ===================================================================


class NotebookAppendBody(BaseModel):
    session_id: str = Field(alias="sessionId")
    session_name: str = Field(default="", alias="sessionName")
    node_id: str = Field(default="", alias="nodeId")
    label: str = ""
    query: str = ""
    result_raw: str | None = Field(default=None, alias="resultRaw")
    severity: str = ""
    timestamp: str = ""
    confidence: float | None = None
    reasoning: str = ""
    tags: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class NotebookAppendResponse(BaseModel):
    ok: bool = True
    path: str = ""
    notebook: str = ""


def _nb_path(session_id: str) -> Path | None:
    safe_id = _sanitize_id(session_id)
    return _safe_path(settings.notebooks_dir, f"investigation-{safe_id[:8]}.ipynb")


def _init_notebook(session_id: str, session_name: str) -> dict:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelname": "trino",
            "session_id": session_id,
            "session_name": session_name,
        },
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [f"# Investigation: {session_name or session_id}\n"],
            }
        ],
    }


@router.post("/notebook/append", response_model=NotebookAppendResponse)
async def notebook_append(body: NotebookAppendBody):
    if not body.session_id or not body.query:
        raise HTTPException(status_code=400, detail="sessionId and query required")

    nb_fp = _nb_path(body.session_id)
    if not nb_fp:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    settings.notebooks_dir.mkdir(parents=True, exist_ok=True)

    # Load or init notebook
    if nb_fp.exists():
        try:
            async with aiofiles.open(nb_fp, "r") as f:
                nb = json.loads(await f.read())
        except Exception:
            nb = _init_notebook(body.session_id, body.session_name)
    else:
        nb = _init_notebook(body.session_id, body.session_name)

    node_ts = body.timestamp or _now_iso()

    # Markdown header cell
    md_source = [
        f"## {body.label or 'Query'}\n",
        "\n",
        f"**Severity:** {body.severity or 'benign'} | **Time:** {node_ts}\n",
    ]
    if body.confidence is not None:
        md_source.append(f"**Confidence:** {int(body.confidence * 100)}%\n")
    if body.reasoning:
        md_source.append(f"**Reasoning:** {body.reasoning}\n")
    if body.tags:
        md_source.append(f"**Tags:** {', '.join(body.tags)}\n")

    nb.setdefault("cells", []).append({
        "cell_type": "markdown",
        "metadata": {"node_id": body.node_id},
        "source": md_source,
    })

    # Code cell
    code_count = sum(1 for c in nb["cells"] if c.get("cell_type") == "code") + 1
    outputs = []
    if body.result_raw:
        outputs.append({"output_type": "stream", "name": "stdout", "text": [body.result_raw[:50000]]})

    nb["cells"].append({
        "cell_type": "code",
        "metadata": {"node_id": body.node_id, "timestamp": node_ts, "severity": body.severity or "benign"},
        "source": [body.query],
        "outputs": outputs,
        "execution_count": code_count,
    })

    async with aiofiles.open(nb_fp, "w") as f:
        await f.write(json.dumps(nb, indent=2))

    nb_name = f"investigation-{_sanitize_id(body.session_id)[:8]}"
    return NotebookAppendResponse(path=str(nb_fp), notebook=nb_name)


@router.get("/notebook/{session_id}")
async def get_notebook(session_id: str):
    nb_fp = _nb_path(session_id)
    if not nb_fp:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not nb_fp.exists():
        raise HTTPException(status_code=404, detail="Notebook not found")

    async with aiofiles.open(nb_fp, "r") as f:
        content = await f.read()

    nb_name = f"investigation-{_sanitize_id(session_id)[:8]}"
    return Response(
        content=content,
        media_type="application/x-ipynb+json",
        headers={"Content-Disposition": f'attachment; filename="{nb_name}.ipynb"'},
    )


# ===================================================================
# MCP Tools (stub)
# ===================================================================


@router.get("/mcp/tools", response_model=list[dict[str, Any]])
async def list_mcp_tools():
    return []
