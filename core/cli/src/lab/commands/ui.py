"""Live UI operations, including client-only navigation, layouts and menus."""
from __future__ import annotations

import json

import click

from lab.api_client import output, request


def invoke(action, params=None, *, client=None, timeout=15):
    return request('POST', '/api/ui/command', body={'action': action, 'params': params or {},
        'client_id': client, 'timeout': timeout}, timeout=timeout+5)


@click.group(name='ui')
@click.option('--client', envvar='LAB_UI_CLIENT', default=None, help='Target from lab ui clients; required when multiple views are open.')
@click.option('--timeout', type=click.IntRange(1,60), default=15, show_default=True)
@click.pass_context
def ui_group(ctx, client, timeout):
    """Inspect and operate the same controls as the user in an open Lab view."""
    ctx.obj={'client':client,'timeout':timeout}


@ui_group.command('clients')
def clients():
    """List connected Lab views; choose one before manipulating its UI."""
    output(request('GET','/api/ui/clients'))


@ui_group.command('inspect')
@click.option('--offset', type=click.IntRange(0), default=0)
@click.option('--limit', type=click.IntRange(1,1000), default=200)
@click.pass_obj
def inspect(options, offset, limit):
    """Show current context, dialogs and visible controls with unique selectors."""
    output(invoke('inspect', {'offset':offset,'limit':limit}, **options))


@ui_group.command('command')
@click.argument('action')
@click.option('--json', 'json_body', default='{}', help='Action parameters; see lab context cli.')
@click.option('--body-file', type=click.File('r'), default=None, help='Read parameters from JSON, or - for stdin.')
@click.pass_obj
def command(options, action, json_body, body_file):
    """Run a named UI action with JSON parameters."""
    try:
        params=json.loads(body_file.read() if body_file else json_body)
        if not isinstance(params,dict): raise ValueError('parameters must be an object')
    except ValueError as exc:
        raise click.ClickException(f'Invalid parameters: {exc}') from exc
    output(invoke(action,params,**options))


def _pointer_command(action):
    @ui_group.command(action)
    @click.argument('selector')
    @click.option('--modifier', multiple=True, type=click.Choice(['meta','ctrl','alt','shift']))
    @click.option('--prompt', multiple=True, help='Answer native prompts, in order, for this action only.')
    @click.option('--confirm', type=click.Choice(['yes','no']), default=None, help='Answer a native confirmation for this action only.')
    @click.pass_obj
    def pointer(options, selector, modifier, prompt, confirm):
        """Activate a unique selector from inspect; menus and dialogs stay available."""
        dialogs=[{'type':'prompt','value':value} for value in prompt]
        if confirm is not None: dialogs.append({'type':'confirm','value':confirm=='yes'})
        output(invoke(action,{'selector':selector,'modifiers':list(modifier),'dialogs':dialogs},**options))
    return pointer


for _action in ('click','contextmenu','hover'):
    _pointer_command(_action)


@ui_group.command('fill')
@click.argument('selector')
@click.argument('value')
@click.pass_obj
def fill(options, selector, value):
    """Edit an input, select, checkbox or Markdown editor using its UI handlers."""
    output(invoke('fill',{'selector':selector,'value':value},**options))


@ui_group.command('key')
@click.argument('key')
@click.option('--selector', default=None, help='Defaults to the focused control.')
@click.option('--modifier', multiple=True, type=click.Choice(['meta','ctrl','alt','shift']))
@click.pass_obj
def key(options, key, selector, modifier):
    """Send Enter, Escape or a keyboard shortcut to the selected view."""
    output(invoke('key',{'key':key,'selector':selector,'modifiers':list(modifier)},**options))


@ui_group.command('drag')
@click.argument('source')
@click.argument('target')
@click.pass_obj
def drag(options, source, target):
    """Move tasks, assets, worktrees, terminals or tabs through their drop handlers."""
    output(invoke('drag',{'selector':source,'target':target},**options))


@ui_group.command('scroll')
@click.argument('selector')
@click.option('--y', type=int, default=500)
@click.option('--x', type=int, default=0)
@click.pass_obj
def scroll(options, selector, y, x):
    """Scroll a pane by the supplied pixels."""
    output(invoke('scroll',{'selector':selector,'y':y,'x':x},**options))


@ui_group.command('wait')
@click.argument('selector')
@click.option('--text', default=None, help='Wait for matching text within the control.')
@click.option('--absent', is_flag=True, help='Wait for the control to disappear.')
@click.pass_obj
def wait(options, selector, text, absent):
    """Wait for an asynchronous UI result without repeating the action."""
    output(invoke('wait',{'selector':selector,'text':text,'absent':absent,'ms':max(1,options['timeout']*1000-1000)},**options))


@ui_group.command('rename-tab')
@click.argument('name')
@click.argument('label')
@click.pass_obj
def rename_tab(options, name, label):
    """Rename a terminal tab in the selected view and persist its label."""
    output(invoke('terminal-rename',{'name':name,'label':label},**options))


@ui_group.command('paste')
@click.argument('text', required=False)
@click.option('--file', 'text_file', type=click.File('r'), default=None, help='Read text from a file, or - for stdin.')
@click.option('--terminal', default=None, help='Select this terminal before pasting; otherwise use the current terminal.')
@click.option('--submit', is_flag=True, help='Send Enter after pasting.')
@click.pass_obj
def paste(options, text, text_file, terminal, submit):
    """Paste into a connected terminal; Enter is sent only with --submit."""
    if (text is None)==(text_file is None):
        raise click.ClickException('Use exactly one of TEXT or --file.')
    output(invoke('terminal-input',{'name':terminal,'text':text_file.read() if text_file else text,'submit':submit},**options))
