"""Delegate to visible Lab child terminals from any supported agent CLI."""
import uuid

import click

from lab import terminal_context


def parent_identity():
    try:
        current = terminal_context.current()
        created, socket = terminal_context.tmux(current.socket, 'display-message', '-p',
            '-t', current.pane, '#{session_created}\t#{socket_path}').split('\t', 1)
        return {'name':current.name, 'tmux_socket':socket,
                'tmux_id':current.session_id, 'created':int(created)}
    except (terminal_context.TerminalContextError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


@click.command('spawn')
@click.option('--agent', type=click.Choice(['copilot', 'codex', 'claude']),
              help="Child provider; defaults to the calling terminal's provider.")
@click.option('--name', required=True, help='Short name displayed on the child terminal tab.')
@click.option('--prompt', help='Task for this child; use --prompt-file for multiline tasks.')
@click.option('--prompt-file', type=click.File('r', encoding='utf-8'), help='UTF-8 task file; - reads stdin.')
@click.option('--request-id', type=click.UUID, help='Reuse this UUID when retrying a launch; prevents duplicates.')
def spawn(agent, name, prompt, prompt_file, request_id):
    """Launch a subagent in its own tmux session beneath this LLM terminal."""
    from lab import api_client
    if (prompt is None) == (prompt_file is None):
        raise click.UsageError('Use exactly one of --prompt or --prompt-file.')
    text = prompt_file.read(64001) if prompt_file else prompt
    if not text.strip() or len(text) > 64000 or '\x00' in text:
        raise click.UsageError('Task must contain 1–64000 characters without NUL bytes.')
    if not name.strip() or len(name) > 120:
        raise click.UsageError('Name must contain 1–120 characters.')
    ident = str(request_id or uuid.uuid4())
    # Print before network I/O so even a timeout leaves a retryable launch ID.
    click.echo('Launch request: ' + ident, err=True)
    api_client.output(api_client.request('POST', '/api/term/subagents', body={
        'parent':parent_identity(), 'request_id':ident, 'agent':agent,
        'label':name.strip(), 'prompt':text}, timeout=60))


@click.command('children')
def children():
    """List this terminal's live subagents and their explicit agent reports."""
    from lab import api_client
    api_client.output(api_client.request('POST', '/api/term/subagents/list',
        body={'parent':parent_identity()}))


@click.command('read')
@click.argument('child_id', type=click.UUID)
@click.option('--lines', type=click.IntRange(1, 2000), default=200, show_default=True)
def read_child(child_id, lines):
    """Read a child's recent terminal output without opening or reviewing it."""
    from lab import api_client
    api_client.output(api_client.request('POST', '/api/term/subagents/read', body={
        'parent':parent_identity(), 'child_id':str(child_id), 'lines':lines}))
