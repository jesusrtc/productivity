"""Submitted agent requests, retained across a terminal's conversation resets.

Provider transcripts are authoritative: PTY keystrokes also contain drafts,
cursor movement, menus and shell commands, so they are never stored as prompts.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import threading

from lab import paths

_LOCK = threading.RLock()
_CACHE = {}
_TRANSCRIPTS = {}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json_lines(path):
    if not path.is_file():
        return []
    stat = path.stat()
    cached = _TRANSCRIPTS.get(str(path))
    start, events = 0, []
    if cached and cached[0] == stat.st_ino and stat.st_size >= cached[1] and (stat.st_size > cached[1] or stat.st_mtime_ns == cached[2]):
        start, events = cached[1], list(cached[3])
    with path.open('rb') as handle:
        handle.seek(start)
        data = handle.read()
    # A writer may still be appending its final line. Read that line again on
    # the next poll instead of losing a submitted turn forever.
    end = data.rfind(b'\n') + 1
    for line in data[:end].splitlines():
        try:
            event = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(event, dict) and (event.get('type') in {'user', 'user.message'} or (
                event.get('type') == 'event_msg' and isinstance(event.get('payload'), dict)
                and event['payload'].get('type') == 'user_message')):
            events.append(event)
    if len(_TRANSCRIPTS) >= 32:
        _TRANSCRIPTS.pop(next(iter(_TRANSCRIPTS)))
    _TRANSCRIPTS[str(path)] = (stat.st_ino, start+end, stat.st_mtime_ns, events)
    return events


def _records(row):
    from core.routes.term import _message_content_text, _clean_agent_task, _request_clears_session

    agent, thread = row.get('agent'), row.get('agent_session_id') or row.get('claude_session_id')
    if agent not in {'claude', 'codex', 'copilot'} or not isinstance(thread, str):
        return [], ()
    # IDs are used in provider-owned paths. Never accept path components.
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,150}', thread):
        return [], ()
    sources, items = [], []
    if agent == 'claude':
        slug = re.sub(r'[^A-Za-z0-9]', '-', str(Path(row.get('cwd') or '').resolve()))
        sources = [Path.home()/'.claude/projects'/slug/f'{thread}.jsonl']
    elif agent == 'copilot':
        home = Path(os.environ.get('COPILOT_HOME') or Path.home()/'.copilot')
        sources = [home/'session-state'/thread/'events.jsonl']
    else:
        home = Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex')
        state, history = home/'state_5.sqlite', home/'thread_history_1.sqlite'
        sources = [state, Path(f'{state}-wal'), history, Path(f'{history}-wal')]
        if state.is_file():
            try:
                with closing(sqlite3.connect(f'file:{state}?mode=ro', uri=True, timeout=.2)) as conn:
                    result = conn.execute('SELECT rollout_path FROM threads WHERE id = ?', (thread,)).fetchone()
                if result and result[0]:
                    sources.append(Path(result[0]))
            except sqlite3.Error:
                pass
    fingerprint = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in sources if p.is_file())
    cache_key = (agent, thread, row.get('cwd'))
    cached = _CACHE.get(cache_key)
    if cached and cached[0] == fingerprint:
        return cached[1], fingerprint

    occurrences = {}

    def add(raw, timestamp=None):
        if not isinstance(raw, str):
            return
        # Projection databases can lag behind the original transcript. Keep
        # stable keys when the same turns later become available there too.
        digest = hashlib.sha256(raw.strip().encode()).hexdigest()
        occurrences[digest] = occurrences.get(digest, 0) + 1
        key = f'{digest}:{occurrences[digest]}'
        if _request_clears_session(raw) or raw.strip().lower() == '/new':
            items.append({'key':str(key), 'type':'boundary', 'text':'Session cleared' if '/clear' in raw.lower() else 'New session',
                          'command':'/clear' if '/clear' in raw.lower() else '/new', 'timestamp':timestamp})
        elif _clean_agent_task(raw, max_len=max(280, len(raw)+1)):
            items.append({'key':str(key), 'type':'request', 'text':raw.strip(), 'timestamp':timestamp})

    if agent == 'claude':
        for event in _json_lines(sources[0]):
            message = event.get('message')
            if (event.get('type') == 'user' and event.get('isSidechain') is not True
                    and event.get('userType') in (None, 'external') and not event.get('toolUseResult')
                    and not event.get('sourceToolAssistantUUID') and isinstance(message, dict)):
                add(_message_content_text(message.get('content')), event.get('timestamp'))
    elif agent == 'copilot':
        for event in _json_lines(sources[0]):
            data = event.get('data')
            if event.get('type') == 'user.message' and isinstance(data, dict):
                add(_message_content_text(data.get('content')), event.get('timestamp'))
    else:
        rollout = sources[-1] if len(sources) > 4 else None
        events = _json_lines(rollout) if rollout else []
        # event_msg is the accepted user turn, including pasted/edited text.
        accepted = [e for e in events if e.get('type') == 'event_msg'
                    and isinstance(e.get('payload'), dict) and e['payload'].get('type') == 'user_message']
        if accepted:
            for event in accepted:
                add(event['payload'].get('message'), event.get('timestamp'))
        elif history.is_file():
            try:
                with closing(sqlite3.connect(f'file:{history}?mode=ro', uri=True, timeout=.2)) as conn:
                    records = conn.execute("SELECT item_json, rollout_ordinal FROM thread_items WHERE thread_id = ? AND item_type = 'userMessage' ORDER BY rollout_ordinal", (thread,)).fetchall()
                for raw, ordinal in records:
                    try:
                        item = json.loads(raw)
                    except (ValueError, TypeError):
                        continue
                    add(_message_content_text(item.get('content')))
            except sqlite3.Error:
                pass
    if len(_CACHE) >= 256:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[cache_key] = (fingerprint, items)
    return items, fingerprint


def _connect():
    path = paths.global_config_dir()/'terminal-requests.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=2)
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS terminals (name TEXT PRIMARY KEY, provider TEXT, thread TEXT, fingerprint TEXT, pending_command TEXT);
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY, terminal TEXT NOT NULL, provider TEXT, thread TEXT,
            source_key TEXT, type TEXT NOT NULL, text TEXT NOT NULL, command TEXT, timestamp TEXT,
            UNIQUE(terminal, provider, thread, source_key)
        );
        CREATE INDEX IF NOT EXISTS terminal_requests_name ON entries(terminal, id);
    ''')
    return conn


def sync(row):
    name, provider = row.get('name'), row.get('agent')
    thread = row.get('agent_session_id') or row.get('claude_session_id')
    if not name or not thread or provider not in {'codex', 'claude', 'copilot'}:
        return
    with _LOCK:
        items, fingerprint = _records(row)
        fingerprint = json.dumps(fingerprint)
        with closing(_connect()) as conn, conn:
            previous = conn.execute('SELECT provider, thread, fingerprint, pending_command FROM terminals WHERE name = ?', (name,)).fetchone()
            if previous and tuple(previous)[:3] == (provider, thread, fingerprint):
                return
            pending = previous['pending_command'] if previous else None
            if not previous or tuple(previous)[:2] != (provider, thread):
                if not pending:
                    conn.execute('INSERT INTO entries(terminal, provider, thread, type, text, timestamp) VALUES(?,?,?,?,?,?)',
                                 (name, provider, thread, 'boundary', 'Session refreshed' if previous else 'Session started', _now() if previous else None))
                pending = None
            for item in items:
                if pending and item.get('command') == pending and not conn.execute(
                        'SELECT 1 FROM entries WHERE terminal = ? AND provider = ? AND thread = ? AND source_key = ?',
                        (name, provider, thread, item['key'])).fetchone():
                    # Merge the slash command observed at Enter with its
                    # later provider event instead of showing two separators.
                    conn.execute('UPDATE entries SET source_key = ? WHERE id = (SELECT MAX(id) FROM entries WHERE terminal = ? AND command = ?)',
                                 (item['key'], name, pending))
                    pending = None
                    continue
                conn.execute('INSERT OR IGNORE INTO entries(terminal, provider, thread, source_key, type, text, command, timestamp) VALUES(?,?,?,?,?,?,?,?)',
                             (name, provider, thread, item['key'], item['type'], item['text'], item.get('command'), item.get('timestamp')))
            conn.execute('INSERT OR REPLACE INTO terminals VALUES(?,?,?,?,?)', (name, provider, thread, fingerprint, pending))


def command(row, value):
    """Retain an explicitly submitted /clear or /new, before thread discovery."""
    sync(row)
    with _LOCK, closing(_connect()) as conn, conn:
        name = row['name']
        previous = conn.execute('SELECT pending_command FROM terminals WHERE name = ?', (name,)).fetchone()
        if previous and previous[0] == value:
            return
        latest = conn.execute('SELECT id, type, text, command FROM entries WHERE terminal = ? ORDER BY id DESC LIMIT 1', (name,)).fetchone()
        if latest and latest['type'] == 'boundary' and latest['command'] == value:
            return  # The provider already persisted this command.
        label = 'Session cleared' if value == '/clear' else 'New session'
        if latest and latest['type'] == 'boundary' and latest['text'] == 'Session refreshed':
            conn.execute('UPDATE entries SET text = ?, command = ? WHERE id = ?', (label, value, latest['id']))
            return  # Thread discovery won the race; annotate that separator.
        conn.execute('INSERT INTO entries(terminal, provider, thread, type, text, command, timestamp) VALUES(?,?,?,?,?,?,?)',
                     (name, row.get('agent'), row.get('agent_session_id') or row.get('claude_session_id'),
                      'boundary', label, value, _now()))
        conn.execute('INSERT INTO terminals(name, provider, thread, pending_command) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET pending_command = excluded.pending_command',
                     (name, row.get('agent'), row.get('agent_session_id') or row.get('claude_session_id'), value))


def history(name):
    with _LOCK, closing(_connect()) as conn:
        return [dict(row) for row in conn.execute('SELECT id, provider, thread, type, text, command, timestamp FROM entries WHERE terminal = ? ORDER BY id', (name,))]
