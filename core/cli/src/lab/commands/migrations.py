"""Read packaged migration and format guidance without touching client data."""
from pathlib import Path

import click

from lab.agent_context import GUIDE_DIR


GUIDES = {
    'overview': 'migrations.md',
    'assistant-documents': 'migrations/assistant-documents.md',
    'assistant-subtabs': 'migrations/assistant-subtabs.md',
    'assistant-records-v2': 'migrations/assistant-records-v2.md',
    'workspace-agent-context': 'migrations/workspace-agent-context.md',
    'vault-workspace-names': 'migrations/vault-workspace-names.md',
}


@click.command(name='migrations')
@click.argument('topic', default='overview', type=click.Choice(list(GUIDES)))
@click.option('--path', 'show_path', is_flag=True, help='Print the installed guide path.')
def migrations_cmd(topic: str, show_path: bool) -> None:
    """Read migration instructions and expected formats; does not migrate data."""
    source: Path = GUIDE_DIR / GUIDES[topic]
    click.echo(str(source) if show_path else source.read_text(encoding='utf-8'))
