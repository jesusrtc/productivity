"""Bounded, persistent reconnects for owned automation connections and services."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid

from fastapi import APIRouter, HTTPException, Request

from core import auth, automation_reminders as reminders, fsguard
from core import terminal_automations, terminal_automation_lifecycle as lifecycle
from lab import terminal_status

router = APIRouter()
log = logging.getLogger(__name__)
OPTION = '@lab_reconnect_alert'
INTERVAL, RETRY_SECONDS, VERIFY_SECONDS, RESUME_GRACE, MAX_ATTEMPTS = 10, 120, 30, 120, 3


def decode(token):
    try:
        if not token or len(token) > 262144:
            return None
        raw = json.loads(base64.b64decode(token, validate=True))
        if not isinstance(raw, dict):
            return None
    except (ValueError, TypeError, UnicodeError):
        return None
    report = terminal_status.decode(terminal_status.encode({key: raw.get(key) for key in
        ('version', 'state', 'id', 'message', 'revision', 'updated_at')}))
    if (not report or raw.get('kind') != 'reconnect' or type(raw.get('active')) is not bool
            or not isinstance(raw.get('source'), str) or not raw['source'].startswith('reconnect:')
            or not isinstance(raw.get('targets'), list) or not raw['targets']):
        return None
    targets = raw['targets']
    if any(not isinstance(t, dict) or not lifecycle.NAME.fullmatch(str(t.get('logical_name', '')))
           or not isinstance(t.get('launch_id'), str) or not 1 <= len(t['launch_id']) <= 80 for t in targets):
        return None
    return {**report, 'kind': 'reconnect', 'active': raw['active'], 'source': raw['source'], 'targets': targets}


def remote_seen(live, snapshot):
    if not live or snapshot is None or live.get('pane_pid') not in snapshot:
        return False
    descendants = {live['pane_pid']}
    while True:
        children = {pid for pid, row in snapshot.items() if row['ppid'] in descendants and not row['stat'].startswith('Z')}
        if children <= descendants:
            break
        descendants |= children
    return any(Path(snapshot[pid]['comm']).name.split(':', 1)[0] in ('ssh', 'tmux', 'mosh-client') for pid in descendants)


def transition(run, live, state, now):
    """Unknown observations cannot spend attempts or establish recovery/failure."""
    identity = [live['tmux_socket'], live['tmux_id'], live['created'], live['pane_id']]
    previous = run.get('recovery')
    current = previous if (isinstance(previous, dict) and previous.get('identity') == identity
                           and previous.get('launch_id') == run['launch_id']) else None
    if state in ('unknown', 'starting'):
        return current, False
    if state == 'running':
        if current and current.get('phase') == 'verifying' and now < current['verify_at']:
            return current, False
        return None, False
    if state != 'stopped':
        return current, False
    current = dict(current or {'identity': identity, 'launch_id': run['launch_id'], 'source': uuid.uuid4().hex,
                               'attempts': 0, 'phase': 'waiting', 'next_at': now})
    if current['phase'] == 'verifying':
        if now < current['verify_at']:
            return current, False
        current['phase'] = 'failed' if current['attempts'] >= MAX_ATTEMPTS else 'waiting'
    return current, current['phase'] == 'waiting' and now >= current['next_at']


def _owner_context(root, workspace):
    from core import task_terminal_cleanup
    saved, registry = task_terminal_cleanup._workspace(root, workspace)
    return {logical: task_terminal_cleanup._owner(root, workspace, saved, logical, registry) for logical in saved}


class Supervisor:
    def __init__(self, *, now=None):
        now = time.time() if now is None else now
        self.grace_until, self.last_tick = now + RESUME_GRACE, now
        self.lock, self.last_result = threading.Lock(), {}
        self.stop = threading.Event()

    def tick(self, root, *, now=None):
        from core.routes import term, terminal_cleanup
        with self.lock:
            started = time.monotonic()
            now = time.time() if now is None else now
            if now < self.last_tick or now - self.last_tick > INTERVAL * 3:
                self.grace_until = now + RESUME_GRACE
            self.last_tick = now
            result = {'checked_at': now, 'attempted': 0, 'failed': 0, 'warnings': [], 'grace_until': self.grace_until}
            if self.stop.is_set() or now < self.grace_until:
                self.last_result = result
                return result
            roots = terminal_cleanup._roots(root)
            listing = term._tmux_list(term._tmux_discovery_prefixes_all(roots), prune_draining=False, progress=True)
            if listing is None:
                raise HTTPException(503, 'Automation connections unavailable; retries were preserved')
            groups, _, warnings = reminders.groups(roots, listing)
            result['warnings'].extend(warnings)
            snapshot = lifecycle.processes([live for group in groups for _, _, live in group['members'] if live])
            contexts = {}
            for group in groups:
                try:
                    key = (group['root'], group['workspace'])
                    if key not in contexts:
                        contexts[key] = fsguard.guarded(group['root'], _owner_context, *key)
                    self._group(group, snapshot, contexts[key], now + time.monotonic() - started, result)
                except (OSError, ValueError, HTTPException, subprocess.TimeoutExpired):
                    result['warnings'].append(group['main']['name'])
                    log.warning('Automation recovery check failed', exc_info=True)
            self.last_tick = now + time.monotonic() - started
            self.last_result = result
            return result

    def _group(self, group, snapshot, owners, now, result):
        from core.routes import term
        from lab.workspace_identity import operation_lease
        started = time.monotonic()
        allowed = set()
        root, workspace, folder = group['root'], group['workspace'], group['folder']
        # One queue is shared with manual reconnects. Waiting never holds the
        # global automation/catalog lock. New liveness checks precede every replay.
        with operation_lease(root, workspace), lifecycle.recovery_queue(folder, blocking=False) as queued:
            if not queued:
                return
            last_started = None
            for logical, observed, live in sorted(group['members'], key=lambda row: (row[0].rsplit('-', 1)[0], int(row[0].rsplit('-', 1)[1]))):
                if not live or live.get('windows', 1) != 1 or live.get('pane_count', 1) != 1:
                    continue
                owner = owners.get(logical)
                if owner and owner['status'] != 'in_progress':
                    continue
                with terminal_automations.lock:
                    runs = fsguard.guarded(root, lifecycle.read, folder)
                    run = runs.get(logical)
                    if not run or run['launch_id'] != observed['launch_id']:
                        continue
                    identity = [live[key] for key in ('tmux_socket', 'tmux_id', 'created', 'pane_id')]
                    if run.get('monitor_identity') and run['monitor_identity'] != identity:
                        continue
                    seen = remote_seen(live, snapshot)
                    eligible = lifecycle.connection_kind(run['command']) in ('ssh', 'tmux', 'mosh') or run.get('health_command') or run.get('remote_seen') or seen
                    if not eligible:
                        continue
                    state = lifecycle.status(run, live, True, snapshot, now=now)['state']
                    recovery, attempt = transition(run, live, state, now)
                    before = dict(run)
                    allowed.add(logical)
                    run['monitor_identity'] = identity
                    if seen:
                        run['remote_seen'] = True
                    run['recovery'] = recovery
                    if run != before:
                        fsguard.guarded(root, lifecycle.save, folder, runs)
                    delay = lifecycle.launch_delay(folder, run) if attempt else 0
                if not attempt:
                    continue
                if last_started is not None and delay:
                    if self.stop.wait(max(0, last_started + delay - time.monotonic())):
                        return
                if self.stop.is_set():
                    return
                with terminal_automations.lock:
                    runs = fsguard.guarded(root, lifecycle.read, folder)
                    current = runs.get(logical)
                    if not current or current['launch_id'] != run['launch_id']:
                        continue
                    # Persist the claim before executing. A backend crash cannot
                    # replay the same attempt immediately after restart.
                    attempt_at = now + time.monotonic() - started
                    recovery = {**recovery, 'attempts': recovery['attempts'] + 1, 'phase': 'verifying',
                                'next_at': attempt_at + RETRY_SECONDS, 'verify_at': attempt_at + VERIFY_SECONDS}
                    current['recovery'] = recovery
                    fsguard.guarded(root, lifecycle.save, folder, runs)
                    attempted = True
                    try:
                        outcome = term._relaunch_automation_target(root, folder, workspace, None,
                            term.AutomationRecoveryTarget(logical_name=logical, launch_id=current['launch_id']), uuid.uuid4(),
                            expected_identity=identity)
                        if 'skipped' in outcome:
                            attempted = False
                            recovery = {**recovery, 'attempts': recovery['attempts'] - 1, 'phase': 'waiting'}
                    except (OSError, ValueError, HTTPException, subprocess.TimeoutExpired):
                        # A failed spawn is an attempted reconnect, not a healthy
                        # connection. Keep its backoff and bounded retry budget.
                        log.warning('Automation reconnect attempt failed for %s', logical, exc_info=True)
                    runs = fsguard.guarded(root, lifecycle.read, folder)
                    if logical in runs:
                        runs[logical]['monitor_identity'] = identity
                        runs[logical]['recovery'] = {**recovery, 'launch_id': runs[logical]['launch_id']}
                        fsguard.guarded(root, lifecycle.save, folder, runs)
                    result['attempted'] += attempted
                    if attempted:
                        last_started = time.monotonic()
            self._alert(group, now + time.monotonic() - started, result, allowed)

    def _alert(self, group, now, result, allowed):
        from core.routes import term
        with terminal_automations.lock:
            runs = fsguard.guarded(group['root'], lifecycle.read, group['folder'])
            failed = [(logical, runs[logical]) for logical, _, live in group['members']
                      if live and logical in allowed and logical in runs and (runs[logical].get('recovery') or {}).get('phase') == 'failed']
            main = next((row for row in term._tmux_list(term._tmux_discovery_prefixes(group['root']), prune_draining=False, progress=True) or []
                         if row['name'] == group['main']['name'] and row['tmux_id'] == group['main']['tmux_id']
                         and row['created'] == group['main']['created']), None)
            if not main:
                return
            previous = decode(main.get('_recovery_alert_token', ''))
            if failed:
                targets = [{'logical_name': logical, 'launch_id': run['launch_id']} for logical, run in failed]
                source = 'reconnect:' + hashlib.sha256(json.dumps(targets, sort_keys=True).encode()).hexdigest()
                if previous and previous['active'] and previous['source'] == source:
                    return
                names = ', '.join(run['label'] for _, run in failed)
                alert = {'version': 1, 'state': 'attention', 'id': uuid.uuid4().hex, 'revision': time.monotonic_ns() // 1000,
                         'updated_at': now, 'kind': 'reconnect', 'active': True, 'source': source, 'targets': targets,
                         'message': ('Could not reconnect after 3 attempts, 2 minutes apart: ' + names + '. Reconnect to try again.')[:terminal_status.MAX_MESSAGE]}
            elif previous and previous['active']:
                alert = {**previous, 'active': False}
            else:
                return
            if reminders.persist(main, alert, option=OPTION, token_key='_recovery_alert_token'):
                result['failed'] += bool(failed)


@router.get('/api/term/automations/recovery')
def status(request: Request):
    auth.require_admin(request)
    return {'enabled': os.environ.get('LAB_AUTOMATION_RECOVERY') != '0', 'retry_seconds': RETRY_SECONDS,
            'max_attempts': MAX_ATTEMPTS, 'verify_seconds': VERIFY_SECONDS, 'resume_grace_seconds': RESUME_GRACE,
            'last_run': request.app.state.automation_recovery.last_result}


@router.post('/api/term/automations/recovery/check')
def check(request: Request):
    auth.require_admin(request)
    if os.environ.get('LAB_AUTOMATION_RECOVERY') == '0':
        raise HTTPException(409, 'Automatic automation recovery is disabled')
    return request.app.state.automation_recovery.tick(request.app.state.index_cache.root)


async def run(app):
    try:
        while True:
            try:
                await asyncio.to_thread(app.state.automation_recovery.tick, app.state.index_cache.root)
            except Exception:
                log.exception('Automation recovery supervisor tick failed')
            await asyncio.sleep(INTERVAL)
    finally:
        app.state.automation_recovery.stop.set()
