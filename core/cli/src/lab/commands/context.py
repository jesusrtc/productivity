"""Read framework capabilities without writing to a vault or workspace."""
import os

import click
from lab.agent_context import ContextError, TOPICS, current_context, guide_path, read_context, llm_context
from lab.agent_context import context_version, CONTEXT_VERSION_OPTION
from lab import terminal_context, terminal_status


@click.command(name='context')
@click.argument('topic', default='overview', type=click.Choice([*TOPICS, 'llm', 'version', 'update']))
@click.option('--path', 'show_path', is_flag=True, help='Print the installed guide path.')
def context_cmd(topic: str, show_path: bool) -> None:
    """LLM loads full agent context and marks its terminal. UPDATE is silent if current.

    VERSION prints the content ID. Other topics read individual guides.
    """
    try:
        if topic in ('llm', 'version', 'update'):
            if show_path:
                raise click.UsageError('--path is only available for documentation topics.')
            version = context_version()
            if topic == 'version':
                click.echo(version)
                return
            # No process-global or browser-selected destination. Outside tmux,
            # print context each time without persisting an acknowledgement.
            terminal = None
            if os.environ.get('TMUX') or os.environ.get('TMUX_PANE'):
                terminal = terminal_context.current()
                if topic == 'llm':
                    if terminal.option(terminal_status.LLM_OPTION) not in ('1', 'claude', 'codex', 'copilot'):
                        terminal.set_option(terminal_status.LLM_OPTION, '1')
                elif terminal.option(CONTEXT_VERSION_OPTION) == version:
                    return
            click.echo(llm_context(version=version))
            click.get_text_stream('stdout').flush()
            # Mark only after successful output; a failed read/pipe stays pending.
            if terminal:
                terminal.set_option(CONTEXT_VERSION_OPTION, version)
            return
        content = str(guide_path(topic)) if show_path else current_context() if topic == 'overview' else read_context(topic)
    except (ContextError, terminal_context.TerminalContextError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(content)
