"""Workspace-owned objectives; Assistant documents are references, never copies.

The registry lives beside workspace state, while each owned document is an
ordinary Markdown file with stable embedded subtab IDs. No workspace/tasks
catalog fields are repurposed. Reads do not launch terminals or scan worktrees.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse
import uuid

from lab import assistant_documents, assistant_records, paths, storage, workspace_identity

PALETTES = [
    ['#58a6ff', '#ff7b72', '#3fb950', '#d29922'],
    ['#bc8cff', '#e3b341', '#56d6c0', '#ff9bce'],
    ['#ffa657', '#f778ba', '#a9d14c', '#238a97'],
]
_DOCUMENT_CACHE = {}


def identifier():
    return uuid.uuid4().hex


def revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:24]


def directory(root, workspace_id):
    if not workspace_id or workspace_id.startswith('__') or not re.fullmatch(r'[A-Za-z0-9_.-]+', workspace_id) or workspace_id in {'.', '..'}:
        raise ValueError('Choose a real workspace')
    folder = paths.workspace_dir(root, workspace_id)
    if not paths.workspace_file(root, workspace_id).is_file():
        raise ValueError('Workspace not found')
    return folder


def registry(root, workspace_id):
    return directory(root, workspace_id) / '.lab' / 'objectives.json'


def load(root, workspace_id):
    file = registry(root, workspace_id)
    if file.is_file():
        data = storage.read_json(file)
    else:
        data = {'version': 1, 'enabled': False, 'focused': [], 'objectives': [], 'terminal_links': {}}
    return {**data, 'revision': revision(data)}


def _text(value, name='Name', limit=512):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or '\x00' in value:
        raise ValueError(f'{name} must contain 1–{limit} characters')
    return value.strip()


def _date(value):
    if not value:
        return None
    if not isinstance(value, str):
        raise ValueError('Use an ISO calendar date')
    date.fromisoformat(value)
    return value


def _find(rows, key):
    return next((row for row in rows if row['id'] == key), None)


def _color(data, objective):
    used = {tree['color'] for item in data['objectives'] for tree in item['worktrees']}
    for color in objective['palette']:
        if color not in used:
            return color
    # Extra worktrees keep globally unique colors; the reserved four are first.
    for hue in range(0, 360, 37):
        import colorsys
        color = '#%02x%02x%02x' % tuple(round(n * 255) for n in colorsys.hsv_to_rgb(hue / 360, .55, .9))
        if color not in used:
            return color
    raise ValueError('No unused worktree colors remain')


def _owned_path(folder, resource):
    relative = Path(resource['path'])
    target = folder / relative
    boundary = (folder / 'objectives').resolve()
    if relative.is_absolute() or not target.resolve().is_relative_to(boundary):
        raise ValueError('Document must belong to this workspace objective')
    return target


def document(folder, resource):
    target = _owned_path(folder, resource)
    stat = target.stat()
    signature = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
    hit = _DOCUMENT_CACHE.get(str(target))
    if hit and hit[0] == signature:
        return deepcopy(hit[1])
    raw = target.read_bytes()
    if resource['kind'] == 'notebook':
        content = {'notebook': json.loads(raw)}
    else:
        owner, body, tabs = assistant_documents.unpack(raw)
        content = {'body': body, 'tabs': [{**metadata, 'body': text} for metadata, text in tabs]}
    content['revision'] = hashlib.sha256(raw).hexdigest()[:24]
    _DOCUMENT_CACHE[str(target)] = (signature, content)
    while len(_DOCUMENT_CACHE) > 128:
        del _DOCUMENT_CACHE[next(iter(_DOCUMENT_CACHE))]
    return deepcopy(content)


def payload(root, workspace_id):
    data = load(root, workspace_id)
    folder = directory(root, workspace_id)
    for objective in data['objectives']:
        for resource in objective['resources']:
            if resource['kind'] not in {'document', 'notebook'}:
                continue
            try:
                resource['content'] = document(folder, resource)
            except (OSError, ValueError) as exc:
                resource['error'] = str(exc)
    return data


def _metadata(identifier_, title, parent=None):
    return {'schema': 2, 'id': identifier_, 'type': 'note', 'title': title,
            'created': date.today().isoformat(), 'updated': date.today().isoformat(),
            **({'parent': parent} if parent else {})}


def _write_document(folder, resource, body='', tabs=None):
    target = _owned_path(folder, resource)
    assistant_records.atomic_bytes(target, assistant_documents.pack(
        _metadata(resource['id'], resource['title']), body, tabs or []))


def _resource(folder, objective, action):
    kind = action.get('kind', 'document')
    if kind not in {'document', 'notebook', 'assistant', 'link', 'file'}:
        raise ValueError('Unsupported resource type')
    item = {'id': identifier(), 'kind': kind, 'title': _text(action.get('title')),
            'worktree': action.get('worktree') or None}
    if item['worktree'] and not _find(objective['worktrees'], item['worktree']):
        raise ValueError('Worktree must belong to this objective')
    if kind in {'document', 'notebook'}:
        extension = '.ipynb' if kind == 'notebook' else '.md'
        if not item['title'].endswith(extension):
            item['title'] += extension
        filename = re.sub(r'[/\\\x00-\x1f]', '_', item['title']).strip('. ')
        relative = Path('objectives') / objective['id'] / filename
        while (folder / relative).exists():
            relative = relative.with_name(relative.stem + '-' + identifier()[:6] + extension)
        item['path'] = relative.as_posix()
        if kind == 'notebook':
            storage.write_json(_owned_path(folder, item), {'nbformat': 4, 'nbformat_minor': 5,
                'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}},
                'cells': [{'id': identifier(), 'cell_type': 'markdown', 'metadata': {}, 'source': '# ' + item['title'].removesuffix('.ipynb') + '\n'},
                          {'id': identifier(), 'cell_type': 'code', 'metadata': {}, 'source': 'print(1 + 1)', 'outputs': [], 'execution_count': None}]})
        else:
            _write_document(folder, item, action.get('body', ''))
    elif kind == 'file':
        file_root = Path(action.get('file_root') or folder).resolve()
        if file_root not in [folder.resolve(), *(Path(t['path']).resolve() for t in objective['worktrees'])]:
            raise ValueError('File folder must belong to this objective')
        target = (file_root / str(action.get('path', ''))).resolve()
        if not target.is_relative_to(file_root) or not target.is_file():
            raise ValueError('Choose an existing objective file')
        item.update(file_root=str(file_root), path=target.relative_to(file_root).as_posix())
    elif kind == 'link':
        item['url'] = _text(action.get('url'), 'URL', 4096)
        if urlparse(item['url']).scheme not in {'http', 'https'} or not urlparse(item['url']).netloc:
            raise ValueError('Use a full http or https URL')
    else:
        item['document_id'] = _text(action.get('document_id'), 'Document ID')
        item['assistant_root'] = _text(action.get('assistant_root'), 'Assistant location', 4096)
        item['tab_id'] = action.get('tab_id') or None
    objective['resources'].append(item)
    return item


def _task_details(folder, objective, task, parent=None, resource_id=None):
    resource = _find(objective['resources'], resource_id) if resource_id else None
    if resource_id and not resource:
        raise ValueError('Task document not found')
    if not resource:
        resource = next((r for r in objective['resources'] if r.get('task_document')), None)
    if not resource:
        resource = _resource(folder, objective, {'kind': 'document', 'title': 'Tasks', 'body': '# Task details\n\nOpen a task subtab to read its context.'})
        resource['task_document'] = True
    if resource['kind'] != 'document':
        raise ValueError('Task details must link to an objective document')
    target = _owned_path(folder, resource)
    owner, body, tabs = assistant_documents.unpack(target.read_bytes())
    tab_id = identifier()
    tabs.append((_metadata(tab_id, task['title'], {'id': parent['tab_id'] if parent and parent['document_id'] == resource['id'] else owner['id'], 'type': 'note'}),
                 '# ' + task['title'] + '\n\nDescribe the outcome, evidence, and next steps here.'))
    assistant_records.atomic_bytes(target, assistant_documents.pack(owner, body, tabs))
    task.update(document_id=resource['id'], tab_id=tab_id)


def mutate(root, workspace_id, action, expected=None):
    folder = directory(root, workspace_id)
    with workspace_identity.operation_lease(root, workspace_id):
        data = load(root, workspace_id)
        if expected is not None and data['revision'] != expected:
            raise ValueError('Objectives changed elsewhere. Refresh and retry.')
        data.pop('revision')
        operation = action.get('type')
        objective = _find(data['objectives'], action.get('objective_id'))
        if operation == 'create':
            if len(data['objectives']) >= 100:
                raise ValueError('An objective workspace supports up to 100 saved objectives')
            objective = {'id': identifier(), 'name': _text(action.get('name'), limit=80),
                         'purpose': str(action.get('purpose', ''))[:4096], 'worktrees': [], 'resources': [], 'tasks': [],
                         'palette': PALETTES[len(data['objectives']) % 3][:]}
            objective['color'] = objective['palette'][0]
            data['objectives'].append(objective)
            data['enabled'] = True
            if len(data['focused']) < 3:
                data['focused'].append(objective['id'])
            else:
                slot = action.get('replace')
                if slot not in data['focused']:
                    raise ValueError('Choose which of the three focus slots to replace')
                data['focused'][data['focused'].index(slot)] = objective['id']
            if action.get('import_existing'):
                from lab import scope_links
                metadata = storage.read_json(paths.workspace_file(root, workspace_id))
                for tree in metadata.get('worktrees', []):
                    path = tree.get('dir') or tree.get('path')
                    if not path or not Path(path).is_dir() or any(t['path'] == path for o in data['objectives'] for t in o['worktrees']):
                        continue
                    objective['worktrees'].append({'id':identifier(), 'path':path, 'resolved_path':str(Path(path).resolve()),
                        'label':tree.get('branch') or tree.get('mp') or Path(path).name,
                        'repo':tree.get('repo', path), 'branch':tree.get('branch',''), 'kind':'worktree', 'color':_color(data, objective)})
                # Copy references; the original scope links and Assistant files
                # retain their ownership and all existing behavior.
                seen = set()
                reference_file = folder / '.lab' / 'document-links.json'
                refs = storage.read_json(reference_file).get('documents', []) if reference_file.is_file() else []
                for source, worktree in [(folder,None), *((Path(t['path']),t['id']) for t in objective['worktrees'])]:
                    for ref in scope_links.read(source)['links']:
                        refs.append({**ref, 'worktree':worktree})
                for ref in refs:
                    identity = (ref.get('document_id') or ref.get('url'), ref.get('worktree'), ref.get('tab_id'))
                    if identity in seen:
                        continue
                    seen.add(identity)
                    if ref.get('document_id') and ref.get('assistant_root'):
                        _resource(folder, objective, {**ref, 'kind':'assistant', 'title':ref.get('label') or ref.get('title') or 'Assistant document'})
                    elif ref.get('url'):
                        _resource(folder, objective, {**ref, 'kind':'link', 'title':ref.get('label') or ref.get('type_name') or 'Link'})
                for directory_ in ['docs', 'notebooks', 'notes']:
                    for file in sorted((folder / directory_).glob('*')):
                        if file.is_file() and file.suffix in {'.md','.ipynb'}:
                            _resource(folder, objective, {'kind':'file','title':file.name,'path':file.relative_to(folder).as_posix()})
        elif objective is None:
            raise ValueError('Objective not found')
        elif operation == 'focus':
            if objective['id'] not in data['focused']:
                if len(data['focused']) < 3:
                    data['focused'].append(objective['id'])
                elif action.get('replace') in data['focused']:
                    data['focused'][data['focused'].index(action['replace'])] = objective['id']
                else:
                    raise ValueError('Choose a focus slot to replace')
        elif operation == 'settings':
            objective['name'] = _text(action.get('name', objective['name']), limit=80)
            objective['purpose'] = str(action.get('purpose', objective['purpose']))[:4096]
        elif operation == 'worktree':
            path = _text(action.get('path'), 'Worktree path', 4096)
            if not Path(path).is_absolute() or not Path(path).is_dir():
                raise ValueError('Choose an existing worktree or folder')
            if any(t['path'] == path for o in data['objectives'] for t in o['worktrees']):
                raise ValueError('This worktree already belongs to an objective')
            objective['worktrees'].append({'id': identifier(), 'path': path, 'resolved_path': str(Path(path).resolve()), 'label': _text(action.get('label', Path(path).name)),
                'repo': str(action.get('repo', path)), 'branch': str(action.get('branch', '')),
                'kind': action.get('kind', 'worktree'), 'color': _color(data, objective)})
        elif operation == 'resource':
            _resource(folder, objective, action)
        elif operation == 'scope':
            resource = _find(objective['resources'], action.get('resource_id'))
            if not resource:
                raise ValueError('Resource not found')
            tree = action.get('worktree') or None
            if tree and not _find(objective['worktrees'], tree):
                raise ValueError('Worktree must belong to this objective')
            resource['worktree'] = tree
        elif operation == 'rename':
            resource = _find(objective['resources'], action.get('resource_id'))
            if not resource:
                raise ValueError('Resource not found')
            title = _text(action.get('title'))
            if action.get('tab_id'):
                if resource['kind'] != 'document':
                    raise ValueError('Choose an owned Markdown subtab')
                target = _owned_path(folder, resource)
                owner, body, tabs = assistant_documents.unpack(target.read_bytes())
                if not any(meta['id'] == action['tab_id'] for meta, _ in tabs):
                    raise ValueError('Subtab not found')
                tabs = [({**meta, 'title': title} if meta['id'] == action['tab_id'] else meta, text) for meta, text in tabs]
                assistant_records.atomic_bytes(target, assistant_documents.pack(owner, body, tabs))
            else:
                resource['title'] = title
                if resource['kind'] in {'document', 'notebook'}:
                    extension = '.ipynb' if resource['kind'] == 'notebook' else '.md'
                    if not resource['title'].endswith(extension):
                        resource['title'] += extension
                    target = _owned_path(folder, resource)
                    filename = re.sub(r'[/\\\x00-\x1f]', '_', resource['title']).strip('. ')
                    destination = target.with_name(filename)
                    if destination != target:
                        if destination.exists():
                            raise ValueError('A document with this filename already exists')
                        target.rename(destination)
                        resource['path'] = destination.relative_to(folder).as_posix()
                    if resource['kind'] == 'document':
                        owner, body, tabs = assistant_documents.unpack(destination.read_bytes())
                        assistant_records.atomic_bytes(destination, assistant_documents.pack({**owner, 'title':resource['title']}, body, tabs))
        elif operation == 'task':
            parent = _find(objective['tasks'], action.get('parent_id')) if action.get('parent_id') else None
            if action.get('parent_id') and parent is None:
                raise ValueError('Parent task not found')
            task = {'id': identifier(), 'title': _text(action.get('title')), 'done': False, 'due': _date(action.get('due')), 'children': []}
            _task_details(folder, objective, task, parent, action.get('document_id') or (parent or {}).get('document_id'))
            (parent['children'] if parent else objective['tasks']).append(task)
        elif operation == 'task-update':
            task = next((t for parent in objective['tasks'] for t in [parent, *parent['children']] if t['id'] == action.get('task_id')), None)
            if task is None:
                raise ValueError('Task not found')
            if 'done' in action:
                if not isinstance(action['done'], bool):
                    raise ValueError('Task completion must be a boolean')
                task['done'] = action['done']
                for child in task['children']:
                    child['done'] = action['done']
            if 'due' in action:
                task['due'] = _date(action['due'])
            if 'title' in action:
                task['title'] = _text(action['title'])
        elif operation == 'document':
            resource = _find(objective['resources'], action.get('resource_id'))
            if not resource or resource['kind'] != 'document':
                raise ValueError('Choose an owned Markdown document')
            target = _owned_path(folder, resource)
            current = document(folder, resource)
            if action.get('document_revision') != current['revision']:
                raise ValueError('Document changed elsewhere. Refresh before saving.')
            owner, body, tabs = assistant_documents.unpack(target.read_bytes())
            text = action.get('body')
            if not isinstance(text, str) or len(text) > 2000000:
                raise ValueError('Document content must be text, up to 2 MB')
            tab_id = action.get('tab_id')
            if tab_id:
                if not any(meta['id'] == tab_id for meta, _ in tabs):
                    raise ValueError('Subtab not found')
                tabs = [(meta, text if meta['id'] == tab_id else content) for meta, content in tabs]
            else:
                body = text
            assistant_records.atomic_bytes(target, assistant_documents.pack(owner, body, tabs))
        elif operation == 'subtab':
            resource = _find(objective['resources'], action.get('resource_id'))
            if not resource or resource['kind'] != 'document':
                raise ValueError('Choose an owned document')
            target = _owned_path(folder, resource)
            owner, body, tabs = assistant_documents.unpack(target.read_bytes())
            title = _text(action.get('title'))
            parent = action.get('parent_id') or owner['id']
            if parent != owner['id'] and not any(meta['id'] == parent for meta, _ in tabs):
                raise ValueError('Parent subtab not found')
            tabs.append((_metadata(identifier(), title, {'type': 'note', 'id': parent}), action.get('body', '')))
            assistant_records.atomic_bytes(target, assistant_documents.pack(owner, body, tabs))
        elif operation == 'terminal':
            name = _text(action.get('session_id'), 'Terminal identity')
            resource = _find(objective['resources'], action.get('resource_id'))
            if action.get('resource_id') and not resource:
                raise ValueError('Resource not found')
            if action.get('tab_id'):
                if not resource or resource['kind'] not in {'document', 'assistant'}:
                    raise ValueError('Choose a document subtab')
                if resource['kind'] == 'document' and not any(t['id'] == action['tab_id'] for t in document(folder, resource)['tabs']):
                    raise ValueError('Subtab not found')
            linked_file = action.get('file')
            if linked_file:
                allowed = [folder.resolve(), *(Path(t['path']).resolve() for t in objective['worktrees'])]
                file_root = Path(linked_file.get('root', '')).resolve()
                if file_root not in allowed:
                    raise ValueError('File folder must belong to this objective')
                relative = Path(linked_file.get('path', ''))
                target = (file_root / relative).resolve()
                if not target.is_relative_to(file_root) or not target.is_file():
                    raise ValueError('Choose a file in this objective')
                linked_file = {'root':str(file_root), 'path':target.relative_to(file_root).as_posix()}
            data['terminal_links'][name] = {'objective_id': objective['id'], 'resource_id': action.get('resource_id'),
                                          'tab_id': action.get('tab_id'), 'file': linked_file}
        elif operation == 'remove-resource':
            resource_id = action.get('resource_id')
            if any(t['document_id'] == resource_id for p in objective['tasks'] for t in [p, *p['children']]):
                raise ValueError('A task still needs this document')
            objective['resources'] = [r for r in objective['resources'] if r['id'] != resource_id]
            # Preserve owned files so unlinking never destroys user content.
        else:
            raise ValueError('Unsupported objective action')
        storage.write_json(registry(root, workspace_id), data)
    return payload(root, workspace_id)
