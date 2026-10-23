"""Report state to Lab's existing terminal dots without sending notifications."""
from __future__ import annotations

import time
import uuid

import click

from lab import terminal_context, terminal_status


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
    state = {'wip': 'working', 'input': 'attention', 'review': 'attention'}.get(state, state)
    report = {'version': 1, 'state': state, 'message': message.strip(),
              'id': uuid.uuid4().hex, 'revision': time.monotonic_ns() // 1000, 'updated_at': time.time()}
    try:
        terminal = terminal_context.current()
        terminal.set_option(terminal_status.OPTION, terminal_status.encode(report))
        if state in ('attention', 'finished'):
            terminal.set_option(terminal_status.NOTIFICATION_OPTION, terminal_status.encode(report))
    except terminal_context.TerminalContextError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f'{state}: {terminal.name}' + (f' · {report["message"]}' if report['message'] else ''))
