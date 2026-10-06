"""Discover workspace-owned Objective files; keep only UI state in .lab.

Reads never migrate. Legacy registries remain readable until an explicit
migration or a successful Objective mutation converts them without editing
documents, notebooks or Assistant references.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import fcntl
import math
from pathlib import Path
import re

from lab import assistant_records, storage

LAYOUT = 'objective-files-v1'
MANIFEST = '.objective.json'


def state_file(folder):
    return folder / '.lab' / 'objectives-state.json'


def legacy_file(folder):
    return folder / '.lab' / 'objectives.json'


@contextmanager
def lock(folder, *, write=False):
    target = folder / '.lab' / 'state' / 'objectives.lock'
    if not write and not target.exists():
        yield
        return
    if write:
        target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('a' if write else 'r') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX if write else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _json(target):
    try:
        value = storage.read_json(target)
        if not isinstance(value, dict):
            raise ValueError('Expected a JSON object')
        return value
    except (OSError, ValueError) as exc:
        raise ValueError(f'{target}: {exc}') from exc


def _validate(value, target):
    """Validate editable file structure before any metadata can be overwritten."""
    value = deepcopy(value)
    oid = value.get('id')
    if not isinstance(oid, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', oid) or oid in {'.', '..'}:
        raise ValueError(f'{target}: Objective needs a stable id')
    if type(value.get('version', 1)) is not int or value.get('version', 1) != 1:
        raise ValueError(f'{target}: Unsupported Objective file version')
    if not isinstance(value.get('name'), str) or not value['name'].strip():
        raise ValueError(f'{target}: Objective needs a name')
    value.setdefault('purpose', '')
    for field in ('resources', 'worktrees', 'tasks', 'shared_assets', 'archived_assets', 'asset_shelf'):
        rows = value.setdefault(field, [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError(f'{target}: {field} must be an array of objects')
    for field in ('trashed_assets', 'assignment_suggestions'):
        rows = value.get(field, [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError(f'{target}: {field} must be an array of objects')
    suggestions = value.get('assignment_suggestions', [])
    if len({row.get('id') for row in suggestions if isinstance(row.get('id'), str)}) != len(suggestions):
        raise ValueError(f'{target}: Assignment suggestions need unique ids')
    for row in suggestions:
        destination = row.get('destination')
        if (not isinstance(row.get('asset'), dict) or not isinstance(destination, dict)
                or destination.get('bucket') not in {'task', 'objective'}
                or row.get('status') not in {'pending', 'accepted', 'rejected', 'superseded'}
                or not isinstance(row.get('reason'), str)):
            raise ValueError(f'{target}: Invalid assignment suggestion')
    for field in ('resources', 'worktrees', 'tasks'):
        rows = value[field]
        if any(not isinstance(row.get('id'), str) or not row['id'] for row in rows) or len({r['id'] for r in rows}) != len(rows):
            raise ValueError(f'{target}: {field} need unique ids')
    for tree in value['worktrees']:
        if not isinstance(tree.get('path'), str):
            raise ValueError(f'{target}: Worktree needs a path')
    for resource in value['resources']:
        if resource.get('kind') not in {'file', 'document', 'notebook', 'link', 'assistant'} or not isinstance(resource.get('title'), str):
            raise ValueError(f'{target}: Resource needs a supported kind and title')
    task_ids = set()
    for parent in value['tasks']:
        children = parent.setdefault('children', [])
        if not isinstance(children, list) or any(not isinstance(child, dict) for child in children):
            raise ValueError(f'{target}: Task children must be an array')
        for task in [parent, *children]:
            if not isinstance(task.get('id'), str) or not task['id'] or task['id'] in task_ids:
                raise ValueError(f'{target}: Tasks need unique ids')
            task_ids.add(task['id'])
            if not isinstance(task.get('title'), str):
                raise ValueError(f'{target}: Task needs a title')
            task.setdefault('children', [])
            task.setdefault('done', False)
            if 'status' in task:
                if not isinstance(task['status'], str) or task['status'] not in {'todo', 'in_progress', 'done', 'paused', 'wont_do'}:
                    raise ValueError(f'{target}: Task status must be todo, in_progress, done, paused or wont_do')
                task['done'] = task['status'] == 'done'
            if 'completed_at' in task and (type(task['completed_at']) not in {int, float}
                    or not math.isfinite(task['completed_at']) or task['completed_at'] <= 0):
                raise ValueError(f'{target}: Task completion time must be a positive timestamp')
    return value


def _manifest(folder, objective):
    """Convert runtime paths to paths relative to the containing Objective."""
    value = deepcopy(objective)
    owner = Path(value.pop('path', str(folder / 'objectives' / value['id'])))
    for field in ('manifest_path', 'palette', 'color'):
        value.pop(field, None)
    value['version'] = 1
    for tree in value.get('worktrees', []):
        tree.pop('color', None)
        tree.pop('resolved_path', None)
    for resource in value.get('resources', []):
        resource.pop('content', None)
        resource.pop('error', None)
        if resource.get('kind') in {'document', 'notebook'}:
            target = (folder / resource['path']).resolve()
            if not target.is_relative_to(owner.resolve()):
                raise ValueError('Owned documents must stay inside their Objective folder')
            resource['path'] = target.relative_to(owner.resolve()).as_posix()
    return value


def _runtime(folder, value, target, *, legacy=False):
    value = _validate(value, target)
    owner = folder / 'objectives' / value['id'] if legacy else target.parent
    value['path'] = str(owner)
    value['manifest_path'] = str(target) + ('#objective=' + value['id'] if legacy else '')
    for resource in value['resources']:
        if resource.get('kind') not in {'document', 'notebook'}:
            continue
        relative = resource.get('path')
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise ValueError(f'{target}: Owned document path must be relative')
        document = (folder if legacy else owner) / relative
        if not document.resolve().is_relative_to(owner.resolve()):
            raise ValueError(f'{target}: Owned document escapes its Objective folder')
        resource['path'] = document.relative_to(folder).as_posix()
    return value


def read(folder):
    state = _json(state_file(folder)) if state_file(folder).is_file() else {}
    if state.get('storage_layout') not in {None, LAYOUT}:
        raise ValueError('Unsupported Objective storage layout')
    legacy = legacy_file(folder)
    legacy_data = _json(legacy) if state.get('storage_layout') != LAYOUT and legacy.is_file() else None
    data = deepcopy(legacy_data or state)
    rows = data.get('objectives', []) if legacy_data is not None else []
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f'{legacy}: objectives must be an array of objects')
    found = {}
    for row in rows:
        obj = _runtime(folder, row, legacy, legacy=True)
        if obj['id'] in found:
            raise ValueError(f'{legacy}: Duplicate Objective id {obj["id"]}')
        found[obj['id']] = obj
    boundary = (folder / 'objectives').resolve()
    if not boundary.is_relative_to(folder.resolve()):
        raise ValueError('Objective folders must belong to this workspace')
    for target in sorted((folder / 'objectives').glob('*/' + MANIFEST)):
        if not target.resolve().is_relative_to(boundary) or target.is_symlink():
            raise ValueError(f'{target}: Objective manifest must belong to this workspace')
        obj = _runtime(folder, _json(target), target)
        previous = found.get(obj['id'])
        if previous:
            # A partially completed migration can be retried, but a native
            # file with conflicting content must never be silently replaced.
            if legacy_data is None or _manifest(folder, obj) != _manifest(folder, previous) or obj['path'] != previous['path']:
                raise ValueError(f'{target}: Duplicate or conflicting Objective id {obj["id"]}')
        else:
            found[obj['id']] = obj
    order = data.get('order', list(found))
    if not isinstance(order, list) or any(not isinstance(oid, str) for oid in order):
        raise ValueError('Objective order must be an array of ids')
    ordered = list(dict.fromkeys([oid for oid in order if oid in found] + list(found)))
    focused = data.get('focused', ordered[:5])
    if not isinstance(focused, list) or len(focused) > 5 or any(oid is not None and not isinstance(oid, str) for oid in focused):
        raise ValueError('Objective focus must contain up to five ids')
    if len([oid for oid in focused if oid]) != len(set(oid for oid in focused if oid)):
        raise ValueError('Objective focus ids must be unique')
    data.update(version=1, enabled=bool(found) or bool(data.get('enabled')), order=ordered,
                focused=[oid if oid in found else None for oid in focused],
                objectives=[found[oid] for oid in ordered])
    links = data.setdefault('terminal_links', {})
    if not isinstance(links, dict) or any(not isinstance(link, dict) for link in links.values()):
        raise ValueError('Objective terminal links must be an object')
    # Adopt one legacy whole-Objective terminal as its main. Other saved
    # sessions remain usable; normalizing a read never writes or kills them.
    for oid in ordered:
        candidates = [(name, link) for name, link in links.items() if link.get('objective_id') == oid
                      and not any(link.get(field) for field in ('task_id', 'resource_id', 'file', 'folder', 'view'))]
        primary = next((name for name, link in candidates if link.get('main') == 'objective'),
                       candidates[0][0] if candidates else None)
        for name, link in candidates:
            if name == primary:
                link['main'] = 'objective'
            else:
                link.pop('main', None)
                link['view'] = 'tasks'
    workflow_main = False
    for link in links.values():
        if link.get('main') == 'workflow':
            if workflow_main:
                link.clear()
                link['view'] = 'workflow'
            workflow_main = True
    return data


def _state(data):
    value = deepcopy(data)
    for field in ('objectives', 'revision', 'slot_palettes'):
        value.pop(field, None)
    value.update(version=1, storage_layout=LAYOUT, order=[obj['id'] for obj in data['objectives']])
    return value


def _write_changed(target, value):
    if not target.is_file() or _json(target) != value:
        storage.write_json(target, value)


def migration(folder, *, apply=False):
    """Preflight every target; retry identical partial migrations safely."""
    data = read(folder)
    source = legacy_file(folder)
    pending = data.get('storage_layout') != LAYOUT and source.is_file()
    targets = [(Path(obj['path']) / MANIFEST, _manifest(folder, obj)) for obj in data['objectives']]
    for target, value in targets:
        if target.exists() and _manifest(folder, _runtime(folder, _json(target), target)) != value:
            raise ValueError(f'{target}: Existing Objective file conflicts with the legacy registry')
    backup = folder / '.lab' / 'objectives.legacy.json'
    if pending:
        raw = source.read_bytes()
        index = 1
        while backup.exists() and backup.read_bytes() != raw:
            backup = folder / '.lab' / f'objectives.legacy-{index}.json'
            index += 1
    report = {'migration_required': pending, 'objectives': len(targets),
              'manifests': [str(target) for target, _ in targets],
              'legacy_backup': str(backup) if pending else None, 'applied': False}
    if apply and pending:
        # Keep a byte-identical backup before publishing the new layout. The
        # marker is written last so interrupted conversion keeps legacy reads.
        if not backup.exists():
            assistant_records.atomic_bytes(backup, raw)
        for target, value in targets:
            _write_changed(target, value)
        storage.write_json(state_file(folder), _state(data))
        source.unlink()
        report['applied'] = True
    return report


def save(folder, data):
    # Mutations are already validated. Convert the original registry first;
    # never use partially mutated JSON as a legacy migration source.
    migration(folder, apply=True)
    for objective in data['objectives']:
        target = Path(objective.get('path', folder / 'objectives' / objective['id'])) / MANIFEST
        boundary = (folder / 'objectives').resolve()
        if not target.resolve().is_relative_to(boundary):
            raise ValueError('Objective file must belong to this workspace')
        value = _manifest(folder, objective)
        if not target.is_file() or _manifest(folder, _runtime(folder, _json(target), target)) != value:
            storage.write_json(target, value)
    _write_changed(state_file(folder), _state(data))
