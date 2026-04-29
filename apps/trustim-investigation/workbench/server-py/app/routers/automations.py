from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import APIRouter, HTTPException, Query, Request

from ..config import settings
from ..models.automation import Automation, AutomationSummary, ExecutionResult
from ..models.common import SuccessResponse

router = APIRouter(prefix="/automations", tags=["automations"])

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


# Headless account mapping for skill categories
ACCOUNT_MAP: dict[str, str] = {
    "registration-events": "register",
    "account-takeover": "ir2ato",
    "scraping": "ir2scraping",
    "login-analysis": "login",
    "fake-account-research": "ir2fake",
    "challenge-events": "trustim",
    "invitation-scoring": "trustim",
    "site-traffic": "trustim",
    "rule-performance": "trustim",
    "account-activity": "trustim",
    "device-fingerprint": "trustim",
}

# DAVI widget definitions (always available)
DAVI_WIDGETS: list[dict] = [
    {
        "id": "davi-sevcalculator",
        "name": "SevCalculatorWidget",
        "desc": "Automated cohort SEV assessment (DIHE + scraping WoW)",
        "category": "sev-assessment",
        "params": [
            {
                "name": "COHORT_MEMBER_IDS",
                "type": "string",
                "description": "SQL subquery returning member IDs",
                "required": True,
            }
        ],
        "body": "SevCalculatorWidget(cohort_member_ids={COHORT_MEMBER_IDS})",
    },
    {
        "id": "davi-dihe",
        "name": "DiheWidget",
        "desc": "DIHE analysis by account type",
        "category": "impact-analysis",
        "params": [
            {
                "name": "ACCOUNT_TYPE",
                "type": "string",
                "description": "fake or ato",
                "required": True,
                "default": "fake",
            },
            {
                "name": "PERIOD",
                "type": "string",
                "description": "Time period",
                "required": False,
                "default": "7d",
            },
        ],
        "body": "DiheWidget(account_type={ACCOUNT_TYPE}, period={PERIOD})",
    },
    {
        "id": "davi-ipactivity",
        "name": "IPActivityWidget",
        "desc": "IP/search pivot from member IDs or IPs",
        "category": "ato",
        "params": [
            {
                "name": "INPUT_VALUES",
                "type": "member_id_list",
                "description": "Member IDs or IPs",
                "required": True,
            },
            {
                "name": "PERIOD",
                "type": "string",
                "description": "Lookback period",
                "required": False,
                "default": "30d",
            },
        ],
        "body": "IPActivityWidget(input_values={INPUT_VALUES}, period={PERIOD})",
    },
    {
        "id": "davi-scraping",
        "name": "CaptainScrapingWidget",
        "desc": "Per-member scraping patterns (InVizor)",
        "category": "scraping",
        "params": [
            {
                "name": "MEMBER_IDS",
                "type": "member_id_list",
                "description": "Member IDs",
                "required": True,
            }
        ],
        "body": "CaptainScrapingWidget(member_ids={MEMBER_IDS})",
    },
    {
        "id": "davi-surface",
        "name": "SurfaceVisualizationWidget",
        "desc": "Registration traffic visualization with NL filtering",
        "category": "registration",
        "params": [
            {
                "name": "START_DATE",
                "type": "date",
                "description": "Start date",
                "required": True,
            },
            {
                "name": "END_DATE",
                "type": "date",
                "description": "End date",
                "required": True,
            },
            {
                "name": "PROMPT",
                "type": "string",
                "description": "Natural language filter",
                "required": False,
                "default": "top 10 countries hourly line chart",
            },
        ],
        "body": "SurfaceVisualizationWidget(start_date={START_DATE}, end_date={END_DATE}, prompt={PROMPT})",
    },
    {
        "id": "davi-keywords",
        "name": "KeywordsAnalysisWidget",
        "desc": "Find members searching specific keywords",
        "category": "messaging-abuse",
        "params": [
            {
                "name": "KEYWORDS",
                "type": "string",
                "description": "Comma-separated keywords",
                "required": True,
            },
            {
                "name": "PERIOD",
                "type": "string",
                "description": "Lookback period",
                "required": False,
                "default": "7d",
            },
        ],
        "body": "KeywordsAnalysisWidget(keywords={KEYWORDS}, period={PERIOD})",
    },
    {
        "id": "davi-searchterms",
        "name": "SearchTermRankingWidget",
        "desc": "Search term ranking by member IDs",
        "category": "messaging-abuse",
        "params": [
            {
                "name": "MIDS",
                "type": "member_id_list",
                "description": "Member IDs",
                "required": True,
            },
            {
                "name": "PERIOD",
                "type": "string",
                "description": "Lookback period",
                "required": False,
                "default": "30d",
            },
        ],
        "body": "SearchTermRankingWidget(mids={MIDS}, period={PERIOD})",
    },
    {
        "id": "davi-magicplot",
        "name": "MagicPlotWidget",
        "desc": "Auto-detect and plot any DataFrame",
        "category": "utility",
        "params": [
            {
                "name": "DATA_QUERY",
                "type": "string",
                "description": "SQL query or DataFrame expression",
                "required": True,
            }
        ],
        "body": "MagicPlotWidget(data_query={DATA_QUERY})",
    },
]

# Skill automation cache (30s TTL)
_skill_cache: list[dict] | None = None
_skill_cache_time: float = 0


def _load_skill_automations() -> list[dict]:
    global _skill_cache, _skill_cache_time
    if _skill_cache is not None and time.time() - _skill_cache_time < 30:
        return _skill_cache

    automations: list[dict] = []
    action_skills_dir = settings.skills_dir / "actions"
    if not action_skills_dir.exists():
        _skill_cache = []
        _skill_cache_time = time.time()
        return []

    try:
        for skill_dir in action_skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_path = skill_dir / "SKILL.md"
            if not skill_path.exists():
                continue
            try:
                content = skill_path.read_text()
                # Parse YAML frontmatter
                fm_match = re.match(r"^---\n([\s\S]*?)\n---", content)
                name = skill_dir.name
                description = ""
                if fm_match:
                    name_match = re.search(r"name:\s*(.+)", fm_match.group(1))
                    desc_match = re.search(
                        r"description:\s*(.+)", fm_match.group(1)
                    )
                    if name_match:
                        name = name_match.group(1).strip()
                    if desc_match:
                        description = desc_match.group(1).strip()

                # Extract SQL blocks
                sql_blocks = re.findall(
                    r"```sql\n([\s\S]*?)```", content
                )
                for i, sql in enumerate(sql_blocks):
                    sql = sql.strip()
                    # Extract parameter placeholders
                    param_names = list(
                        {m for m in re.findall(r"\{([A-Z_]+)\}", sql)}
                    )
                    inputs = []
                    for pn in param_names:
                        ptype = "string"
                        if "DATE" in pn:
                            ptype = "date"
                        elif "MEMBER" in pn:
                            ptype = "member_id_list"
                        inputs.append(
                            {
                                "name": pn,
                                "type": ptype,
                                "description": pn.lower().replace("_", " "),
                                "required": True,
                            }
                        )

                    # Find section header above this SQL block
                    block_text = f"```sql\n{sql_blocks[i]}```"
                    block_idx = content.find(block_text)
                    header = f"Query {i + 1}"
                    if block_idx > 0:
                        preceding = content[:block_idx]
                        hdr_match = re.search(
                            r"###?\s+(.+)\n[^#]*$", preceding
                        )
                        if hdr_match:
                            header = hdr_match.group(1)

                    automations.append(
                        {
                            "id": f"skill-{skill_dir.name}-{i}",
                            "name": f"{name}: {header}",
                            "description": description or header,
                            "category": skill_dir.name,
                            "exec_type": "trino_query",
                            "exec_body": sql,
                            "exec_config": {
                                "headless_account": ACCOUNT_MAP.get(
                                    skill_dir.name, "trustim"
                                )
                            },
                            "inputs": inputs,
                            "outputs": [
                                {
                                    "name": "result",
                                    "type": "string",
                                    "description": "Query result",
                                    "required": True,
                                }
                            ],
                            "source": "skill",
                            "source_skill": skill_dir.name,
                        }
                    )
            except Exception:
                continue
    except Exception:
        pass

    # Add DAVI widgets
    for w in DAVI_WIDGETS:
        automations.append(
            {
                "id": w["id"],
                "name": w["name"],
                "description": w["desc"],
                "category": w["category"],
                "exec_type": "davi_widget",
                "exec_body": w["body"],
                "exec_config": {
                    "widget_name": w["name"],
                    "timeout": 300000,
                },
                "inputs": w["params"],
                "outputs": [
                    {
                        "name": "result",
                        "type": "string",
                        "description": "Widget output",
                        "required": True,
                    }
                ],
                "source": "built-in",
            }
        )

    _skill_cache = automations
    _skill_cache_time = time.time()
    return automations


async def _load_custom_automations() -> list[dict]:
    automations_dir = settings.automations_dir
    customs: list[dict] = []
    if not automations_dir.exists():
        return customs
    for fp in automations_dir.glob("*.json"):
        try:
            async with aiofiles.open(fp, "r") as f:
                data = json.loads(await f.read())
            data["source"] = "custom"
            customs.append(data)
        except Exception:
            continue
    return customs


async def _get_all_automations() -> list[dict]:
    skill_autos = _load_skill_automations()
    custom_autos = await _load_custom_automations()
    return [*skill_autos, *custom_autos]


async def _find_automation(auto_id: str) -> dict | None:
    all_autos = await _get_all_automations()
    return next((a for a in all_autos if a.get("id") == auto_id), None)


# ---------------------------------------------------------------------------
# Migration stub (BEFORE /:id to avoid FastAPI treating "migrate" as an ID)
# ---------------------------------------------------------------------------


class _MigrateResult(SuccessResponse):
    migrated: int = 0
    message: str = "Automations are now loaded dynamically from skills"
    errors: list[str] = []


@router.post("/migrate", response_model=_MigrateResult)
async def migrate_automations():
    all_autos = await _get_all_automations()
    return _MigrateResult(migrated=len(all_autos))


# ---------------------------------------------------------------------------
# CRUD routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[AutomationSummary])
async def list_automations(
    category: Optional[str] = Query(None),
    exec_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    all_autos = await _get_all_automations()
    result = all_autos
    if category:
        result = [a for a in result if a.get("category") == category]
    if exec_type:
        result = [a for a in result if a.get("exec_type") == exec_type]
    if search:
        q = search.lower()
        result = [
            a
            for a in result
            if q in (a.get("name") or "").lower()
            or q in (a.get("description") or "").lower()
        ]
    return [
        AutomationSummary(
            id=a["id"],
            name=a.get("name", ""),
            description=a.get("description", ""),
            category=a.get("category", ""),
            exec_type=a.get("exec_type", "trino_query"),
            input_count=len(a.get("inputs") or []),
            source_skill=a.get("source_skill"),
        )
        for a in result
    ]


@router.get("/{auto_id}", response_model=Automation)
async def get_automation(auto_id: str):
    safe_id = _sanitize_id(auto_id)
    auto = await _find_automation(safe_id)
    if not auto:
        raise HTTPException(status_code=404, detail="Not found")
    return auto


@router.post("", response_model=Automation)
async def create_automation(body: Automation):
    now = datetime.utcnow().isoformat() + "Z"
    auto_id = f"custom-{int(time.time() * 1000)}-{hex(id(body))[-4:]}"
    data = body.model_dump()
    data.update(
        id=auto_id,
        created_at=now,
        updated_at=now,
    )
    fp = _safe_path(settings.automations_dir, f"{auto_id}.json")
    if not fp:
        raise HTTPException(status_code=400, detail="Invalid ID")
    settings.automations_dir.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(fp, "w") as f:
        await f.write(json.dumps(data, indent=2))
    return data


@router.put("/{auto_id}", response_model=Automation)
async def update_automation(auto_id: str, request: Request):
    safe_id = _sanitize_id(auto_id)
    fp = _safe_path(settings.automations_dir, f"{safe_id}.json")
    if not fp or not fp.exists():
        raise HTTPException(
            status_code=404, detail="Can only edit custom automations"
        )
    async with aiofiles.open(fp, "r") as f:
        existing = json.loads(await f.read())
    body = await request.json()
    updated = {
        **existing,
        **body,
        "id": existing["id"],
        "created_at": existing.get("created_at", ""),
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    async with aiofiles.open(fp, "w") as f:
        await f.write(json.dumps(updated, indent=2))
    return updated


@router.delete("/{auto_id}", response_model=SuccessResponse)
async def delete_automation(auto_id: str):
    safe_id = _sanitize_id(auto_id)
    fp = _safe_path(settings.automations_dir, f"{safe_id}.json")
    if fp and fp.exists():
        fp.unlink()
    return SuccessResponse()


@router.post("/{auto_id}/run", response_model=ExecutionResult)
async def run_automation(auto_id: str):
    safe_id = _sanitize_id(auto_id)
    auto = await _find_automation(safe_id)
    if not auto:
        raise HTTPException(status_code=404, detail="Not found")
    return ExecutionResult(
        success=False,
        error="Not implemented in Python server",
    )
