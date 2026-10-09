"""Client-defined, one-level presentation groups for existing asset references."""
from copy import deepcopy
import json
import uuid


def _key(item):
    return json.dumps(item, sort_keys=True, separators=(',', ':'))


def _target(item):
    if not isinstance(item, dict):
        raise ValueError('Choose an asset reference')
    if set(item) == {'folder'}:
        folder = item['folder']
        if isinstance(folder, dict) and set(folder) == {'root', 'path'} and all(isinstance(v, str) and v for v in folder.values()):
            return item
    elif (item.get('resource_id') and set(item) <= {'resource_id', 'tab_id', 'sub_link_id'}
          and all(isinstance(v, str) and v for v in item.values()) and not ('tab_id' in item and 'sub_link_id' in item)):
        return item
    raise ValueError('Groups contain asset references only, with one level of children')


def validate(objective):
    groups, order = objective.get('asset_groups', []), objective.get('asset_order', [])
    if not isinstance(groups, list) or len(groups) > 128 or not isinstance(order, list) or len(order) > 4096:
        raise ValueError('Invalid asset group layout')
    ids, members = set(), set()
    for group in groups:
        if (not isinstance(group, dict) or not isinstance(group.get('id'), str) or not group['id']
                or group['id'] in ids or not isinstance(group.get('title'), str) or not group['title'].strip()
                or len(group['title']) > 120 or not isinstance(group.get('assets'), list) or len(group['assets']) > 512):
            raise ValueError('Asset groups need unique ids, names and a flat asset list')
        ids.add(group['id'])
        for asset in group['assets']:
            identity = _key(_target(asset))
            if identity in members:
                raise ValueError('An asset can belong to only one group')
            members.add(identity)
    seen = set()
    for item in order:
        if isinstance(item, dict) and set(item) == {'group_id'}:
            if not isinstance(item['group_id'], str) or item['group_id'] not in ids:
                raise ValueError('Asset group not found')
        else:
            _target(item)
            if _key(item) in members:
                raise ValueError('Grouped assets must stay inside their group')
        if _key(item) in seen:
            raise ValueError('Asset order must not repeat entries')
        seen.add(_key(item))


def _tasks(rows):
    for task in rows:
        yield task
        yield from _tasks(task.get('children', []))


def _catalog(objective):
    rows = [{'resource_id':r['id']} for r in objective['resources'] if not r.get('task_document')]
    rows += [{'folder':{'root':t.get('resolved_path', t['path']), 'path':'.'}} for t in objective['worktrees']]
    rows += [a for field in ('shared_assets', 'archived_assets', 'asset_shelf') for a in objective.get(field, [])]
    rows += [a for task in _tasks(objective['tasks']) for a in task.get('assets', [])]
    rows += [a for group in objective.get('asset_groups', []) for a in group['assets']]
    targets = [{k:v for k,v in row.items() if k != 'id'} for row in rows]
    return list({_key(row):row for row in targets}.values())


def _group(objective, group_id):
    group = next((g for g in objective.get('asset_groups', []) if g['id'] == group_id), None)
    if group is None:
        raise ValueError('Asset group not found')
    return group


def _owner(objective, asset):
    return next((g for g in objective.get('asset_groups', []) if asset in g['assets']), None)


def _root_order(objective):
    members = {_key(a) for g in objective.get('asset_groups', []) for a in g['assets']}
    candidates = [{'group_id':g['id']} for g in objective.get('asset_groups', [])]
    candidates += [a for a in _catalog(objective) if _key(a) not in members]
    remaining = {_key(a):a for a in candidates}
    result = []
    for item in objective.get('asset_order', []):
        if _key(item) in remaining:
            result.append(remaining.pop(_key(item)))
    return result + list(remaining.values())


def mutate(objective, action, asset=None):
    operation = action['type']
    order = _root_order(objective)
    groups = objective.setdefault('asset_groups', [])
    if operation == 'asset-group-create':
        if len(groups) >= 128:
            raise ValueError('This Objective supports up to 128 asset groups')
        title = action.get('title')
        if not isinstance(title, str) or not title.strip() or len(title) > 120 or '\x00' in title:
            raise ValueError('Group name must contain 1–120 characters')
        group = {'id':uuid.uuid4().hex, 'title':title.strip(), 'assets':[]}
        position = order.index(asset) if asset in order else len(order)
        groups.append(group)
        order.insert(position, {'group_id':group['id']})
    elif operation in {'asset-group-rename', 'asset-group-ungroup'}:
        group = _group(objective, action.get('group_id'))
        if operation == 'asset-group-rename':
            title = action.get('title')
            if not isinstance(title, str) or not title.strip() or len(title) > 120 or '\x00' in title:
                raise ValueError('Group name must contain 1–120 characters')
            group['title'] = title.strip()
        else:
            order = [child for item in order for child in (group['assets'] if item == {'group_id':group['id']} else [item])]
            groups.remove(group)
    elif operation == 'asset-group-member':
        group = _group(objective, action['group_id']) if action.get('group_id') else None
        if _owner(objective, asset) is group:
            return
    elif operation == 'asset-order':
        item, relative = action.get('item'), action.get('relative')
        if action.get('position') not in {'before', 'after'} or item == relative:
            raise ValueError('Choose two different assets and an order')
        if isinstance(item, dict) and set(item) == {'group_id'}:
            _group(objective, item['group_id'])
            owner = None
        else:
            _target(item)
            owner = _owner(objective, item)
        rows = owner['assets'] if owner else order
        if item not in rows or relative not in rows:
            raise ValueError('Reorder entries within the same group or asset list')
        rows.remove(item)
        rows.insert(rows.index(relative) + (action['position'] == 'after'), item)
    else:
        raise ValueError('Unsupported asset group action')
    if operation in {'asset-group-create', 'asset-group-member'}:
        _target(asset)
        for old in groups:
            old['assets'] = [a for a in old['assets'] if a != asset]
        order = [item for item in order if item != asset]
        if group:
            if len(group['assets']) >= 512:
                raise ValueError('This group supports up to 512 assets')
            group['assets'].append(deepcopy(asset))
        else:
            order.append(deepcopy(asset))
    objective['asset_order'] = order
    validate(objective)


def prune(objective, remove):
    for group in objective.get('asset_groups', []):
        group['assets'] = [a for a in group['assets'] if not remove(a)]
    if 'asset_order' in objective:
        objective['asset_order'] = [a for a in objective['asset_order'] if 'group_id' in a or not remove(a)]
