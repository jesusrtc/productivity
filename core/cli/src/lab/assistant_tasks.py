"""Document-owned tasks, independent of the content-tab tree."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import uuid

from lab import assistant_documents as documents, assistant_records as records

FORMAT = 'document-tasks-v1'
STATUSES = {'not_started', 'in_progress', 'blocked', 'done', 'skipped', 'cancelled'}
CLOSED = {'done', 'skipped', 'cancelled'}
FIELDS = {'title','priority','status','done','tab_id','parent_id','due','owner','tldr',
          'scheduled','defer_until','recurrence','recurrence_anchor','group','waiting_on',
          'waiting_since','follow_up_at','last_follow_up_at','follow_up_channel',
          'reviewer','review_requested_at','executor','attributes','depends_on'}
LEGACY_STATUS = {'inbox':'not_started','ready':'not_started','waiting':'in_progress',
                 'ready_to_review':'in_progress','completed':'done'}


def now():
    return datetime.now(timezone.utc).isoformat()


def enabled(root):
    return records.manifest(root).get('task_format') == FORMAT


def validate(tasks, tab_ids):
    if not isinstance(tasks, list) or len(tasks) > 10000:
        raise ValueError('Tasks must be a list of at most 10000 items')
    by_id = {}
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get('id'), str) or not re.fullmatch(r'[A-Za-z0-9_-]+', task['id']) or task['id'] in by_id:
            raise ValueError('Each task needs a unique stable ID')
        if not isinstance(task.get('title'), str) or not task['title'].strip() or len(task['title']) > 2000:
            raise ValueError('Task titles must contain 1–2000 characters')
        if not isinstance(task.get('priority'),str) or task.get('priority') not in {'P0','P1','P2','P3'} or type(task.get('done',False)) is not bool:
            raise ValueError('Invalid task priority or completion')
        if not isinstance(task.get('status','not_started'),str) or task.get('status','not_started') not in STATUSES or task.get('status_override') is not None and (not isinstance(task['status_override'],str) or task['status_override'] not in {'in_progress','blocked'}):
            raise ValueError('Invalid task status')
        if task.get('parent_id') is not None and not isinstance(task['parent_id'], str):
            raise ValueError('Invalid task parent')
        if task.get('tab_id') is not None and (not isinstance(task['tab_id'], str) or task['tab_id'] not in tab_ids):
            raise ValueError('Linked tab is not in this document')
        for field in FIELDS - {'parent_id','tab_id','status','done'}:
            if field in task:
                records.validate_value(None, task, field, task[field])
        by_id[task['id']] = task
    for task in tasks:
        seen = {task['id']}
        parent = task.get('parent_id')
        while parent is not None:
            if parent not in by_id or parent in seen:
                raise ValueError('Invalid task parent or cycle')
            seen.add(parent)
            if len(seen) > 30:
                raise ValueError('Task nesting is limited to 30 levels')
            parent = by_id[parent].get('parent_id')


def normalize(tasks):
    tasks = deepcopy(tasks)
    children = {}
    for task in tasks:
        children.setdefault(task.get('parent_id'), []).append(task)
    # An explicit recursive argument lets the normalized tree be released
    # with its caller instead of being retained by a closure cycle.
    def visit(recurse, task):
        nested = [recurse(recurse, child) for child in children.get(task['id'], [])]
        status = task.get('status', 'done' if task.get('done') else 'not_started')
        if not nested:
            task.pop('status_override', None)
        elif all(item in CLOSED for item in nested):
            status = 'cancelled' if all(item == 'cancelled' for item in nested) else 'skipped' if all(item == 'skipped' for item in nested) else 'done'
            task.pop('status_override', None)
        elif task.get('status_override'):
            status = task['status_override']
        elif 'blocked' in nested:
            status = 'blocked'
        elif any(item != 'not_started' for item in nested):
            status = 'in_progress'
        else:
            status = 'not_started'
        task['status'] = status
        task['done'] = status in {'done','skipped'}
        return status
    for task in children.get(None, []):
        visit(visit, task)
    return tasks


def linked_tab(tasks, task):
    by_id = {item['id']:item for item in tasks}
    while task:
        if task.get('tab_id'):
            return task['tab_id']
        task = by_id.get(task.get('parent_id'))
    return None


def summary(tasks):
    tasks = normalize(tasks)
    parents = {task.get('parent_id') for task in tasks}
    leaves = [task for task in tasks if task['id'] not in parents]
    pending = [task for task in leaves if task['status'] not in CLOSED]
    def branches(recurse, task, status):
        return sum(recurse(recurse,child,status) for child in tasks if child.get('parent_id') == task['id']) or int(task['status'] == status)
    roots = [task for task in tasks if not task.get('parent_id')]
    status = None if not tasks else 'cancelled' if all(task['status'] == 'cancelled' for task in roots) else 'done' if not pending else 'blocked' if any(task['status'] == 'blocked' for task in tasks) else 'in_progress' if any(task['status'] != 'not_started' for task in tasks) else 'not_started'
    return {'status':status,'automatic_status':status,'tracked':bool(tasks),'derived':bool(tasks),
            'completed':sum(task['status'] in {'done','skipped'} for task in leaves), 'total':len(leaves),
            'pending':len(pending),'wip':sum(branches(branches,task,'in_progress') for task in roots),
            'blocked':sum(branches(branches,task,'blocked') for task in roots)}


def read(root, reference, *, record_rows=None):
    source, _, _ = records.resolve(root, reference, 'documents', record_rows=record_rows)
    source = documents.physical(source)
    raw = source.read_bytes()
    meta, body, tabs = documents.unpack(raw)
    if meta.get('task_format') != FORMAT:
        raise ValueError('Migrate this database with lab assistant migrate --document-tasks --apply first')
    validate(meta.get('tasks', []), {meta['id'], *(tab['id'] for tab,_ in tabs)})
    return source, raw, meta, body, tabs


def view(root, reference, *, record_rows=None):
    source, raw, meta, _, _ = read(root, reference, record_rows=record_rows)
    tasks = normalize(meta.get('tasks', []))
    return {'document_id':meta['id'],'path':source.relative_to(root).as_posix(),
            'revision':hashlib.sha256(raw).hexdigest(),'tasks':tasks,'summary':summary(tasks)}


def mutate(meta, tabs, values, task_id=None, delete=False):
    unknown = set(values) - FIELDS
    if unknown:
        raise ValueError('Unknown task fields: ' + ', '.join(sorted(unknown)))
    tasks = normalize(meta.get('tasks', []))
    if task_id:
        task = next((item for item in tasks if item['id'] == task_id), None)
        if task is None:
            raise ValueError('Task not found')
    else:
        task = {'id':'task_' + uuid.uuid4().hex,'title':'','status':'not_started','done':False,
                'priority':'P2','tab_id':None,'parent_id':None,'created':now()}
        tasks.append(task)
    parent = next((item for item in tasks if item['id'] == values.get('parent_id')),None)
    if parent and parent['status'] in {'in_progress','blocked'}:
        parent['status_override'] = parent['status']
    task.update({key:value for key,value in values.items() if key not in {'status','done'}})
    if isinstance(task.get('title'), str):
        task['title'] = task['title'].strip()
    status = values.get('status')
    if status is None and 'done' in values:
        if type(values['done']) is not bool:
            raise ValueError('Completion must be true or false')
        status = 'done' if values['done'] else 'not_started'
    if status is not None:
        if not isinstance(status,str) or status not in STATUSES:
            raise ValueError('Invalid task status')
        if 'done' in values and (status in {'done','skipped'}) != values['done']:
            raise ValueError('Conflicting status and completion')
        task['status'] = status
        if status in {'in_progress','blocked'}:
            nested = [item for item in tasks if item.get('parent_id') == task['id']]
            if nested and all(item['status'] in CLOSED for item in nested):
                raise ValueError('Reopen a subtask before starting a completed parent')
            if nested:
                task['status_override'] = status
        else:
            pending = [task['id']]
            visited = set()
            while pending:
                identifier = pending.pop()
                if identifier in visited:
                    raise ValueError('Task parent cycle')
                visited.add(identifier)
                for item in tasks:
                    if item['id'] == identifier:
                        item['status'] = status
                        item.pop('status_override', None)
                    if item.get('parent_id') == identifier:
                        pending.append(item['id'])
    validate(tasks, {meta['id'], *(tab['id'] for tab,_ in tabs)})
    if delete:
        removed = {task['id']}
        while True:
            more = {item['id'] for item in tasks if item.get('parent_id') in removed} - removed
            if not more:
                break
            removed.update(more)
        tasks = [item for item in tasks if item['id'] not in removed]
    task['updated'] = now()
    meta['tasks'] = normalize(tasks)
    meta['updated'] = now()
    return task['id']


def change(root, reference, values, *, task_id=None, expected=None, delete=False):
    with records.lock(root):
        source, raw, meta, body, tabs = read(root, reference)
        if expected is not None and hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('This document changed elsewhere. Refresh and try again; your changes have not been saved.')
        identifier = mutate(meta, tabs, values, task_id, delete)
        records.atomic_bytes(source, documents.pack(meta, body, tabs))
        documents.snapshot(root, force=True)
        return view(root, meta['id']) | {'task_id':identifier}


CHECKBOX = re.compile(r'^(?P<prefix>[ \t]*(?:[-*+]|\d+[.)])[ \t]+)\[(?P<done>[ xX])\][ \t]+(?P<title>.+?)(?P<end>\r?\n)?$')


def convert_checkboxes(body, tab_id, owner_id, priority):
    """Move live checkbox state to JSON; retain the note's words as ordinary bullets."""
    tasks, lines, stack = [], [], []
    fence = None
    for index, line in enumerate(body.splitlines(keepends=True)):
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            lines.append(line)
            continue
        match = CHECKBOX.match(line) if fence is None else None
        if not match:
            lines.append(line)
            if line.strip() and not line[:1].isspace():
                stack = []
            continue
        indent = len(match['prefix']) - len(match['prefix'].lstrip())
        while stack and stack[-1][0] >= indent:
            stack.pop()
        identifier = 'check_' + hashlib.sha256(f'{tab_id}:{index}:{line}'.encode()).hexdigest()[:24]
        status = 'done' if match['done'].lower() == 'x' else 'not_started'
        tasks.append({'id':identifier,'title':match['title'],'status':status,'done':status == 'done',
                      'priority':priority,'tab_id':tab_id,'parent_id':stack[-1][1] if stack else owner_id,
                      'legacy_checkbox':{'tab_id':tab_id,'line':index + 1,'source':line.rstrip('\r\n')}})
        stack.append((indent,identifier))
        lines.append(match['prefix'] + match['title'] + (match['end'] or ''))
    return ''.join(lines), tasks


def convert(raw):
    meta, body, tabs = documents.unpack(raw)
    if meta.get('task_format') == FORMAT:
        validate(meta.get('tasks',[]), {meta['id'], *(tab['id'] for tab,_ in tabs)})
        return raw, {'tracked':0,'checkboxes':0,'existing':len(meta.get('tasks',[]))}
    tasks = deepcopy(meta.get('tasks', []))
    stats = {'tracked':0,'checkboxes':0,'existing':len(tasks)}
    contents = [(meta, body), *tabs]
    converted = []
    by_id = {row['id']:row for row,_ in contents}
    tracked_ids = {row['id'] for row,_ in contents if records.tracks_task(row)}
    for row, text in contents:
        owner = None
        if records.tracks_task(row):
            owner = row['id']
            if any(task['id'] == owner for task in tasks):
                raise ValueError('Task ID collision while migrating ' + owner)
            status = LEGACY_STATUS.get(row.get('status'), row.get('status') or 'not_started')
            ancestor = row
            while ancestor.get('parent'):
                ancestor = by_id[ancestor['parent']['id']]
                if ancestor['id'] in tracked_ids and ancestor.get('status') in {'skipped','cancelled'}:
                    status = ancestor['status']
            task = {key:deepcopy(value) for key,value in row.items() if key in FIELDS - {'parent_id','tab_id','done'}}
            task.update(id=owner,title=row['title'],status=status,done=status in {'done','skipped'},
                        priority=row.get('priority') or 'P2',parent_id=None,tab_id=row['id'],
                        created=row.get('created'),updated=row.get('updated'),legacy_record_id=row['id'])
            tasks.append(task)
            stats['tracked'] += 1
        text, checkboxes = convert_checkboxes(text, row['id'], owner, row.get('priority') or 'P2')
        if owner and checkboxes and task['status'] in {'in_progress','blocked'}:
            task['status_override'] = task['status']
        if owner and task['status'] in CLOSED:
            for checkbox in checkboxes:
                checkbox.update(status=task['status'],done=task['status'] in {'done','skipped'})
        tasks.extend(checkboxes)
        stats['checkboxes'] += len(checkboxes)
        # Historical metadata remains available, but tabs no longer own lifecycle.
        row['track_task'] = False
        converted.append((row,text))
    meta, body = converted[0]
    meta['task_format'] = FORMAT
    meta.pop('poc', None)
    meta['tasks'] = normalize(tasks)
    validate(meta['tasks'], set(by_id))
    return documents.pack(meta, body, converted[1:]), stats


def migrate(root, *, dry_run=True):
    """Verified backup, compare-before-write, journal, rollback, and idempotency."""
    root = Path(root)
    manifest_path = root/'.assistant/manifest.json'
    with records.lock(root):
        info = records.manifest(root)
        if info.get('document_format') != documents.FORMAT or info.get('storage_layout') != 'unified-documents-v1':
            raise ValueError('Migrate embedded subtabs and documents storage first')
        records.verify(root)
        originals, converted, plan = {}, {}, []
        for source in sorted((root/'documents').glob('*.md')):
            records.safe(root, source)
            raw = source.read_bytes()
            updated, stats = convert(raw)
            if raw != updated:
                relative = source.relative_to(root).as_posix()
                originals[relative] = raw
                converted[relative] = updated
                plan.append({'path':relative, **stats})
        report = {'task_format':FORMAT,'documents':plan,'changed_documents':len(plan),
                  'tasks':sum(len(documents.unpack(value)[0]['tasks']) for value in converted.values())}
        if dry_run or not originals and info.get('task_format') == FORMAT:
            return report | {'applied':False,'noop':not originals and info.get('task_format') == FORMAT}
        run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
        backup = root/'.assistant/backups'/('document-tasks-' + run)
        backup.mkdir(parents=True)
        originals['.assistant/manifest.json'] = manifest_path.read_bytes()
        for candidate in [root/'AGENTS.md',root/'README.md',root/'.assistant/dashboard.json',*sorted((root/'.assistant/dashboard').glob('*.json'))]:
            if candidate.is_file():
                originals[candidate.relative_to(root).as_posix()] = candidate.read_bytes()
        hashes = {}
        for relative, raw in originals.items():
            records.atomic_bytes(backup/relative, raw)
            hashes[relative] = hashlib.sha256(raw).hexdigest()
            if hashlib.sha256((backup/relative).read_bytes()).hexdigest() != hashes[relative]:
                raise ValueError('Backup verification failed: ' + relative)
        journal_path = root/'.assistant/migrations'/('document-tasks-' + run + '.json')
        journal = {'format':FORMAT,'backup':str(backup),'sha256':hashes,'plan':plan,'state':'prepared'}
        records.write_json(journal_path,journal)
        try:
            for relative, raw in originals.items():
                if (root/relative).read_bytes() != raw:
                    raise ValueError('Source changed during migration: ' + relative)
            records.write_json(manifest_path, info | {'state':'migrating'})
            for relative, raw in converted.items():
                records.atomic_bytes(root/relative,raw)
            records.write_json(manifest_path, info | {'task_format':FORMAT})
            documents.snapshot(root,force=True)
            records.verify(root)
            for relative, raw in converted.items():
                if (root/relative).read_bytes() != raw:
                    raise ValueError('Migration verification failed: ' + relative)
            journal['state'] = 'complete'
            records.write_json(journal_path,journal)
        except Exception:
            for relative, raw in originals.items():
                records.atomic_bytes(root/relative,raw)
            journal['state'] = 'rolled_back'
            records.write_json(journal_path,journal)
            documents.snapshot(root,force=True)
            raise
        return report | {'applied':True,'backup':str(backup),'journal':str(journal_path)}


def find(root, identifier):
    matches = [(row['id'],task) for row in records.records(root) if not row.get('parent')
               and row.get('task_format') == FORMAT for task in normalize(row.get('tasks',[])) if task['id'] == identifier]
    if len(matches) != 1:
        raise ValueError('Task ID is missing or ambiguous; use lab assistant task with its document ID')
    return matches[0]


def repeat(root, reference, task_id, *, expected=None):
    """Create a task's next occurrence in its owning document, idempotently."""
    from calendar import monthrange
    from datetime import date, timedelta
    with records.lock(root):
        source, raw, meta, body, tabs = read(root,reference)
        if expected is not None and hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('This document changed elsewhere. Refresh and try again.')
        items = normalize(meta.get('tasks',[]))
        task = next((item for item in items if item['id'] == task_id),None)
        if not task or task['status'] != 'done':
            raise ValueError('Complete the task before creating its next occurrence')
        frequency = task.get('recurrence')
        if frequency not in {'weekly','monthly','yearly'}:
            raise ValueError('Choose a repeat frequency for this task first')
        try:
            due = date.fromisoformat(task.get('due') or '')
            anchor = date.fromisoformat(task.get('recurrence_anchor') or task.get('due') or '')
        except ValueError as exc:
            raise ValueError('Set a valid due date before creating the next occurrence') from exc
        if frequency == 'weekly':
            following = due + timedelta(days=7)
        else:
            year,month = (due.year+1,due.month) if frequency == 'yearly' else (due.year+due.month//12,due.month%12+1)
            following = date(year,month,min(anchor.day,monthrange(year,month)[1]))
        existing = next((item for item in items if item.get('previous_task') == task_id and item.get('due') == following.isoformat()),None)
        if existing:
            return view(root,reference) | {'task_id':existing['id']}
        next_task = deepcopy(task)
        identifier='task_' + uuid.uuid4().hex
        next_task.update(id=identifier,status='not_started',done=False,created=now(),updated=now(),
                         due=following.isoformat(),recurrence_anchor=anchor.isoformat(),
                         recurrence_root=task.get('recurrence_root') or task_id,previous_task=task_id)
        for field in ('status_override','completed','legacy_record_id','legacy_checkbox'):
            next_task.pop(field,None)
        copied=[next_task]
        def copy_children(parent,new_parent):
            for child in items:
                if child.get('parent_id') != parent:
                    continue
                item=deepcopy(child)
                item.update(id='task_'+uuid.uuid4().hex,parent_id=new_parent,status='not_started',done=False,created=now(),updated=now())
                for field in ('status_override','completed','legacy_record_id','legacy_checkbox'):
                    item.pop(field,None)
                copied.append(item)
                copy_children(child['id'],item['id'])
        copy_children(task_id,identifier)
        meta['tasks']=normalize([*items,*copied])
        validate(meta['tasks'],{meta['id'],*(tab['id'] for tab,_ in tabs)})
        meta['updated']=now()
        records.atomic_bytes(source,documents.pack(meta,body,tabs))
        documents.snapshot(root,force=True)
        return view(root,reference) | {'task_id':identifier}
