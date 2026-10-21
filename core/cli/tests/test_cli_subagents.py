"""Shared subagent commands preserve literal tasks and refuse guessed parents."""
from click.testing import CliRunner
import pytest

from lab import agent_context, api_client, terminal_context
from lab.cli import main


@pytest.mark.parametrize('options', [[],['--prompt',''],['--prompt','x','--prompt-file','-'],['--prompt','x\0y'],['--prompt','x'*64001]])
def test_invalid_task_never_contacts_server(options,monkeypatch):
    calls=[];monkeypatch.setattr(api_client,'request',lambda *a,**k:calls.append(a))
    result=CliRunner().invoke(main,['agents','spawn','--name','Child',*options],input='task')
    assert result.exit_code!=0 and not calls


def test_outside_lab_refuses_to_guess_parent(monkeypatch):
    monkeypatch.delenv('TMUX',raising=False);monkeypatch.delenv('TMUX_PANE',raising=False)
    calls=[];monkeypatch.setattr(api_client,'request',lambda *a,**k:calls.append(a))
    result=CliRunner().invoke(main,['agents','spawn','--name','Child','--prompt','Read only'])
    assert result.exit_code!=0 and 'owning Lab tmux' in result.output and not calls


@pytest.mark.parametrize('provider',['copilot','codex','claude'])
def test_prompt_file_is_literal_and_preserves_provider_options(provider,tmp_path,monkeypatch):
    prompt=tmp_path/'task.txt';text='--flags `never execute`\n$(still literal) 🧪';prompt.write_text(text)
    launches=[]
    monkeypatch.setattr(agent_context,'prepare_launch',lambda agent,args,env:([agent,*args],env))
    monkeypatch.setattr('os.execvpe',lambda binary,argv,env:launches.append(argv))
    monkeypatch.setattr(terminal_context,'current',lambda env:(_ for _ in ()).throw(terminal_context.TerminalContextError('outside')))
    result=CliRunner().invoke(main,['agents','run','--prompt-file',str(prompt),provider,'--','--model','chosen'])
    assert result.exit_code==0,result.output
    assert launches==[[provider,'--model','chosen',*(['--interactive',text] if provider=='copilot' else ['--',text])]]
