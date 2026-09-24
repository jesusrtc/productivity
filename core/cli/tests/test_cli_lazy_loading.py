"""Fresh agent launches must keep normal Click behavior without other commands."""
import importlib
import json
import subprocess
import sys

import click
from click.testing import CliRunner
import pytest

from lab.cli import main


@pytest.mark.parametrize('alias', ['agent', 'agents'])
def test_fresh_agent_launch_preserves_arguments_context_and_loads_only_its_commands(tmp_path, alias):
    result = subprocess.run([sys.executable, '-c', r'''
import json,os,sys
from pathlib import Path
from click.testing import CliRunner
from lab.cli import main
assert not any(name.startswith('lab.commands.') for name in sys.modules)
from lab import agent_context
calls=[]
agent_context.shutil.which=lambda name,**kwargs:'/synthetic/'+name
os.execvpe=lambda binary,argv,env:calls.append((binary,argv,env))
root=Path(sys.argv[1]).resolve()
context=str(root/'document-context.json')
result=CliRunner().invoke(main,[sys.argv[2],'run','--vault',str(root),'claude','--','--session-id','saved-id'],
    env={'LAB_DOCUMENT_CONTEXT':context,'LAB_ASSISTANT_HOME':str(root)})
assert result.exit_code==0,(result.output,result.exception)
assert len(calls)==1
binary,argv,env=calls[0]
assert binary=='/synthetic/claude'
assert argv==[binary,'--append-system-prompt-file',str(agent_context.guide_path()),'--session-id','saved-id']
assert env['LAB_VAULT']==str(root) and env['LAB_ASSISTANT_HOME']==str(root)
assert env['LAB_DOCUMENT_CONTEXT']==context
commands=sorted(name for name in sys.modules if name.startswith('lab.commands.'))
assert commands==['lab.commands.agents','lab.commands.context'],commands
assert 'lab.assistant' not in sys.modules
print(json.dumps({'commands':commands,'launches':len(calls)}))
''', str(tmp_path), alias], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['launches'] == 1


def test_all_help_errors_aliases_and_completion_match_eager_click_registration():
    # The previous public command registration, independent of the lazy table.
    registrations = {
        'agents': [('agents', 'agents_group'), ('agent', 'agents_group')],
        'assistant': [('assistant', 'assistant_group')],
        'app': [('app', 'app_group')],
        'artifact': [('artifact', 'artifact_group')],
        'config': [('config', 'config_group')],
        'context': [('context', 'context_cmd')],
        'migrations': [('migrations', 'migrations_cmd')],
        'index': [('index', 'index_group')],
        'link': [('link', 'link_group')],
        'notebook': [('notebook', 'notebook_group')],
        'ref': [('ref', 'ref_group')],
        'repo': [('repo', 'repo_group')],
        'pr': [('pr', 'pr_group')],
        'workspace': [('workspace', 'workspace_group')],
        'search': [('search', 'search_cmd')],
        'service': [('open', 'open_cmd'), ('start', 'start'), ('stop', 'stop')],
        'task': [('task', 'task_group')],
        'terminal': [('terminal', 'terminal_group')],
        'vault': [('init', 'init_cmd'), ('vault', 'vault_group')],
    }
    eager = click.Group(name=main.name, callback=main.callback, params=main.params, help=main.help)
    for module, entries in registrations.items():
        loaded = importlib.import_module('lab.commands.' + module)
        for name, attribute in entries:
            eager.add_command(getattr(loaded, attribute), name=name)
    paths = []
    def visit(command, path):
        paths.append(path)
        if isinstance(command, click.Group):
            with click.Context(command) as context:
                for name in command.list_commands(context):
                    visit(command.get_command(context, name), [*path, name])
    visit(eager, [])
    runner = CliRunner()
    for args in [*[path + ['--help'] for path in paths], ['--version'], [], ['unknown-command'],
                 ['agents', 'run', 'unknown-agent'], ['--bad-option']]:
        expected = runner.invoke(eager, args, prog_name='lab')
        actual = runner.invoke(main, args, prog_name='lab')
        assert (actual.exit_code, actual.stdout, actual.stderr) == (
            expected.exit_code, expected.stdout, expected.stderr), args
    with click.Context(main) as lazy_context, click.Context(eager) as eager_context:
        assert main.get_command(lazy_context, 'agent') is main.get_command(lazy_context, 'agents')
        for prefix in ('', 'a', 'work', '--'):
            assert [(item.value, item.type, item.help) for item in main.shell_complete(lazy_context, prefix)] == [
                (item.value, item.type, item.help) for item in eager.shell_complete(eager_context, prefix)]
