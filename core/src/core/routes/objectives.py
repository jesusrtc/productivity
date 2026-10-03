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
        if action.get('type') == 'task-asset':
            from core import terminal_task_links
            from core.routes.term import LinkedTask
            from pathlib import Path
            source = action.get('reference')
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
            if not any(s.get('session_id') == action.get('session_id') for s in sessions):
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
        if action.get('type') == 'rename' and not action.get('tab_id'):
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
            objectives.mutate(root, body.workspace_id, action, body.expected)
        return payload(request, root, body.workspace_id)
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(409 if 'changed elsewhere' in str(exc) else 400, str(exc)) from exc
