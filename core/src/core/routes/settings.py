"""Global lab/agent settings and read-only framework context checks.

Uses the validated ``lab.settings`` writer. ``/api/settings/global`` stores
Lab-wide choices; ``/api/settings`` retains legacy vault-scoped compatibility.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from lab import agentsync
from lab import projects
from lab import settings as lab_settings

from core import auth, fsguard, vault_config

router = APIRouter()


# The CLI binary each agent launches (see routes/term.py).
_AGENT_BIN = {"claude": "claude", "codex": "codex", "copilot": "copilot"}


def _agent_available(agent: str) -> bool:
    binary = _AGENT_BIN.get(agent)
    return bool(binary and shutil.which(binary))


@router.get("/api/agents/available")
def agents_available() -> dict:
    """Which agents are actually launchable (their CLI is on PATH)."""
    return {agent: _agent_available(agent) for agent in ("claude", "codex", "copilot")}


def _with_flags(cfg: dict) -> dict:
    """Attach the human-readable autopilot flag per agent so the UI can show
    what each checkbox actually appends to the launch command."""
    cfg["homeFolder"] = str(Path.home())
    cfg["autopilotFlags"] = {
        agent: " ".join(flags)
        for agent, flags in lab_settings.AUTOPILOT_FLAGS.items()
    }
    return cfg


@router.get("/api/settings")
def get_settings(request: Request) -> dict:
    """Return the merged global settings (defaults + saved overrides)."""
    root = auth.request_root(request)
    return _with_flags(lab_settings.load(root))


class SettingsPatch(BaseModel):
    # All optional: only the keys the client sends are updated. ``model`` may be
    # explicitly null to clear the global default.
    defaultAgent: str | None = None
    model: str | None = None
    theme: str | None = None
    # Per-agent map: launch this agent with its autopilot flag (see
    # lab.settings.AUTOPILOT_FLAGS). Partial patches merge per key.
    autopilot: dict[str, bool] | None = None
    documentTerminals: dict | None = None
    projectsFolder: str | None = None
    worktreesFolder: str | None = None
    projectLocations: list[dict] | None = None
    scopeLinkTypes: list[dict] | None = None


@router.post("/api/settings")
def update_settings(body: SettingsPatch, request: Request) -> dict:
    """Patch one or more settings (validated). Returns the full merged config."""
    root = auth.request_root(request)
    patch = body.model_dump(exclude_unset=True)
    if {'projectsFolder', 'worktreesFolder', 'projectLocations', 'scopeLinkTypes'} & patch.keys():
        auth.require_admin(request)
    if not patch:
        return _with_flags(lab_settings.load(root))
    requested_default = patch.get("defaultAgent")
    if requested_default and requested_default not in vault_config.supported_agents(root):
        raise HTTPException(
            status_code=400,
            detail=f"agent {requested_default!r} is not enabled for this vault",
        )
    try:
        return _with_flags(lab_settings.update(root, patch))
    except lab_settings.SettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/agents/sync")
def agents_sync(request: Request, dry_run: bool = False) -> dict:
    """Compatibility endpoint; no longer creates or links agent files."""
    root = auth.request_root(request)
    return agentsync.sync_all(root, dry_run=dry_run)


@router.get("/api/agents/context")
def agents_context(request: Request) -> dict:
    """Report packaged context readiness without writing to the workspace."""
    return agentsync.doctor_all(auth.request_root(request), include_cli=True)


@router.get("/api/agents/context/guide")
def agent_launch_context() -> dict:
    """Read the same installed framework guide used by the agent launcher."""
    try:
        from lab.agent_context import read_context
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="The installed Lab CLI does not expose launch context yet.") from exc
    return {"content": read_context()}


@router.get('/api/settings/global')
def get_global_settings(request: Request) -> dict:
    auth.require_admin(request)
    return _with_flags(lab_settings.load(Path(request.app.state.index_cache.root)))


@router.post('/api/settings/global')
def update_global_settings(body: SettingsPatch, request: Request) -> dict:
    auth.require_admin(request)
    patch = body.model_dump(exclude_unset=True)
    agent = patch.get('defaultAgent')
    if agent and agent in _AGENT_BIN and not _agent_available(agent):
        raise HTTPException(400, f'{agent} is not installed on the computer running Lab. Choose an installed agent.')
    try:
        return _with_flags(lab_settings.update_global(Path(request.app.state.index_cache.root), patch))
    except lab_settings.SettingsError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('/api/projects')
def project_catalog(request: Request) -> dict:
    auth.require_admin(request)
    root = Path(request.app.state.index_cache.root)
    config = lab_settings.load(root)
    return fsguard.guarded(projects.location(config['projectsFolder']),
                           lambda: projects.catalog(config, fsguard.checkpoint))


@router.get('/api/projects/scopes')
def project_scope_catalog(request: Request) -> dict:
    auth.require_admin(request)
    root = Path(request.app.state.index_cache.root)
    config = lab_settings.load(root)
    return fsguard.guarded(projects.location(config['projectsFolder']),
                           lambda: projects.sidebar_scopes(config, fsguard.checkpoint),
                           timeout=15, operation_key=('project-scopes', str(root), config['projectsFolder'],
                               config['worktreesFolder'], tuple((row['path'], row.get('worktreeFolder', '')) for row in config['projectLocations'])))


class ProjectLocation(BaseModel):
    path: str
    worktreeFolder: str = ''


class ProjectSelection(BaseModel):
    projects: list[ProjectLocation]
    base: str | None = None


@router.post('/api/projects/register')
def register_projects(body: ProjectSelection, request: Request) -> dict:
    auth.require_admin(request)
    root = Path(request.app.state.index_cache.root)
    try:
        result = projects.register(root, [row.model_dump() for row in body.projects],
                                   projects.location(body.base) if body.base else None)
        result['settings'] = _with_flags(result['settings'])
        return result
    except (lab_settings.SettingsError, OSError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc


class ScopeLinksBody(BaseModel):
    path: str
    links: list[dict]
    expected: str


def _scope_link_root(path, request):
    from core.routes.diff import _git_status_dir_allowed
    auth.require_admin(request)
    try:
        root = projects.location(path).resolve()
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc
    if not _git_status_dir_allowed(root, auth.request_root(request), include_projects=True):
        raise HTTPException(403, 'Folder is outside the configured projects')
    return root


def _internal_scope_link(link, request, record_rows=None):
    from core.routes.assistant import _require_root
    from core.routes import assistant_v2
    from lab import assistant_records as records
    root = _require_root(request)
    if str(root) != link.get('assistant_root'):
        raise ValueError('Internal document belongs to another Assistant library')
    rows = list(records.records(root)) if record_rows is None else record_rows
    owner = next((row for row in rows if row['id'] == link.get('document_id') and not row.get('parent') and row['type'] in {'note', 'task'}), None)
    if owner is None:
        raise ValueError('Internal document is no longer available')
    target = owner
    if link.get('tab_id'):
        candidates = [owner, *records.descendants(rows, owner, by_parent=records.children_index(rows))]
        target = next((row for row in candidates if row['id'] == link['tab_id']), None)
        if target is None:
            raise ValueError('The selected tab does not belong to this document')
    return {'title': owner['title'] + (' / ' + target['title'] if target != owner else ''),
            'document_title': owner['title'], 'tab_title': target['title'] if target != owner else None,
            'path': target['path'], 'document_kind': assistant_v2.kind(owner)}


def _present_scope_links(data, types, request):
    from lab import assistant_records as records, paths
    from core.link_services import EXTERNAL_TYPES
    types_by_id = {row['id']: row for row in [*EXTERNAL_TYPES, *types]}
    rows = None
    if any(link.get('kind') == 'internal' for link in data['links']):
        root = paths.assistant_root()
        if root and root.is_dir():
            rows = list(records.records(root))
    presented = []
    for link in data['links']:
        row = {**link, 'type_name': types_by_id.get(link['type'], {}).get('name', link['type'])}
        if link['kind'] == 'internal':
            try:
                row.update(_internal_scope_link(link, request, rows))
            except (ValueError, OSError, HTTPException) as exc:
                row.update(unavailable=True, error=str(getattr(exc, 'detail', exc)))
        presented.append(row)
    return {**data, 'links': presented, 'types': types}


@router.get('/api/scope-links')
def get_scope_links(path: str, request: Request):
    from lab import scope_links
    root = _scope_link_root(path, request)
    types = lab_settings.load(auth.request_root(request))['scopeLinkTypes']
    return _present_scope_links(scope_links.read(root), types, request)


@router.put('/api/scope-links')
def update_scope_links(body: ScopeLinksBody, request: Request):
    from urllib.parse import urlsplit
    from uuid import uuid4
    from lab import scope_links, assistant_records as records, paths
    from core.link_services import EXTERNAL_TYPES, infer
    root = _scope_link_root(body.path, request)
    types = lab_settings.load(auth.request_root(request))['scopeLinkTypes']
    by_id = {row['id']: row for row in [*EXTERNAL_TYPES, *types]}
    if len(body.links) > 100:
        raise HTTPException(400, 'A scope can have at most 100 links')
    normalized = []
    ids = set()
    record_rows = None
    try:
        for link in body.links:
            automatic = link.get('kind') == 'external' or ('url' in link and link.get('type') is None)
            link_type = by_id.get(link.get('type')) if isinstance(link.get('type'), str) else None
            if automatic:
                service = infer(str(link.get('url') or '').strip())
                link_type = {'id': service['id'] if service else 'url', 'kind': 'external'}
            if link_type is None:
                raise ValueError('Choose an allowed link type, or add it in Settings')
            identifier = str(link.get('id') or uuid4())
            if identifier in ids or len(identifier) > 100:
                raise ValueError('Link IDs must be unique')
            ids.add(identifier)
            label = str(link.get('label') or '').strip()
            if len(label) > 200:
                raise ValueError('Link labels must be at most 200 characters')
            row = {'id': identifier, 'type': link_type['id'], 'kind': link_type['kind'], 'label': label}
            if row['kind'] == 'external':
                url = str(link.get('url') or '').strip()
                parsed = urlsplit(url)
                if len(url) > 4096 or parsed.scheme not in {'http', 'https'} or not parsed.hostname:
                    raise ValueError('External links need a full http or https URL')
                row['url'] = url
            else:
                row.update(assistant_root=link.get('assistant_root'), document_id=link.get('document_id'), tab_id=link.get('tab_id') or None)
                if record_rows is None:
                    assistant_root = paths.assistant_root()
                    record_rows = list(records.records(assistant_root)) if assistant_root and assistant_root.is_dir() else []
                _internal_scope_link(row, request, record_rows)
            normalized.append(row)
        data = scope_links.write(root, normalized, body.expected)
        return _present_scope_links(data, types, request)
    except (ValueError, OSError) as exc:
        raise HTTPException(409 if 'changed elsewhere' in str(exc) else 400, str(exc)) from exc
