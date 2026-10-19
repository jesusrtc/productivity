"""Progress diagnostics and provider lifecycle integration."""
import json
import os
import sys

import click

from lab import terminal_context, terminal_progress, terminal_status


@click.group('progress')
def progress_group():
    """Inspect progress freshness or run Lab's provider hooks."""


@progress_group.command('status')
def status():
    """Show this terminal's last report, activity and progress alert as JSON."""
    try:
        terminal = terminal_context.current()
        result = terminal_progress.view(
            terminal_status.decode(terminal.option(terminal_status.OPTION)),
            terminal_progress.decode(terminal.option(terminal_progress.HOOK_OPTION)),
            terminal_progress.decode(terminal.option(terminal_progress.ALERT_OPTION)),
            enabled=terminal.option(terminal_status.LLM_OPTION) != '0')
    except terminal_context.TerminalContextError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(result))


@progress_group.command('hook')
@click.argument('event', type=click.Choice(['start', 'prompt', 'post-tool', 'stop', 'end']))
def hook(event):
    """Read a Copilot hook payload from stdin; emit only the hook response JSON."""
    try:
        if not os.environ.get('TMUX') or not os.environ.get('TMUX_PANE'):
            click.echo('{}')
            return
        raw = sys.stdin.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError('Hook payload exceeds 10 MiB')
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError('Expected a hook object')
        output = terminal_progress.handle_hook(event, payload, terminal_context.current())
    except (terminal_context.TerminalContextError, ValueError) as exc:
        # Fail open: a reporting problem must not trap the user in a stop loop.
        click.echo('Lab progress hook: ' + str(exc), err=True)
        output = {}
    click.echo(json.dumps(output))
