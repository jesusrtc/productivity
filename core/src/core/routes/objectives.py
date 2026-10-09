"""Fast objective metadata and explicitly owned document mutations."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from lab import objectives, assistant_documents
from core import auth, workspace_documents

router = APIRouter(prefix='/api/objectives')


def payload(request, root, workspace_id):
    data = objectives.payload(root, workspace_id)
    # Read the original document for the sidebar tree. Its renderer, ownership,
    # content, task model and terminals continue to belong to Assistant.
    from core import terminal_task_links
    from core.routes.term import LinkedTask
    from pathlib import Path
    for objective in data['objectives']:
        for resource in objective['resources']:
            if resource['kind'] != 'assistant':
                continue
            try:
                ref = terminal_task_links.validate(request, LinkedTask(
                    document_id=resource['document_id'], assistant_root=resource['assistant_root']))
                raw = (Path(ref['assistant_root']) / ref['path']).read_bytes()
                owner, body, tabs = assistant_documents.unpack(raw)
                resource.update(title=owner['title'], path=ref['path'], content={
                    'body':body, 'tabs':[{**meta,'body':text} for meta,text in tabs]})
            except (HTTPException, ValueError, OSError) as exc:
                resource['error'] = str(getattr(exc, 'detail', exc))
    return data


class Action(BaseModel):
    workspace_id: str
    vault: str | None = None
    expected: str | None = None
    action: dict = Field(default_factory=dict)


def _task_terminal_rows(root, workspace_id, terminal_ids):
    from core.routes import term
    return [row for row in term._get_workspace_sessions(root, workspace_id)
            if isinstance(row, dict) and row.get('session_id') in terminal_ids and not row.get('linked_task')]


def _delete_task_terminals(request, root, workspace_id, plan, vault=None):
    """Close only sessions verified to belong to this workspace and review."""
    import subprocess
    from core import terminal_requests, terminal_automation_lifecycle, terminal_automations
    from core.routes import term, ui
    rows = _task_terminal_rows(root, workspace_id, plan['terminal_ids'])
    meta = term._load_meta(root)
    targets = []
    for row in rows:
        owned = [(name, info) for name, info in meta.items()
                 if info.get('workspace_id') == workspace_id and info.get('session_id') == row['session_id']]
        name, info = owned[0] if owned else (term._tmux_name_for(workspace_id, row['name'], root), {})
        existing = meta.get(name)
        if existing and (existing.get('workspace_id') != workspace_id or existing.get('logical_name') != row['name']):
            raise ValueError('Terminal ownership changed. Review the deletion again.')
        socket = term._tmux_find_session_socket(name) if term._tmux_available() else None
        if not term._tmux_available() and existing:
            raise ValueError('Cannot close task terminals while tmux is unavailable')
        targets.append((row, name, socket))
    # Disable automatic default recreation before closing a selected session.
    if targets:
        ui.set_term_autospawn(ui.TermAutoSpawnState(workspace_id=workspace_id, vault=vault, enabled=False), request)
    for row, name, socket in targets:
        if socket:
            try:
                result = subprocess.run(term._tmux_command(socket, 'kill-session', '-t', name),
                    capture_output=True, text=True, env=term._tmux_child_env(), timeout=5)
            except subprocess.TimeoutExpired as exc:
                raise ValueError('Timed out closing task terminal: ' + row['name']) from exc
            if result.returncode and term._tmux_find_session_socket(name):
                raise ValueError('Could not close task terminal: ' + row['name'])
        meta.pop(name, None)
        if row['name'] == 'server':
            from core.routes import servers
            servers.set_desired(root, workspace_id, 'stopped')
    if targets:
        term._save_meta(root, meta)
        workspace = term._load_workspace(root, workspace_id)
        workspace['sessions'] = [row for row in workspace.get('sessions', [])
                                 if not isinstance(row, dict) or row.get('session_id') not in {r['session_id'] for r, _, _ in targets}]
        term._save_workspace(root, workspace_id, workspace)
        with terminal_automations.lock:
            runs = terminal_automation_lifecycle.read(objectives.directory(root, workspace_id))
            terminal_automation_lifecycle.save(objectives.directory(root, workspace_id),
                {key:value for key,value in runs.items() if key not in {r['name'] for r, _, _ in targets}})
        terminal_requests.forget([name for _, name, _ in targets])
        term._invalidate_workspace_term_caches()


@router.post('/task-delete-preview')
def task_delete_preview(request: Request, body: Action):
    auth.require_admin(request)
    root = workspace_documents.workspace(request, body.workspace_id, body.vault)
    try:
        result = objectives.task_delete_preview(root, body.workspace_id, body.action)
        result['terminal_ids'] = [row['session_id'] for row in _task_terminal_rows(root, body.workspace_id, result['terminal_ids'])]
        return result
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('')
def read(request: Request, workspace_id: str, vault: str | None = None):
    root = workspace_documents.workspace(request, workspace_id, vault)
    try:
        return payload(request, root, workspace_id)
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post('')
def change(request: Request, body: Action):
    auth.require_admin(request)
    root = workspace_documents.workspace(request, body.workspace_id, body.vault)
    try:
        action = body.action
        if action.get('type') == 'worktree':
            from core.routes.diff import _entry_root
            _entry_root(action.get('path', ''), request)
        if action.get('type') == 'resource' and action.get('kind') == 'assistant':
            from core import terminal_task_links
            from core.routes.term import LinkedTask
            reference = terminal_task_links.validate(request, LinkedTask(
                document_id=action.get('document_id'), assistant_root=action.get('assistant_root')))
            action = {**action, **reference}
        if action.get('type') in {'task-asset', 'asset-star', 'asset-bucket', 'suggest-assignment', 'asset-assign', 'asset-trash', 'accept-assignment'}:
            from core import terminal_task_links
            from core.routes.term import LinkedTask
            from pathlib import Path
            source = action.get('reference')
            if action.get('type') == 'accept-assignment':
                current = objectives.load(root, body.workspace_id)
                owner = next((o for o in current['objectives'] if o['id'] == action.get('objective_id')), {})
                suggestion = next((s for s in owner.get('assignment_suggestions', []) if s['id'] == action.get('suggestion_id')), {})
                target = suggestion.get('asset', {})
                source = next((r for r in owner.get('resources', []) if r['id'] == target.get('resource_id')), {})
                action = {**target, **action}
            if source is None and action.get('resource_id'):
                current = objectives.load(root, body.workspace_id)
                owner = next((o for o in current['objectives'] if o['id'] == action.get('objective_id')), {})
                source = next((r for r in owner.get('resources', []) if r['id'] == action['resource_id']), {})
            if isinstance(source, dict) and source.get('kind') == 'assistant':
                reference = terminal_task_links.validate(request, LinkedTask(
                    document_id=source.get('document_id'), assistant_root=source.get('assistant_root')))
                tab = action.get('tab_id') or source.get('tab_id')
                if tab:
                    _, _, tabs = assistant_documents.unpack((Path(reference['assistant_root']) / reference['path']).read_bytes())
                    if not any(meta['id'] == tab for meta, _ in tabs):
                        raise ValueError('Subtab not found')
                if action.get('reference') is not None:
                    action = {**action, 'reference':{**source, **reference}}
        if action.get('type') == 'terminal':
            from core.routes import term
            sessions = term._get_workspace_sessions(root, body.workspace_id)
            entry = next((s for s in sessions if s.get('session_id') == action.get('session_id')), None)
            terminal_workspace, terminal_vault = body.workspace_id, body.vault
            if not entry:
                source = action.get('source') or {}
                if not source.get('workspace_id'):
                    raise ValueError('Choose a saved terminal in this workspace')
                active = auth.request_root(request)
                owner = term._vault_root_for(active, source.get('vault'))
                term._require_workspace_access(request, active, owner, source['workspace_id'])
                entry = next((s for s in term._get_workspace_sessions(owner,source['workspace_id'])
                              if s.get('session_id')==action.get('session_id') and s.get('name')==source.get('logical_name')),None)
                refs = workspace_documents.references(root,body.workspace_id)
                refs += [r for o in objectives.load(root,body.workspace_id)['objectives'] for r in o['resources'] if r['kind']=='assistant']
                linked = (entry or {}).get('linked_task') or {}
                if not entry or not any(r.get('document_id')==linked.get('document_id') and r.get('assistant_root')==linked.get('assistant_root') for r in refs):
                    raise ValueError('This terminal is not shared with this workspace')
                terminal_workspace, terminal_vault = source['workspace_id'], source.get('vault')
            if action.get('rename_to_task') is True and not action.get('task_id'):
                raise ValueError('Choose a task to name this terminal')
        if action.get('type') == 'task-delete':
            from core import notebook_kernel
            # Hold the kernel guard through the mutation, preventing a new
            # execution from starting while an owned notebook is removed.
            with notebook_kernel._sessions_guard:
                def validate(plan):
                    if any(notebook_kernel.workspace_busy(root, path) for path in plan['files']):
                        raise ValueError('Wait for this task’s notebooks to finish before deleting it')
                def cleanup(plan):
                    _delete_task_terminals(request, root, body.workspace_id, plan, body.vault)
                    for path in plan['files']:
                        notebook_kernel.shutdown_workspace(root, path)
                result = objectives.mutate(root, body.workspace_id, action, body.expected,
                                           delete_terminals=cleanup, validate_delete=validate)
        elif action.get('type') == 'rename' and not action.get('tab_id'):
            from core import notebook_kernel
            from contextlib import nullcontext
            from lab import paths
            before = objectives.load(root, body.workspace_id)
            objective = next((o for o in before['objectives'] if o['id'] == action.get('objective_id')), {})
            resource = next((r for r in objective.get('resources', []) if r['id'] == action.get('resource_id')), {})
            old = paths.workspace_dir(root, body.workspace_id) / resource.get('path', '')
            with notebook_kernel._sessions_guard if resource.get('kind') == 'notebook' else nullcontext():
                if resource.get('kind') == 'notebook' and notebook_kernel.workspace_busy(root, old):
                    raise ValueError('Wait for this notebook to finish running before renaming it')
                result = objectives.mutate(root, body.workspace_id, action, body.expected)
                if resource.get('kind') == 'notebook':
                    updated = next(r for o in result['objectives'] for r in o['resources'] if r['id'] == resource['id'])
                    notebook_kernel.relocate_file(root, old, paths.workspace_dir(root, body.workspace_id) / updated['path'])
        else:
            result = objectives.mutate(root, body.workspace_id, action, body.expected)
        if action.get('type') == 'terminal' and action.get('rename_to_task') is True:
            objective = next(o for o in result['objectives'] if o['id'] == action['objective_id'])
            task = next(t for t in objectives._tasks(objective) if t['id'] == action['task_id'])
            term.update_session_metadata(term.SessionMetadata(workspace_id=terminal_workspace,
                vault=terminal_vault, name=entry['name'], label=task['title']), request)
        return payload(request, root, body.workspace_id)
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(409 if 'changed elsewhere' in str(exc) else 400, str(exc)) from exc
