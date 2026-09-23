"""Durable Assistant task links to user-owned terminal sessions.

Links live with the saved session, independently of file/folder associations.
Reading or changing them never sends input, changes cwd, or starts a process.
"""
from pathlib import Path
import os

from fastapi import HTTPException
from lab import assistant_records as records, assistant_documents as documents


def validate(request, link):
    from core.routes.assistant import _require_root
    root = _require_root(request)
    try:
        source, _, _ = records.resolve(root, link.document_id, 'documents')
        source = documents.physical(source)
        owner, _, _ = documents.unpack(source.read_bytes())
        task = None
        if link.task_id:
            task = next((row for row in owner.get('tasks', []) if row['id'] == link.task_id), None)
            if task is None:
                raise ValueError('Task does not belong to this document')
        return {'assistant_root': str(root.resolve()), 'document_id': owner['id'],
                'task_id': link.task_id or None, 'path': source.relative_to(root).as_posix(),
                'title': (task or owner)['title']}
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


def identity(link):
    if not isinstance(link, dict) or not link.get('assistant_root') or not link.get('document_id'):
        return None
    return (str(Path(link['assistant_root']).resolve()), link['document_id'], link.get('task_id') or None)


def list_terminals(request, document_id=None):
    from core.routes import term
    from core.routes.assistant import _require_root
    root = _require_root(request)
    owner = None
    if document_id:
        owner = validate(request, term.LinkedTask(document_id=document_id))
    active_root = term.auth.request_root(request)
    vaults = term._known_vaults(active_root)
    live = term._tmux_list(term._tmux_discovery_prefixes_all(vaults), prune_draining=False)
    if live is None:
        raise HTTPException(503, 'Could not check running terminals. Try again.')
    live_by_name = {row['name']: row for row in live}
    live_names = set(live_by_name)
    # Home saves tabs in one shared file, but runtime registrations can belong
    # to different vaults (and old framework-root sessions). Resolve all of them
    # before deduplicating the metadata files; never allocate UUIDs on a read.
    runtime_by_tab = {}
    runtime_by_name = {}
    runtime_root_by_name = {}
    framework = term.lab_paths.find_framework_root().resolve()
    runtime_roots = [Path(vault['path']) for vault in vaults]
    if framework not in runtime_roots:
        runtime_roots.append(framework)
    for runtime_root in runtime_roots:
        if not runtime_root.is_dir():
            continue
        for name, row in term._load_meta(runtime_root).items():
            runtime_by_name[name] = row
            runtime_root_by_name[name] = runtime_root
            workspace = row.get('workspace_id')
            logical = row.get('logical_name')
            if not workspace or not logical:
                continue
            key = (term._workspace_json(runtime_root, workspace), logical)
            if key not in runtime_by_tab or name in live_names:
                runtime_by_tab[key] = name
    result, seen = [], set()
    for vault in vaults:
        vault_root = Path(vault['path'])
        for workspace_id in dict.fromkeys([term.ASSISTANT_WORKSPACE_ID, *term._known_workspace_ids(vault_root)]):
            metadata_path = term._workspace_json(vault_root, workspace_id)
            if metadata_path in seen:
                continue
            seen.add(metadata_path)
            data = term._load_workspace(vault_root, workspace_id)
            if not data:
                continue
            term._require_workspace_access(request, active_root, vault_root, workspace_id)
            for saved in data.get('sessions', []):
                if not isinstance(saved, dict) or not saved.get('name'):
                    continue
                link = saved.get('linked_task')
                if owner and (not identity(link) or identity(link)[:2] != identity(owner)[:2]):
                    continue
                name = runtime_by_tab.get((metadata_path, saved['name']))
                if not name:
                    prefix = os.environ.get('LAB_TMUX_PREFIX')
                    if prefix:
                        name = prefix + term._sanitize(workspace_id) + '-' + term._sanitize(saved['name'])
                    elif saved.get('session_id'):
                        name = term._SESSION_PREFIX + saved['session_id'].replace('-', '')
                running = name in live_names
                if not owner and not running:
                    continue
                result.append({**saved, **live_by_name.get(name, {}), **runtime_by_name.get(name, {}),
                               'name': name, 'logical_name': saved['name'],
                               'workspace_id': workspace_id,
                               'vault': term._vault_id_for_root(active_root, runtime_root_by_name[name])
                                        if name in runtime_root_by_name else vault['id'],
                               'workspace_name': data.get('name') or workspace_id,
                               'label': saved.get('label') or saved['name'],
                               'kind': saved.get('kind') or 'terminal',
                               'agent': saved.get('agent'),
                               'state': 'running' if running else 'stopped',
                               'linked_task': link})
    return result
