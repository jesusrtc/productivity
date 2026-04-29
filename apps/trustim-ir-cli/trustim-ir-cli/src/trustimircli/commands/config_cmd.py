import sys

import click

from trustimircli.config import ENVIRONMENTS, ENV_ALIASES, get_env, set_env, resolve_env, get_cert_name, set_cert_name

ALL_ENV_KEYS = list(ENVIRONMENTS.keys()) + list(ENV_ALIASES.keys())


def _interactive_select(options, current):
    """Arrow-key selection menu. Returns selected key or None on ctrl-c."""
    try:
        import tty
        import termios
    except ImportError:
        # Fallback for systems without termios (Windows)
        click.echo('Interactive selection not supported. Use: ir config --env <env>')
        return None

    keys = list(options.keys())
    idx = keys.index(current) if current in keys else 0

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    def _render(selected_idx):
        # Move cursor up to overwrite previous render (except first time)
        for key_idx, key in enumerate(keys):
            env = options[key]
            marker = '>' if key_idx == selected_idx else ' '
            highlight = click.style(f' {env["name"]} ({key})', bold=(key_idx == selected_idx))
            click.echo(f'  {marker}{highlight}')

    def _clear_lines(n):
        for _ in range(n):
            sys.stdout.write('\033[A\033[2K')
        sys.stdout.flush()

    click.echo('Select environment (arrow keys + enter):')
    click.echo()
    _render(idx)

    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch == '\r' or ch == '\n':
                break
            if ch in ('\x03', '\x04', ''):  # ctrl-c, ctrl-d, EOF
                return None
            if ch == '\x1b':
                seq = sys.stdin.read(2)
                if seq == '[A':  # up
                    idx = (idx - 1) % len(keys)
                elif seq == '[B':  # down
                    idx = (idx + 1) % len(keys)
            _clear_lines(len(keys))
            _render(idx)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    return keys[idx]


@click.command('config')
@click.option('--env', 'env_key', type=click.Choice(ALL_ENV_KEYS, case_sensitive=False),
              default=None, help='Set environment non-interactively (stg, prod, ei).')
@click.option('--cert', 'cert_name', default=None,
              help='Set mTLS client certificate name (from --list-certs).')
@click.option('--list-certs', is_flag=True, help='List available mTLS client certificates.')
def config(env_key, cert_name, list_certs):
    """Configure active environment and mTLS certificate."""
    if list_certs:
        _show_certs()
        return

    if cert_name is not None:
        _set_cert(cert_name)
        return

    if env_key is not None:
        resolved = resolve_env(env_key)
        set_env(resolved)
        env = ENVIRONMENTS[resolved]
        if env_key != resolved:
            click.echo(f'Environment set to {env["name"]} ({env_key} -> {resolved}) -> {env["host"]}')
        else:
            click.echo(f'Environment set to {env["name"]} ({resolved}) -> {env["host"]}')
        return

    # Interactive arrow-key selection
    selected = _interactive_select(ENVIRONMENTS, current=get_env())
    if selected is None:
        click.echo('Cancelled.')
        return

    set_env(selected)
    env = ENVIRONMENTS[selected]
    click.echo()
    click.echo(f'Environment set to {env["name"]} ({selected}) -> {env["host"]}')


def _show_certs():
    try:
        from trustimircli.client import list_keychain_identities
    except ImportError:
        click.echo('Certificate listing requires macOS with pyobjc.')
        return

    identities = list_keychain_identities()
    if not identities:
        click.echo('No client certificates found in keychain.')
        return

    import os
    try:
        username = os.getlogin()
    except OSError:
        username = os.environ.get('USER', '')

    configured = get_cert_name()
    click.echo('Available mTLS client certificates:')
    click.echo()
    for subject, _ in identities:
        markers = []
        if configured and subject == configured:
            markers.append('configured')
        elif not configured and subject == username:
            markers.append('auto-detected')
        suffix = f'  <- {", ".join(markers)}' if markers else ''
        click.echo(f'  {subject}{suffix}')
    click.echo()
    if configured:
        click.echo(f'Using: {configured} (set via --cert)')
    elif username:
        click.echo(f'Using: {username} (auto-detected from system username)')
    else:
        click.echo('No cert configured. Run: ir config --cert <name>')


def _set_cert(name):
    try:
        from trustimircli.client import list_keychain_identities
    except ImportError:
        set_cert_name(name)
        click.echo(f'Certificate set to: {name}')
        return

    identities = list_keychain_identities()
    subjects = [s for s, _ in identities]

    if name in subjects:
        set_cert_name(name)
        click.echo(f'Certificate set to: {name}')
    else:
        # Check partial match
        matches = [s for s in subjects if name.lower() in s.lower()]
        if len(matches) == 1:
            set_cert_name(matches[0])
            click.echo(f'Certificate set to: {matches[0]}')
        elif matches:
            click.echo(f'Multiple matches for "{name}":')
            for m in matches:
                click.echo(f'  {m}')
            click.echo('Be more specific.')
        else:
            click.echo(f'Warning: No cert named "{name}" found in keychain. Saving anyway.')
            set_cert_name(name)
            click.echo(f'Certificate set to: {name}')
