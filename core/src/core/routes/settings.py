"""Global lab/agent settings + the cross-tool agent-sync trigger.

Reads/writes ``.agents/config.json`` through the validated ``lab.settings``
library (no subprocess — the server already depends on ``lab``). The settings
modal in the UI is the primary client.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from lab import agentsync
from lab import settings as lab_settings

router = APIRouter()


# The CLI binary each agent launches (see routes/term.py). copilot is the
# standalone agentic CLI, not the `gh copilot` suggest/explain extension.
_AGENT_BIN = {"claude": "claude", "codex": "codex", "copilot": "copilot"}


@router.get("/api/agents/available")
async def agents_available() -> dict:
    """Which agents are actually launchable (their CLI is on PATH)."""
    return {agent: bool(shutil.which(binary)) for agent, binary in _AGENT_BIN.items()}


@router.get("/api/settings")
async def get_settings(request: Request) -> dict:
    """Return the merged global settings (defaults + saved overrides)."""
    root: Path = request.app.state.index_cache.root
    return lab_settings.load(root)


class SettingsPatch(BaseModel):
    # All optional: only the keys the client sends are updated. ``model`` may be
    # explicitly null to clear the global default.
    defaultAgent: str | None = None
    model: str | None = None
    theme: str | None = None


@router.post("/api/settings")
async def update_settings(body: SettingsPatch, request: Request) -> dict:
    """Patch one or more settings (validated). Returns the full merged config."""
    root: Path = request.app.state.index_cache.root
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        return lab_settings.load(root)
    try:
        return lab_settings.update(root, patch)
    except lab_settings.SettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/agents/sync")
async def agents_sync(request: Request, dry_run: bool = False) -> dict:
    """Run ``lab agents sync`` (AGENTS.md + memory + skill symlinks). Idempotent."""
    root: Path = request.app.state.index_cache.root
    return agentsync.sync_all(root, dry_run=dry_run)
