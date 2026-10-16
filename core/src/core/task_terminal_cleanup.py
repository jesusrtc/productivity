"""Retire task-owned tmux sessions after a status-based grace period."""
from __future__ import annotations

import asyncio
from contextlib import nullcontext
import logging
import os
from pathlib import Path
import subprocess
import threading
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core import auth, fsguard
from core.routes import term, terminal_cleanup as reviewed
from lab import assistant_records, assistant_tasks, objective_store, objectives, paths, storage, tmux_sockets
from lab.workspace_identity import operation_lease

router = APIRouter()
log = logging.getLogger(__name__)
RETENTION = {'todo': 3600, 'done': 3600, 'wont_do': 3600, 'paused': 3 * 86400}
ASSISTANT_STATUS = {'not_started': 'todo', 'done': 'done', 'skipped': 'wont_do',
                    'cancelled': 'wont_do', 'blocked': 'paused', 'in_progress': 'in_progress'}
INTERVAL = 60
_LOCK = threading.RLock()
_last_result = {}


def _journal_path(root):
    return paths.vault_state_dir(root) / 'task-terminal-retention.json'


def _journal(root):
    try:
        data = storage.read_json(_journal_path(root))
        if not isinstance(data, dict):
            raise ValueError('Invalid task terminal retention journal')
        return data
    except FileNotFoundError:
        return {}


def save_parents(root, workspace, parents):
    """Persist cleanup inheritance independently of the browser's layout."""
    with term._SESSION_METADATA_LOCK:
        data = term._load_workspace(root, workspace)
        if data is None:
            raise HTTPException(404, 'Workspace not found')
        saved = {s['name']: s for s in data.get('sessions', []) if isinstance(s, dict) and s.get('name')}
        before = {name: ('parent_terminal' in row, row.get('parent_terminal')) for name, row in saved.items()}
        for child, parent in parents.items():
            # Borrowed/shared document terminals must retain their own owner.
            if child not in saved or parent is not None and parent not in saved:
                continue
            if parent is None:
                saved[child]['parent_terminal'] = None
            else:
                saved[child]['parent_terminal'] = parent
        for name in saved:
            seen, current = set(), name
            while current in saved:
                if current in seen:
                    raise HTTPException(400, 'Terminal parents cannot form a cycle')
                seen.add(current)
                current = saved[current].get('parent_terminal')
        if before != {name: ('parent_terminal' in row, row.get('parent_terminal')) for name, row in saved.items()}:
            term._save_workspace(root, workspace, data)


class TerminalParents(BaseModel):
    workspace_id: str
    vault: str | None = None
    parents: dict[str, str | None] = Field(default_factory=dict, max_length=10000)


@router.post('/api/term/sessions/parents')
@term._with_workspace_lease
def set_parents(body: TerminalParents, request: Request):
    root = term._vault_root_for(auth.request_root(request), body.vault)
    save_parents(root, body.workspace_id, body.parents)
    return {'ok': True}


def _parent(saved, logical):
    row = saved[logical]
    if 'parent_terminal' in row:
        return row['parent_terminal']
    if term.terminal_automation_lifecycle.NAME.fullmatch(logical) and not logical.endswith('-1'):
        return logical.rsplit('-', 1)[0] + '-1'
    return None


def _owner(root, workspace, saved, logical, registry, *, assistant_cache=None):
    """A child's own task wins; otherwise walk its saved parent chain."""
    seen, objective_id = set(), None
    while logical in saved and logical not in seen:
        seen.add(logical)
        row = saved[logical]
        link = registry.get('terminal_links', {}).get(row.get('session_id'), {})
        if objective_id and link.get('objective_id') and objective_id != link['objective_id']:
            return None
        objective_id = objective_id or link.get('objective_id')
        if link.get('main'):
            return None
        if link.get('task_id'):
            objective = next((o for o in registry.get('objectives', []) if o['id'] == link.get('objective_id')), None)
            task = next((t for t in objectives._tasks(objective) if t['id'] == link['task_id']), None) if objective else None
            if task is None:
                return None
            # Checklist edits can reopen completion even before its next save.
            status = task.get('status', 'done' if task.get('done') else 'todo')
            if status == 'done' and any(objectives.task_checklists.counts(
                    objectives._task_body(paths.workspace_dir(root, workspace), objective, child))['pending']
                    for child, _ in objectives._task_tree([task])):
                return None
            return {'owner': ['objective', workspace, objective['id'], task['id']],
                    'status': status, 'changed_at': task.get('status_changed_at'), 'title': task['title']}
        linked = row.get('linked_task') or {}
        if linked.get('task_id') and linked.get('assistant_root'):
            assistant_root = Path(linked['assistant_root']).resolve()
            # Only the configured Assistant database is eligible, never an
            # arbitrary filesystem location supplied in terminal metadata.
            configured = paths.assistant_root()
            if configured is None or assistant_root != configured.resolve():
                return None
            key = (str(assistant_root), linked['document_id'])
            cache = assistant_cache if assistant_cache is not None else {}
            if key not in cache:
                cache[key] = assistant_tasks.view(assistant_root, linked['document_id'], _refresh=False)
            task = next((t for t in cache[key]['tasks'] if t['id'] == linked['task_id']), None)
            if task is None:
                return None
            return {'owner': ['assistant', *key, task['id']],
                    'status': ASSISTANT_STATUS.get(task['status']),
                    'changed_at': task.get('status_changed_at'), 'title': task['title']}
        # Legacy automation runs have deterministic siblings, including CLI
        # launches made before parent inheritance was persisted.
        logical = _parent(saved, logical)
    return None


def _workspace(root, workspace, *, locked=False):
    data = term._load_workspace(root, workspace) or {}
    saved = {s['name']: s for s in data.get('sessions', []) if isinstance(s, dict) and s.get('name')}
    registry = objectives.load(root, workspace, _locked=locked) if (
        not workspace.startswith('__') and paths.workspace_file(root, workspace).is_file()) else {}
    return saved, registry


def _clock(owner, live, previous, now):
    identity = [live['tmux_socket'], live['tmux_id'], live['created'], live.get('pane_pid')]
    signature = {key: owner.get(key) for key in ('owner', 'status', 'changed_at')}
    signature['identity'] = identity
    if all(previous.get(k) == v for k, v in signature.items()) and isinstance(previous.get('since'), (int, float)):
        since = previous['since']
    else:
        changed = owner.get('changed_at')
        since = changed if type(changed) in {int, float} and 0 < changed <= now else now
        since = max(since, live['created'])
    return {**signature, 'since': since}


def _root_pending(root, listing, now, persist):
    meta, journal = term._load_meta(root), _journal(root)
    updated, workspaces, assistant_cache, pending = {}, {}, {}, []
    for live in listing:
        fsguard.checkpoint()
        name = live['name']
        info = meta.get(name)
        if not info:
            continue
        workspace, logical = info.get('workspace_id'), info.get('logical_name')
        if (not workspace or not logical or logical == 'server' or logical.startswith('server-')
                or info.get('document_key') or not live.get('tmux_id') or not live.get('created') or not live.get('pane_pid')):
            continue
        if workspace not in workspaces:
            workspaces[workspace] = _workspace(root, workspace)
        saved, registry = workspaces[workspace]
        owner = _owner(root, workspace, saved, logical, registry, assistant_cache=assistant_cache)
        if not owner or owner['status'] not in RETENTION:
            continue
        clock = _clock(owner, live, journal.get(name, {}), now)
        updated[name] = clock
        ancestors, current = set(), logical
        while current in saved and current not in ancestors:
            ancestors.add(current)
            current = _parent(saved, current)
        pending.append({**info, **live, **owner, **clock, 'root': root, 'depth': len(ancestors),
                        'expires_at': clock['since'] + RETENTION[owner['status']]})
    if persist and updated != journal:
        fsguard.checkpoint()
        storage.write_json(_journal_path(root), updated)
    return pending


def _scan(active_root, *, persist=False):
    roots = reviewed._roots(active_root)
    listing = term._tmux_list(term._tmux_discovery_prefixes_all(roots), prune_draining=False, activity=True)
    if listing is None:
        raise HTTPException(503, 'Could not inspect tmux sessions. Nothing was stopped.')
    pending, warnings, seen = [], [], set()
    now = time.time()
    for vault in roots:
        root = vault['path']
        try:
            rows = fsguard.guarded(root, _root_pending, root, listing, now, persist)
            for row in rows:
                key = row['tmux_socket'], row['name']
                if key not in seen:
                    seen.add(key)
                    pending.append({**row, 'vault': vault['id']})
        except (OSError, ValueError, HTTPException):
            log.warning('Could not inspect task terminals in %s', root, exc_info=True)
            warnings.append(f'Could not inspect {vault["id"]}; its terminals are excluded.')
            pending = [row for row in pending if row['root'] != root]
    return pending, warnings


def _stop(row):
    checks = [f'#{{==:#{{session_id}},{row["tmux_id"]}}}',
              f'#{{==:#{{session_created}},{row["created"]}}}',
              f'#{{==:#{{pane_pid}},{row["pane_pid"]}}}']
    condition = checks[0]
    for check in checks[1:]:
        condition = '#{&&:' + condition + ',' + check + '}'
    target = '=' + row['name']
    result = subprocess.run(term._tmux_command(row['tmux_socket'], 'if-shell', '-F', '-t', target + ':', condition,
                            'kill-session -t ' + term._shell_quote(target),
                            'display-message -p lab-cleanup-skipped'), capture_output=True, text=True,
                            env=term._tmux_child_env(), timeout=5)
    if result.returncode:
        raise RuntimeError('Could not stop task terminal')
    return 'lab-cleanup-skipped' not in result.stdout


def _public(row):
    return {key: row.get(key) for key in ('name', 'logical_name', 'workspace_id', 'vault', 'title', 'status', 'since', 'expires_at')}


def _retire_saved(row):
    # Keep conversation IDs and parent ownership, but persist restore suppression
    # before killing. A stale browser restore cannot resurrect this process.
    data = term._load_workspace(row['root'], row['workspace_id'])
    saved = next((s for s in (data or {}).get('sessions', []) if isinstance(s, dict) and s.get('name') == row['logical_name']), None)
    if saved is None:
        raise ValueError('Task terminal ownership changed')
    saved['task_terminal_retired_at'] = time.time()
    term._save_workspace(row['root'], row['workspace_id'], data)


def reconcile(active_root):
    global _last_result
    with _LOCK:
        pending, warnings = _scan(active_root, persist=True)
        killed, errors = [], []
        # Resolve children first. Saved ownership remains available even if a
        # child fails to stop and its parent expires during this tick.
        for row in sorted(pending, key=lambda row: row['depth'], reverse=True):
            if time.time() < row['expires_at']:
                continue
            try:
                root, workspace = row['root'], row['workspace_id']
                objective_lock = objective_store.lock(paths.workspace_dir(root, workspace)) if row['owner'][0] == 'objective' else nullcontext()
                assistant_lock = assistant_records.lock(Path(row['owner'][1])) if row['owner'][0] == 'assistant' else nullcontext()
                with operation_lease(root, workspace), tmux_sockets.state_lock(), term._SESSION_METADATA_LOCK, objective_lock, assistant_lock:
                    saved, registry = _workspace(root, workspace, locked=row['owner'][0] == 'objective')
                    fresh = _owner(root, workspace, saved, row['logical_name'], registry)
                    if not fresh or any(fresh.get(k) != row.get(k) for k in ('owner', 'status', 'changed_at')):
                        continue
                    # Automatic retention intentionally expires even attached or
                    # busy inactive-task sessions. It is independent of idle cleanup.
                    reviewed._disable_autospawn(root, workspace)
                    _retire_saved(row)
                    if _stop(row):
                        killed.append(_public(row))
                        meta = term._load_meta(root)
                        meta.pop(row['name'], None)
                        term._save_meta(root, meta)
                        term._invalidate_workspace_term_caches()
                        log.info('Task terminal expired: %s (%s)', row['name'], row['status'])
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, HTTPException) as exc:
                log.warning('Task terminal cleanup failed for %s', row['name'], exc_info=True)
                errors.append({'name': row['name'], 'reason': str(getattr(exc, 'detail', exc))})
        _last_result = {'checked_at': time.time(), 'killed': killed, 'errors': errors, 'warnings': warnings}
        return _last_result


@router.get('/api/term/task-cleanup')
def status(request: Request):
    auth.require_admin(request)
    with _LOCK:
        pending, warnings = _scan(request.app.state.index_cache.root)
        return {'enabled': os.environ.get('LAB_TASK_TERMINAL_CLEANUP') != '0', 'interval_seconds': INTERVAL,
                'retention_seconds': RETENTION, 'pending': [_public(row) for row in pending],
                'last_run': _last_result, 'warnings': warnings}


@router.post('/api/term/task-cleanup')
def cleanup(request: Request):
    auth.require_admin(request)
    return reconcile(request.app.state.index_cache.root)


async def run(app):
    while True:
        try:
            await asyncio.to_thread(reconcile, app.state.index_cache.root)
        except Exception:
            log.exception('Task terminal cleanup tick failed')
        await asyncio.sleep(INTERVAL)
