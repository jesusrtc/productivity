"""Progress freshness is independent of the agent's explicitly reported state."""
from __future__ import annotations

import base64
import json
import math
import time
import uuid

from lab import terminal_status

HOOK_OPTION = '@lab_progress_hook'
ALERT_OPTION = '@lab_progress_alert'
REMIND_SECONDS = 20 * 60
STALE_SECONDS = 30 * 60


def decode(value: str) -> dict:
    if not value or len(value) > 16384:
        return {}
    try:
        result = json.loads(base64.b64decode(value, validate=True))
        return result if isinstance(result, dict) and result.get('version') == 1 else {}
    except (ValueError, TypeError, UnicodeError):
        return {}


def timestamp(value) -> float:
    return value if type(value) in (float, int) and math.isfinite(value) and value > 0 else 0


def work(report: dict | None, hook: dict) -> dict | None:
    """A new prompt also needs a first report; an old finish cannot satisfy it."""
    started = timestamp(hook.get('started_at'))
    if started and hook.get('turn_id') and (not report or report['id'] == hook.get('before_report')):
        return {'source': 'turn:' + str(hook['turn_id']), 'since': started,
                'message': 'No progress report for this turn yet'}
    if report and report['state'] == 'working':
        return {'source': report['id'], 'since': report['updated_at'], 'message': report['message']}
    return None


def view(report, hook, alert, *, enabled=True, now=None) -> dict:
    now = time.time() if now is None else now
    current = work(report, hook) if enabled else None
    result = {'last_activity_at': timestamp(hook.get('last_activity_at')) or None,
              'last_report_at': report['updated_at'] if report else None,
              'remind_after_seconds': REMIND_SECONDS, 'stale_after_seconds': STALE_SECONDS}
    if current:
        result.update(current, age_seconds=max(0, now - current['since']),
                      reminder_due=now - current['since'] >= REMIND_SECONDS)
    # Persisted history remains readable, but a new explicit report resolves it
    # immediately, without waiting for the supervisor or changing any status dot.
    normalized = terminal_status.decode(terminal_status.encode(alert)) if alert else None
    if normalized and alert.get('kind') in ('stale', 'stopped', 'exited') and isinstance(alert.get('source'), str):
        result['alert'] = {**normalized, 'kind': alert['kind'], 'source': alert['source'],
                           'active': bool(current and current['source'] == alert['source'])}
    return result


def next_alert(report, hook, previous, *, now):
    current = work(report, hook)
    if not current or view(report, hook, previous, now=now).get('alert', {}).get('source') == current['source']:
        return None
    stopped = hook.get('stop_source') == current['source'] and hook.get('phase') in ('stopped', 'exited')
    if not stopped and now - current['since'] < STALE_SECONDS:
        return None
    kind = hook['phase'] if stopped else 'stale'
    message = {'stale': 'WIP has not been updated for 30 minutes',
               'stopped': 'Agent ended its turn without reporting finished or attention',
               'exited': 'Agent session ended without closing its WIP status'}[kind]
    if current['message']:
        message += ' · Last report: ' + current['message']
    return {'version': 1, 'state': 'attention', 'id': uuid.uuid4().hex,
            'revision': time.monotonic_ns() // 1000, 'updated_at': now,
            'message': message[:terminal_status.MAX_MESSAGE], 'kind': kind, 'source': current['source']}


def handle_hook(event, payload, terminal, *, now=None, retry=True):
    """Copilot root-agent hooks. No prompt keystrokes and no invented reports."""
    if payload.get('agentId') or payload.get('agent_id'):
        return {}
    now = time.time() if now is None else now
    session = payload.get('sessionId') or payload.get('session_id')
    if not isinstance(session, str) or not session or len(session) > 256:
        return {}
    hook_token = terminal.option(HOOK_OPTION)
    status_token = terminal.option(terminal_status.OPTION)
    hook = decode(hook_token)
    report = terminal_status.decode(status_token)
    before = dict(hook)
    if hook.get('session') != session:
        if hook and event not in ('start', 'prompt'):
            return {}  # A late stop/tool from an older provider session.
        hook = {'version': 1, 'session': session}
    if event == 'prompt':
        hook = {'version': 1, 'session': session, 'turn_id': uuid.uuid4().hex,
                'started_at': now, 'before_report': report['id'] if report else None,
                'last_activity_at': now, 'phase': 'running'}
    # A session may be resumed with no prompt hook (e.g. autopilot). Start a
    # reporting window on its first tool, but never just from opening the CLI.
    if event == 'post-tool' and not hook.get('started_at'):
        hook.update(turn_id=uuid.uuid4().hex, started_at=now,
                    before_report=report['id'] if report else None, phase='running')
    current = work(report, hook)
    output = {}
    if event == 'post-tool':
        if now - timestamp(hook.get('last_activity_at')) >= 60:
            hook['last_activity_at'] = now
        if current and now - current['since'] >= REMIND_SECONDS and (
                hook.get('reminded_source') != current['source'] or now - timestamp(hook.get('reminded_at')) >= REMIND_SECONDS):
            output['additionalContext'] = (
                'Lab progress checkpoint: your WIP report is at least 20 minutes old. '
                'Run lab notifications working with a concise, factual update: what you completed, '
                'what you are doing now, and what comes next. If waiting for a process, name it '
                'and explain the wait. Use attention if user input is required, or finished '
                'only when the requested work is complete. Then continue the task.')
            hook.update(reminded_source=current['source'], reminded_at=now)
    elif event in ('stop', 'end') and current:
        hook.update(last_activity_at=now, stop_source=current['source'])
        if event == 'stop' and not payload.get('stop_hook_active') and hook.get('stop_attempt') != hook.get('turn_id'):
            hook.update(stop_attempt=hook.get('turn_id'), phase='closing')
            output = {'decision': 'block', 'reason':
                'Before ending this turn, report the actual outcome to Lab: run '
                'lab notifications finished "What was completed" if the requested work is complete, '
                'or lab notifications attention "What is needed" if waiting for input or blocked. '
                'Do not claim completion for unfinished work. If reporting fails, explain that failure.'}
        else:
            hook['phase'] = 'stopped' if event == 'stop' else 'exited'
    if hook != before:
        if not terminal.compare_set_option(HOOK_OPTION, terminal_status.encode(hook),
                {HOOK_OPTION: hook_token, terminal_status.OPTION: status_token}):
            return handle_hook(event, payload, terminal, now=now, retry=False) if retry else {}
    return output
