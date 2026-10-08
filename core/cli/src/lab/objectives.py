"""Workspace-owned objectives; Assistant documents are references, never copies.

Each Objective is defined by its folder's .objective.json. Owned documents are
ordinary Markdown files with stable embedded subtab IDs. No workspace/tasks
catalog fields are repurposed. Reads do not launch terminals or scan worktrees.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlparse
import uuid

from lab import assistant_documents, assistant_records, objective_store, paths, storage, workspace_identity
from lab import task_checklists, task_cycles

PALETTES = [
    ['#58a6ff', '#ff7b72', '#3fb950', '#d29922'],
    ['#bc8cff', '#e3b341', '#56d6c0', '#ff9bce'],
    ['#ffa657', '#f778ba', '#a9d14c', '#238a97'],
    ['#39c5cf', '#d67ad2', '#e5a07c', '#85c56a'],
    ['#8b9dff', '#e87f91', '#a6be4f', '#58b9a6'],
]
FOCUS_SLOTS = 5
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
    """Workspace UI preferences only; Objective content lives in its own folder."""
    return objective_store.state_file(directory(root, workspace_id))


def load(root, workspace_id, *, _locked=False):
    folder = directory(root, workspace_id)
    if _locked:
        data = objective_store.read(folder)
    else:
        refresh_recurring(root, workspace_id)
        with objective_store.lock(folder):
            data = objective_store.read(folder)
    saved_revision = revision(data)
    _slot_colors(data)
    if not _locked:
        for objective in data['objectives']:
            for parent in objective['tasks']:
                for task in [*parent['children'], parent]:
                    if task.get('done') and task_checklists.counts(_task_body(folder, objective, task))['pending']:
                        _set_task_status(task, 'in_progress' if task['children'] else 'todo')
                if parent.get('done') and any(not child.get('done') and child.get('status') != 'wont_do' for child in parent['children']):
                    _set_task_status(parent, _children_status(parent['children']))
    return {**data, 'revision': saved_revision}


def migrate(root, workspace_id, *, apply=False):
    folder = directory(root, workspace_id)
    with workspace_identity.operation_lease(root, workspace_id), objective_store.lock(folder, write=apply):
        return objective_store.migration(folder, apply=apply)


def _objective_dir(folder, objective):
    return Path(objective.get('path', folder / 'objectives' / objective['id']))


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


def _tasks(objective):
    return [task for parent in objective['tasks'] for task in [parent, *parent['children']]]


def _set_task_status(task, status):
    task['status'] = status
    task['done'] = status == 'done'
    if status == 'done':
        task.setdefault('completed_at', time.time())
    else:
        task.pop('completed_at', None)


def _children_status(children):
    if all(c.get('status') == 'wont_do' for c in children):
        return 'wont_do'
    if all(c['done'] or c.get('status') == 'wont_do' for c in children):
        return 'done'
    if any(c['done'] or c.get('status') == 'in_progress' for c in children):
        return 'in_progress'
    return 'paused' if all(c.get('status') == 'paused' for c in children) else 'todo'


def _asset_target(asset):
    return {key:value for key,value in asset.items() if key != 'id'}


def _prune_assets(objective, remove):
    for field in ('shared_assets', 'archived_assets', 'asset_shelf', 'trashed_assets'):
        if field in objective:
            objective[field] = [asset for asset in objective[field] if not remove(asset)]
    _prune_task_assets(objective, remove)
    if 'assignment_suggestions' in objective:
        objective['assignment_suggestions'] = [s for s in objective['assignment_suggestions'] if not remove(s['asset'])]


def _prune_task_assets(objective, remove):
    for task in _tasks(objective):
        assets = task.get('assets', [])
        kept = [asset for asset in assets if not remove(asset)]
        if len(kept) != len(assets):
            task['assets'] = kept
            if task.get('icon_asset_id') not in {'details', *(a['id'] for a in kept)}:
                task.pop('icon_asset_id', None)


def _folder_target(folder, objective, linked):
    if not isinstance(linked, dict) or not isinstance(linked.get('root'), str) or not isinstance(linked.get('path', ''), str):
        raise ValueError('Choose a folder in this objective')
    root = Path(linked['root']).resolve()
    allowed = [folder.resolve(), _objective_dir(folder, objective).resolve(), *(Path(t['path']).resolve() for t in objective['worktrees'])]
    target = (root / linked.get('path', '')).resolve()
    if root not in allowed or not target.is_relative_to(root) or not target.is_dir():
        raise ValueError('Choose a folder in this objective')
    return {'root':str(root), 'path':target.relative_to(root).as_posix()}


def _task_asset(folder, objective, action):
    if action.get('folder') is not None:
        if action.get('resource_id') or action.get('reference') or action.get('tab_id') or action.get('sub_link_id'):
            raise ValueError('Choose one task asset')
        return {'folder':_folder_target(folder, objective, action['folder'])}
    resource = _find(objective['resources'], action.get('resource_id'))
    reference = action.get('reference')
    if reference is not None:
        if action.get('resource_id') or not isinstance(reference, dict) or reference.get('kind') not in {'file','assistant','link'}:
            raise ValueError('Choose an existing file, document or link')
        candidate = _resource(folder, objective, reference)
        fields = {'file':['file_root','path'], 'assistant':['assistant_root','document_id','tab_id'], 'link':['url']}[candidate['kind']]
        resource = next((r for r in objective['resources'] if r['id'] != candidate['id'] and r['kind'] == candidate['kind']
                         and all(r.get(field) == candidate.get(field) for field in fields)), candidate)
        if candidate['kind'] == 'file':
            target = (Path(candidate['file_root']) / candidate['path']).resolve()
            resource = next((r for r in objective['resources'] if r['id'] != candidate['id'] and r['kind'] in {'file','document','notebook'}
                             and (Path(r.get('file_root') or folder) / r['path']).resolve() == target), resource)
        if resource is not candidate:
            objective['resources'].remove(candidate)
    if resource is None:
        raise ValueError('Task asset not found')
    result = {'resource_id':resource['id']}
    tab = action.get('tab_id') or (reference or {}).get('tab_id')
    if tab:
        if resource['kind'] not in {'document','assistant'}:
            raise ValueError('Choose a document subtab')
        if resource['kind'] == 'document' and not any(t['id'] == tab for t in document(folder, resource)['tabs']):
            raise ValueError('Subtab not found')
        result['tab_id'] = _text(tab, 'Subtab ID', 128)
    if action.get('sub_link_id'):
        if tab or resource['kind'] != 'link' or not _find(list(_sublink_rows(resource)), action['sub_link_id']):
            raise ValueError('Sublink not found')
        result['sub_link_id'] = action['sub_link_id']
    return result


def _put_asset(objective, field, target, limit=512):
    rows = objective.setdefault(field, [])
    existing = next((asset for asset in rows if _asset_target(asset) == target), None)
    if existing:
        return existing
    if len(rows) >= limit:
        raise ValueError(f'This asset list supports up to {limit} references')
    asset = {'id':identifier(), **target}
    rows.append(asset)
    return asset


def _asset_bucket(folder, objective, action):
    star = action.get('type') == 'asset-star'
    if star and type(action.get('starred')) is not bool:
        raise ValueError('Asset star must be a boolean')
    bucket = 'objective' if star and action['starred'] else 'unassigned' if star else action.get('bucket')
    if bucket not in {'objective', 'unassigned', 'archive'}:
        raise ValueError('Choose Objective, Unassigned or Archive')
    asset = _task_asset(folder, objective, action)
    if not star and bucket != 'objective' and any(
        asset.get('resource_id') == task['document_id']
        and (not asset.get('tab_id') or asset['tab_id'] == task['tab_id'])
        for task in _tasks(objective)
    ):
        raise ValueError('Task details must remain associated with their task')
    if asset.get('folder'):
        _put_asset(objective, 'asset_shelf', asset)
    for field in ('shared_assets',) if star and not action['starred'] else ('shared_assets', 'archived_assets'):
        objective[field] = [row for row in objective.get(field, []) if _asset_target(row) != asset]
    if bucket == 'objective':
        _put_asset(objective, 'shared_assets', asset)
    elif not star:
        _prune_task_assets(objective, lambda row: _asset_target(row) == asset)
        if bucket == 'archive':
            _put_asset(objective, 'archived_assets', asset)


def _covers(container, asset):
    """A hidden document/link also hides its subtabs/sublinks."""
    return _asset_target(container) == asset or bool(
        container.get('resource_id') and container['resource_id'] == asset.get('resource_id')
        and not container.get('tab_id') and not container.get('sub_link_id'))


def _optional_asset(objective, asset):
    if any(asset.get('resource_id') == task['document_id']
           and (not asset.get('tab_id') or asset['tab_id'] == task['tab_id']) for task in _tasks(objective)):
        raise ValueError('Task details must remain associated with their task')


def _assignment_destination(data, objective, action):
    destination = action.get('destination')
    if not isinstance(destination, dict) or destination.get('bucket') not in {'task', 'objective'}:
        raise ValueError('Choose a task or Objective for the assignment')
    owner = _find(data['objectives'], destination.get('objective_id', objective['id']))
    if owner is None:
        raise ValueError('Suggested Objective no longer exists')
    target = {'bucket':destination['bucket'], 'objective_id':owner['id']}
    if target['bucket'] == 'task':
        if not _find(_tasks(owner), destination.get('task_id')):
            raise ValueError('Suggested task no longer exists')
        target['task_id'] = destination['task_id']
    return owner, target


def _assignment_asset(folder, objective, action):
    # Suggestions may only refer to registered assets, never import/create one.
    if action.get('reference') is not None:
        raise ValueError('Register the asset before suggesting an assignment')
    asset = _task_asset(folder, objective, action)
    if asset.get('folder'):
        registered = [*objective.get('asset_shelf', []), *objective.get('shared_assets', []),
                      *objective.get('archived_assets', []), *(a for task in _tasks(objective) for a in task.get('assets', [])),
                      *({'folder':{'root':str(Path(t['path']).resolve()), 'path':'.'}} for t in objective['worktrees'])]
        if not any(_asset_target(row) == asset for row in registered):
            raise ValueError('Register the folder asset before suggesting or changing its assignment')
    _optional_asset(objective, asset)
    if any(_covers(row, asset) for row in objective.get('trashed_assets', [])):
        raise ValueError('This asset was removed')
    return asset


def _transfer_asset(folder, data, source, owner, asset):
    """Move a registration, retaining the original file/document ownership."""
    if source is owner:
        return asset
    if asset.get('folder'):
        tree = next((t for t in source['worktrees'] if Path(t['path']).resolve() == Path(asset['folder']['root']).resolve()), None)
        if tree is None or asset['folder']['path'] != '.':
            raise ValueError('Only an associated whole worktree can move to another Objective')
        source['worktrees'].remove(tree)
        owner['worktrees'].append(tree)
        for resource in source['resources']:
            if resource.get('worktree') == tree['id']:
                resource['worktree'] = None
        _prune_assets(source, lambda row: row.get('folder', {}).get('root') == asset['folder']['root'])
        return asset
    resource = _find(source['resources'], asset.get('resource_id'))
    if asset.get('tab_id') and resource['kind'] != 'assistant':
        raise ValueError('Move the whole document to another Objective, rather than an individual subtab')
    reference = deepcopy(resource)
    reference.update(id=identifier(), worktree=None)
    reference.pop('task_document', None)
    if resource['kind'] in {'document', 'notebook'}:
        reference.update(kind='file', file_root=str(folder), path=resource['path'])
    if asset.get('sub_link_id'):
        reference.update(deepcopy(_find(list(_sublink_rows(resource)), asset['sub_link_id'])))
        reference['id'] = identifier()
        reference.pop('sublinks', None)
    identity = {'file':['file_root', 'path'], 'link':['url'], 'assistant':['assistant_root', 'document_id', 'tab_id']}[reference['kind']]
    existing = next((r for r in owner['resources'] if r['kind'] == reference['kind'] and all(r.get(k) == reference.get(k) for k in identity)), None)
    if existing is None:
        owner['resources'].append(reference)
    result = {'resource_id':(existing or reference)['id']}
    if asset.get('tab_id'):
        result['tab_id'] = asset['tab_id']
    if asset.get('tab_id') or asset.get('sub_link_id'):
        _prune_assets(source, lambda row: _asset_target(row) == asset)
        _put_asset(source, 'trashed_assets', asset)
    else:
        source['resources'].remove(resource)
        _prune_assets(source, lambda row: row.get('resource_id') == resource['id'])
    # Running terminals keep their original mappings and launch directories.
    return result


def _assign_asset(folder, data, objective, asset, owner, destination):
    asset = _transfer_asset(folder, data, objective, owner, asset)
    _prune_task_assets(owner, lambda row: _asset_target(row) == asset)
    _asset_bucket(folder, owner, {**asset, 'type':'asset-bucket', 'bucket':destination['bucket'] if destination['bucket'] == 'objective' else 'unassigned'})
    if destination['bucket'] == 'task':
        task = _find(_tasks(owner), destination['task_id'])
        _put_asset(task, 'assets', asset, 128)
    for suggestion in owner.get('assignment_suggestions', []):
        if suggestion['asset'] == asset and suggestion['status'] == 'pending':
            suggestion['status'] = 'superseded'


def _suggest_assignment(folder, data, objective, action):
    asset = _assignment_asset(folder, objective, action)
    if any(_covers(row, asset) for row in objective.get('archived_assets', [])):
        raise ValueError('Restore the archived asset before suggesting an assignment')
    owner, destination = _assignment_destination(data, objective, action)
    if owner is not objective:
        # Validate the transfer on a copy; a proposal never alters membership.
        preview = deepcopy(data)
        _transfer_asset(folder, preview, _find(preview['objectives'], objective['id']), _find(preview['objectives'], owner['id']), asset)
    rows = objective.setdefault('assignment_suggestions', [])
    if any(s['asset'] == asset and s['destination'] == destination for s in rows):
        return  # Includes rejected proposals: do not re-offer the same decision.
    if len(rows) >= 2048:
        raise ValueError('This Objective supports up to 2048 assignment suggestions')
    rows.append({'id':identifier(), 'asset':asset, 'destination':destination,
                 'reason':_text(action.get('reason'), 'Suggestion reason', 1024), 'status':'pending'})


def _trash_asset(folder, objective, action):
    if action.get('confirmed') is not True:
        raise ValueError('Confirm removing this asset first')
    asset = _assignment_asset(folder, objective, action)
    if asset.get('folder'):
        root = Path(asset['folder']['root']).resolve()
        if root in {folder.resolve(), _objective_dir(folder, objective).resolve()} and asset['folder']['path'] == '.':
            raise ValueError('Root and Objective folders cannot be removed')
        tree = next((t for t in objective['worktrees'] if Path(t['path']).resolve() == root), None)
        if tree and asset['folder']['path'] == '.':
            objective['worktrees'].remove(tree)
            for resource in objective['resources']:
                if resource.get('worktree') == tree['id']:
                    resource['worktree'] = None
            _prune_assets(objective, lambda row: row.get('folder', {}).get('root') == asset['folder']['root'])
        else:
            _prune_assets(objective, lambda row: _asset_target(row) == asset)
        _put_asset(objective, 'trashed_assets', asset)
    elif asset.get('tab_id') or asset.get('sub_link_id'):
        _prune_assets(objective, lambda row: _asset_target(row) == asset)
        _put_asset(objective, 'trashed_assets', asset)
    else:
        objective['resources'] = [r for r in objective['resources'] if r['id'] != asset['resource_id']]
        _prune_assets(objective, lambda row: row.get('resource_id') == asset['resource_id'])


def _color(data, objective):
    if objective['id'] not in data['focused']:
        return '#8b949e'
    used = {tree['color'] for item in data['objectives'] if item['id'] in data['focused'] for tree in item['worktrees']}
    for color in objective['palette']:
        if color not in used:
            return color
    # Extra worktrees must not borrow another slot's reserved colors.
    used.update(color for palette in PALETTES for color in palette)
    for hue in range(0, 360, 37):
        import colorsys
        color = '#%02x%02x%02x' % tuple(round(n * 255) for n in colorsys.hsv_to_rgb(hue / 360, .55, .9))
        if color not in used:
            return color
    raise ValueError('No unused worktree colors remain')


def _slot_colors(data):
    for objective in data['objectives']:
        slot = data['focused'].index(objective['id']) if objective['id'] in data['focused'] else None
        objective['palette'] = PALETTES[slot][:] if slot is not None else []
        objective['color'] = objective['palette'][0] if slot is not None else '#8b949e'
        for tree in objective['worktrees']:
            tree['color'] = '#8b949e'
    for objective in data['objectives']:
        if objective['id'] not in data['focused']:
            continue
        for index, tree in enumerate(objective['worktrees']):
            tree['color'] = objective['palette'][index] if index < len(objective['palette']) else _color(data, objective)


def _focus(data, objective, action):
    focused = data['focused']
    slot = action.get('slot')
    if slot is not None:
        if type(slot) is not int or not 0 <= slot < FOCUS_SLOTS:
            raise ValueError('Choose a focus slot from 1 to 5')
    elif objective['id'] in focused:
        return
    elif action.get('replace') in focused and action.get('replace'):
        slot = focused.index(action['replace'])
    else:
        slot = next((i for i in range(FOCUS_SLOTS) if i >= len(focused) or not focused[i]), None)
        if slot is None:
            raise ValueError('Choose which of the five focus slots to replace')
    if objective['id'] in focused:
        focused.remove(objective['id'])
    else:
        # An available slot absorbs the shift before any focused work is parked.
        vacancy = next((i for i in range(slot, len(focused)) if not focused[i]), None)
        if vacancy is not None:
            focused.pop(vacancy)
    focused.extend([None] * max(0, slot - len(focused)))
    focused.insert(slot, objective['id'])
    del focused[FOCUS_SLOTS:]
    _slot_colors(data)


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
    data['slot_palettes'] = deepcopy(PALETTES)
    folder = directory(root, workspace_id)
    for objective in data['objectives']:
        for field in ('shared_assets', 'archived_assets', 'asset_shelf'):
            objective.setdefault(field, [])
        for tree in objective['worktrees']:
            # Older registries may only store the shortcut path. Match native
            # sessions launched through either spelling without rewriting it.
            tree['resolved_path'] = str(Path(tree['path']).resolve())
        for resource in objective['resources']:
            if resource['kind'] not in {'document', 'notebook'}:
                continue
            try:
                resource['content'] = document(folder, resource)
            except (OSError, ValueError) as exc:
                resource['error'] = str(exc)
        for task in _tasks(objective):
            task['checklist'] = task_checklists.counts(_task_body(folder, objective, task))
            task['recurrence_state'] = task_cycles.state(task)
    return data


def _task_body(folder, objective, task):
    if not task.get('document_id'):
        return ''
    resource = _find(objective['resources'], task['document_id'])
    if not resource or resource.get('kind') != 'document':
        raise ValueError('Task details document is unavailable')
    content = document(folder, resource)
    if not task.get('tab_id'):
        return content['body']
    tab = _find(content['tabs'], task['tab_id'])
    if tab is None:
        raise ValueError('Task details tab is unavailable')
    return tab['body']


def _settle_tasks(folder, objective):
    task_cycles.validate_tree([t | {'parent_id':parent['id'] if t is not parent else None}
                              for parent in objective['tasks'] for t in [parent, *parent['children']]])
    for parent in objective['tasks']:
        for task in [*parent['children'], parent]:
            if task.get('done') and task_checklists.counts(_task_body(folder, objective, task))['pending']:
                _set_task_status(task, 'todo')
            if task is parent and task['children']:
                status = _children_status(task['children'])
                if status == 'done' and task_checklists.counts(_task_body(folder, objective, task))['pending']:
                    status = 'in_progress'
                if parent.get('status') != 'in_progress' or status == 'done':
                    _set_task_status(parent, status)
            if task.get('done'):
                task_cycles.completed(task)
            else:
                task_cycles.reopened(task)


def refresh_recurring(root, workspace_id, *, now=None):
    """Reconcile only explicit schedules and completion claims contradicted by Markdown."""
    folder = directory(root, workspace_id)
    with objective_store.lock(folder):
        preview = objective_store.read(folder)
        candidates = any(t.get('done') and isinstance(t.get('recurrence'), dict) and (task_cycles.ready(t, now=now)
            or not t.get('recurrence_next_due')
            or any(task_checklists.counts(_task_body(folder, o, item))['pending'] for item in [t,*t['children']]))
            for o in preview['objectives'] for t in _tasks(o))
    if not candidates:
        return False
    with workspace_identity.operation_lease(root, workspace_id), objective_store.lock(folder, write=True):
        data = objective_store.read(folder)
        before = deepcopy(data)
        for objective in data['objectives']:
            if not any(task.get('done') and isinstance(task.get('recurrence'), dict) and
                       (not task.get('recurrence_next_due') or task_cycles.ready(task, now=now) or
                        any(task_checklists.counts(_task_body(folder, objective, item))['pending'] for item in [task,*task['children']]))
                       for task in _tasks(objective)):
                continue
            for task in _tasks(objective):
                branch = [task, *task['children']]
                if not task.get('done') or not task_cycles.ready(task, now=now) or any(task_checklists.counts(_task_body(folder, objective, item))['pending'] for item in branch):
                    continue
                # Read every affected file before writing any of them. Reset
                # only this branch's tabs, retaining all unrelated content.
                edits = {}
                for item in branch:
                    if not item.get('document_id'):
                        continue
                    resource = _find(objective['resources'], item['document_id'])
                    target = _owned_path(folder, resource)
                    if target not in edits:
                        edits[target] = assistant_documents.unpack(target.read_bytes())
                    owner, body, tabs = edits[target]
                    if item.get('tab_id'):
                        if not any(meta['id'] == item['tab_id'] for meta, _ in tabs):
                            raise ValueError('Task details tab is unavailable')
                        tabs = [(meta, task_checklists.reset(text) if meta['id'] == item['tab_id'] else text) for meta, text in tabs]
                    else:
                        body = task_checklists.reset(body)
                    edits[target] = owner, body, tabs
                for target, content in edits.items():
                    assistant_records.atomic_bytes(target, assistant_documents.pack(*content))
                task['due'] = task.pop('recurrence_next_due')
                for item in branch:
                    _set_task_status(item, 'todo')
                    task_cycles.reopened(item)
            _settle_tasks(folder, objective)
        if data != before:
            objective_store.save(folder, data)
            return True
    return False


def _metadata(identifier_, title, parent=None):
    return {'schema': 2, 'id': identifier_, 'type': 'note', 'title': title,
            'created': date.today().isoformat(), 'updated': date.today().isoformat(),
            **({'parent': parent} if parent else {})}


def _write_document(folder, resource, body='', tabs=None):
    target = _owned_path(folder, resource)
    assistant_records.atomic_bytes(target, assistant_documents.pack(
        _metadata(resource['id'], resource['title']), body, tabs or []))


def _sublink_rows(resource):
    for item in resource.get('sublinks', []):
        yield item
        yield from _sublink_rows(item)


def _link_fields(action, depth=0, seen=None):
    result = {}
    if 'title' in action:
        result['title'] = _text(action['title'])
    if 'url' in action:
        url = _text(action['url'], 'URL', 4096)
        parsed = urlparse(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc or any(ord(c) < 32 or ord(c) == 127 for c in url):
            raise ValueError('Use a full http or https URL')
        result['url'] = url
    if 'tldr' in action:
        text = action['tldr']
        if not isinstance(text, str) or len(text) > 8192 or '\x00' in text:
            raise ValueError('TL;DR must be text up to 8192 characters')
        result['tldr'] = text
    if 'metadata' in action:
        metadata = action['metadata']
        if not isinstance(metadata, dict) or len(metadata) > 50 or any(not isinstance(k, str) or not k.strip() or len(k) > 80 for k in metadata):
            raise ValueError('Metadata must contain up to 50 named properties')
        try:
            encoded = json.dumps(metadata, allow_nan=False)
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError('Metadata must contain JSON values') from exc
        if len(encoded) > 16384:
            raise ValueError('Metadata must be at most 16 KB')
        result['metadata'] = deepcopy(metadata)
    if 'sublinks' in action:
        rows = action['sublinks']
        if not isinstance(rows, list) or depth >= 4 and rows:
            raise ValueError('Sublinks support up to four nested levels')
        seen = set() if seen is None else seen
        result['sublinks'] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('Choose a sublink title and URL')
            sid = row.get('id') or identifier()
            if not isinstance(sid, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', sid) or sid in seen:
                raise ValueError('Sublink IDs must be unique')
            seen.add(sid)
            if len(seen) > 100:
                raise ValueError('A link supports up to 100 sublinks')
            result['sublinks'].append({'id': sid, **_link_fields({**row, 'title':row.get('title'), 'url':row.get('url')}, depth+1, seen)})
    return result


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
        relative = _objective_dir(folder, objective).relative_to(folder) / filename
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
        if file_root not in [folder.resolve(), _objective_dir(folder, objective).resolve(), *(Path(t['path']).resolve() for t in objective['worktrees'])]:
            raise ValueError('File folder must belong to this objective')
        target = (file_root / str(action.get('path', ''))).resolve()
        if not target.is_relative_to(file_root) or not target.is_file():
            raise ValueError('Choose an existing objective file')
        item.update(file_root=str(file_root), path=target.relative_to(file_root).as_posix())
    elif kind == 'link':
        item.update(_link_fields({**action, 'url': action.get('url')}))
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
    with workspace_identity.operation_lease(root, workspace_id), objective_store.lock(folder, write=True):
        data = load(root, workspace_id, _locked=True)
        if expected is not None and data['revision'] != expected:
            raise ValueError('Objectives changed elsewhere. Refresh and retry.')
        data.pop('revision')
        operation = action.get('type')
        objective = _find(data['objectives'], action.get('objective_id'))
        if operation == 'terminal':
            role = action.get('main')
            if role is not None and (not isinstance(role, str) or role not in {'workflow', 'objective'}):
                raise ValueError('Choose a workflow or Objective main terminal')
            targets = ('task_id', 'resource_id', 'tab_id', 'sub_link_id', 'file', 'folder', 'view')
            if role and any(action.get(field) for field in targets):
                raise ValueError('A main terminal cannot have another target')
            name = _text(action.get('session_id'), 'Terminal identity')
            previous = data['terminal_links'].get(name, {})
            proposed = role or ('objective' if objective and not any(action.get(field) for field in targets) else None)
            if previous.get('main') and (previous['main'] != proposed
                    or previous.get('objective_id') != (None if proposed == 'workflow' else action.get('objective_id'))):
                raise ValueError('Main terminals have a fixed workflow or Objective context')
        if operation == 'terminal-policy':
            enabled = action.get('task_terminals')
            if not isinstance(enabled, bool):
                raise ValueError('Choose whether each task gets its own terminal')
            data['task_terminals'] = enabled
        elif operation == 'create':
            if len(data['objectives']) >= 100:
                raise ValueError('An objective workspace supports up to 100 saved objectives')
            objective = {'id': identifier(), 'name': _text(action.get('name'), limit=80),
                         'purpose': str(action.get('purpose', ''))[:4096], 'worktrees': [], 'resources': [], 'tasks': [],
                         'palette': [], 'color': '#8b949e'}
            data['objectives'].append(objective)
            data['enabled'] = True
            _focus(data, objective, action)
            (folder / 'objectives' / objective['id']).mkdir(parents=True, exist_ok=True)
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
        elif operation == 'terminal' and action.get('main') == 'workflow':
            if action.get('objective_id'):
                raise ValueError('A workflow main terminal belongs to the workspace')
            for other, link in data['terminal_links'].items():
                if other != name and link.get('main') == 'workflow':
                    link.clear()
                    link['view'] = 'workflow'
            data['terminal_links'][name] = {'main': 'workflow'}
        elif operation == 'terminal' and action.get('view') == 'workflow':
            if action.get('objective_id') or any(action.get(field) for field in targets if field != 'view'):
                raise ValueError('Choose only the workflow context for this terminal')
            data['terminal_links'][name] = {'view': 'workflow'}
        elif objective is None:
            raise ValueError('Objective not found')
        elif operation == 'focus':
            _focus(data, objective, action)
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
        elif operation in {'asset-star', 'asset-bucket'}:
            _asset_bucket(folder, objective, action)
        elif operation == 'suggest-assignment':
            _suggest_assignment(folder, data, objective, action)
        elif operation in {'accept-assignment', 'reject-assignment'}:
            suggestion = _find(objective.get('assignment_suggestions', []), action.get('suggestion_id'))
            if not suggestion or suggestion['status'] != 'pending':
                raise ValueError('This suggestion is no longer pending')
            if operation == 'reject-assignment':
                suggestion['status'] = 'rejected'
            else:
                asset = _assignment_asset(folder, objective, suggestion['asset'])
                if any(_covers(row, asset) for row in objective.get('archived_assets', [])):
                    raise ValueError('Restore the archived asset before accepting its assignment')
                owner, destination = _assignment_destination(data, objective, suggestion)
                _assign_asset(folder, data, objective, asset, owner, destination)
                suggestion['status'] = 'accepted'
        elif operation == 'asset-assign':
            asset = _assignment_asset(folder, objective, action)
            owner, destination = _assignment_destination(data, objective, action)
            _assign_asset(folder, data, objective, asset, owner, destination)
        elif operation == 'asset-trash':
            _trash_asset(folder, objective, action)
        elif operation == 'scope':
            resource = _find(objective['resources'], action.get('resource_id'))
            if not resource:
                raise ValueError('Resource not found')
            tree = action.get('worktree') or None
            if tree and not _find(objective['worktrees'], tree):
                raise ValueError('Worktree must belong to this objective')
            resource['worktree'] = tree
        elif operation == 'link-update':
            resource = _find(objective['resources'], action.get('resource_id'))
            if not resource or resource['kind'] != 'link':
                raise ValueError('Choose an external link in this objective')
            target = _find(list(_sublink_rows(resource)), action.get('sub_link_id')) if action.get('sub_link_id') else resource
            if target is None:
                raise ValueError('Sublink not found')
            target.update(_link_fields(action))
            if 'sublinks' in action:
                resource.update(_link_fields({'sublinks':resource.get('sublinks', [])}))
                remaining = {r['id'] for r in _sublink_rows(resource)}
                for link in data['terminal_links'].values():
                    if link.get('resource_id') == resource['id'] and link.get('sub_link_id') and link['sub_link_id'] not in remaining:
                        link.pop('sub_link_id')
                _prune_assets(objective, lambda a: a.get('resource_id') == resource['id'] and a.get('sub_link_id') and a['sub_link_id'] not in remaining)
        elif operation == 'link-sublink':
            resource = _find(objective['resources'], action.get('resource_id'))
            if not resource or resource['kind'] != 'link':
                raise ValueError('Choose an external link in this objective')
            updated = deepcopy(resource)
            target = _find(list(_sublink_rows(updated)), action.get('parent_id')) if action.get('parent_id') else updated
            if target is None:
                raise ValueError('Parent sublink not found')
            target.setdefault('sublinks', []).append({'id':identifier(), **_link_fields({**action, 'title':action.get('title'), 'url':action.get('url')})})
            resource.update(_link_fields({'sublinks':updated['sublinks']}))
        elif operation == 'link-remove-sublink':
            resource = _find(objective['resources'], action.get('resource_id'))
            if not resource or resource['kind'] != 'link':
                raise ValueError('Choose an external link in this objective')
            target = _find(list(_sublink_rows(resource)), action.get('sub_link_id'))
            if target is None:
                raise ValueError('Sublink not found')
            removed = {target['id'], *(r['id'] for r in _sublink_rows(target))}
            for parent in [resource, *_sublink_rows(resource)]:
                if 'sublinks' in parent:
                    parent['sublinks'] = [r for r in parent['sublinks'] if r['id'] not in removed]
            for link in data['terminal_links'].values():
                if link.get('resource_id') == resource['id'] and link.get('sub_link_id') in removed:
                    link.pop('sub_link_id')
            _prune_assets(objective, lambda a: a.get('resource_id') == resource['id'] and a.get('sub_link_id') in removed)
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
            task = {'id': identifier(), 'title': _text(action.get('title')), 'done': False, 'status': 'todo', 'due': _date(action.get('due')), 'children': []}
            if 'recurrence' in action:
                task_cycles.validate(action['recurrence'], task.get('due'))
                task['recurrence'] = deepcopy(action['recurrence'])
            task_cycles.configure(task, action)
            task_cycles.validate_tree([*(_t | {'parent_id':p['id'] if _t is not p else None} for p in objective['tasks'] for _t in [p, *p['children']]), task | {'parent_id':parent['id'] if parent else None}])
            _task_details(folder, objective, task, parent, action.get('document_id') or (parent or {}).get('document_id'))
            (parent['children'] if parent else objective['tasks']).append(task)
        elif operation in {'task-update', 'task-asset', 'task-remove-asset'}:
            task = _find(_tasks(objective), action.get('task_id'))
            if task is None:
                raise ValueError('Task not found')
            previous = deepcopy(task)
            if 'due' in action:
                task['due'] = _date(action['due'])
            if 'recurrence' in action:
                task_cycles.validate(action['recurrence'], task.get('due'))
                task['recurrence'] = deepcopy(action['recurrence'])
            task_cycles.configure(task, action, previous)
            task_cycles.validate_tree([t | {'parent_id':p['id'] if t is not p else None} for p in objective['tasks'] for t in [p, *p['children']]])
            if operation == 'task-asset':
                if 'choose_icon' in action and type(action['choose_icon']) is not bool:
                    raise ValueError('Icon selection must be a boolean')
                asset = _task_asset(folder, objective, action)
                implicit = {'resource_id':task['document_id'], 'tab_id':task['tab_id']}
                if asset != implicit:
                    attached = _put_asset(task, 'assets', asset, 128)
                if asset.get('folder'):
                    _put_asset(objective, 'asset_shelf', asset)
                if 'archived_assets' in objective:
                    objective['archived_assets'] = [row for row in objective['archived_assets'] if _asset_target(row) != asset]
                if action.get('choose_icon'):
                    task['icon_asset_id'] = 'details' if asset == implicit else attached['id']
            elif operation == 'task-remove-asset':
                asset_id = action.get('asset_id')
                if not _find(task.get('assets', []), asset_id):
                    raise ValueError('Task asset not found')
                task['assets'] = [a for a in task['assets'] if a['id'] != asset_id]
                if task.get('icon_asset_id') == asset_id:
                    task.pop('icon_asset_id')
            if 'status' in action or 'done' in action:
                if 'done' in action and type(action['done']) is not bool:
                    raise ValueError('Task completion must be a boolean')
                status = action.get('status', 'done' if action.get('done') else 'todo')
                if not isinstance(status, str) or status not in {'todo', 'in_progress', 'done', 'paused', 'wont_do'}:
                    raise ValueError("Choose Undo, In progress, Completed, Paused or Won't do")
                if 'done' in action and action['done'] != (status == 'done'):
                    raise ValueError('Task status and completion must agree')
                if status == 'done':
                    for item in [task, *task['children']]:
                        task_checklists.require_complete(_task_body(folder, objective, item))
                _set_task_status(task, status)
                if status != 'in_progress':
                    for child in task['children']:
                        _set_task_status(child, status)
                parent = next((p for p in objective['tasks'] if task in p['children']), None)
                if parent:
                    children = parent['children']
                    _set_task_status(parent, _children_status(children))
            if 'title' in action:
                task['title'] = _text(action['title'])
            if 'icon_asset_id' in action:
                icon_id = action['icon_asset_id']
                if icon_id != 'details' and not _find(task.get('assets', []), icon_id):
                    raise ValueError('Choose an icon from this task’s assets')
                task['icon_asset_id'] = icon_id
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
            if action.get('sub_link_id'):
                if not resource or resource['kind'] != 'link' or not _find(list(_sublink_rows(resource)), action['sub_link_id']):
                    raise ValueError('Sublink not found')
            linked_file = action.get('file')
            linked_folder = action.get('folder')
            view = action.get('view')
            task_id = action.get('task_id')
            if task_id and not _find(_tasks(objective), task_id):
                raise ValueError('Task not found')
            if view is not None and view not in ('tasks', 'objective'):
                raise ValueError('Choose an objective view')
            for field in ['file', 'folder']:
                if action.get(field) is not None and not isinstance(action[field], dict):
                    raise ValueError('Choose a file or folder target')
            if sum(bool(target) for target in [resource, linked_file, linked_folder, view, task_id]) > 1:
                raise ValueError('Choose one terminal target')
            if linked_file or linked_folder:
                allowed = [folder.resolve(), _objective_dir(folder, objective).resolve(), *(Path(t['path']).resolve() for t in objective['worktrees'])]
                linked = linked_file or linked_folder
                if not isinstance(linked.get('root'), str) or not isinstance(linked.get('path', ''), str):
                    raise ValueError('Choose a file or folder target')
                file_root = Path(linked.get('root', '')).resolve()
                if file_root not in allowed:
                    raise ValueError('File folder must belong to this objective')
                relative = Path(linked.get('path', ''))
                target = (file_root / relative).resolve()
                if not target.is_relative_to(file_root) or not (target.is_file() if linked_file else target.is_dir()):
                    raise ValueError('Choose a file or folder in this objective')
                normalized = {'root':str(file_root), 'path':target.relative_to(file_root).as_posix()}
                if linked_file:
                    linked_file = normalized
                else:
                    linked_folder = normalized
            data['terminal_links'][name] = {'objective_id': objective['id'], 'resource_id': action.get('resource_id'),
                                          'tab_id': action.get('tab_id'), 'file': linked_file}
            if action.get('sub_link_id'):
                data['terminal_links'][name]['sub_link_id'] = action['sub_link_id']
            if linked_folder:
                data['terminal_links'][name]['folder'] = linked_folder
            if view:
                data['terminal_links'][name]['view'] = view
            if task_id:
                # A task owns one primary terminal. Replacing that association
                # leaves the former terminal alive and independently usable.
                for other, link in data['terminal_links'].items():
                    if other != name and link.get('objective_id') == objective['id'] and link.get('task_id') == task_id:
                        link.pop('task_id', None)
                        link['view'] = 'tasks'
                data['terminal_links'][name]['task_id'] = task_id
            elif not any([resource, linked_file, linked_folder, view]):
                for other, link in data['terminal_links'].items():
                    if other != name and link.get('objective_id') == objective['id'] and link.get('main') == 'objective':
                        link.pop('main', None)
                        link['view'] = 'tasks'
                data['terminal_links'][name]['main'] = 'objective'
        elif operation == 'remove-resource':
            resource_id = action.get('resource_id')
            if any(t['document_id'] == resource_id for p in objective['tasks'] for t in [p, *p['children']]):
                raise ValueError('A task still needs this document')
            objective['resources'] = [r for r in objective['resources'] if r['id'] != resource_id]
            _prune_assets(objective, lambda a: a.get('resource_id') == resource_id)
            # Preserve owned files so unlinking never destroys user content.
        else:
            raise ValueError('Unsupported objective action')
        if objective and operation in {'task', 'task-update', 'document'}:
            _settle_tasks(folder, objective)
        objective_store.save(folder, data)
    return payload(root, workspace_id)
