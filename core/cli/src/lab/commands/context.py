"""Read framework capabilities without writing to a vault or workspace."""
import click
from lab.agent_context import ContextError, TOPICS, current_context, guide_path, read_context


@click.command(name='context')
@click.argument('topic', default='overview', type=click.Choice(list(TOPICS)))
@click.option('--path', 'show_path', is_flag=True, help='Print the installed guide path.')
def context_cmd(topic: str, show_path: bool) -> None:
    """Read Lab's user guide, changelog, overview or capability topics."""
    try:
        content = str(guide_path(topic)) if show_path else current_context() if topic == 'overview' else read_context(topic)
    except (ContextError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(content)
