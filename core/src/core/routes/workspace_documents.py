"""Document references and shared terminal views in real workspaces."""
from typing import Literal
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

from core import terminal_task_links, workspace_documents as links

router = APIRouter(prefix='/api/workspace-documents')


class DocumentLink(BaseModel):
    workspace_id: str
    vault: str | None = None
    assistant_root: str
    document_id: str


class UnlinkTerminal(BaseModel):
    workspace_id: str
    vault: str | None = None
    source_workspace_id: str
    source_vault: str | None = None
    name: str
    linked_task: dict
    destination: Literal['workspace', 'assistant']


@router.get('')
def list_documents(request: Request, workspace_id: str, vault: str | None = None):
    return links.list_documents(request, workspace_id, vault)


@router.post('')
def link_document(request: Request, body: DocumentLink):
    return links.change_link(request, body)


@router.delete('')
def unlink_document(request: Request, body: DocumentLink):
    return links.change_link(request, body, remove=True)


@router.post('/unlink-terminal')
def unlink_terminal(request: Request, body: UnlinkTerminal):
    return links.unlink_terminal(request, body)


def _notification_context(root: Path, workspace_id: str, sessions: list[dict]) -> dict:
    """Read names once per owner, without loading document bodies or transcripts."""
    from core.routes import term
    from lab import objective_store, objectives

    workspace = term._load_workspace(root, workspace_id) or {}
    folder = objectives.directory(root, workspace_id)
    with objective_store.lock(folder):
        registry = objective_store.read(folder)
    by_id = {row['id']: row for row in registry.get('objectives', [])}
    saved = {row['name']: row for row in workspace.get('sessions', []) if isinstance(row, dict) and row.get('name')}
    native = {row.get('logical_name'): row for row in sessions if row.get('logical_name')}
    terminal_links = registry.get('terminal_links', {})

    def owner(session):
        seen = set()
        while session:
            logical = session.get('logical_name') or session.get('name')
            if logical in seen:
                return None
            seen.add(logical)
            entry = {**saved.get(logical, {}), **session}
            binding = next((terminal_links[key] for key in
                            (entry.get('session_id'), logical, entry.get('name')) if key in terminal_links), {})
            if binding.get('main') == 'workflow' or binding.get('view') == 'workflow':
                return None
            objective_id = binding.get('objective_id') or entry.get('context_objective_id')
            if objective_id:
                return by_id.get(objective_id)
            parent = entry.get('parent_terminal')
            if 'parent_terminal' not in entry and term.terminal_automation_lifecycle.NAME.fullmatch(logical or '') and not logical.endswith('-1'):
                parent = logical.rsplit('-', 1)[0] + '-1'
            if parent:
                session = native.get(parent) or saved.get(parent)
                continue
            root_path = (entry.get('linked_scope') or {}).get('root') or entry.get('cwd')
            return next((o for o in by_id.values() if root_path and
                         (o.get('path') == root_path or any(root_path in (w.get('path'), w.get('resolved_path'))
                                                          for w in o.get('worktrees', [])))), None)
        return None

    name = workspace.get('display_name') or workspace.get('name') or workspace_id
    result = {}
    for session in sessions:
        objective = owner(session)
        result[session['name']] = {'workspace': name, **({'objective': objective['name']} if objective else {})}
    return result


@router.get('/attention')
def attention(request: Request):
    """One bounded batch for inactive tabs, without capture-pane summaries."""
    from core.routes import term
    rows = term.list_sessions(request)
    active = term.auth.request_root(request)
    user = term.auth.require_user(request)
    vaults = term._known_vaults(active)
    # Home can retain sessions registered in the framework checkout, which is
    # not necessarily a registered vault (especially after switching vaults).
    framework = term.lab_paths.find_framework_root().resolve()
    if term.auth.is_admin(user) and not any(Path(v['path']).resolve() == framework for v in vaults):
        home = term.fsguard.guarded(framework, term._sessions_for_root, framework,
            term.SELF_WORKSPACE_ID, include_agent_details=False,
            operation_key=('terminal-sessions', term.SELF_WORKSPACE_ID))
        known = {row['name'] for row in rows}
        rows.extend({**row, 'vault':'framework'} for row in home if row['name'] not in known)
    result = {}
    linked = {}
    for row in rows:
        scope = (row.get('vault') or 'framework') + '::' + str(row.get('workspace_id', ''))
        result.setdefault(scope, []).append(row)
        identity = terminal_task_links.identity(row.get('linked_task'))
        if identity:
            linked.setdefault(identity[:2], []).append(row)
    # Context comes from the native owner before shared views borrow its rows.
    # It rides this batch rather than making every card fetch Objective content.
    roots = {v['id']: Path(v['path']) for v in vaults}
    for scope, sessions in result.items():
        vault_id, workspace_id = scope.split('::', 1)
        root = roots.get(vault_id)
        if not root or workspace_id.startswith('__') or not any(
                row.get('terminal_notification') or row.get('terminal_status') for row in sessions):
            continue
        try:
            contexts = term.fsguard.guarded(root, _notification_context, root, workspace_id, sessions)
        except (OSError, ValueError, term.HTTPException):
            continue
        for row in sessions:
            row['notification_context'] = contexts[row['name']]
    for vault in vaults:
        if not term.auth.can_access_vault(user, str(vault['id'])):
            continue
        root = Path(vault['path'])
        for workspace_id in term._known_workspace_ids(root):
            refs = links.references(root, workspace_id)
            if not refs:
                continue
            term._require_workspace_access(request, active, root, workspace_id)
            key = vault['id'] + '::' + workspace_id
            sessions = result.setdefault(key, [])
            names = {row['name'] for row in sessions}
            for ref in refs:
                identity = terminal_task_links.identity(ref)
                for row in linked.get(identity[:2], []) if identity else []:
                    if row['name'] not in names:
                        sessions.append(row)
                        names.add(row['name'])
    # Keep the original owner on borrowed rows so a header message opens the
    # exact terminal, even across vaults. No transcript/capture reads are needed.
    fields = ('name', 'session_id', 'created', 'created_at', 'tmux_socket', 'tmux_id',
              'terminal_status', 'terminal_notification', 'workspace_id', 'vault', 'logical_name', 'label',
              'llm_controlled', 'notification_context')
    return {scope: [{key: row[key] for key in fields if key in row} for row in sessions]
            for scope, sessions in result.items()}
