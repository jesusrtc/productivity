"""User-requested, incarnation-scoped terminal watches, independent of agent status."""
from __future__ import annotations

import base64
import json
import math
import uuid

from lab import terminal_status

OPTION = '@lab_watch'


def decode(token):
    try:
        if not token or len(token) > 16384:
            return None
        value = json.loads(base64.b64decode(token, validate=True))
        if (not isinstance(value, dict) or value.get('version') != 1
                or value.get('mode') not in ('pin', 'remind', 'closed')
                or not isinstance(value.get('id'), str) or len(value['id']) != 32
                or not terminal_status.decode(terminal_status.encode(value.get('report')))
                or any(type(value.get(k)) not in (int, float) or not math.isfinite(value[k])
                       or value[k] < 0 for k in ('due_at', 'updated_at'))):
            return None
        return value
    except (ValueError, TypeError, UnicodeError):
        return None


def latest(row, fallback=None):
    reports = [row.get('terminal_recovery_alert'), row.get('terminal_status'), row.get('terminal_notification'), row.get('terminal_automation_alert'),
               row.get('terminal_progress', {}).get('alert'), fallback]
    alerts = [report for report in reports if report and terminal_status.decode(terminal_status.encode(report))
              and report['state'] in ('attention', 'finished')]
    if alerts:
        return max(alerts, key=lambda report: report['revision'])
    return fallback


def create(row, mode, *, now, due_at=0):
    identity = uuid.uuid4().hex
    # Even an ordinary shell with no reports can be watched. This yellow card
    # requests a manual check; it never claims that the process has finished.
    fallback = {'version': 1, 'state': 'attention', 'kind': 'watch', 'id': identity,
                'revision': int(now * 1_000_000), 'updated_at': due_at or now,
                'message': 'Check this terminal' + (': ' + row['terminal_status']['message']
                    if (row.get('terminal_status') or {}).get('message') else '')}
    fallback['message'] = fallback['message'][:terminal_status.MAX_MESSAGE]
    report = latest(row) or fallback
    return {'version': 1, 'id': identity, 'mode': mode, 'due_at': due_at,
            'updated_at': now, 'report': report}


def view(value, row):
    if not value:
        return None
    # Retain the latest alert through working/review transitions. A synthetic
    # check card must not outrank a later real alert based on its own revision.
    fallback = value.get('report')
    report = latest(row, fallback if fallback and fallback.get('kind') != 'watch' else None) or fallback
    return {**value, 'report': report}
