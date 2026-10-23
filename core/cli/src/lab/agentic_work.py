"""Existing work/status commands for an explicitly owned, non-tmux mission run."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import time

from lab.agentic_store import ACTIVE_RUNS, Store


def current():
    workspace, run_id = os.environ.get('LAB_AGENTIC_WORKSPACE'), os.environ.get('LAB_AGENTIC_RUN')
    if not workspace and not run_id:
        return None
    if not workspace or not run_id or not (Path(workspace) / '.lab/agentic/state.sqlite3').is_file():
        raise ValueError('Incomplete managed mission run context')
    store = Store(Path(workspace))
    run = store.run(run_id)
    if not run or run['status'] not in ACTIVE_RUNS:
        raise ValueError('The managed mission run is no longer active')
    return store, run_id


@contextmanager
def transaction(owner):
    store, run_id = owner
    with store.transaction() as db:
        run = store.get(db, 'runs', run_id)
        if not run or run['status'] not in ACTIVE_RUNS:
            raise ValueError('The managed mission run is no longer active')
        yield store, db, run


def start(owner, title, *, request='', context='', parent_id=None, assignment_id=None):
    if not title.strip() or len(title) > 200 or len(request) > 64000 or len(context) > 64000:
        raise ValueError('Use a title of 1–200 characters and bounded request/context')
    with transaction(owner) as (store, db, run):
        if assignment_id and assignment_id != run['id']:
            raise ValueError('Resume only the assignment owned by this mission run')
        if parent_id:
            raise ValueError('The coordinator owns mission delegation; do not create nested agents')
        record = {'id': run['id'], 'title': title, 'request': request, 'context': context,
                  'status': 'working', 'task_id': run['task_id']}
        store.event(db, 'work-start', record, run_id=run['id'], task_id=run['task_id'])
        return record


def finish(owner, summary='', state='finished'):
    if state not in ('finished', 'attention') or len(summary) > 8000:
        raise ValueError('Invalid assignment state or summary')
    with transaction(owner) as (store, db, run):
        record = {'id': run['id'], 'summary': summary, 'status': state}
        store.event(db, 'work-finish', record, run_id=run['id'], task_id=run['task_id'])
        # Only the runner's validated final result can finish the task.
        return record


def record(owner, file_paths, operation='modified', previous_path=None, assignment_id=None):
    if operation not in ('created', 'modified', 'deleted', 'renamed') or not 1 <= len(file_paths) <= 200:
        raise ValueError('Choose an operation and 1–200 files')
    if operation == 'renamed' and (len(file_paths) != 1 or not previous_path):
        raise ValueError('A rename needs one destination and --previous-path')
    with transaction(owner) as (store, db, run):
        if assignment_id and assignment_id != run['id']:
            raise ValueError('Record only files owned by this mission run')
        def scoped(value):
            path = Path(value).expanduser().resolve()
            if not path.is_relative_to(store.workspace):
                raise ValueError('Reported files must be inside this workspace')
            return path
        old_path = str(scoped(previous_path)) if previous_path else None
        records = []
        for value in file_paths:
            path = scoped(value)
            if operation != 'deleted' and not path.is_file():
                raise ValueError(f'File not found: {path}')
            size = path.stat().st_size if path.is_file() else None
            row = {'path': str(path), 'operation': operation, 'previous_path': old_path,
                   'size': size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest() if size is not None and size <= 2_000_000 else None}
            records.append(row)
            store.put(db, 'files', {**row, 'id': hashlib.sha256((run['id'] + str(path)).encode()).hexdigest(),
                                   'run_id': run['id'], 'task_id': run['task_id'], 'reported': time.time()})
        store.event(db, 'files-reported', {'files': records}, run_id=run['id'], task_id=run['task_id'])
        return {'assignment_id': run['id'], 'recorded': [r['path'] for r in records], 'count': len(records)}


def history(owner, include_children=False):
    store, run_id = owner
    return {'assignment_id': run_id, 'events': store.events(run_id=run_id, latest=True, limit=2000)}


def report(owner, state, message):
    with transaction(owner) as (store, db, run):
        value = {'state': state, 'message': message, 'updated_at': time.time()}
        run['report'] = value
        store.put(db, 'runs', run)
        store.event(db, 'status-report', value, run_id=run['id'], task_id=run['task_id'])
        return run['id']
