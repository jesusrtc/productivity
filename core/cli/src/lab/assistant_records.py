"""Version 2 Assistant records: flat documents and stable, independent links."""
from __future__ import annotations

from contextlib import contextmanager
from collections import Counter
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import uuid


def manifest(root):
    path = root / '.assistant/manifest.json'
    return json.loads(path.read_text()) if path.is_file() else {}


def enabled(root):
    info = manifest(root)
    if info.get('state') == 'migrating':
        raise ValueError('Assistant migration is in progress; retry after it finishes')
    return info.get('schema') == 2


@contextmanager
def lock(root):
    directory = root / '.assistant'
    directory.mkdir(exist_ok=True)
    with (directory / 'write.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def atomic_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path, value):
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def split_document(data):
    """The contract uses JSON-compatible values on each frontmatter line."""
    text = data.decode('utf-8')
    match = re.match(r'\A---\r?\n(.*?)\r?\n---\r?\n', text, re.S)
    if not match:
        return {}, text
    metadata = {}
    for line in match[1].splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, sep, value = line.partition(':')
        if not sep or not key.strip() or key[:1].isspace():
            raise ValueError('Use one frontmatter field per line with JSON-compatible values')
        if key.strip() in metadata:
            raise ValueError('Duplicate frontmatter field: ' + key.strip())
        try:
            parsed = json.loads(value.strip()) if value.strip() else None
        except json.JSONDecodeError:
            if value.strip() in {'|', '>', '|-', '>-'}:
                raise ValueError('Multiline frontmatter values must be JSON-encoded strings')
            parsed = value.strip()
        metadata[key.strip()] = parsed
    return metadata, text[match.end():]


def encode_document(metadata, body):
    return ('---\n' + '\n'.join(f'{key}: {json.dumps(value, ensure_ascii=False)}'
                               for key, value in metadata.items()) + '\n---\n' + body).encode('utf-8')


def read_document(path):
    from lab import assistant_documents as documents
    return documents.read(path)


def write_document(path, metadata, body):
    from lab import assistant_documents as documents
    if '#tab=' in str(path) or (path.exists() and 'tabs' in split_document(path.read_bytes())[0]):
        documents.write(path, metadata, body)
    else:
        atomic_bytes(path, encode_document(metadata, body))


def safe(root, source):
    root = root.absolute()
    reference = Path(source)
    source = Path(str(source).split("#tab=", 1)[0])
    if not source.is_absolute():
        source = root / source
    try:
        relative = source.relative_to(root)
    except ValueError as exc:
        raise ValueError('Record path escapes Assistant') from exc
    current = root
    for part in relative.parts:
        if part in {'..', '.'}:
            raise ValueError('Invalid record path')
        current /= part
        if current.is_symlink():
            raise ValueError('Assistant record paths cannot contain symlinks')
    if not source.resolve().is_relative_to(root.resolve()):
        raise ValueError('Record path escapes Assistant')
    return Path(str(source) + "#tab=" + str(reference).split("#tab=", 1)[1]) if "#tab=" in str(reference) else source


def workspaces(root):
    path = root / '.assistant/workspaces.json'
    return json.loads(path.read_text()).get('workspaces', []) if path.is_file() else []


def workspace(root, identifier):
    return next((row for row in workspaces(root) if row['id'] == identifier), {})


def add_workspace(root, identifier, **values):
    from lab import assistant as db
    db.validate_id(identifier)
    with lock(root):
        rows = workspaces(root)
        if any(row['id'] == identifier for row in rows):
            raise ValueError('Workspace reference already exists')
        rows.append(dict(id=identifier, **{key: str(value) if isinstance(value, Path) else value
                                          for key, value in values.items()}))
        path = root / '.assistant/workspaces.json'
        write_json(path, {'schema': 2, 'workspaces': rows})
        return path


def records(root, collection=None):
    from lab import assistant_documents as documents
    if documents.enabled(root):
        for row in documents.snapshot(root):
            if collection is None or row['type'] + 's' == collection:
                yield row
        return
    for folder in [collection] if collection else ['tasks', 'notes', 'projects']:
        if folder not in {'tasks', 'notes', 'projects'}:
            raise ValueError('Invalid record collection')
        for source in sorted((root / folder).glob('*.md')):
            safe(root, source)
            metadata, body = split_document(source.read_bytes())
            if metadata.get('schema') != 2 or metadata.get('id') != source.stem:
                raise ValueError(f'Invalid record identity: {source.relative_to(root)}')
            expected = {'tasks': 'task', 'notes': 'note', 'projects': 'project'}[folder]
            if metadata.get('type') != expected:
                raise ValueError(f'Invalid record type: {source.relative_to(root)}')
            yield {**metadata, 'path': source.relative_to(root).as_posix(), 'body': body,
                   'mtime': source.stat().st_mtime}


def resolve(root, reference, collection=None):
    reference = str(reference)
    if Path(reference).is_absolute() or '..' in Path(reference).parts:
        raise ValueError('Invalid Assistant reference')
    collections = {'subtasks': 'tasks', 'meetings': 'notes', 'meeting-series': 'notes'}
    folder = collections.get(collection, collection)
    matches = [row for row in records(root, folder) if reference in
               [row['id'], row['path'], *(row.get('aliases') or [])]]
    if len(matches) != 1:
        raise ValueError('Assistant document not found or reference is ambiguous')
    row = matches[0]
    if collection == 'meetings' and row.get('note_type') != 'meeting':
        raise ValueError('Expected a meeting note')
    if collection == 'meeting-series' and row.get('note_type') != 'series':
        raise ValueError('Expected a meeting series')
    source = safe(root, root / row['path'])
    return source, *read_document(source)


def parent_key(metadata):
    parent = metadata.get('parent')
    return (parent.get('type'), parent.get('id')) if isinstance(parent, dict) else None


def key(row):
    return row['type'], row['id']


def descendants(rows, record):
    found, frontier, seen = [], [key(record)], {key(record)}
    while frontier:
        parent = frontier.pop()
        for row in rows:
            if parent_key(row) == parent:
                identity = key(row)
                if identity in seen:
                    raise ValueError('Document parent cycle')
                seen.add(identity)
                frontier.append(identity)
                found.append(row)
    return found


def validate_graph(rows, refs):
    by_key = {key(row): row for row in rows}
    if len(by_key) != len(rows):
        raise ValueError('Duplicate Assistant IDs')
    aliases = {}
    for row in rows:
        for alias in [row['path'], *(row.get('aliases') or [])]:
            if alias in aliases and aliases[alias] != key(row):
                raise ValueError('Ambiguous legacy alias: ' + alias)
            aliases[alias] = key(row)
        if row.get('parent') is not None and not (isinstance(row['parent'], dict) and set(row['parent']) == {'type','id'}):
            raise ValueError('Parent must be a typed task/note reference')
        for field in ('project', 'workspace'):
            if row.get(field) is not None and not isinstance(row[field], str):
                raise ValueError('Expected a single ID for ' + field)
        if row.get('project') and ('project', row['project']) not in by_key:
            raise ValueError('Missing project for ' + row['id'])
        if row.get('workspace') and row['workspace'] not in refs:
            raise ValueError('Missing workspace reference for ' + row['id'])
        seen, current = {key(row)}, row
        while current.get('parent'):
            parent = parent_key(current)
            if parent not in by_key or parent[0] not in {'task', 'note'}:
                raise ValueError('Missing or invalid parent for ' + row['id'])
            if parent in seen:
                raise ValueError('Document parent cycle')
            seen.add(parent)
            current = by_key[parent]
        if row.get('top_level'):
            owner = by_key.get(parent_key(row))
            if not owner or owner.get('parent'):
                raise ValueError('Top-level tabs must link directly to the document root')
        if row.get('series'):
            series = by_key.get(('note', row['series']), {})
            if series.get('note_type') != 'series':
                raise ValueError('Missing meeting series for ' + row['id'])


def progress_map(rows):
    """Parents derive progress from direct child branches; skip completes a branch."""
    by_parent = {}
    for row in rows:
        by_parent.setdefault(parent_key(row), []).append(row)
    result, visiting = {}, set()
    def visit(row):
        identity = key(row)
        if identity in result:
            return result[identity]
        if identity in visiting:
            raise ValueError('Document parent cycle')
        visiting.add(identity)
        children = [visit(child) for child in by_parent.get(identity, [])]
        raw = row.get('status') or 'not_started'
        normalized = {'inbox':'not_started','ready':'not_started','waiting':'in_progress',
                      'blocked':'in_progress','ready_to_review':'in_progress','completed':'done'}.get(raw,raw)
        if children:
            statuses = [child['status'] for child in children]
            automatic = 'done' if all(status in {'done','skipped'} for status in statuses) else (
                'in_progress' if any(status != 'not_started' for status in statuses) else 'not_started')
        else:
            automatic = 'not_started' if normalized == 'cancelled' else normalized
        status = normalized if normalized in {'cancelled','skipped'} else automatic
        result[identity] = dict(status=status, automatic_status=automatic, derived=bool(children),
                                completed=sum(child['status'] in {'done','skipped'} for child in children), total=len(children))
        visiting.remove(identity)
        return result[identity]
    for row in rows:
        visit(row)
    return result


def task_rows(root, children_only=False):
    from lab import assistant as db
    rows = list(records(root))
    from lab import assistant_documents as documents
    embedded = documents.enabled(root)
    progress = progress_map(rows)
    for row in rows:
        if embedded and not children_only and row.get('embedded'):
            continue
        if row['type'] != 'task' or children_only and not row.get('parent'):
            continue
        reference = workspace(root, row.get('workspace'))
        children = []
        for child in descendants(rows, row):
            if not embedded and child['type'] != 'task':
                continue
            context = workspace(root, child.get('workspace'))
            children.append({**child, 'workspace': child.get('workspace') or '',
                             'workspace_name': context.get('name'), 'document_backed': True,
                             'status': progress[key(child)]['status'] if embedded else child.get('status'),
                             'done': progress[key(child)]['status'] in {'done','skipped'}})
        legacy = db.extract_subtasks(row['body'])
        all_children = [*legacy, *children]
        yield {**row, 'workspace': row.get('workspace') or '', 'workspace_name': reference.get('name'),
               'vault': reference.get('vault'), 'vault_path': reference.get('vault_path'),
               'workspace_path': reference.get('workspace_path'), 'document_backed': True,
               'status': progress[key(row)]['status'] if embedded else row.get('status') or 'inbox',
               'progress':progress[key(row)], 'stored_status':row.get('status'),
               'search_text':' '.join(str(child.get(field) or '') for child in [row,*descendants(rows,row)] for field in ('title','tldr','owner')), 'priority': row.get('priority') or 'P2',
               'subtasks': all_children, 'first_class_subtasks': children, 'legacy_subtasks': legacy,
               'subtasks_done': sum(child.get('status') in {'done','skipped'} for child in all_children),
               'subtasks_total': len(all_children), 'done': progress[key(row)]['status'] in {'done','skipped'}}


def note_rows(root, note_type):
    from lab import assistant_meetings as meetings
    notes = list(records(root, 'notes'))
    for row in notes:
        if row.get('note_type') != note_type:
            continue
        reference = workspace(root, row.get('workspace'))
        series = next((item for item in notes if item['id'] == row.get('series')), {})
        actions = meetings.actions(row['body']) if note_type == 'meeting' else []
        yield {**row, 'workspace': row.get('workspace') or '', 'workspace_name': reference.get('name'),
               'vault': reference.get('vault'), 'vault_path': reference.get('vault_path'),
               'workspace_path': reference.get('workspace_path'), 'summary': meetings.summary(row['body'], row.get('tldr')),
               'series_title': series.get('title'), 'series_path': series.get('path'),
               'action_items': actions, 'action_items_total': len(actions),
               'action_items_done': sum(item['status'] == 'done' for item in actions),
               'has_raw': raw_path(root, root / row['path']).is_file(),
               'content_count': sum(parent_key(item) == key(row) for item in notes)}


def raw_path(root, source):
    return safe(root, root / '.assistant/assets' / read_document(source)[0]['id'] / 'raw.txt')


def resolve_content(root, reference):
    aliases = manifest(root).get('asset_aliases', {})
    target = aliases.get(reference, reference)
    if target.startswith('.assistant/assets/') and target.endswith('/raw.txt'):
        source = safe(root, root / target)
        meeting, metadata, _ = resolve(root, source.parent.name, 'meetings')
        if not source.is_file():
            raise FileNotFoundError('Original notes not found')
        return source, meeting, {'title': 'Raw notes', 'kind': 'raw', 'workspace': metadata.get('workspace')}
    source, metadata, _ = resolve(root, reference, 'notes')
    parent = parent_key(metadata)
    if not parent or parent[0] != 'note':
        raise ValueError('Content has no meeting parent')
    meeting, _, _ = resolve(root, parent[1], 'meetings')
    return source, meeting, {**metadata, 'kind': metadata.get('note_type')}


def contents(root, source):
    for row in records(root, 'notes'):
        if parent_key(row) == ('note', read_document(source)[0]['id']):
            yield {**row, 'kind': row.get('note_type')}


def create(root, record_type, title, *, identifier=None, body='', **fields):
    from lab import assistant as db
    if record_type not in {'task', 'note', 'project'} or not str(title).strip():
        raise ValueError('A record type and title are required')
    identifier = identifier or record_type + '_' + uuid.uuid4().hex
    db.validate_id(identifier)
    source = safe(root, root / (record_type + 's') / (identifier + '.md'))
    from lab import assistant_documents as documents
    if documents.enabled(root):
        return documents.create(root, record_type, title, identifier, body, fields)
    now = db.now_iso()
    metadata = dict(schema=2, id=identifier, type=record_type, title=title, created=now, updated=now)
    if record_type == 'task':
        metadata.update(status='inbox', priority='P2', project=None, workspace=None, parent=None)
    if record_type == 'note':
        metadata.update(note_type='plain', project=None, workspace=None, parent=None)
    metadata.update(fields)
    if metadata.get('status') == 'waiting':
        metadata.setdefault('waiting_since', now)
    if metadata.get('status') == 'ready_to_review':
        metadata.setdefault('review_requested_at', now)
    if record_type == 'task' and metadata.get('status') == 'done':
        raise ValueError('New tasks cannot start completed')
    with lock(root):
        if source.exists():
            raise ValueError('Record ID already exists')
        validate_value(root, metadata, 'status', metadata.get('status')) if record_type == 'task' else None
        validate_value(root, metadata, 'priority', metadata.get('priority')) if record_type == 'task' else None
        for field in ('due', 'scheduled', 'defer_until', 'date', 'recurrence'):
            if metadata.get(field) is not None:
                validate_value(root, metadata, field, metadata[field])
        candidate = {**metadata, 'path': source.relative_to(root).as_posix(), 'body': body}
        by_key = {key(row): row for row in records(root)}
        current, seen = candidate, set()
        while parent_key(current) in by_key:
            identity = parent_key(current)
            if identity in seen:
                raise ValueError('Document parent cycle')
            seen.add(identity)
            current = by_key[identity]
            if record_type == 'task' and current['type'] == 'task' and current.get('status') == 'done':
                raise ValueError('Reopen the completed parent task first')
        validate_graph([*records(root), candidate], {row['id'] for row in workspaces(root)})
        write_document(source, metadata, body)
    return source


def validate_value(root, metadata, field, value):
    from lab import assistant as db, assistant_meetings as meetings
    if field in {'id', 'type', 'schema', 'aliases', 'legacy_path', 'tabs', 'document_path', 'embedded'}:
        raise ValueError('Record identity cannot be edited')
    if field == 'title':
        meetings.validate_title(value)
    if field == 'status' and value not in (*db.STATUSES, 'not_started', 'skipped', 'cancelled'):
        raise ValueError('Invalid task status')
    if field in {'owner','tldr','group'} and value is not None and not isinstance(value,str):
        raise ValueError(field + ' must be text')
    if field == 'priority' and value not in db.PRIORITIES:
        raise ValueError('Invalid priority')
    if field in {'due', 'scheduled', 'defer_until', 'follow_up_at', 'date'} and value is not None:
        meetings.validate_date(value)
    if field == 'recurrence' and value not in {None, 'weekly', 'monthly', 'yearly'}:
        raise ValueError('Invalid recurrence')
    if field in {'project', 'workspace'} and value is not None and not isinstance(value, str):
        raise ValueError('A task can reference at most one project and one workspace')
    if field == 'top_level' and not isinstance(value, bool):
        raise ValueError('top_level must be true or false')
    if field == 'position' and (not isinstance(value, (int,float)) or isinstance(value, bool)):
        raise ValueError('Position must be a number')
    if field == 'parent' and value is not None and not (isinstance(value, dict) and
            set(value) == {'type', 'id'} and value['type'] in {'task', 'note'} and isinstance(value['id'], str)):
        raise ValueError('Parent must be a typed task/note reference')


UNSET = object()


def update(root, reference, field, value, *, collection=None, expected=UNSET):
    from lab import assistant as db
    with lock(root):
        source, metadata, body = resolve(root, reference, collection)
        if expected is not UNSET and metadata.get(field) != expected:
            raise ValueError('This property changed elsewhere. Reload the document.')
        validate_value(root, metadata, field, value)
        rows = list(records(root))
        from lab import assistant_documents as documents
        embedded = documents.enabled(root)
        if embedded and '#tab=' in str(source) and field in {'project','workspace'}:
            raise ValueError('Subtabs inherit project and workspace; edit the containing task or note')
        if embedded and field == 'status':
            progress = progress_map(rows)[key(metadata)]
            permitted = {'skipped'} if parent_key(metadata) else {'cancelled'}
            if value == 'cancelled' and parent_key(metadata):
                raise ValueError('Cancel the overall task or note; use skipped for a subtab')
            if value == 'skipped' and not parent_key(metadata):
                raise ValueError('Skipped is a subtab status')
            if progress['derived'] and value not in {*permitted, progress['automatic_status']}:
                raise ValueError('Overall status is calculated from subtabs; change their statuses')
        if embedded and field == 'parent':
            if value is None or '#tab=' not in str(source):
                raise ValueError('A document root stays independent; subtabs must retain a parent')
            parent_row = next((row for row in rows if key(row) == (value['type'],value['id'])), {})
            if parent_row.get('document_path') != str(documents.physical(source).relative_to(root)):
                raise ValueError('Subtab parent must be in the same Markdown document')
        if field == 'status' and value == 'done':
            if embedded:
                # Derived completion follows child branches, including skipped
                # branches. Only an explicitly completed leaf checks its body.
                incomplete = [] if progress['derived'] else [item for item in db.extract_subtasks(body) if not item['done']]
            else:
                candidates = [metadata | {'body': body}, *descendants(rows, metadata)]
                incomplete = [item for item in candidates[1:] if item['type'] == 'task' and item.get('status') != 'done']
                incomplete += [item for row in candidates for item in db.extract_subtasks(row['body']) if not item['done']]
            if incomplete:
                raise ValueError('Complete all descendant tasks and checkboxes first')
        if not embedded and field == 'status' and value != 'done' and metadata.get('status') == 'done':
            current = metadata
            by_key = {key(row): row for row in rows}
            while parent_key(current):
                current = by_key[parent_key(current)]
                if current.get('type') == 'task' and current.get('status') == 'done':
                    raise ValueError('Reopen the completed parent task first')
        if not embedded and field == 'parent' and value is not None:
            by_key = {key(row): row for row in rows}
            pending = metadata.get('type') == 'task' and metadata.get('status') != 'done' or any(row['type'] == 'task' and row.get('status') != 'done' for row in descendants(rows, metadata))
            current, seen = value, set()
            while current and (current.get('type'), current.get('id')) in by_key:
                identity = current['type'], current['id']
                if identity in seen:
                    raise ValueError('Document parent cycle')
                seen.add(identity)
                ancestor = by_key[identity]
                if pending and ancestor['type'] == 'task' and ancestor.get('status') == 'done':
                    raise ValueError('Reopen the completed parent task first')
                current = ancestor.get('parent')
        metadata.update({field: value, 'updated': db.now_iso()})
        if field == 'status':
            if value == 'done':
                metadata['completed'] = db.now_iso()
            else:
                metadata.pop('completed', None)
            if value == 'waiting' and not metadata.get('waiting_since'):
                metadata['waiting_since'] = db.now_iso()
            if value == 'ready_to_review' and not metadata.get('review_requested_at'):
                metadata['review_requested_at'] = db.now_iso()
        candidate = metadata | {'path': source.relative_to(root).as_posix(), 'body': body}
        validate_graph([candidate if key(row) == key(candidate) else row for row in rows],
                       {row['id'] for row in workspaces(root)})
        write_document(source, metadata, body)
        if embedded:
            documents.snapshot(root, force=True)
        return source


def verify(root):
    rows = list(records(root))
    validate_graph(rows, {row['id'] for row in workspaces(root)})
    return {'schema': 2, 'document_format':manifest(root).get('document_format','separate-records'), 'counts': dict(Counter(row['type'] for row in rows)),
            'task_roots': sum(row['type'] == 'task' and not row.get('parent') for row in rows),
            'workspaces': len(workspaces(root)), 'valid': True}


def create_subtab(root, title, *, parent, project=UNSET, workspace=UNSET, top_level=False):
    """Create a tab in the same document, nested by default or beside its main tab."""
    if not isinstance(parent, dict) or set(parent) != {'type', 'id'} or parent['type'] not in {'task', 'note'}:
        raise ValueError('A subtab requires a typed task/note parent')
    _, owner, _ = resolve(root, parent['id'], parent['type'] + 's')
    if top_level and owner.get('parent'):
        raise ValueError('Top-level tabs must link directly to the document root')
    siblings = [row for row in records(root) if parent_key(row) == (parent['type'], parent['id'])]
    position = max((row.get('position', 0) for row in siblings), default=-1) + 1
    return create(root, 'note', title, note_type='subtab', parent=parent, position=position, status='not_started', priority='P2',
                  project=owner.get('project') if project is UNSET else project,
                  workspace=owner.get('workspace') if workspace is UNSET else workspace,
                  **({'top_level':True} if top_level else {}))
