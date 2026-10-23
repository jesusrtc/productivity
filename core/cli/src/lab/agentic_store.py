"""Local, transactional mission state shared by Lab, its CLI and task runners.

No model calls live here. Each workspace has an independent database; a single
SQLite write transaction arbitrates capacity and state changes across processes.
Assignments and execution events are append-only. A task survives its executor.
"""
from __future__ import annotations

from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


PROVIDERS = ('codex', 'copilot', 'claude')
TASK_STATES = ('queued', 'running', 'paused', 'blocked', 'review', 'completed', 'cancelled', 'failed')
ACTIVE_RUNS = ('starting', 'running', 'stopping', 'waiting')
EXECUTING_RUNS = ('starting', 'running', 'stopping')
DEFAULT_SETTINGS = {'enabled': True, 'max_workers': 5, 'reminder_seconds': 7200,
                    'provider': None, 'model': None, 'timezone': 'UTC'}


def identifier(value=None):
    value = value or str(uuid.uuid4())
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', value):
        raise ValueError('Invalid record ID')
    return value


def text(value, name, *, required=True, maximum=64000):
    if not isinstance(value, str) or '\x00' in value or len(value) > maximum or (required and not value.strip()):
        raise ValueError(f'{name} must be text, at most {maximum} characters' + (' and nonempty' if required else ''))
    return value


def cron_fields(expression):
    """Five-field numeric cron, including lists, ranges and steps; Sunday 0/7."""
    pieces = expression.split()
    if len(pieces) != 5:
        raise ValueError('Cron requires minute hour day month weekday')
    result = []
    for part, (low, high) in zip(pieces, ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))):
        values = set()
        for piece in part.split(','):
            base, _, step_text = piece.partition('/')
            if step_text and not step_text.isdigit():
                raise ValueError('Invalid cron step')
            step = int(step_text or 1)
            if step < 1 or step > high + 1:
                raise ValueError('Invalid cron step')
            if base == '*':
                start, end = low, high
            elif re.fullmatch(r'\d+-\d+', base):
                start, end = map(int, base.split('-'))
            elif base.isdigit():
                start = int(base)
                end = high if step_text else start
            else:
                raise ValueError('Invalid cron field')
            if not low <= start <= end <= high:
                raise ValueError('Cron field outside its allowed range')
            values.update(range(start, end + 1, step))
        result.append(values)
    if 7 in result[4]:
        result[4].remove(7)
        result[4].add(0)
    return result, pieces


def next_cron(expression, after, zone='UTC'):
    fields, pieces = cron_fields(expression)
    tz = ZoneInfo(zone)
    candidate = int(after // 60) * 60 + 60
    for _ in range(366 * 24 * 60 * 5):
        dt = datetime.fromtimestamp(candidate, tz)
        day, weekday = dt.day in fields[2], (dt.weekday() + 1) % 7 in fields[4]
        day_match = (day or weekday) if pieces[2] != '*' and pieces[4] != '*' else (day and weekday)
        if dt.minute in fields[0] and dt.hour in fields[1] and dt.month in fields[3] and day_match:
            return candidate
        candidate += 60
    raise ValueError('Cron expression has no occurrence in the next five years')


def require_idle(workspace):
    workspace = Path(workspace)
    if (workspace / '.lab/agentic/state.sqlite3').is_file():
        if any(r['status'] in ACTIVE_RUNS for r in Store(workspace).snapshot()['runs']):
            raise ValueError('Pause the agentic workspace and stop its active runs before moving, deleting or changing its kind/status')


class Store:
    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise ValueError('Workspace directory does not exist')
        self.directory = self.workspace / '.lab' / 'agentic'
        if not self.directory.resolve().is_relative_to(self.workspace):
            raise ValueError('Agentic state must remain inside the workspace')
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = self.directory / 'state.sqlite3'
        if self.database.is_symlink():
            raise ValueError('Agentic database cannot be a symbolic link')
        with closing(self._connect()) as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
                    PRIMARY KEY(kind,id));
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT,
                    task_id TEXT, kind TEXT NOT NULL, body TEXT NOT NULL, at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS events_run ON events(run_id,seq);
                CREATE INDEX IF NOT EXISTS events_task ON events(task_id,seq);
            ''')
        self.database.chmod(0o600)

    def _connect(self):
        db = sqlite3.connect(self.database, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=15000')
        return db

    @contextmanager
    def transaction(self):
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise

    @staticmethod
    def get(db, kind, ident):
        row = db.execute('SELECT body FROM records WHERE kind=? AND id=?', (kind, ident)).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def rows(db, kind):
        return [json.loads(row[0]) for row in db.execute('SELECT body FROM records WHERE kind=? ORDER BY rowid', (kind,))]

    @staticmethod
    def put(db, kind, row):
        db.execute('INSERT INTO records(kind,id,body) VALUES(?,?,?) '
                   'ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body',
                   (kind, row['id'], json.dumps(row, ensure_ascii=False)))

    @staticmethod
    def event(db, kind, body, *, task_id=None, run_id=None, now=None):
        db.execute('INSERT INTO events(run_id,task_id,kind,body,at) VALUES(?,?,?,?,?)',
                   (run_id, task_id, kind, json.dumps(body, ensure_ascii=False), now or time.time()))

    def settings(self, db):
        return {**DEFAULT_SETTINGS, **(self.get(db, 'settings', 'workspace') or {})}

    def snapshot(self, *, include_prompts=False):
        with closing(self._connect()) as db:
            db.execute('BEGIN')
            data = {kind: self.rows(db, kind) for kind in ('missions', 'tasks', 'runs', 'messages', 'schedules', 'assets', 'memory', 'permissions')}
            data['settings'] = self.settings(db)
            data['revision'] = db.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0]
            db.execute('COMMIT')
        if not include_prompts:
            data['runs'] = [{key: value for key, value in row.items() if key not in ('prompt', 'context', 'request')}
                            for row in data['runs']]
        return data

    def detail(self, task_id):
        with closing(self._connect()) as db:
            if task_id == '__coordinator__':
                runs = [r for r in self.rows(db, 'runs') if r['role'] == 'coordinator']
                responses = [m['content'] for m in self.rows(db, 'messages') if m['role'] == 'assistant']
                return {'coordinator': True, 'task': {'id': task_id, 'title': 'Coordinator history',
                        'status': 'running' if any(r['status'] in ACTIVE_RUNS for r in runs) else 'completed',
                        'instruction': 'Inspect the exact context and plan for each coordinator turn.',
                        'result': responses[-1] if responses else 'No response yet.'},
                        'runs': runs, 'assets': [], 'files': [], 'permissions': [], 'events': self.events(task_id=task_id, latest=True)}
            task = self.get(db, 'tasks', task_id)
            if not task:
                raise ValueError('Task not found')
            return {'task': task,
                    'runs': [r for r in self.rows(db, 'runs') if r.get('task_id') == task_id],
                    'assets': [r for r in self.rows(db, 'assets') if r.get('task_id') == task_id],
                    'permissions': [r for r in self.rows(db, 'permissions') if r.get('task_id') == task_id],
                    'files': [r for r in self.rows(db, 'files') if r.get('task_id') == task_id],
                    'events': self.events(task_id=task_id, latest=True)}

    def events(self, *, task_id=None, run_id=None, after=0, before=None, latest=False, limit=500):
        sql, args = 'SELECT * FROM events WHERE seq>?', [after]
        if task_id == '__coordinator__':
            sql += ' AND task_id IS NULL'
        elif task_id:
            sql += ' AND task_id=?'
            args.append(task_id)
        if run_id:
            sql += ' AND run_id=?'
            args.append(run_id)
        if before is not None:
            sql += ' AND seq<?'
            args.append(before)
        sql += ' ORDER BY seq ' + ('DESC' if latest else 'ASC') + ' LIMIT ?'
        args.append(min(max(int(limit), 1), 2000))
        with closing(self._connect()) as db:
            rows = [{**dict(row), 'body': json.loads(row['body'])} for row in db.execute(sql, args)]
            return rows[::-1] if latest else rows

    def append_event(self, kind, body, **scope):
        with self.transaction() as db:
            self.event(db, kind, body, **scope)

    def message(self, content, *, role='user', mission_id=None, task_id=None, request_id=None, db=None):
        text(content, 'Message')
        if role not in ('user', 'assistant', 'notice', 'event'):
            raise ValueError('Invalid message role')
        if db is None:
            with self.transaction() as connection:
                return self.message(content, role=role, mission_id=mission_id, task_id=task_id,
                                    request_id=request_id, db=connection)
        ident = identifier(request_id)
        existing = self.get(db, 'messages', ident)
        if existing:
            if (existing['content'], existing['role'], existing.get('task_id'), existing.get('mission_id')) != (content, role, task_id, mission_id):
                raise ValueError('Message request ID already has different content')
            return existing
        if mission_id and not self.get(db, 'missions', mission_id):
            raise ValueError('Mission not found')
        if task_id:
            task = self.get(db, 'tasks', task_id)
            if not task or (mission_id and task['mission_id'] != mission_id):
                raise ValueError('Task does not belong to this mission')
            mission_id = task['mission_id']
        row = {'id': ident, 'role': role, 'content': content, 'mission_id': mission_id,
               'task_id': task_id, 'created': time.time(),
               'status': 'pending' if role in ('user', 'event') else 'delivered'}
        if role == 'notice':
            row['notification_state'] = 'attention'
        self.put(db, 'messages', row)
        self.event(db, 'message', {'id': ident, 'role': role}, task_id=task_id)
        return row

    def notifications(self):
        state = self.snapshot()
        latest = {}
        tasks = {t['id']: t for t in state['tasks']}
        missions = {m['id']: m for m in state['missions']}
        recovered = max((r.get('finished', 0) for r in state['runs']
                         if r['role'] == 'coordinator' and r['status'] == 'completed'), default=0)
        for row in state['messages']:
            if not row.get('notification_state'):
                continue
            task = tasks.get(row.get('task_id'), {})
            mission = missions.get(row.get('mission_id'), {})
            latest[row.get('task_id') or 'coordinator'] = {
                'report_id': row['id'], 'state': row['notification_state'], 'message': row['content'],
                'created_at': row['created'], 'active': not row.get('reviewed') and not (not row.get('task_id') and row['created'] < recovered),
                'task_id': row.get('task_id'), 'title': task.get('title', 'Coordinator'),
                'mission': mission.get('title', '')}
        return list(latest.values())

    def acknowledge(self, message_id):
        with self.transaction() as db:
            row = self.get(db, 'messages', message_id)
            if not row or not row.get('notification_state'):
                raise ValueError('Notification not found')
            row['reviewed'] = time.time()
            self.put(db, 'messages', row)
            self.event(db, 'notification-reviewed', {'id': message_id}, task_id=row.get('task_id'))
            return {'reviewed': message_id}

    def configure(self, patch):
        if not isinstance(patch, dict) or set(patch) - set(DEFAULT_SETTINGS):
            raise ValueError('Unknown agentic setting')
        with self.transaction() as db:
            data = {**self.settings(db), **patch, 'id': 'workspace'}
            if type(data['enabled']) is not bool or type(data['max_workers']) is not int or not 1 <= data['max_workers'] <= 5:
                raise ValueError('Choose enabled and between one and five executors')
            if type(data['reminder_seconds']) is not int or not 60 <= data['reminder_seconds'] <= 604800:
                raise ValueError('Reminder interval must be between one minute and seven days')
            if data['provider'] is not None and data['provider'] not in PROVIDERS:
                raise ValueError('Choose codex, copilot or claude, or inherit Settings')
            if data['model'] is not None:
                text(data['model'], 'Model', maximum=256)
            ZoneInfo(data['timezone'])
            self.put(db, 'settings', data)
            self.event(db, 'settings', patch)
            return data

    def apply(self, actions, *, actor='user', db=None, source=None):
        if not isinstance(actions, list) or len(actions) > 100:
            raise ValueError('Provide at most 100 actions')
        if db is None:
            with self.transaction() as connection:
                return self.apply(actions, actor=actor, db=connection, source=source)
        results = []
        for action in actions:
            if not isinstance(action, dict):
                raise ValueError('Each action must be an object')
            kind = action.get('type')
            if actor == 'executor':
                if kind != 'asset-add' or not source or not source.get('task_id') or action.get('task_id') != source['task_id']:
                    raise ValueError('Executors can only attach evidence to their own task; the coordinator and user own task controls')
            ident = identifier(action.get('id'))
            now = time.time()
            if kind == 'mission-create':
                if self.get(db, 'missions', ident):
                    raise ValueError('Mission ID already exists')
                row = {'id': ident, 'title': text(action.get('title'), 'Title', maximum=240),
                       'objective': text(action.get('objective'), 'Objective'), 'status': 'active',
                       'result': '', 'created': now, 'updated': now}
                self.put(db, 'missions', row)
            elif kind == 'mission-update':
                row = self.get(db, 'missions', ident)
                if not row:
                    raise ValueError('Mission not found')
                for key in ('title', 'objective', 'result'):
                    if key in action:
                        row[key] = text(action[key], key, required=key != 'result')
                if 'status' in action:
                    status = action['status']
                    if status not in ('active', 'paused', 'completed', 'cancelled'):
                        raise ValueError('Invalid mission status')
                    if status == 'completed' and any(t['mission_id'] == ident and t['status'] not in ('completed', 'cancelled') for t in self.rows(db, 'tasks')):
                        raise ValueError('Mission still has unfinished tasks')
                    row['status'] = status
                    if status in ('paused', 'cancelled'):
                        for task in self.rows(db, 'tasks'):
                            if task['mission_id'] == ident and (task.get('active_run') or status == 'cancelled' and task['status'] not in ('completed', 'cancelled')):
                                self._control(db, task, 'pause' if status == 'paused' else 'cancel', 'Mission ' + status)
                row['updated'] = now
                self.put(db, 'missions', row)
            elif kind == 'task-create':
                mission = self.get(db, 'missions', action.get('mission_id'))
                if not mission or self.get(db, 'tasks', ident):
                    raise ValueError('Mission missing or task ID already exists')
                priority = action.get('priority', 50)
                if type(priority) is not int or not 0 <= priority <= 100:
                    raise ValueError('Priority must be an integer from 0 to 100 (highest)')
                deps = action.get('depends_on', [])
                if not isinstance(deps, list) or len(set(deps)) != len(deps):
                    raise ValueError('Dependencies must be a list without duplicates')
                for dep in deps + ([action['parent_id']] if action.get('parent_id') else []):
                    other = self.get(db, 'tasks', dep)
                    if not other or other['mission_id'] != mission['id']:
                        raise ValueError('Parent and dependencies must exist in the same mission')
                status = action.get('status', 'queued')
                if status not in ('queued', 'paused', 'blocked'):
                    raise ValueError('New tasks start queued, paused or blocked')
                row = {'id': ident, 'mission_id': mission['id'], 'parent_id': action.get('parent_id'),
                       'title': text(action.get('title'), 'Task title', maximum=240),
                       'instruction': text(action.get('instruction'), 'Instruction'),
                       'context': text(action.get('context', ''), 'Context', required=False),
                       'status': status, 'priority': priority, 'depends_on': deps,
                       'review_required': bool(action.get('review_required', False)),
                       'group': bool(action.get('group', False)), 'result': '', 'checkpoint': '',
                       'blocker': action.get('blocker', ''), 'active_run': None,
                       'next_reminder': now + self.settings(db)['reminder_seconds'] if status == 'blocked' else None,
                       'created': now, 'updated': now, 'version': 1}
                if status == 'blocked':
                    text(row['blocker'], 'Blocker')
                self.put(db, 'tasks', row)
                if mission['status'] == 'completed':
                    mission['status'] = 'active'
                    self.put(db, 'missions', mission)
            elif kind == 'task-update':
                row = self.get(db, 'tasks', ident)
                if not row:
                    raise ValueError('Task not found')
                if 'expected_version' in action and action['expected_version'] != row['version']:
                    raise ValueError('Task changed while the coordinator was planning; inspect its latest state')
                for key in ('title', 'instruction', 'context'):
                    if key in action:
                        row[key] = text(action[key], key, required=key != 'context')
                if 'priority' in action:
                    if type(action['priority']) is not int or not 0 <= action['priority'] <= 100:
                        raise ValueError('Priority must be between 0 and 100')
                    row['priority'] = action['priority']
                row['updated'], row['version'] = now, row['version'] + 1
                self.put(db, 'tasks', row)
            elif kind in ('task-pause', 'task-resume', 'task-cancel', 'task-retry', 'task-approve', 'task-block', 'task-snooze'):
                row = self.get(db, 'tasks', ident)
                if not row:
                    raise ValueError('Task not found')
                control = kind[5:]
                if control == 'approve' and actor != 'user':
                    quote = action.get('approval_quote')
                    if not source or source.get('role') != 'user' or not isinstance(quote, str) or not quote.strip() or quote not in source['content']:
                        raise ValueError('Only the user can approve a review gate; quote their current explicit approval')
                    if not action.get('review_run_id') or action['review_run_id'] != row.get('review_run_id'):
                        raise ValueError('Approval must identify the current preview execution')
                    if source['created'] < row.get('review_since', float('inf')):
                        raise ValueError('Approval must follow the current preview')
                row = self._control(db, row, control, action.get('reason', ''), action.get('seconds'))
                if row.get('group') and control in ('pause', 'cancel'):
                    descendants = {row['id']}
                    tasks = self.rows(db, 'tasks')
                    for _ in range(len(tasks)):
                        before = len(descendants)
                        descendants.update(t['id'] for t in tasks if t.get('parent_id') in descendants)
                        if len(descendants) == before:
                            break
                    for child in tasks:
                        if child['id'] != row['id'] and child['id'] in descendants and child['status'] not in ('completed', 'cancelled'):
                            self._control(db, child, control, action.get('reason', ''))
            elif kind == 'asset-add':
                row = self._asset(db, action, run_id=source['id'] if actor == 'executor' else None)
            elif kind == 'permission-respond':
                if actor != 'user':
                    raise ValueError('Tool permission decisions require the user')
                row = self.get(db, 'permissions', ident)
                if not row or row['status'] != 'pending':
                    raise ValueError('Permission request is no longer pending')
                run = self.get(db, 'runs', row['run_id'])
                if not run or run['status'] not in ('waiting', 'running') or run.get('stop_requested'):
                    raise ValueError('The requesting execution is no longer waiting')
                option = next((o for o in row['request']['options'] if o['optionId'] == action.get('option_id')), None)
                if not option or option['kind'] not in ('allow_once', 'reject_once'):
                    raise ValueError('Choose an offered one-time permission decision')
                row.update(status='decided', option_id=option['optionId'], decided=now)
                self.put(db, 'permissions', row)
            elif kind == 'memory-set':
                row = {'id': ident, 'content': text(action.get('content'), 'Memory', maximum=12000),
                       'mission_id': action.get('mission_id'), 'updated': now, 'actor': actor}
                if row['mission_id'] and not self.get(db, 'missions', row['mission_id']):
                    raise ValueError('Memory mission not found')
                self.put(db, 'memory', row)
            elif kind == 'schedule-create':
                if self.get(db, 'schedules', ident) or not self.get(db, 'missions', action.get('mission_id')):
                    raise ValueError('Mission missing or schedule ID already exists')
                interval, cron = action.get('interval_seconds'), action.get('cron')
                if bool(interval) == bool(cron):
                    raise ValueError('Choose an interval or a cron expression')
                if interval is not None and (type(interval) is not int or not 60 <= interval <= 31536000):
                    raise ValueError('Schedule interval must be at least 60 seconds')
                zone = action.get('timezone', self.settings(db)['timezone'])
                ZoneInfo(zone)
                due = next_cron(cron, now, zone) if cron else now + interval
                row = {'id': ident, 'mission_id': action['mission_id'],
                       'title': text(action.get('title'), 'Schedule title', maximum=240),
                       'instruction': text(action.get('instruction'), 'Schedule instruction'),
                       'interval_seconds': interval, 'cron': cron, 'timezone': zone,
                       'next_due': due, 'enabled': True, 'last_task': None, 'last_fingerprint': None,
                       'created': now, 'updated': now}
                self.put(db, 'schedules', row)
            elif kind in ('schedule-pause', 'schedule-resume'):
                row = self.get(db, 'schedules', ident)
                if not row:
                    raise ValueError('Schedule not found')
                row['enabled'] = kind == 'schedule-resume'
                row['updated'] = now
                self.put(db, 'schedules', row)
            else:
                raise ValueError(f'Unknown mission action: {kind}')
            self.event(db, kind, {'actor': actor, 'action': action}, task_id=row['id'] if kind.startswith('task-') else None)
            results.append(row)
        self._rollup(db)
        return results

    def _control(self, db, task, control, reason='', seconds=None):
        now = time.time()
        active = self.get(db, 'runs', task['active_run']) if task.get('active_run') else None
        if control in ('pause', 'cancel'):
            if task['status'] in ('completed', 'cancelled'):
                raise ValueError('Finished task cannot be paused or cancelled')
            if active and active['status'] in ACTIVE_RUNS:
                active['stop_requested'] = control
                self.put(db, 'runs', active)
            else:
                task['status'] = 'paused' if control == 'pause' else 'cancelled'
        elif control in ('resume', 'retry'):
            if task['status'] not in ('paused', 'blocked', 'failed') or (active and active['status'] in ACTIVE_RUNS):
                raise ValueError('Task must be stopped before resuming')
            task.update(status='queued', blocker='', next_reminder=None)
        elif control == 'approve':
            if task['status'] != 'review':
                raise ValueError('Task is not waiting for review')
            task.update(status='completed', next_reminder=None, blocker='')
            self.message('Approved: ' + task['title'], role='event', task_id=task['id'], db=db)
        elif control == 'block':
            if task['status'] == 'running':
                raise ValueError('Pause a running task before marking it blocked')
            task.update(status='blocked', blocker=text(reason, 'Blocker'),
                        next_reminder=now + self.settings(db)['reminder_seconds'])
        elif control == 'snooze':
            if task['status'] not in ('blocked', 'review'):
                raise ValueError('Only blocked or review tasks have reminders')
            if type(seconds) is not int or not 60 <= seconds <= 604800:
                raise ValueError('Choose a snooze between one minute and seven days')
            task['next_reminder'] = now + seconds
        task['updated'], task['version'] = now, task['version'] + 1
        self.put(db, 'tasks', task)
        return task

    def _asset(self, db, asset, run_id):
        task = self.get(db, 'tasks', asset.get('task_id'))
        if not task:
            raise ValueError('Asset task not found')
        target = text(asset.get('target'), 'Asset target', maximum=4096)
        kind = 'url' if urlparse(target).scheme in ('http', 'https') else 'file'
        if kind == 'file':
            path = (self.workspace / target).resolve()
            if not path.is_relative_to(self.workspace) or not path.is_file():
                raise ValueError('Asset file must exist inside this workspace')
            target = str(path.relative_to(self.workspace))
        role = asset.get('role', 'output')
        if role not in ('input', 'support', 'source', 'output'):
            raise ValueError('Invalid asset role')
        origin = asset.get('origin', 'agent')
        if origin not in ('user', 'consulted', 'agent'):
            raise ValueError('Invalid asset origin')
        row = {'id': identifier(asset.get('id')), 'task_id': task['id'], 'mission_id': task['mission_id'],
               'run_id': run_id, 'target': target, 'kind': kind, 'role': role, 'origin': origin,
               'title': text(asset.get('title', Path(target).name or target), 'Asset title', maximum=240),
               'description': text(asset.get('description', ''), 'Description', required=False), 'created': time.time()}
        if self.get(db, 'assets', row['id']):
            raise ValueError('Asset IDs are immutable; register a new revision instead')
        if kind == 'file':
            row['size'] = path.stat().st_size
            if row['size'] <= 20_000_000:
                row['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.put(db, 'assets', row)
        return row

    def tick(self, now=None):
        """Coalesce missed ticks and reminders; never run duplicate schedule work."""
        now = time.time() if now is None else now
        with self.transaction() as db:
            if not self.settings(db)['enabled']:
                return
            for task in self.rows(db, 'tasks'):
                if task['status'] in ('blocked', 'review') and task.get('next_reminder') and task['next_reminder'] <= now:
                    self.message(task['title'] + ': ' + (task['blocker'] or 'Waiting for your review'),
                                 role='notice', task_id=task['id'], db=db)
                    task['next_reminder'] = now + self.settings(db)['reminder_seconds']
                    self.put(db, 'tasks', task)
            for schedule in self.rows(db, 'schedules'):
                mission = self.get(db, 'missions', schedule['mission_id'])
                if not schedule['enabled'] or schedule['next_due'] > now or mission['status'] != 'active':
                    continue
                previous = self.get(db, 'tasks', schedule['last_task']) if schedule['last_task'] else None
                if previous and previous['status'] not in ('completed', 'cancelled'):
                    continue
                context = 'Scheduled check. Previous notification fingerprint: ' + str(schedule['last_fingerprint'])
                if previous:
                    # One durable recurring task, with a new immutable run per
                    # occurrence. Old results/assets remain in execution history.
                    row = previous
                    row.update(status='queued', result='', blocker='', active_run=None, next_reminder=None,
                               instruction=schedule['instruction'], context=context, updated=now, version=row['version'] + 1)
                    self.event(db, 'schedule-reopened', {'schedule_id': schedule['id']}, task_id=row['id'], now=now)
                else:
                    row = self.apply([{'type': 'task-create', 'mission_id': schedule['mission_id'],
                                      'title': schedule['title'], 'instruction': schedule['instruction'], 'context': context}],
                                     actor='schedule', db=db)[0]
                row['schedule_id'] = schedule['id']
                self.put(db, 'tasks', row)
                schedule['last_task'] = row['id']
                schedule['next_due'] = next_cron(schedule['cron'], now, schedule['timezone']) if schedule['cron'] else now + schedule['interval_seconds']
                self.put(db, 'schedules', schedule)

    def reserve(self, *, provider, model=None):
        """Atomically admit one coordinator or one executor. No external work here."""
        if provider not in PROVIDERS:
            raise ValueError('Unsupported provider')
        with self.transaction() as db:
            settings = self.settings(db)
            if not settings['enabled']:
                return None
            active = [r for r in self.rows(db, 'runs') if r['status'] in ACTIVE_RUNS]
            pending = [m for m in self.rows(db, 'messages') if m['status'] == 'pending']
            pending.sort(key=lambda m: (m['role'] != 'user', m['created']))
            role, task, message = None, None, None
            if pending and not any(r['role'] == 'coordinator' for r in active):
                role, message = 'coordinator', pending[0]
            elif sum(r['role'] == 'executor' and r['status'] in EXECUTING_RUNS for r in active) < settings['max_workers']:
                tasks = self.rows(db, 'tasks')
                done = {t['id'] for t in tasks if t['status'] == 'completed'}
                missions = {m['id'] for m in self.rows(db, 'missions') if m['status'] == 'active'}
                by_id = {t['id']: t for t in tasks}
                def parent_ready(task):
                    while task.get('parent_id'):
                        task = by_id[task['parent_id']]
                        if task['status'] in ('paused', 'blocked', 'review', 'cancelled', 'failed'):
                            return False
                    return True
                ready = [t for t in tasks if t['status'] == 'queued' and not t.get('group')
                         and t['mission_id'] in missions and set(t['depends_on']) <= done and parent_ready(t)]
                ready.sort(key=lambda t: (-t['priority'], t['created']))
                if ready:
                    role, task = 'executor', ready[0]
            if not role:
                return None
            row = {'id': identifier(), 'role': role, 'provider': settings['provider'] or provider,
                   'model': settings['model'] or model, 'task_id': task['id'] if task else None,
                   'message_id': message['id'] if message else None, 'status': 'starting',
                   'created': time.time(), 'pid': None, 'process_started': None,
                   'stop_requested': None, 'prompt': None, 'context': None, 'result': None}
            self.put(db, 'runs', row)
            if task:
                task.update(status='running', active_run=row['id'], updated=time.time(), version=task['version'] + 1)
                self.put(db, 'tasks', task)
            if message:
                message.update(status='processing', run_id=row['id'])
                self.put(db, 'messages', message)
            self.event(db, 'run-reserved', {'role': role, 'provider': row['provider']}, run_id=row['id'], task_id=row['task_id'])
            return row

    def run(self, run_id):
        with closing(self._connect()) as db:
            return self.get(db, 'runs', run_id)

    def prepare_run(self, run_id, prompt, context, argv):
        with self.transaction() as db:
            row = self.get(db, 'runs', run_id)
            if not row or row['status'] != 'starting' or row['prompt'] is not None:
                raise ValueError('An assignment may only be recorded once before launch')
            row.update(prompt=prompt, context=context, argv=argv)
            self.put(db, 'runs', row)
            self.event(db, 'assignment', {'prompt': prompt, 'context': context, 'argv': argv},
                       run_id=run_id, task_id=row['task_id'])
            return row

    def register_process(self, run_id, pid, started):
        with self.transaction() as db:
            row = self.get(db, 'runs', run_id)
            if not row or row['status'] not in ACTIVE_RUNS:
                raise ValueError('Run is no longer active')
            if row['pid'] and (row['pid'] != pid or row['process_started'] != started):
                raise ValueError('Another process owns this run')
            row.update(pid=pid, process_started=started, status='running', heartbeat=time.time())
            self.put(db, 'runs', row)

    def register_child(self, run_id, pid, started):
        with self.transaction() as db:
            row = self.get(db, 'runs', run_id)
            if not row or row['status'] not in ACTIVE_RUNS:
                raise ValueError('Run is no longer active')
            row.update(child_pid=pid, child_started=started)
            self.put(db, 'runs', row)

    def mark_orphan(self, run_id):
        with self.transaction() as db:
            row = self.get(db, 'runs', run_id)
            if not row.get('orphan_since'):
                row['orphan_since'] = time.time()
                self.put(db, 'runs', row)
                self.event(db, 'orphan-stop', {'reason': 'Lost runner; stopping its owned CLI'}, run_id=run_id, task_id=row['task_id'])
            return row['orphan_since']

    def permission(self, run_id, request, *, executing_tools=False):
        with self.transaction() as db:
            run = self.get(db, 'runs', run_id)
            if not run or run['status'] not in ACTIVE_RUNS or run.get('stop_requested'):
                raise ValueError('Execution no longer accepts permission requests')
            row = {'id': identifier(), 'run_id': run_id, 'task_id': run['task_id'], 'request': request,
                   'status': 'pending', 'created': time.time()}
            self.put(db, 'permissions', row)
            run['status'] = 'running' if executing_tools else 'waiting'
            self.put(db, 'runs', run)
            if run['task_id']:
                task = self.get(db, 'tasks', run['task_id'])
                task.update(status='blocked', blocker='Copilot needs permission: ' + request.get('toolCall', {}).get('title', 'Review the requested operation'),
                            next_reminder=time.time() + self.settings(db)['reminder_seconds'], version=task['version'] + 1)
                self.put(db, 'tasks', task)
            self.message('Copilot needs permission. Open the task to inspect the operation and allow it once or reject it.', role='notice', task_id=run['task_id'], db=db)
            self.event(db, 'permission-request', row, task_id=run['task_id'], run_id=run_id)
            return row

    def permission_idle(self, run_id):
        """Release capacity only after all previously allowed tools have ended."""
        with self.transaction() as db:
            run = self.get(db, 'runs', run_id)
            if run and run['status'] == 'running' and not run.get('stop_requested'):
                if any(p['run_id'] == run_id and p['status'] in ('pending', 'decided') for p in self.rows(db, 'permissions')):
                    run['status'] = 'waiting'
                    self.put(db, 'runs', run)

    def take_permission(self, permission_id):
        with self.transaction() as db:
            row = self.get(db, 'permissions', permission_id)
            if not row or row['status'] != 'decided':
                return None
            run = self.get(db, 'runs', row['run_id'])
            if not run or run['status'] not in ('waiting', 'running') or run.get('stop_requested'):
                return None
            if run['role'] == 'executor':
                active = sum(r['role'] == 'executor' and r['status'] in EXECUTING_RUNS for r in self.rows(db, 'runs'))
                if run['status'] == 'waiting' and active >= self.settings(db)['max_workers']:
                    return None
                task = self.get(db, 'tasks', run['task_id'])
                mission = self.get(db, 'missions', task['mission_id'])
                if mission['status'] != 'active' or not self.settings(db)['enabled']:
                    return None
                task.update(status='running', blocker='', next_reminder=None, version=task['version'] + 1)
                self.put(db, 'tasks', task)
            run['status'] = 'running'
            self.put(db, 'runs', run)
            row['status'] = 'consumed'
            self.put(db, 'permissions', row)
            self.event(db, 'permission-consumed', {'permission_id': row['id'], 'option_id': row['option_id']}, run_id=run['id'], task_id=run['task_id'])
            return row

    def coordinator_error(self, run_id, error):
        """Replan an invalid atomic plan with fresh state; never replay task work."""
        with self.transaction() as db:
            run = self.get(db, 'runs', run_id)
            source = self.get(db, 'messages', run['message_id'])
            attempts = source.get('plan_attempts', 0) + 1
            run.update(status='failed', error=error, finished=time.time())
            self.put(db, 'runs', run)
            source.update(status='pending' if attempts < 3 else 'failed', plan_attempts=attempts, plan_error=error)
            self.put(db, 'messages', source)
            self.event(db, 'plan-rejected', {'error': error, 'attempt': attempts}, run_id=run_id)
            if attempts >= 3:
                self.message('The coordinator could not validate its plan: ' + error, role='notice', db=db)

    def checkpoint(self, run_id, content):
        with self.transaction() as db:
            run = self.get(db, 'runs', run_id)
            if not run or run['status'] not in ACTIVE_RUNS or not run['task_id']:
                raise ValueError('No active task run for this checkpoint')
            task = self.get(db, 'tasks', run['task_id'])
            task['checkpoint'] = text(content, 'Checkpoint')
            self.put(db, 'tasks', task)
            self.event(db, 'checkpoint', {'content': content}, run_id=run_id, task_id=task['id'])

    def finish(self, run_id, *, result=None, error=None, stopped=None):
        with self.transaction() as db:
            run = self.get(db, 'runs', run_id)
            if not run or run['status'] not in ACTIVE_RUNS:
                return False
            now = time.time()
            stopped = stopped or run.get('stop_requested')
            for permission in self.rows(db, 'permissions'):
                if permission['run_id'] == run_id and permission['status'] in ('pending', 'decided'):
                    permission['status'] = 'cancelled'
                    self.put(db, 'permissions', permission)
            if error or stopped:
                run.update(status='stopped' if stopped else 'failed', error=str(error or stopped), finished=now)
                if run['task_id']:
                    task = self.get(db, 'tasks', run['task_id'])
                    task.update(status='cancelled' if stopped == 'cancel' else 'paused' if stopped else 'failed',
                                active_run=None, updated=now, version=task['version'] + 1)
                    if error:
                        task['blocker'] = str(error)
                    self.put(db, 'tasks', task)
                if run['message_id']:
                    message = self.get(db, 'messages', run['message_id'])
                    message['status'] = 'failed'
                    self.put(db, 'messages', message)
                self.message('Execution stopped: ' + str(error or stopped), role='notice', task_id=run['task_id'], db=db)
            elif run['role'] == 'coordinator':
                if not isinstance(result, dict):
                    raise ValueError('Coordinator must return an object')
                response = text(result.get('message'), 'Coordinator response')
                source = self.get(db, 'messages', run['message_id'])
                self.apply(result.get('actions', []), actor='coordinator', db=db, source=source)
                self.message(response, role='assistant', mission_id=source.get('mission_id'), task_id=source.get('task_id'), db=db)
                source['status'] = 'handled'
                self.put(db, 'messages', source)
                run.update(status='completed', result=result, finished=now)
            else:
                if not isinstance(result, dict) or result.get('status') not in ('completed', 'blocked', 'review'):
                    raise ValueError('Executor must return completed, blocked or review with a result')
                summary = text(result.get('summary'), 'Result summary')
                task = self.get(db, 'tasks', run['task_id'])
                state = result['status']
                if state == 'completed' and task['review_required']:
                    state = 'review'
                if state == 'blocked':
                    text(result.get('blocker'), 'Blocker with an actionable next step')
                if state == 'review':
                    task.update(review_run_id=run_id, review_since=now)
                task.update(status=state, result=summary, blocker=result.get('blocker', '') if state == 'blocked' else 'Waiting for your review' if state == 'review' else '',
                            active_run=None, updated=now, version=task['version'] + 1,
                            next_reminder=now + self.settings(db)['reminder_seconds'] if state in ('blocked', 'review') else None)
                if result.get('checkpoint'):
                    task['checkpoint'] = text(result['checkpoint'], 'Checkpoint')
                assets = result.get('assets', [])
                if not isinstance(assets, list) or len(assets) > 100:
                    raise ValueError('Provide at most 100 assets')
                for asset in assets:
                    self._asset(db, {**asset, 'task_id': task['id']}, run_id)
                self.put(db, 'tasks', task)
                notify = True
                if task.get('schedule_id'):
                    schedule = self.get(db, 'schedules', task['schedule_id'])
                    fingerprint = result.get('fingerprint') or hashlib.sha256(summary.encode()).hexdigest()
                    notify = fingerprint != schedule['last_fingerprint']
                    schedule['last_fingerprint'] = fingerprint
                    if result.get('schedule_done') is True:
                        notify = notify or schedule['enabled']
                        schedule['enabled'] = False
                    self.put(db, 'schedules', schedule)
                if notify:
                    notice = self.message(task['title'] + '\n' + summary, role='event', task_id=task['id'], db=db)
                    notice['notification_state'] = 'finished' if state == 'completed' else 'attention'
                    self.put(db, 'messages', notice)
                run.update(status='completed', result=result, finished=now)
                self._rollup(db)
            self.put(db, 'runs', run)
            self.event(db, 'run-finished', {'status': run['status'], 'result': result, 'error': error},
                       run_id=run_id, task_id=run['task_id'])
            return True

    def _rollup(self, db):
        tasks = self.rows(db, 'tasks')
        for _ in range(len(tasks)):
            changed = False
            for parent in tasks:
                children = [t for t in tasks if t.get('parent_id') == parent['id']]
                if parent.get('group') and children and parent['status'] == 'queued' and all(t['status'] == 'completed' for t in children):
                    parent['status'] = 'review' if parent['review_required'] else 'completed'
                    if parent['status'] == 'review':
                        parent.update(review_run_id=identifier(), review_since=time.time(), blocker='Waiting for your review',
                                      next_reminder=time.time() + self.settings(db)['reminder_seconds'])
                    parent['result'] = '\n\n'.join(t['title'] + '\n' + t['result'] for t in children)
                    parent['version'] += 1
                    self.put(db, 'tasks', parent)
                    changed = True
            if not changed:
                break
