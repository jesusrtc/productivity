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
    """Read names and icon choices once per owner, without loading content."""
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

    def ancestry(session):
        seen = set()
        while session:
            logical = session.get('logical_name') or session.get('name')
            if logical in seen:
                return
            seen.add(logical)
            entry = {**saved.get(logical, {}), **session}
            binding = next((terminal_links[key] for key in
                            (entry.get('session_id'), logical, entry.get('name')) if key in terminal_links), {})
            parent = entry.get('parent_terminal')
            if 'parent_terminal' not in entry and term.terminal_automation_lifecycle.NAME.fullmatch(logical or '') and not logical.endswith('-1'):
                parent = logical.rsplit('-', 1)[0] + '-1'
                entry['parent_terminal'] = parent
            yield entry, binding
            session = (native.get(parent) or saved.get(parent)) if parent else None

    def owner(chain):
        for entry, binding in chain:
            if binding.get('main') == 'workflow' or binding.get('view') == 'workflow':
                return None
            objective_id = binding.get('objective_id') or entry.get('context_objective_id')
            if objective_id:
                return by_id.get(objective_id)
            if entry.get('parent_terminal'):
                continue
            root_path = (entry.get('linked_scope') or {}).get('root') or entry.get('cwd')
            return next((o for o in by_id.values() if root_path and
                         (o.get('path') == root_path or any(root_path in (w.get('path'), w.get('resolved_path'))
                                                          for w in o.get('worktrees', [])))), None)
        return None

    def asset_icon(asset, objective):
        if not asset:
            return None
        objective = by_id.get(asset.get('objective_id'), objective) or {}
        if asset.get('file'):
            return {'file': asset['file']['path']}
        if asset.get('folder'):
            worktree = any(asset['folder']['root'] in (w.get('path'), w.get('resolved_path'))
                           and w.get('kind', 'worktree') == 'worktree' for w in objective.get('worktrees', []))
            return {'emoji': '⑂' if worktree else '⌂'}
        resource = asset.get('reference') or next((r for r in objective.get('resources', [])
                                                 if r['id'] == asset.get('resource_id')), None)
        if not resource:
            return None
        if resource['kind'] == 'link':
            child = next((c for c in objectives._sublink_rows(resource) if c['id'] == asset.get('sub_link_id')), {})
            return {'link': {'kind': 'external', 'url': child.get('url') or resource.get('url')}}
        return {'file': resource.get('path') or resource.get('title')} if resource['kind'] != 'assistant' else {'emoji': '▤'}

    def icon(chain):
        entry, binding = chain[0]
        appearance = next((row['automation_appearance'] for row, _ in chain if row.get('automation_appearance')), None)
        if appearance:
            choice = appearance.get('icon')
            for ancestor, _ in chain:
                inherited = ancestor.get('automation_appearance')
                if inherited:
                    choice = inherited.get('icon') or choice
                    if not inherited.get('inherit_icon'):
                        break
            return {'automation': choice or {}}
        objective = by_id.get(binding.get('objective_id'))
        linked = asset_icon(binding.get('asset') or binding, objective)
        if linked:
            return linked
        if binding.get('main') == 'workflow':
            return {'emoji': '🏠'}
        if objective and not any(binding.get(k) for k in ('task_id', 'resource_id', 'file', 'folder', 'view')):
            candidates = [(key, value) for key, value in terminal_links.items()
                          if value.get('objective_id') == objective['id']
                          and not any(value.get(k) for k in ('task_id', 'resource_id', 'file', 'folder', 'view'))]
            primary = next((key for key, value in candidates if value.get('main') == 'objective'), candidates[0][0])
            if primary in (entry.get('session_id'), entry.get('logical_name'), entry.get('name')):
                return {'emoji': '🎯'}
        for ancestor, link in chain:
            if link.get('main'):
                break
            task_owner = by_id.get(link.get('objective_id'))
            task = next((t for t in objectives._tasks(task_owner) if t['id'] == link.get('task_id')), None) if task_owner else None
            if task:
                custom = task.get('icon') or {}
                if custom.get('emoji') or custom.get('service'):
                    return {key: custom[key] for key in ('emoji', 'service') if custom.get(key)}
                asset = custom.get('asset') or next((a for a in task.get('assets', []) if a['id'] == task.get('icon_asset_id')), None)
                return asset_icon(asset, task_owner) or {'emoji': '⏺' if len(chain) > 1 or ancestor is not entry else '💻'}
        if len(chain) > 1 or entry.get('parent_terminal'):
            return {'emoji': '⏺'}
        if (entry.get('linked_file') or {}).get('path'):
            return {'file': entry['linked_file']['path']}
        if (entry.get('linked_task') or {}).get('document_id'):
            return {'emoji': '▤'}
        agent = entry.get('agent') or entry.get('kind')
        return {'emoji': {'codex': '🧠', 'copilot': '🐙', 'claude': '🤖'}.get(agent, '💻') if entry.get('kind') == 'claude' else '💻'}

    name = workspace.get('display_name') or workspace.get('name') or workspace_id
    result = {}
    for session in sessions:
        chain = list(ancestry(session))
        objective = owner(chain)
        result[session['name']] = {'workspace': name, 'icon': icon(chain),
                                   **({'objective': objective['name']} if objective else {})}
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
                row.get('terminal_notification') or row.get('terminal_status')
                or row.get('terminal_progress', {}).get('alert') or row.get('terminal_automation_alert') or row.get('terminal_watch') or row.get('terminal_recovery_alert') for row in sessions):
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
              'terminal_status', 'terminal_notification', 'terminal_progress', 'terminal_automation_alert', 'terminal_watch', 'terminal_recovery_alert', 'workspace_id', 'vault', 'logical_name', 'label',
              'llm_controlled', 'notification_context', 'kind', 'agent', 'linked_file', 'linked_task', 'automation_appearance')
    return {scope: [{key: row[key] for key in fields if key in row} for row in sessions]
            for scope, sessions in result.items()}
