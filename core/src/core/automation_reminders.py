"""Read-only connection checks; recurring reminders belong to the group main."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import time
import uuid

from core import fsguard, terminal_automations, terminal_automation_lifecycle as lifecycle
from lab import terminal_progress, terminal_status

OPTION = '@lab_automation_alert'
PERIOD = 30 * 60


def decode(token):
    raw = terminal_progress.decode(token)
    report = terminal_status.decode(token)
    if (report and raw.get('kind') == 'automation' and isinstance(raw.get('source'), str)
            and raw['source'].startswith('automation:') and type(raw.get('active')) is bool):
        return {**report, 'kind': 'automation', 'source': raw['source'], 'active': raw['active']}
    return None


def _main(saved, logical):
    from core.task_terminal_cleanup import _parent
    seen = set()
    while logical in saved and logical not in seen:
        seen.add(logical)
        if (saved[logical].get('automation_appearance') or {}).get('role') == 'main':
            return logical
        parent = _parent(saved, logical)
        if not parent:
            if (saved[logical].get('automation_appearance') or {}).get('role') == 'child' and 'parent_terminal' not in saved[logical]:
                return None  # A borrowed/unknown main must not turn its child into the notifier.
            return logical
        logical = parent
    return None


def _workspace(root, workspace, live):
    from core.routes import term
    folder = term._workspace_cwd(root, workspace)
    runs = lifecycle.read(folder)
    saved = term._workspace_session_by_name(root, workspace)
    groups = {}
    for logical, run in runs.items():
        if logical not in saved:
            continue
        main = _main(saved, logical)
        if main not in live:
            continue
        group = groups.setdefault(main, {'main': live[main], 'members': []})
        current = live.get(logical)
        # A saved run must still own this socket/name before its process counts.
        if current and (current['name'] != run.get('name') or current['tmux_socket'] != run.get('tmux_socket')):
            current = None
        group['members'].append((logical, run, current))
    return [{**group, 'root': root, 'workspace': workspace, 'folder': folder, 'saved': saved}
            for group in groups.values()]


def groups(roots, listing):
    """Read only owning workspaces with live sessions; never replay commands."""
    from core.routes import term
    result, known, warnings = [], {}, []
    for vault in roots:
        root = Path(vault['path'])
        try:
            meta = fsguard.guarded(root, term._load_meta, root)
            workspaces = {}
            for row in listing:
                info = meta.get(row['name'])
                if not info or not info.get('workspace_id') or not info.get('logical_name'):
                    continue
                if info.get('tmux_socket') != row['tmux_socket']:
                    continue
                workspaces.setdefault(info['workspace_id'], {})[info['logical_name']] = row
            for workspace, live in workspaces.items():
                try:
                    owned = fsguard.guarded(root, _workspace, root, workspace, live)
                    result.extend(owned)
                    for row in live.values():
                        known[(row['tmux_socket'], row['tmux_id'], row['created'])] = row
                except (OSError, ValueError, term.HTTPException):
                    warnings.append(f'{vault["id"]}::{workspace}')
        except (OSError, ValueError, term.HTTPException):
            warnings.append(vault['id'])
    return result, known, warnings


def persist(row, alert, *, option=OPTION, token_key='_automation_alert_token'):
    """CAS protects the main incarnation, pane and previous reminder."""
    from core.routes import term
    token = row.get(token_key, '')
    if not re.fullmatch(r'[A-Za-z0-9+/=]*', token):
        return False
    checks = [f'#{{==:#{{session_id}},{row["tmux_id"]}}}',
              f'#{{==:#{{session_created}},{row["created"]}}}',
              f'#{{==:#{{pane_id}},{row["pane_id"]}}}',
              f'#{{==:#{{pane_pid}},{row["pane_pid"]}}}',
              '#{==:#{' + option + '},' + token + '}']
    condition = checks[0]
    for check in checks[1:]:
        condition = '#{&&:' + condition + ',' + check + '}'
    command = 'set-option -t ' + shlex.quote(row['tmux_id']) + ' ' + option + ' ' + terminal_status.encode(alert)
    process = subprocess.run(term._tmux_command(row['tmux_socket'], 'if-shell', '-F', '-t', '=' + row['name'] + ':',
        condition, command, 'display-message -p lab-automation-reminder-skipped'),
        capture_output=True, text=True, timeout=5, env=term._tmux_child_env())
    if process.returncode:
        raise RuntimeError('Could not save automation reminder')
    return 'lab-automation-reminder-skipped' not in process.stdout


def _remote_status(run, current, snapshot, now):
    state = lifecycle.status({**run, 'health_command': ''}, current, True, snapshot, now=now)['state']
    if lifecycle.connection_kind(run['command']) in ('ssh', 'tmux') or state != 'running':
        return state
    # Scripts and Make targets can start SSH without naming it in the recipe.
    descendants = {current['pane_pid']}
    while True:
        children = {pid for pid, row in snapshot.items()
                    if row['ppid'] in descendants and not row['stat'].startswith('Z')}
        if children <= descendants:
            break
        descendants |= children
    return 'running' if any(Path(snapshot[pid]['comm']).name.split(':', 1)[0] in ('ssh', 'tmux', 'mosh-client')
                            for pid in descendants) else 'stopped'


def next_alert(group, snapshot, previous, now):
    main = group['main']
    if main.get('pane_dead'):
        return {**previous, 'active': False} if previous and previous['active'] else None
    if main.get('windows', 1) != 1 or main.get('pane_count', 1) != 1:
        return None
    # Health commands may open new SSH connections. Periodic reminders inspect
    # existing local processes only; they never execute a recipe or remote probe.
    states = [_remote_status(run, current, snapshot, now)
              for _, run, current in group['members']]
    if 'running' not in states:
        if states and all(state == 'stopped' for state in states) and previous and previous['active']:
            return {**previous, 'active': False}
        return None  # Unknown is neither healthy nor finished.
    generation = [main['tmux_socket'], main['tmux_id'], main['created'], main['pane_id'], main['pane_pid'],
                  sorted((logical, run['launch_id']) for logical, run, _ in group['members'])]
    source = 'automation:' + hashlib.sha256(json.dumps(generation).encode()).hexdigest()
    since = max(main['created'], *(run['updated_at'] for _, run, _ in group['members']))
    cycle = int((now - since) // PERIOD)
    if cycle < 1:
        if previous and previous['active'] and previous['source'] != source:
            return {**previous, 'active': False}
        return None
    due = since + cycle * PERIOD
    if previous and previous['source'] == source and previous['active'] and previous['updated_at'] >= due:
        return None
    return {'version': 1, 'state': 'attention', 'id': uuid.uuid4().hex,
            'revision': time.monotonic_ns() // 1000, 'updated_at': now,
            'message': '30-minute check-in · Check this automation’s status in its main terminal.',
            'kind': 'automation', 'source': source, 'active': True}


def check(roots, listing, *, now):
    changed = 0
    # Launch/recovery use the same lock. Keep the generation stable while
    # reading its saved recipe and checking its existing owned processes.
    with terminal_automations.lock:
        selected, known, warnings = groups(roots, listing)
        members = [current for group in selected for _, _, current in group['members'] if current]
        snapshot = lifecycle.processes(members) if members else None
        covered = set()
        for group in selected:
            row = group['main']
            key = (row['tmux_socket'], row['tmux_id'], row['created'])
            if key in covered:
                continue
            covered.add(key)
            previous = decode(row.get('_automation_alert_token', ''))
            alert = next_alert(group, snapshot, previous, now)
            if alert:
                try:
                    changed += bool(persist(row, alert))
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
                    warnings.append(row['name'])
        for key, row in known.items():
            previous = decode(row.get('_automation_alert_token', ''))
            if key not in covered and previous and previous['active']:
                try:
                    changed += bool(persist(row, {**previous, 'active': False}))
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
                    warnings.append(row['name'])
    return {'monitored': len(covered), 'changed': changed, 'warnings': warnings}
