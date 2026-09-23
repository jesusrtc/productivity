"""Read explicit main-agent response boundaries, never terminal output silence.

Only scoped terminal lists call this. Reads are bounded and fingerprint-cached;
missing, changing, or unrecognized transcripts leave the state unknown.
"""
from __future__ import annotations

from collections import OrderedDict
from contextlib import closing
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading

TAIL_BYTES = 2 * 1024 * 1024
_CACHE: OrderedDict = OrderedDict()
_LOCK = threading.Lock()


def _stamp(event: dict) -> float:
    try:
        value = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
        return value.timestamp() if value.tzinfo else 0
    except (KeyError, TypeError, ValueError, AttributeError):
        return 0


def response_state(agent: str, events: list[dict]) -> dict:
    state = {'state': 'unknown'}
    turn = None
    final_message = False

    def set_state(value, event=None):
        nonlocal state
        state = {'state': value}
        if value == 'completed' and event:
            stamp = _stamp(event)
            if stamp <= 0:
                state = {'state': 'unknown'}
                return
            token = event.get('uuid') or event.get('id') or hashlib.sha256(
                json.dumps(event, sort_keys=True).encode()).hexdigest()[:24]
            state.update(completed_at=stamp, completion_id=str(token))

    for event in events:
        data = event.get('data') or {}
        if not isinstance(data, dict):
            set_state('unknown')
            continue
        if (event.get('isSidechain') or event.get('parent_tool_use_id')
                or event.get('agentId') or data.get('parentToolCallId')):
            continue
        kind = event.get('type')
        if agent == 'codex' and kind == 'event_msg':
            payload = event.get('payload') or {}
            if not isinstance(payload, dict):
                set_state('unknown')
                continue
            kind = payload.get('type')
            if kind in {'task_started', 'user_message'}:
                turn = payload.get('turn_id') or turn
                set_state('working')
            elif kind == 'task_complete':
                if turn and payload.get('turn_id') != turn:
                    continue
                set_state('error' if payload.get('error') else 'completed', event)
            elif kind == 'turn_aborted':
                set_state('interrupted')
            elif kind == 'error':
                set_state('error')
            elif kind in {'exec_approval_request', 'apply_patch_approval_request',
                          'request_user_input'}:
                set_state('waiting')
        elif agent == 'claude':
            message = event.get('message') or {}
            if not isinstance(message, dict):
                set_state('unknown')
                continue
            if kind == 'user':
                set_state('working')
            elif kind == 'assistant':
                reason = message.get('stop_reason')
                if event.get('isApiErrorMessage') or event.get('error'):
                    set_state('error')
                elif reason in {'end_turn', 'stop_sequence'}:
                    set_state('completed', event)
                else:
                    # Includes tool use, streaming fragments and token limits.
                    set_state('working')
            elif kind == 'system' and event.get('subtype') == 'turn_duration':
                # Also emitted after interruptions: the CLI stopped working,
                # but this does not prove it produced a completed response.
                if state['state'] in {'working', 'waiting'}:
                    set_state('unknown')
        elif agent == 'copilot':
            if kind == 'session.resume':
                turn, final_message = None, False
                # Opening a conversation is not a new request. Discard any
                # in-flight state left by its previous process.
                if state['state'] in {'working', 'waiting'}:
                    set_state('unknown')
            elif kind == 'user.message':
                turn, final_message = None, False
                set_state('working')
            elif kind == 'assistant.turn_start':
                turn, final_message = data.get('turnId'), False
                set_state('working')
            elif kind == 'assistant.message':
                # Copilot ends a model turn after *every* tool batch. Only a
                # matching completed turn with a non-tool response is final.
                turn = data.get('turnId')
                final_message = bool(data.get('content')) and not data.get('toolRequests')
                set_state('working')
            elif kind == 'assistant.turn_end':
                if final_message and turn and data.get('turnId') == turn:
                    set_state('completed', event)
                final_message = False
            elif kind in {'permission.requested', 'user_input.requested'}:
                final_message = False
                set_state('waiting')
            elif kind in {'tool.execution_start', 'tool.execution_complete'}:
                final_message = False
                set_state('working')
            elif kind == 'session.error':
                final_message = False
                set_state('error')
            elif kind in {'abort', 'session.shutdown'}:
                final_message = False
                set_state('interrupted')
    return state


def read_activity(agent: str, path: Path) -> dict:
    key = (agent, str(path))
    try:
        stat = path.stat()
        fingerprint = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
        with _LOCK:
            cached = _CACHE.get(key)
            if cached and cached[0] == fingerprint:
                _CACHE.move_to_end(key)
                return dict(cached[1])
        with path.open('rb') as stream:
            start = max(0, stat.st_size - TAIL_BYTES)
            stream.seek(start)
            raw = stream.read(TAIL_BYTES)
            after = os.fstat(stream.fileno())
        if fingerprint != (after.st_ino, after.st_size, after.st_mtime_ns):
            return {'state': 'unknown'}
        # Never reuse the previous completion while a new event is half-written.
        if raw and not raw.endswith(b'\n'):
            return {'state': 'unknown'}
        lines = raw.splitlines()
        if start:
            lines = lines[1:]
        events = [json.loads(line) for line in lines if line.strip()]
        if not all(isinstance(event, dict) for event in events):
            return {'state': 'unknown'}
        result = response_state(agent, events)
        with _LOCK:
            _CACHE[key] = (fingerprint, result)
            _CACHE.move_to_end(key)
            while len(_CACHE) > 256:
                _CACHE.popitem(last=False)
        return dict(result)
    except (OSError, ValueError, UnicodeError):
        return {'state': 'unknown'}


def enrich(rows: list[dict]) -> None:
    """Use the exact conversation ID already resolved for each terminal."""
    codex_paths = {}
    ids = {r.get('agent_session_id') for r in rows if r.get('agent') == 'codex'} - {None, ''}
    if ids:
        database = Path.home() / '.codex/state_5.sqlite'
        try:
            with closing(sqlite3.connect(f'file:{database}?mode=ro', uri=True, timeout=.2)) as conn:
                codex_paths = dict(conn.execute(
                    f"SELECT id, rollout_path FROM threads WHERE id IN ({','.join('?' for _ in ids)})",
                    sorted(ids),
                ).fetchall())
        except sqlite3.Error:
            pass
    for row in rows:
        agent = row.get('agent')
        if agent not in {'codex', 'claude', 'copilot'}:
            continue
        row['agent_activity'] = {'state': 'unknown'}
        identifier = row.get('agent_session_id')
        if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', identifier):
            continue
        path = None
        if agent == 'codex' and codex_paths.get(identifier):
            path = Path(codex_paths[identifier])
        elif agent == 'claude' and row.get('cwd'):
            slug = re.sub(r'[^A-Za-z0-9]', '-', str(Path(row['cwd']).resolve()))
            path = Path.home() / '.claude/projects' / slug / (identifier + '.jsonl')
        elif agent == 'copilot':
            home = Path(os.environ.get('COPILOT_HOME') or Path.home() / '.copilot')
            path = home / 'session-state' / identifier / 'events.jsonl'
        if path:
            row['agent_activity'] = read_activity(agent, path)
