"""Resumable Assistant terminals with a bounded idle cache and memory admission.

Only entries in this registry are managed; ordinary terminals are untouched.
A single low-frequency worker retires confirmed-idle agents, even with no browser.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

from fastapi import HTTPException
from lab import assistant_records as records, assistant_documents as documents, settings, tmux_sockets

log = logging.getLogger(__name__)
_LOCK = threading.RLock()
_INPUT = {}  # name -> [last input, last submission, unsent input]; RAM only
_STOP = threading.Event()
_WORKER = None
TAIL_BYTES = 512 * 1024
TICK_SECONDS = 60
STARTUP_GRACE_SECONDS = 10
MEMORY_RESERVE_BYTES = 1024 ** 3


def registry_path(root):
    return root/'.lab/state/document-terminals.json'


def _load(root):
    path = registry_path(root)
    if not path.exists():
        return {}
    value = json.loads(path.read_text())
    if value.get('schema') != 1 or not isinstance(value.get('terminals'), dict):
        raise ValueError('Invalid document terminal registry')
    return value['terminals']


def _save(root, entries):
    records.write_json(registry_path(root), {'schema':1, 'terminals':entries})


def _context_path(root, key):
    return root/'.lab/state/document-context'/f'{key}.json'


def _identity(root, reference):
    source, metadata, _ = records.resolve(root, reference, 'documents')
    owner, _, _ = documents.unpack(documents.physical(source).read_bytes())
    identity = owner['type'] + ':' + owner['id']
    key = hashlib.sha256(identity.encode()).hexdigest()[:24]
    return key, owner, documents.physical(source), metadata


def input_callback(name):
    """Bind once per WS; input updates timestamps and draft state in RAM."""
    slot = _INPUT.get(name)
    if slot is None:
        return None
    def used(data):
        # Mouse reports do not change an agent's prompt. Bracketed pastes can
        # contain newlines without submitting; preserve those drafts too.
        if re.fullmatch(r'\x1b(?:\[<\d+;\d+;\d+[Mm]|\[[?0-9;]*[cRn]|\[[IO]|\]\d+;[^\x1b\x07]*(?:\x07|\x1b\\))', data):
            return
        slot[0] = time.time()
        if '\x1b[200~' not in data and data.endswith('\r'):
            slot[1], slot[2] = slot[0], False
        else:
            slot[2] = True
    return used


def _merge_input(entry):
    values = _INPUT.get(entry.get('name'), [0, 0, entry.get('unsent_input', False)])
    entry['last_used'] = max(entry.get('last_used',0), values[0])
    entry['last_submit'] = max(entry.get('last_submit',0), values[1])
    entry['unsent_input'] = values[2]


def _tmux(entry, *args):
    from core.routes import term
    return subprocess.run(term._tmux_command(entry['socket'], *args),
        capture_output=True, text=True, env=term._tmux_child_env(), timeout=5)


def _probe(entry):
    """None is missing; exceptions mean unknown, never permission to kill."""
    # display-message can succeed with "|||" for a missing target. list-panes
    # targets the exact session and reliably fails when it no longer exists.
    response = _tmux(entry, 'list-panes', '-s', '-t', '=' + entry['name'], '-F',
        '#{session_created}|#{pane_pid}|#{pane_tty}|#{pane_dead}|#{session_attached}')
    if response.returncode:
        error = (response.stderr or '').lower()
        if tmux_sockets.is_no_server_error(error) or "can't find" in error or 'no such session' in error:
            return None
        raise RuntimeError('Cannot inspect document terminal')
    values = response.stdout.strip().split('|')
    if len(values) != 5 or not all(values[i].isdigit() for i in (0, 1, 4)):
        raise RuntimeError('Unrecognized terminal identity')
    return {'created':int(values[0]), 'pid':int(values[1]), 'tty':values[2],
            'dead':values[3]=='1', 'attached':int(values[4])}


def _owns(entry, probe):
    return probe and entry.get('pane_pid') == probe['pid'] and entry.get('tmux_created') == probe['created']


def _timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z','+00:00')).timestamp()
    except (ValueError, TypeError):
        return 0


def trace_state(agent, events, last_submit=0):
    """Require an explicit turn boundary; silence/low CPU never proves idle."""
    state, finished = 'unknown', 0
    for event in events:
        if event.get('isSidechain') or event.get('parent_tool_use_id'):
            continue
        kind = event.get('type')
        stamp = _timestamp(event.get('timestamp'))
        if agent == 'codex' and kind == 'event_msg':
            kind = (event.get('payload') or {}).get('type')
            if kind in {'task_started','user_message'}:
                state = 'busy'
            elif kind in {'task_complete','turn_aborted'}:
                state, finished = 'idle', stamp
        elif agent == 'claude':
            message = event.get('message') or {}
            if kind == 'user' or kind == 'assistant' and message.get('stop_reason') == 'tool_use':
                state = 'busy'
            elif kind == 'assistant' and message.get('stop_reason') in {'end_turn','stop_sequence'} or kind == 'system' and event.get('subtype') == 'turn_duration':
                state, finished = 'idle', stamp
        elif agent == 'copilot':
            if kind in {'user.message','assistant.turn_start','tool.execution_start','permission.requested'}:
                state = 'busy'
            elif kind in {'assistant.turn_end','session.idle','session.shutdown'}:
                state, finished = 'idle', stamp
    # A new submission may precede the provider's first trace event.
    if last_submit > finished:
        return 'busy', finished
    return state, finished


def _transcript(entry, probe):
    agent, identifier = entry['agent'], entry.get('conversation_id')
    if agent == 'codex':
        from core.routes import term
        match = term._codex_session_metadata_by_tty({probe['tty']}, {entry['cwd']}).get(term._tty_key(probe['tty']))
        if match:
            identifier = entry['conversation_id'] = match[0]
        if not identifier:
            return None
        database = Path.home()/'.codex/state_5.sqlite'
        if not database.is_file():
            return None
        with closing(sqlite3.connect(f'file:{database}?mode=ro',uri=True,timeout=.2)) as connection:
            row = connection.execute('SELECT rollout_path FROM threads WHERE id = ?', (identifier,)).fetchone()
        return Path(row[0]) if row and row[0] else None
    if not identifier:
        return None
    if agent == 'claude':
        slug = re.sub(r'[^A-Za-z0-9]', '-', entry['cwd'])
        return Path.home()/'.claude/projects'/slug/(identifier+'.jsonl')
    return Path.home()/'.copilot/session-state'/identifier/'events.jsonl'


def _idle(entry, probe):
    if probe['dead']:
        return True
    try:
        path = _transcript(entry, probe)
        if entry.get('unsent_input'):
            entry['work_state'] = 'draft'
            return False
        events, malformed, truncated = [], False, False
        if path and path.is_file():
            with path.open('rb') as stream:
                offset = max(0, path.stat().st_size - TAIL_BYTES)
                truncated = offset > 0
                stream.seek(offset)
                lines = stream.read(TAIL_BYTES).splitlines()
            for line in lines[1:] if offset else lines:
                try:
                    event = json.loads(line)
                    if isinstance(event, dict):
                        events.append(event)
                    else:
                        malformed = True
                except (ValueError, UnicodeDecodeError):
                    malformed = True
        state, finished = trace_state(entry['agent'], events, entry.get('last_submit',0))
        entry['last_used'] = max(entry['last_used'], finished)
        entry['work_state'] = state
        if state != 'unknown':
            entry['had_work'] = True
        if state == 'busy':
            return False
        if state == 'idle':
            # Never discard a conversation before its exact resume ID is saved.
            return not malformed and bool(entry.get('conversation_id'))
        # Opening an interactive CLI sends no prompt or agent task.
        return not (entry.get('last_submit') or entry.get('had_work') or malformed or truncated) and all(
            event.get('type') in {'session_meta', 'session.start', 'session.model_change'}
            for event in events)
    except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError):
        entry['work_state'] = 'unknown'
        return False


def _retire(root, entry, probe, *, automatic=False):
    from core.routes import term
    if probe and not _owns(entry, probe):
        raise RuntimeError('Document terminal identity changed; leaving it untouched')
    if probe:
        current = _probe(entry)
        if current and (not _owns(entry, current) or automatic and current.get('attached') and not current['dead']):
            raise RuntimeError('Terminal reattached or changed during cleanup')
        checked_activity = (entry['last_used'], entry.get('last_submit', 0))
        _merge_input(entry)
        if current and not current['dead'] and (checked_activity != (entry['last_used'], entry.get('last_submit', 0)) or entry.get('unsent_input')):
            raise HTTPException(409, 'New terminal input arrived; keeping the agent running.')
        result = _tmux(entry,'kill-session','-t',entry['name'])
        if result.returncode and _probe(entry) is not None:
            raise RuntimeError('Could not stop document terminal')
    meta = term._load_meta(root)
    if meta.get(entry['name'],{}).get('document_key') == entry['key']:
        meta.pop(entry['name'],None)
        term._save_meta(root,meta)
        term._invalidate_workspace_term_caches()
    _INPUT.pop(entry['name'],None)
    entry['state'] = 'sleeping'
    entry['work_state'] = 'idle'
    entry['unsent_input'] = False


def _forget(root, entries, key):
    entry = entries.pop(key)
    _INPUT.pop(entry['name'],None)
    _context_path(root,key).unlink(missing_ok=True)


def _remember(root, entry, probe):
    from core.routes import term
    entry.update(state='running', pane_pid=probe['pid'], tmux_created=probe['created'])
    _INPUT.setdefault(entry['name'], [entry['last_used'], entry.get('last_submit', 0), entry.get('unsent_input', False)])
    meta = term._load_meta(root)
    meta[entry['name']] = dict(workspace_id=term.ASSISTANT_WORKSPACE_ID,
        logical_name=entry['logical_name'], kind='claude', agent=entry['agent'], cwd=str(root),
        created_at=probe['created'], tmux_socket=entry['socket'], label=entry['title'],
        agent_session_id=entry.get('conversation_id'), document_key=entry['key'])
    term._save_meta(root, meta)
    term._invalidate_workspace_term_caches()


def _reconcile(root, entry):
    """Recover an interrupted spawn; never adopt a same-name foreign session."""
    probe = _probe(entry)
    if probe is None:
        _retire(root, entry, None)
    elif entry['state'] == 'starting':
        marker = _tmux(entry, 'show-environment', '-t', entry['name'], 'LAB_DOCUMENT_KEY')
        if marker.returncode or marker.stdout.strip() != 'LAB_DOCUMENT_KEY=' + entry['key']:
            raise RuntimeError('Document terminal ownership is unknown')
        _remember(root, entry, probe)
    elif not _owns(entry, probe):
        raise RuntimeError('Document terminal identity changed')
    if probe and probe['dead']:
        _retire(root, entry, probe)
        return None
    return probe


def _memory_available():
    """Read OS memory headroom only during admission/cleanup, never on input."""
    if sys.platform == 'darwin':
        result = subprocess.run(['/usr/bin/memory_pressure', '-Q'],
            capture_output=True, text=True, timeout=3)
        total = re.search(r'The system has (\d+)', result.stdout)
        free = re.search(r'System-wide memory free percentage:\s*(\d+)%', result.stdout)
        if result.returncode or not total or not free:
            raise OSError('Cannot read system memory headroom')
        total = int(total[1])
        return total, total * int(free[1]) // 100
    values = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        values[key] = int(value.split()[0]) * 1024
    return values['MemTotal'], values['MemAvailable']


def _memory_ready(entries, now):
    try:
        total, available = _memory_available()
        # Reserve headroom for the OS, other applications and agents still
        # starting up whose full footprint is not visible in the OS sample yet.
        starting = sum(e.get('state') in {'starting', 'running'} and
            now - e.get('started_at', 0) < STARTUP_GRACE_SECONDS for e in entries.values())
        reserve = max(MEMORY_RESERVE_BYTES, total * .15) + starting * (512 * 1024 ** 2)
        return available > reserve, 'memory'
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return False, 'memory_check'


def _can_forget(entry):
    # A lightweight document→conversation bookmark must outlive the process.
    return not (entry.get('conversation_id') or entry.get('last_submit') or
                entry.get('had_work') or entry.get('unsent_input'))


def _sweep(root, entries, policy, now, *, incoming=None, pressure=False):
    idle = []
    for key, entry in list(entries.items()):
        _merge_input(entry)
        age = max(0, now - entry['last_used'])
        if entry['state'] == 'sleeping':
            if _can_forget(entry) and age >= policy['expireHours'] * 3600:
                _forget(root, entries, key)
            continue
        try:
            probe = _reconcile(root, entry)
            if not probe:
                if _can_forget(entry) and age >= policy['expireHours'] * 3600:
                    _forget(root, entries, key)
                continue
            # Checkpoint the conversation while the process still exists, even
            # when it is visible. Attached panes, drafts and working agents stay.
            safe = _idle(entry, probe)
            if safe:
                idle.append((key, entry, probe))
        except (OSError, RuntimeError, subprocess.SubprocessError, HTTPException):
            entry['work_state'] = 'unknown'
            log.warning('Could not inspect/retire a managed document terminal', exc_info=True)
    # maxRunning is the legacy settings key; it now budgets READY/IDLE
    # processes only. Working agents never consume an arbitrary document slot.
    budget = max(0, policy['maxRunning'] - (1 if incoming else 0))
    excess = max(0, len(idle) - budget)
    for key, entry, probe in sorted(idle, key=lambda item:item[1]['last_used']):
        if key == incoming or probe.get('attached'):
            continue
        age = max(0, now - entry['last_used'])
        expired = age >= policy['sleepMinutes'] * 60
        if not (expired or pressure or excess > 0):
            continue
        try:
            _retire(root, entry, probe, automatic=True)
            excess = max(0, excess - 1)
            if _can_forget(entry) and age >= policy['expireHours'] * 3600:
                _forget(root, entries, key)
        except (OSError, RuntimeError, subprocess.SubprocessError, HTTPException):
            entry['work_state'] = 'unknown'
            log.warning('Could not release an idle document terminal', exc_info=True)


def sweep(root):
    with _LOCK:
        if not registry_path(root).exists():
            return
        entries = _load(root)
        if not entries:
            return
        before = json.dumps(entries, sort_keys=True)
        policy = settings.load(root)['documentTerminals']
        ready, _ = _memory_ready(entries, time.time())
        _sweep(root, entries, policy, time.time(), pressure=not ready)
        if json.dumps(entries, sort_keys=True) != before:
            _save(root, entries)


def _argv(root, entry):
    """Exact saved conversation IDs; never resume whichever thread was last."""
    agent, identifier = entry['agent'], entry.get('conversation_id')
    args = []
    if agent == 'claude':
        slug = re.sub(r'[^A-Za-z0-9]', '-', str(root))
        exists = identifier and (Path.home()/'.claude/projects'/slug/(identifier+'.jsonl')).is_file()
        args = ['--resume' if exists else '--session-id', identifier]
    elif agent == 'codex' and identifier:
        args = ['resume', identifier]
    elif agent == 'copilot':
        args = ['--session-id',identifier]
    if settings.resolve_autopilot(root,agent):
        args.extend(settings.AUTOPILOT_FLAGS.get(agent,()))
    model = settings.resolve_model(root)
    if model:
        args.extend(['--model',model])
    return [sys.executable,'-m','lab','agents','run','--vault',str(root),agent,'--',*args]


def _spawn(root, entry, entries):
    from core.routes import term
    if not shutil.which('tmux'):
        raise HTTPException(503, 'tmux is not installed on this client')
    if not shutil.which(entry['agent']):
        raise HTTPException(503, f'{entry["agent"]} is not installed on the computer running Lab. Open Settings → Global → General to choose an installed default agent.')
    command = ['env','LAB_DOCUMENT_CONTEXT='+str(_context_path(root,entry['key'])),
        'LAB_ASSISTANT_HOME='+str(root),*_argv(root,entry)]
    with tmux_sockets.state_lock():
        entry['socket'] = term._active_tmux_socket()
        if entry['socket'] != tmux_sockets.DEFAULT_SOCKET and not term._tmux_server_alive(entry['socket']):
            raise HTTPException(409,'The terminal server is unavailable. Run lab terminal rotate from iTerm.')
        entry['state'] = 'starting'
        entry['started_at'] = time.time()
        _save(root, entries)  # durable intent + exact socket before process creation
        result = _tmux(entry,'new-session','-d','-s',entry['name'],'-c',str(root),
                       '-e', 'LAB_DOCUMENT_KEY=' + entry['key'],
                       ' '.join(term._shell_quote(arg) for arg in command))
    if result.returncode:
        raise HTTPException(503,'Could not start the document terminal: '+result.stderr.strip()[:250])
    probe = _probe(entry)
    if not probe:
        raise HTTPException(503,'The agent exited during startup. Check that its CLI is configured.')
    _remember(root, entry, probe)
    term._configure_tmux_wheel_scrolling(entry['name'],entry['socket'])
    _tmux(entry,'set-option','-t',entry['name'],'history-limit','2000')
    term._invalidate_workspace_term_caches()


def _public(entry, policy):
    return {**{key:entry.get(key) for key in ('key','name','state','agent','title','last_used','work_state')}, 'policy':policy}


def operate(root, reference, action='open'):
    """Serialized admission, stable document ownership, and no duplicate starts."""
    from core.routes import term
    from core import vault_config
    with _LOCK:
        key, owner, source, current = _identity(root,reference)
        policy = settings.load(root)['documentTerminals']
        entries = _load(root)
        now = time.time()
        entry = entries.get(key)
        if action == 'status':
            if entry:
                _merge_input(entry)
                if entry['state'] in {'running', 'starting'}:
                    probe = _reconcile(root, entry)
                    if probe:
                        _idle(entry, probe)
                _save(root, entries)
            return _public(entry,policy) if entry else {'key':key,'state':'absent','policy':policy}
        if action == 'activity':
            if entry:
                entry['last_used'] = now
                _merge_input(entry)
                _save(root,entries)
            return _public(entry,policy) if entry else {'key':key,'state':'absent','policy':policy}
        if action == 'sleep':
            if entry and entry['state'] in {'running', 'starting'}:
                _merge_input(entry)
                probe = _reconcile(root, entry)
                if probe and not _idle(entry,probe):
                    raise HTTPException(409,'The agent is working or its state is unknown; it will stay running.')
                _retire(root,entry,probe)
                _save(root,entries)
            return _public(entry,policy) if entry else {'key':key,'state':'absent','policy':policy}
        if action != 'open':
            raise HTTPException(400,'Unknown document terminal action')
        if not policy['enabled']:
            return {'key':key,'state':'disabled','policy':policy}
        if entry and entry['state'] in {'running', 'starting'}:
            _merge_input(entry)
            _reconcile(root, entry)
            if entry['state'] == 'running':
                _INPUT.setdefault(entry['name'], [entry['last_used'], entry.get('last_submit', 0), entry.get('unsent_input', False)])
        if not entry or entry['state'] != 'running':
            _sweep(root, entries, policy, now, incoming=key)
            entry = entries.get(key)
            ready, reason = _memory_ready(entries, now)
            if not ready:
                _sweep(root, entries, policy, now, incoming=key, pressure=True)
                ready, reason = _memory_ready(entries, now)
            if not ready:
                _save(root, entries)
                return {'key':key, 'state':'waiting', 'reason':reason, 'policy':policy}

        if not entry:
            agent = settings.resolve_agent(root)
            supported = vault_config.supported_agents(root)
            if agent not in supported:
                agent = supported[0]
            logical = 'document-'+key
            entry = dict(key=key,document_id=owner['id'],logical_name=logical,
                name=term._tmux_name_for(term.ASSISTANT_WORKSPACE_ID,logical,root),
                agent=agent,conversation_id=str(uuid.uuid4()) if agent in {'claude','copilot'} else None,
                state='sleeping',last_used=now,last_submit=0,cwd=str(root),title=owner['title'])
            entries[key]=entry
        # A failed first launch has no conversation to preserve. Follow a
        # corrected global default when the user retries from Settings.
        if entry['state'] == 'sleeping' and not entry.get('pane_pid') and not entry.get('had_work'):
            agent = settings.resolve_agent(root)
            supported = vault_config.supported_agents(root)
            if agent not in supported:
                agent = supported[0]
            if agent != entry['agent']:
                entry['agent'] = agent
                entry['conversation_id'] = str(uuid.uuid4()) if agent in {'claude', 'copilot'} else None
        entry.update(title=owner['title'],last_used=now)
        records.write_json(_context_path(root,key),dict(document_id=owner['id'],path=str(source),
            title=owner['title'],tab_id=current['id'],reference=source.relative_to(root).as_posix()))
        # Persist the intent before starting a process; a restart can reconcile it.
        _save(root,entries)
        if entry['state'] != 'running':
            _spawn(root,entry,entries)
        _save(root,entries)
        return _public(entry,policy)


def _restore_input_slots(root):
    with _LOCK:
        for entry in _load(root).values():
            if entry['state'] in {'running', 'starting'}:
                _INPUT.setdefault(entry['name'], [entry['last_used'], entry.get('last_submit', 0), entry.get('unsent_input', False)])


def start_supervisor():
    global _WORKER
    if os.environ.get('LAB_DOCUMENT_TERMINALS_SUPERVISOR') == '0':
        return
    if _WORKER and _WORKER.is_alive():
        return
    from lab import paths
    # Bind input tracking before the first WebSocket can arrive after restart.
    root = paths.assistant_root()
    if root and root.is_dir() and registry_path(root).exists():
        try:
            _restore_input_slots(root)
        except (OSError, ValueError):
            log.warning('Could not restore document input tracking', exc_info=True)
    _STOP.clear()
    def run():
        while not _STOP.is_set():
            try:
                root = paths.assistant_root()
                if root and root.is_dir():
                    _restore_input_slots(root)
                    sweep(root)
            except Exception:
                log.warning('Document terminal cleanup could not complete; keeping sessions', exc_info=True)
            if _STOP.wait(TICK_SECONDS):
                break
    _WORKER = threading.Thread(target=run, name='document-terminal-cleanup', daemon=True)
    _WORKER.start()


def stop_supervisor():
    _STOP.set()
    if _WORKER:
        _WORKER.join(timeout=2)
    # A normal backend restart must not forget unsent text still in a live CLI.
    from lab import paths
    root = paths.assistant_root()
    if root and registry_path(root).exists():
        with _LOCK:
            entries = _load(root)
            for entry in entries.values():
                _merge_input(entry)
            _save(root, entries)
