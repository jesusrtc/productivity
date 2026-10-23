"""Authenticated agentic workspace UI/API; all state is workspace-owned."""
from __future__ import annotations

from contextlib import closing
import mimetypes
import os
from pathlib import Path
import shutil

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core import auth
from core.routes.mutation import _root_for_vault
from lab import paths, settings, storage
from lab.model import validate_id
from lab.agentic_store import Store, PROVIDERS

router = APIRouter()


@router.get('/api/agentic-notifications')
def notifications(request: Request):
    auth.require_admin(request)
    from core.agentic_runtime import Supervisor
    result = []
    registry = {os.path.abspath(v['path']): v['id'] for v in paths.read_vault_registry().get('vaults', [])}
    scanner = Supervisor()
    for vault, workspace, ident in scanner.workspaces(request.app.state.index_cache.root):
        if not (workspace / '.lab/agentic/state.sqlite3').is_file():
            continue
        metadata = storage.read_json(paths.workspace_file(vault, ident))
        for row in Store(workspace).notifications():
            result.append({**row, 'type': 'agentic', 'key': f'agentic:{workspace}:{row["task_id"] or "coordinator"}',
                           'workspace_id': ident, 'workspace_path': str(workspace), 'vault': registry.get(os.path.abspath(vault), vault.name),
                           'label': ' / '.join(filter(None, [metadata.get('title') or metadata.get('name') or ident, row['mission'], row['title']]))})
    return {'notifications': result, 'unavailable_vaults': scanner.errors}


def scope(request, workspace_id, vault):
    auth.require_admin(request)
    try:
        validate_id(workspace_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    root = _root_for_vault(request, vault)
    file = paths.workspace_file(root, workspace_id)
    if not file.is_file():
        raise HTTPException(404, 'Workspace not found')
    data = storage.read_json(file)
    if data.get('kind') != 'agentic':
        raise HTTPException(409, 'This workspace is not agentic')
    return root, Store(paths.workspace_dir(root, workspace_id))


def checked(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('/api/agentic/{workspace_id}')
def state(workspace_id: str, request: Request, vault: str | None = None):
    root, store = scope(request, workspace_id, vault)
    data = store.snapshot()
    data['workspace'] = str(store.workspace)
    data['provider'] = data['settings']['provider'] or settings.resolve_agent(root, workspace_id)
    data['model'] = data['settings']['model'] or settings.resolve_model(root, workspace_id)
    data['providers'] = [{'id': provider, 'available': bool(shutil.which(provider))} for provider in PROVIDERS]
    data['supervisor_error'] = getattr(request.app.state, 'agentic_supervisor', None).errors.get(str(store.workspace)) if getattr(request.app.state, 'agentic_supervisor', None) else 'Agentic supervisor is not running'
    return data


class Message(BaseModel):
    content: str = Field(min_length=1, max_length=64000)
    request_id: str | None = None
    mission_id: str | None = None
    task_id: str | None = None


@router.post('/api/agentic/{workspace_id}/messages')
def message(workspace_id: str, body: Message, request: Request, vault: str | None = None):
    _, store = scope(request, workspace_id, vault)
    return checked(store.message, body.content, request_id=body.request_id, mission_id=body.mission_id, task_id=body.task_id)


class Actions(BaseModel):
    actions: list[dict] = Field(max_length=100)


@router.post('/api/agentic/{workspace_id}/actions')
def apply(workspace_id: str, body: Actions, request: Request, vault: str | None = None):
    _, store = scope(request, workspace_id, vault)
    return {'results': checked(store.apply, body.actions)}


@router.post('/api/agentic/{workspace_id}/notifications/{message_id}/review')
def review_notification(workspace_id: str, message_id: str, request: Request, vault: str | None = None):
    _, store = scope(request, workspace_id, vault)
    return checked(store.acknowledge, message_id)


@router.patch('/api/agentic/{workspace_id}/settings')
def configure(workspace_id: str, body: dict, request: Request, vault: str | None = None):
    _, store = scope(request, workspace_id, vault)
    return checked(store.configure, body)


@router.get('/api/agentic/{workspace_id}/tasks/{task_id}')
def detail(workspace_id: str, task_id: str, request: Request, vault: str | None = None):
    _, store = scope(request, workspace_id, vault)
    return checked(store.detail, task_id)


@router.get('/api/agentic/{workspace_id}/events')
def events(workspace_id: str, request: Request, vault: str | None = None,
           task_id: str | None = None, run_id: str | None = None, after: int = 0,
           before: int | None = None, latest: bool = False):
    _, store = scope(request, workspace_id, vault)
    return {'events': store.events(task_id=task_id, run_id=run_id, after=after, before=before, latest=latest)}


def asset_file(store, asset_id):
    with closing(store._connect()) as db:
        asset = store.get(db, 'assets', asset_id)
    if not asset:
        raise HTTPException(404, 'Asset not found')
    if asset['kind'] != 'file':
        raise HTTPException(422, 'This asset is an external link')
    path = (store.workspace / asset['target']).resolve()
    if not path.is_relative_to(store.workspace) or not path.is_file():
        raise HTTPException(404, 'Asset file is unavailable')
    return asset, path


@router.get('/api/agentic/{workspace_id}/assets/{asset_id}')
def asset(workspace_id: str, asset_id: str, request: Request, vault: str | None = None):
    _, store = scope(request, workspace_id, vault)
    asset, path = asset_file(store, asset_id)
    suffix = path.suffix.lower()
    kind = 'notebook' if suffix == '.ipynb' else 'markdown' if suffix in ('.md', '.markdown') else 'image' if suffix in ('.png', '.jpg', '.jpeg', '.webp', '.gif') else 'pdf' if suffix == '.pdf' else 'video' if suffix in ('.mp4', '.webm', '.mov') else 'audio' if suffix in ('.mp3', '.wav', '.m4a') else 'text'
    data = {'asset': asset, 'kind': kind, 'size': path.stat().st_size}
    if kind == 'notebook':
        from core.diff_parser import parse_notebook
        from core.routes.nb_exec import recover_stale_pending
        recover_stale_pending(path)
        data['cells'] = parse_notebook(str(path))
    if kind in ('text', 'markdown'):
        if path.stat().st_size <= 2_000_000:
            try:
                data['content'] = path.read_text(encoding='utf-8')
            except UnicodeError:
                data['kind'] = 'download'
        else:
            data['kind'] = 'download'
    return data


@router.get('/api/agentic/{workspace_id}/assets/{asset_id}/content')
def content(workspace_id: str, asset_id: str, request: Request, vault: str | None = None, download: bool = False):
    _, store = scope(request, workspace_id, vault)
    _, path = asset_file(store, asset_id)
    media = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    # User/agent HTML and SVG must never execute with Lab's authenticated origin.
    safe_inline = media.startswith(('image/png', 'image/jpeg', 'image/webp', 'image/gif', 'video/', 'audio/')) or media == 'application/pdf'
    return FileResponse(path, media_type=media if safe_inline else 'application/octet-stream',
                        filename=path.name, content_disposition_type='attachment' if download or not safe_inline else 'inline',
                        headers={'X-Content-Type-Options': 'nosniff'})
