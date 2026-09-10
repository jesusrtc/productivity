"""Read framework capabilities without writing to a vault or workspace."""
import click
from lab.agent_context import TOPICS, guide_path, read_context


@click.command(name='context')
@click.argument('topic', default='overview', type=click.Choice(list(TOPICS)))
@click.option('--path', 'show_path', is_flag=True, help='Print the installed guide path.')
def context_cmd(topic: str, show_path: bool) -> None:
    """Read Lab capabilities: overview, markdown, notebooks, or servers."""
    click.echo(str(guide_path(topic)) if show_path else read_context(topic))
