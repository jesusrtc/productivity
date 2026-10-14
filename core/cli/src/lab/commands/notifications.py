"""Report state to Lab's existing terminal dots without sending notifications."""
from __future__ import annotations

import os
import re
import subprocess
import time
import uuid

import click

from lab import terminal_status


def _tmux(socket: str, *args: str) -> str:
    try:
        result = subprocess.run(['tmux', '-S', socket, *args], capture_output=True,
                                text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise click.ClickException(f'Cannot reach this terminal’s tmux session: {exc}') from exc
    if result.returncode:
        raise click.ClickException((result.stderr or 'tmux command failed').strip())
    return result.stdout.strip()


@click.command('notifications')
@click.argument('state', type=click.Choice(['working', 'wip', 'attention', 'input', 'review', 'finished']))
@click.argument('message', default='')
def notifications_cmd(state: str, message: str) -> None:
    """Set this terminal's status dot, with optional hover text. No pop-ups.

    WORKING (or wip): steady yellow. ATTENTION (or input/review): pulsing red.
    FINISHED: blinking green, cleared by clicking the terminal tab. Working
    and attention change only when the agent reports another state.
    Run inside the owning Lab tmux terminal; no session name is needed.
    """
    if len(message) > terminal_status.MAX_MESSAGE:
        raise click.ClickException(f'Hover text must be at most {terminal_status.MAX_MESSAGE} characters.')
    tmux = os.environ.get('TMUX', '').rsplit(',', 2)
    pane = os.environ.get('TMUX_PANE', '')
    if len(tmux) != 3 or not tmux[0] or not re.fullmatch(r'%\d+', pane):
        raise click.ClickException('Run this command inside the owning Lab tmux terminal (TMUX and TMUX_PANE are required).')
    identity = _tmux(tmux[0], 'display-message', '-p', '-t', pane,
                     '#{session_id}\t#{session_name}').split('\t', 1)
    prefix = os.environ.get('LAB_TMUX_PREFIX')
    if (len(identity) != 2 or not re.fullmatch(r'\$\d+', identity[0])
            or not identity[1].startswith((prefix,) if prefix else ('neurona-', 'lab-'))):
        raise click.ClickException('The current pane does not belong to a Lab terminal.')
    state = {'wip': 'working', 'input': 'attention', 'review': 'attention'}.get(state, state)
    report = {'version': 1, 'state': state, 'message': message.strip(),
              'id': uuid.uuid4().hex, 'revision': time.monotonic_ns() // 1000, 'updated_at': time.time()}
    _tmux(tmux[0], 'set-option', '-t', identity[0], terminal_status.OPTION,
          terminal_status.encode(report))
    click.echo(f'{state}: {identity[1]}' + (f' · {report["message"]}' if report['message'] else ''))
