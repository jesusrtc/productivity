"""Agent-reported terminal state, carried by a session-local tmux option."""
from __future__ import annotations

import base64
import binascii
import json
import math

OPTION = '@lab_status'
NOTIFICATION_OPTION = '@lab_notification'
LLM_OPTION = '@lab_llm'
STATES = ('working', 'attention', 'finished')
MAX_MESSAGE = 500


def encode(report: dict) -> str:
    # A single safe tmux argument and listing field, even for quotes, pipes,
    # newlines, semicolons and tmux format expressions in the agent's message.
    return base64.b64encode(json.dumps(report, ensure_ascii=False).encode()).decode()


def decode(value: str) -> dict | None:
    if not value or len(value) > 8192:
        return None
    try:
        report = json.loads(base64.b64decode(value, validate=True))
        if (not isinstance(report, dict) or report.get('version') != 1
                or report.get('state') not in STATES
                or not isinstance(report.get('id'), str) or len(report['id']) != 32
                or not isinstance(report.get('message'), str) or len(report['message']) > MAX_MESSAGE
                or type(report.get('revision')) is not int or not 0 < report['revision'] < 2**53
                or type(report.get('updated_at')) not in (float, int)
                or not math.isfinite(report['updated_at']) or report['updated_at'] <= 0):
            return None
        return {key: report[key] for key in ('version', 'state', 'id', 'message', 'revision', 'updated_at')}
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        return None
