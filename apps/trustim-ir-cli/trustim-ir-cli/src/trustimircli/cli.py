import click

from trustimircli.commands.auth import auth
from trustimircli.commands.alert import alert
from trustimircli.commands.incident import incident
from trustimircli.commands.undo_cmd import undo
from trustimircli.commands.config_cmd import config


@click.group()
@click.version_option(version='0.1.0', prog_name='ir')
def cli():
    """ir - CLI for InResponse (airp-web)."""
    pass


cli.add_command(auth)
cli.add_command(alert)
cli.add_command(incident)
cli.add_command(undo)
cli.add_command(config)


@cli.command()
def help():
    """Show enum reference from the server."""
    from trustimircli import client
    from trustimircli.parser import parse_html
    from trustimircli.formatter import format_table

    resp = client.get('/html/help')
    soup = parse_html(resp.text)

    for h2 in soup.find_all('h2'):
        heading = h2.get_text(strip=True)
        click.echo(click.style(heading, bold=True))
        # Look for a list or table after the heading
        sibling = h2.find_next_sibling()
        while sibling and sibling.name != 'h2':
            if sibling.name == 'ul':
                for li in sibling.find_all('li'):
                    click.echo(f'  - {li.get_text(strip=True)}')
            elif sibling.name == 'table':
                headers = [th.get_text(strip=True) for th in sibling.find_all('th')]
                rows = []
                for tr in sibling.find_all('tr')[1:]:
                    row = [td.get_text(strip=True) for td in tr.find_all('td')]
                    if row:
                        rows.append(row)
                format_table(headers, rows)
            elif sibling.name == 'p':
                text = sibling.get_text(strip=True)
                if text:
                    click.echo(f'  {text}')
            sibling = sibling.find_next_sibling()
        click.echo()
