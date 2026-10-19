"""One background supervisor for stale agent progress across all Lab sockets."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import subprocess
import threading
import time

from fastapi import APIRouter, HTTPException, Request

from core import auth, terminal_llm
from core.routes import term, terminal_cleanup
from lab import terminal_progress as progress, terminal_status

router = APIRouter()
log = logging.getLogger(__name__)
INTERVAL = 60
RESUME_GRACE = 120


def agent_presence(rows):
    """Inspect only these panes once. Unknown reads never mean a dead agent."""
    snapshot = terminal_llm.processes(rows) if rows else None
    result = {}
    for row in rows:
        key = (row['tmux_socket'], row['tmux_id'], row['created'])
        pid = row.get('pane_pid')
        if row.get('pane_dead'):
            result[key] = False
        elif snapshot is None or pid not in snapshot or row.get('pane_count', 1) != 1 or row.get('windows', 1) != 1:
            result[key] = None
        else:
            descendants = {pid}
            while True:
                children = {child for child, process in snapshot.items()
                            if process['ppid'] in descendants and not process['stat'].startswith('Z')}
                if children <= descendants:
                    break
                descendants |= children
            result[key] = any(terminal_llm.provider(child, snapshot[child]['comm'])
                              for child in descendants if not snapshot[child]['stat'].startswith('Z'))
    return result


def persist(row, alert):
    """Compare-and-set inside tmux: never attach an old scan to new work."""
    if any(not re.fullmatch(r'[A-Za-z0-9+/=]*', row[key])
           for key in ('_progress_status_token', '_progress_hook_token')):
        return False
    checks = [f'#{{==:#{{session_id}},{row["tmux_id"]}}}',
              f'#{{==:#{{session_created}},{row["created"]}}}',
              '#{==:#{@lab_status},' + row['_progress_status_token'] + '}',
              '#{==:#{@lab_progress_hook},' + row['_progress_hook_token'] + '}',
              '#{!=:#{@lab_llm},0}']
    condition = checks[0]
    for check in checks[1:]:
        condition = '#{&&:' + condition + ',' + check + '}'
    target = '=' + row['name']
    command = 'set-option -t ' + shlex.quote(row['tmux_id']) + ' ' + progress.ALERT_OPTION + ' ' + terminal_status.encode(alert)
    result = subprocess.run(term._tmux_command(row['tmux_socket'], 'if-shell', '-F', '-t', target + ':',
        condition, command, 'display-message -p lab-progress-skipped'),
        capture_output=True, text=True, timeout=5, env=term._tmux_child_env())
    if result.returncode:
        raise RuntimeError((result.stderr or 'Could not persist progress alert').strip())
    return 'lab-progress-skipped' not in result.stdout


class Supervisor:
    def __init__(self, *, now=None):
        now = time.time() if now is None else now
        self.grace_until = now + RESUME_GRACE
        self.last_tick = now
        self.last_result = {}
        self.presence = {}
        self.lock = threading.Lock()

    def tick(self, root, *, now=None):
        with self.lock:
            now = time.time() if now is None else now
            if now - self.last_tick > INTERVAL * 3 or now < self.last_tick:
                self.grace_until = now + RESUME_GRACE
            self.last_tick = now
            roots = terminal_cleanup._roots(root)
            rows = term._tmux_list(term._tmux_discovery_prefixes_all(roots),
                                  prune_draining=False, progress=True)
            if rows is None:
                raise HTTPException(503, 'Could not inspect terminal progress; existing reports were preserved.')
            changed, monitored, warnings = 0, 0, []
            candidates = [row for row in rows if row.get('llm_controlled') is not False and row.get('tmux_id')
                          and progress.work(row.get('terminal_status'), progress.decode(row['_progress_hook_token']))]
            presence = agent_presence(candidates)
            self.presence = {key: value for key, value in self.presence.items() if key in presence}
            for row in rows:
                if row.get('llm_controlled') is False or not row.get('tmux_id'):
                    continue
                report = row.get('terminal_status')
                hook = progress.decode(row['_progress_hook_token'])
                previous = progress.decode(row['_progress_alert_token'])
                current = progress.work(report, hook)
                if not current:
                    continue
                monitored += 1
                key = row['tmux_socket'], row['tmux_id'], row['created']
                running = presence.get(key)
                if running is True:
                    self.presence[key] = 0
                elif running is False and key in self.presence:
                    self.presence[key] += 1
                elif running is None and key in self.presence:
                    self.presence[key] = 0
                # Two successful observations after seeing the real agent run.
                # A persistent LLM marker or a failed ps query is not evidence.
                if running is False and (row.get('pane_dead') or self.presence.get(key, 0) >= 2):
                    hook = {**hook, 'phase': 'exited', 'stop_source': current['source']}
                if now < self.grace_until:
                    continue
                alert = progress.next_alert(report, hook, previous, now=now)
                if not alert:
                    continue
                try:
                    changed += bool(persist(row, alert))
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
                    warnings.append(row['name'])
                    log.warning('Progress check failed for %s', row['name'], exc_info=True)
            self.last_result = {'checked_at': now, 'monitored': monitored, 'new_alerts': changed,
                                'grace_until': self.grace_until, 'warnings': warnings}
            return self.last_result


@router.get('/api/term/progress')
def status(request: Request):
    auth.require_admin(request)
    supervisor = getattr(request.app.state, 'terminal_progress', None)
    return {'enabled': os.environ.get('LAB_TERMINAL_PROGRESS') != '0', 'interval_seconds': INTERVAL,
            'remind_after_seconds': progress.REMIND_SECONDS, 'stale_after_seconds': progress.STALE_SECONDS,
            'resume_grace_seconds': RESUME_GRACE,
            'last_run': supervisor.last_result if supervisor else {}}


@router.post('/api/term/progress/check')
def check(request: Request):
    auth.require_admin(request)
    if os.environ.get('LAB_TERMINAL_PROGRESS') == '0':
        raise HTTPException(409, 'Terminal progress supervisor is disabled')
    return request.app.state.terminal_progress.tick(request.app.state.index_cache.root)


async def run(app):
    while True:
        try:
            await asyncio.to_thread(app.state.terminal_progress.tick, app.state.index_cache.root)
        except Exception:
            log.exception('Terminal progress supervisor tick failed')
        await asyncio.sleep(INTERVAL)
