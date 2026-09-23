"""Workspace references to Assistant documents and their existing terminals."""
from contextlib import ExitStack

from fastapi import HTTPException
from lab import paths, storage, workspace_identity

from core import terminal_task_links


def _safe_scope(workspace_id):
    if not workspace_id or workspace_id in {'.', '..'} or '/' in workspace_id or '\\' in workspace_id:
        raise HTTPException(400, 'Invalid workspace ID')


def references(root, workspace_id):
    if workspace_id.startswith('__'):
        return []
    file = paths.workspace_dir(root, workspace_id) / '.lab' / 'document-links.json'
    if not file.is_file():
        return []
    return storage.read_json(file).get('documents', [])


def workspace(request, workspace_id, vault=None):
    from core.routes import term
    _safe_scope(workspace_id)
    active = term.auth.request_root(request)
    root = term._vault_root_for(active, vault)
    term._require_workspace_access(request, active, root, workspace_id)
    if workspace_id.startswith('__') or term._load_workspace(root, workspace_id) is None:
        raise HTTPException(404, 'Workspace not found')
    return root


def list_documents(request, workspace_id, vault=None):
    from core.routes import term
    from core.routes.assistant import _require_root
    root = workspace(request, workspace_id, vault)
    refs = references(root, workspace_id)
    if not refs:
        return []
    assistant = str(_require_root(request).resolve())
    result = []
    for ref in refs:
        try:
            if ref['assistant_root'] != assistant:
                raise HTTPException(400, 'Assistant location changed')
            result.append(terminal_task_links.validate(request, term.LinkedTask(document_id=ref['document_id'])))
        except HTTPException as exc:
            if exc.status_code != 400:
                raise
            result.append({**ref, 'missing': True})
    return result


def change_link(request, body, remove=False):
    from core.routes import term
    root = workspace(request, body.workspace_id, body.vault)
    with term._SESSION_METADATA_LOCK, workspace_identity.operation_lease(root, body.workspace_id):
        refs = references(root, body.workspace_id)
        if remove:
            # A missing document must still be removable from this workspace.
            refs = [ref for ref in refs if not (ref['document_id'] == body.document_id
                    and ref['assistant_root'] == body.assistant_root)]
        else:
            ref = terminal_task_links.validate(request, term.LinkedTask(document_id=body.document_id))
            if body.assistant_root != ref['assistant_root']:
                raise HTTPException(409, 'The Assistant location has changed. Refresh and try again.')
            refs = [r for r in refs if terminal_task_links.identity(r)[:2] != terminal_task_links.identity(ref)[:2]]
            refs.append(ref)
        storage.write_json(paths.workspace_dir(root, body.workspace_id) / '.lab' / 'document-links.json',
                           {'documents': refs})
    return {'ok': True}


def borrowed_terminals(request, root, workspace_id, native):
    refs = references(root, workspace_id)
    if not refs:
        return []
    from core.routes import term
    wanted = {terminal_task_links.identity(ref)[:2] for ref in refs}
    names = {row['name'] for row in native}
    rows = []
    # Discover once for all linked documents, preserving the canonical owner.
    for session in terminal_task_links.list_terminals(request):
        key = terminal_task_links.identity(session.get('linked_task'))
        if not key or key[:2] not in wanted or session['name'] in names:
            continue
        names.add(session['name'])
        source = {key: session[key] for key in ('workspace_id', 'vault', 'logical_name')}
        rows.append({**session, 'document_source': source,
                     'logical_name': '@document:' + session['name']})
    term._enrich_session_details(rows)
    return rows


def unlink_terminal(request, body):
    """Move ownership metadata only. No tmux command, input, or cwd change."""
    from core.routes import term
    from core.routes.assistant import _require_root
    active = term.auth.request_root(request)
    workspace_root = workspace(request, body.workspace_id, body.vault)
    source_root = term._vault_root_for(active, body.source_vault)
    assistant_root = _require_root(request)
    _safe_scope(body.source_workspace_id)
    destination_root = workspace_root if body.destination == 'workspace' else assistant_root
    destination_id = body.workspace_id if body.destination == 'workspace' else term.ASSISTANT_WORKSPACE_ID
    term._require_workspace_access(request, active, source_root, body.source_workspace_id)
    term._require_workspace_access(request, active, destination_root, destination_id)
    with term._SESSION_METADATA_LOCK, ExitStack() as locks:
        for root in sorted({source_root, destination_root}):
            locks.enter_context(workspace_identity.identity_lock(root))
        for root, scope in sorted({(source_root, body.source_workspace_id), (destination_root, destination_id)}):
            locks.enter_context(workspace_identity.operation_lease(root, scope))
        source = term._load_workspace(source_root, body.source_workspace_id)
        entry = next((row for row in (source or {}).get('sessions', []) if row.get('name') == body.name), None)
        if not entry or not entry.get('linked_task'):
            raise HTTPException(409, 'The terminal link changed. Refresh and try again.')
        link = entry['linked_task']
        if terminal_task_links.identity(link) != terminal_task_links.identity(body.linked_task):
            raise HTTPException(409, 'The terminal link changed. Refresh and try again.')
        same = (source_root, body.source_workspace_id) == (destination_root, destination_id)
        destination = source if same else term._load_workspace(destination_root, destination_id)
        if destination is None:
            raise HTTPException(404, 'Destination not found')
        taken = {row['name'] for row in destination.get('sessions', [])} if not same else set()
        logical = term._pick_unique_logical_name(body.name, taken)
        moved = {**entry, 'name': logical}
        moved.pop('linked_task', None)
        runtime = {root: term._load_meta(root) for root in {source_root, destination_root}}
        live_name = next((name for name, row in runtime[source_root].items()
                          if row.get('workspace_id') == body.source_workspace_id and row.get('logical_name') == body.name), None)
        writes = {}
        if not same:
            source['sessions'] = [row for row in source.get('sessions', []) if row is not entry]
            destination.setdefault('sessions', []).append(moved)
            writes.update(workspace_identity.session_transfer_writes(source_root, body.source_workspace_id,
                          body.name, destination_root, destination_id, logical, moved.get('session_id'), live_name))
        else:
            source['sessions'] = [moved if row is entry else row for row in source['sessions']]
        if live_name:
            row = runtime[source_root].pop(live_name)
            row.update(workspace_id=destination_id, logical_name=logical)
            row.pop('linked_task', None)
            runtime[destination_root][live_name] = row
        writes[term._workspace_json(source_root, body.source_workspace_id)] = source
        writes[term._workspace_json(destination_root, destination_id)] = destination
        for root, meta in runtime.items():
            writes[term._sessions_file(root)] = meta
        before = {file: file.read_bytes() if file.exists() else None for file in writes}
        try:
            for file, value in writes.items():
                storage.write_json(file, value)
        except Exception:
            for file, contents in before.items():
                if contents is None:
                    file.unlink(missing_ok=True)
                else:
                    file.write_bytes(contents)
            raise
        term._invalidate_workspace_term_caches()
        return {'ok': True, 'session': moved, 'name': live_name, 'workspace_id': destination_id,
                'vault': term._vault_id_for_root(active, destination_root)}
