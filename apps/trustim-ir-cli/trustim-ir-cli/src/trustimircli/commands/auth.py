import webbrowser

import click
import requests

from trustimircli.config import get_auth, save_auth, clear_auth, get_host, get_env, ENVIRONMENTS


@click.group('auth')
def auth():
    """Manage authentication."""
    pass


@auth.command()
@click.option('--host', default=None,
              help='Base URL (defaults to active environment).')
@click.option('--no-validate', is_flag=True,
              help='Skip server-side cookie validation.')
def login(host, no_validate):
    """Log in by pasting cookies from the browser."""
    if host is None:
        host = get_host()
        env_key = get_env()
        env_name = ENVIRONMENTS.get(env_key, {}).get('name', env_key)
        click.echo(f'Environment: {env_name} ({env_key})')
    host = host.rstrip('/')
    cli_url = f'{host}/html/cli'

    click.echo(f'Opening {cli_url} in your browser...')
    click.echo('If it does not open, visit the URL manually.')
    webbrowser.open(cli_url)

    click.echo()
    cookies = click.prompt('Paste the cookie string from the page')
    cookies = cookies.strip()

    if not cookies:
        click.echo('No cookies provided. Aborting.', err=True)
        raise SystemExit(1)

    username = None

    if not no_validate:
        click.echo('Validating...')
        try:
            resp = requests.get(
                cli_url,
                headers={'Cookie': cookies},
                allow_redirects=False,
                timeout=15,
            )
        except requests.ConnectionError:
            click.echo(f'Error: Cannot connect to {host}', err=True)
            raise SystemExit(1)

        if resp.status_code == 200:
            username = _extract_username(resp.text)
        else:
            click.echo(f'Warning: Validation returned HTTP {resp.status_code}. Saving anyway.', err=True)

    if not username:
        username = click.prompt('Enter your LDAP username')

    save_auth(host, cookies, username)
    click.echo(f'Logged in as {username}. Config saved to ~/.config/ir/config.toml')


def _extract_username(html):
    """Try to extract username from the /html/cli page."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    # The template renders username in the page; look for patterns
    for tag in soup.find_all(['code', 'strong', 'span', 'b']):
        text = tag.get_text(strip=True)
        # username is typically a short alphanumeric string
        if text and len(text) < 30 and text.isidentifier():
            return text
    # Fallback: check title or h1
    title = soup.find('title')
    if title:
        text = title.get_text(strip=True)
        if text:
            return text
    return None


@auth.command()
def status():
    """Show current authentication state."""
    env_key = get_env()
    env_name = ENVIRONMENTS.get(env_key, {}).get('name', env_key)
    click.echo(f'Env:      {env_name} ({env_key})')

    auth_config = get_auth()
    if not auth_config.get('cookies'):
        click.echo('Not logged in. Run: ir auth login')
        return

    click.echo(f'Host:     {auth_config.get("host", get_host())}')
    click.echo(f'Username: {auth_config.get("username", "unknown")}')
    cookies = auth_config.get('cookies', '')
    preview = cookies[:40] + '...' if len(cookies) > 40 else cookies
    click.echo(f'Cookies:  {preview}')


@auth.command()
def logout():
    """Clear stored authentication."""
    clear_auth()
    click.echo('Logged out. Cookies cleared.')
