"""Agent-reported file changes by request/assignment, independent of task metadata."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

from lab import paths, terminal_context


def identity(terminal=None):
    terminal = terminal or terminal_context.current()
    created, socket = terminal_context.tmux(terminal.socket, 'display-message', '-p',
        '-t', terminal.pane, '#{session_created}\t#{socket_path}').split('\t', 1)
    return {'name':terminal.name, 'tmux_socket':str(Path(socket).resolve()),
            'tmux_id':terminal.session_id, 'created':int(created)}


def key(terminal):
    value = {**terminal, 'tmux_socket':str(Path(terminal['tmux_socket']).resolve())}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _connect():
    path = paths.global_config_dir() / 'agent-work.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600); os.close(fd)
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS assignments (
        id TEXT PRIMARY KEY, terminal_key TEXT NOT NULL, terminal TEXT NOT NULL,
        title TEXT NOT NULL, request TEXT NOT NULL, context TEXT NOT NULL,
        parent_id TEXT REFERENCES assignments(id), status TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '', created REAL NOT NULL, updated REAL NOT NULL
      );
      CREATE INDEX IF NOT EXISTS assignments_terminal ON assignments(terminal_key, created);
      CREATE TABLE IF NOT EXISTS current_assignment (
        terminal_key TEXT PRIMARY KEY, assignment_id TEXT REFERENCES assignments(id)
      );
      CREATE TABLE IF NOT EXISTS files (
        id TEXT PRIMARY KEY, assignment_id TEXT NOT NULL REFERENCES assignments(id),
        path TEXT NOT NULL, operation TEXT NOT NULL, previous_path TEXT,
        reported REAL NOT NULL, sha256 TEXT, size INTEGER,
        UNIQUE(assignment_id, path)
      );
    ''')
    return conn


def current(terminal):
    with closing(_connect()) as conn:
        row = conn.execute('SELECT a.* FROM assignments a JOIN current_assignment c ON a.id=c.assignment_id WHERE c.terminal_key=?',
                           (key(terminal),)).fetchone()
        return dict(row) if row else None


def start(terminal, title, *, request='', context='', parent_id=None, assignment_id=None, register=False):
    if (not title.strip() or len(title) > 200 or len(request) > 64000 or len(context) > 64000
            or any('\x00' in value for value in (title,request,context))):
        raise ValueError('Use a title of 1–200 characters and request/context of at most 64000 characters each, without NUL bytes')
    ident = str(uuid.UUID(assignment_id)) if assignment_id else str(uuid.uuid4())
    parent_id = str(uuid.UUID(parent_id)) if parent_id else None
    now = time.time(); owner = key(terminal)
    with closing(_connect()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        old = conn.execute('SELECT * FROM assignments WHERE id=?', (ident,)).fetchone()
        if old and old['terminal_key'] != owner:
            raise ValueError('This assignment belongs to a different agent terminal')
        if parent_id:
            if parent_id == ident or not conn.execute('SELECT 1 FROM assignments WHERE id=?', (parent_id,)).fetchone():
                raise ValueError('Choose an existing parent assignment')
            ancestor = parent_id; seen = {ident}
            while ancestor:
                if ancestor in seen:
                    raise ValueError('Assignments cannot form a cycle')
                seen.add(ancestor)
                row = conn.execute('SELECT parent_id FROM assignments WHERE id=?', (ancestor,)).fetchone()
                ancestor = row['parent_id'] if row else None
        if old and register:
            # A fast child may already have resumed/finished before its launcher
            # registers the parent brief. Attach metadata without reopening work.
            conn.execute('UPDATE assignments SET title=?,request=?,context=?,parent_id=? WHERE id=?',
                (title.strip(),request,context,parent_id,ident))
        elif old:
            conn.execute('UPDATE assignments SET status=?, updated=? WHERE id=?', ('working', now, ident))
        else:
            conn.execute('INSERT INTO assignments VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (ident, owner, json.dumps(terminal), title.strip(), request, context, parent_id, 'working', '', now, now))
        if not (register and old):
            conn.execute('INSERT OR REPLACE INTO current_assignment VALUES(?,?)', (owner, ident))
        return dict(conn.execute('SELECT * FROM assignments WHERE id=?', (ident,)).fetchone())


def finish(terminal, summary='', state='finished'):
    assignment = current(terminal)
    if not assignment:
        raise ValueError('Start a request/assignment with lab agents work start first')
    if state not in ('finished', 'attention') or len(summary) > 8000:
        raise ValueError('Invalid assignment state or summary')
    with closing(_connect()) as conn, conn:
        conn.execute('UPDATE assignments SET status=?, summary=?, updated=? WHERE id=?',
                     (state, summary, time.time(), assignment['id']))
    return {**assignment, 'status':state, 'summary':summary}


def record(terminal, file_paths, operation='modified', previous_path=None, assignment_id=None):
    if operation not in ('created', 'modified', 'deleted', 'renamed') or not file_paths or len(file_paths) > 200:
        raise ValueError('Choose an operation and 1–200 files')
    assignment = current(terminal)
    if assignment_id:
        with closing(_connect()) as conn:
            row = conn.execute('SELECT * FROM assignments WHERE id=? AND terminal_key=?',
                               (str(uuid.UUID(assignment_id)), key(terminal))).fetchone()
            assignment = dict(row) if row else None
    if not assignment:
        raise ValueError('Start your own request/assignment before recording files')
    if operation == 'renamed' and (len(file_paths) != 1 or not previous_path):
        raise ValueError('A rename needs one destination and --previous-path')
    records = []
    for value in file_paths:
        path = Path(os.path.abspath(Path(value).expanduser()))
        if operation != 'deleted' and not path.is_file():
            raise ValueError(f'File not found: {path}')
        digest = None; size = None
        if path.is_file():
            size = path.stat().st_size
            if size <= 2_000_000:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append((str(path), digest, size))
    with closing(_connect()) as conn, conn:
        for path, digest, size in records:
            old = conn.execute('SELECT * FROM files WHERE assignment_id=? AND path=?', (assignment['id'],path)).fetchone()
            action = 'created' if old and old['operation'] == 'created' and operation == 'modified' else operation
            conn.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(assignment_id,path) DO UPDATE SET operation=excluded.operation, previous_path=COALESCE(excluded.previous_path,files.previous_path), reported=excluded.reported, sha256=excluded.sha256,size=excluded.size',
                (str(uuid.uuid4()),assignment['id'],path,action,
                 os.path.abspath(os.path.expanduser(previous_path)) if previous_path else None,time.time(),digest,size))
        conn.execute('UPDATE assignments SET updated=? WHERE id=?', (time.time(),assignment['id']))
    return {'assignment_id':assignment['id'], 'recorded':[path for path, _, _ in records], 'count':len(records)}


def history(terminal, include_children=False):
    with closing(_connect()) as conn:
        rows = [dict(row) for row in conn.execute('SELECT * FROM assignments WHERE terminal_key=? ORDER BY created DESC', (key(terminal),))]
        if include_children:
            seen = {row['id'] for row in rows}; frontier = list(seen)
            while frontier:
                parent_id = frontier.pop()
                for child in conn.execute('SELECT * FROM assignments WHERE parent_id=?', (parent_id,)):
                    if child['id'] not in seen:
                        seen.add(child['id']);frontier.append(child['id']);rows.append(dict(child))
        # Keep each request next to its delegated descendants, even when the
        # parent has newer requests of its own.
        known = {row['id'] for row in rows}; children = {}
        for row in rows:
            children.setdefault(row['parent_id'], []).append(row)
        ordered = []; visited = set()
        stack = list(reversed([row for row in rows if row['parent_id'] not in known]))
        while stack:
            row = stack.pop()
            if row['id'] in visited:
                continue
            visited.add(row['id']); ordered.append(row)
            stack.extend(sorted(children.get(row['id'], []), key=lambda item:item['created']))
        rows = ordered
        for row in rows:
            row['terminal'] = json.loads(row['terminal']);row.pop('terminal_key',None)
            row['files'] = [dict(file) for file in conn.execute('SELECT * FROM files WHERE assignment_id=? ORDER BY reported DESC', (row['id'],))]
        return {'terminal':terminal, 'assignments':rows}


def file_record(ident):
    with closing(_connect()) as conn:
        row = conn.execute('SELECT f.*, a.title, a.terminal FROM files f JOIN assignments a ON a.id=f.assignment_id WHERE f.id=?', (ident,)).fetchone()
        return dict(row) if row else None
