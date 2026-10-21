"""CLI → API → independent native tmux agents, without paid model calls."""
import json
import os
from pathlib import Path
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from click.testing import CliRunner
import pytest

from core.routes import term
from lab import api_client, terminal_status
from lab.cli import main
from .test_term_creation_native import native_creation_tmux, native_creation_client  # noqa: F401


@pytest.fixture
def agent_binaries(tmp_path, native_creation_tmux, monkeypatch):
    run, _, _ = native_creation_tmux
    folder = tmp_path / 'agents'; folder.mkdir()
    for agent in ['copilot', 'codex', 'claude']:
        receipt = tmp_path / (agent + '.json')
        script = f'''#!{sys.executable}
import json,os,sys,time,subprocess
if 'app-server' in sys.argv:
 for line in sys.stdin:
  call=json.loads(line)
  value={{'config':{{'developer_instructions':'EXISTING_RULES'}}}} if call['method']=='config/read' else {{}}
  print(json.dumps({{'id':call['id'],'result':value}}),flush=True)
 sys.exit()
context=subprocess.run([sys.executable,'-m','lab','context','llm'],capture_output=True,text=True)
subprocess.run([sys.executable,'-m','lab','notifications','working','Checking delegated task'],check=True)
print('CHILD_RESULT_LITERAL_READY',flush=True)
subprocess.run([sys.executable,'-m','lab','notifications','finished','Delegated task verified'],check=True)
with open({str(receipt)!r},'w') as output:
 json.dump({{'argv':sys.argv[1:],'cwd':os.getcwd(),'tmux':os.environ.get('TMUX'),'pane':os.environ.get('TMUX_PANE'),
 'vault':os.environ.get('LAB_VAULT'),'workspace':os.environ.get('LAB_CONTEXT_WORKSPACE'),
 'context_ok':context.returncode==0 and 'lab agents spawn' in context.stdout}},output)
time.sleep(60)
'''
        executable = folder / agent; executable.write_text(script); executable.chmod(0o700)
    search = str(folder) + os.pathsep + os.environ['PATH']
    monkeypatch.setenv('PATH', search)
    run('set-environment','-g','PATH',search)
    # The base creation fixture intentionally uses a sleeping fake login shell.
    # Use a real command interpreter for the provider process tests.
    run('set-option','-g','default-shell','/bin/sh')
    return tmp_path


def parent(run, client, agent='copilot'):
    created = client.post('/api/term/sessions', json={'workspace_id':'demo','kind':'terminal'}).json()
    run('set-option','-t',created['name'],'@lab_llm',agent)
    row = next(row for row in client.get('/api/term/sessions',params={'workspace_id':'demo'}).json() if row['name']==created['name'])
    identity = {key:row[key] for key in ['name','tmux_socket','tmux_id','created']}
    return row, identity


@pytest.mark.parametrize('agent', ['copilot','codex','claude'])
def test_native_cli_launch_inherits_provider_reports_independently_and_survives_reload(
        agent, native_creation_tmux, native_creation_client, seed_workspace, agent_binaries, monkeypatch):
    run, _, _ = native_creation_tmux
    workspace = seed_workspace('demo'); client = native_creation_client
    owner, identity = parent(run, client, agent)
    address = run('display-message','-p','-t',owner['name'],'#{socket_path},#{pid},0').stdout.strip()
    monkeypatch.setenv('TMUX',address); monkeypatch.setenv('TMUX_PANE',owner['pane_id'])
    def request(method, path, *, body, **kwargs):
        response = client.post(path,json=body)
        assert response.status_code == 200,response.text
        return response.json()
    monkeypatch.setattr(api_client,'request',request)
    prompt = '--literal flags; $(touch SHOULD_NOT_EXIST) `touch ALSO_NOT`\nRead only <scope> 🧪'
    task = agent_binaries / 'assignment.txt'; task.write_text(prompt)
    ident = str(uuid.uuid4()); runner = CliRunner()
    args = ['agents','spawn','--name','Review '+agent,'--prompt-file',str(task),'--request-id',ident]
    result = runner.invoke(main,args)
    assert result.exit_code == 0,result.output
    response = json.loads(result.stdout); child = response['child']
    assert child['agent']==agent and child['running'] and child['parent']==identity
    assert child['name'] != owner['name'] and child['terminal']['tmux_id'] != owner['tmux_id']
    deadline = time.monotonic()+12
    receipt = agent_binaries / (agent+'.json')
    while not receipt.exists():
        assert time.monotonic()<deadline,run('capture-pane','-p','-t',child['name'],check=False).stdout
        time.sleep(.05)
    capture = json.loads(receipt.read_text())
    assert capture['cwd']==str(workspace) and capture['workspace']=='demo' and capture['vault']==str(workspace.parent.parent)
    assert capture['pane'] != owner['pane_id'] and capture['context_ok']
    assert capture['argv'][-1].endswith(prompt)
    assert '--interactive' in capture['argv'] if agent=='copilot' else capture['argv'][-2]=='--'
    assert not (workspace/'SHOULD_NOT_EXIST').exists() and not (workspace/'ALSO_NOT').exists()
    repeat = runner.invoke(main,args)
    assert repeat.exit_code==0 and json.loads(repeat.stdout)['already_launched']
    listed = runner.invoke(main,['agents','children'])
    assert listed.exit_code==0,listed.output
    children = json.loads(listed.stdout)['children']
    assert len(children)==1 and children[0]['terminal_status']['state']=='finished'
    output = runner.invoke(main,['agents','read',ident,'--lines','40'])
    assert output.exit_code==0 and 'CHILD_RESULT_LITERAL_READY' in json.loads(output.stdout)['output']
    assert run('show-options','-qv','-t',owner['name'],'@lab_status').stdout.strip()==''
    report = terminal_status.decode(run('show-options','-qv','-t',child['name'],'@lab_status').stdout.strip())
    assert report['state']=='finished','Parent reads never acknowledge or rewrite the child status'
    saved = client.get('/api/term/sessions/saved',params={'workspace_id':'demo'}).json()
    entry = next(row for row in saved if row['name']==child['logical_name'])
    assert entry['parent_terminal']==owner['logical_name'] and entry['subagent']['parent']==identity
    assert prompt not in term._load_meta(workspace.parent.parent)[child['name']]['cmd']
    term._save_meta(workspace.parent.parent,{})
    rows = client.get('/api/term/sessions',params={'workspace_id':'demo'}).json()
    restored = next(row for row in rows if row['name']==child['name'])
    assert restored['parent_terminal']==owner['logical_name'] and restored['subagent']['id']==ident
    # Existing child records cannot revive or target a replaced incarnation.
    run('kill-session','-t',child['name'])
    replay = runner.invoke(main,args)
    assert replay.exit_code==0 and not json.loads(replay.stdout)['child']['running']
    assert client.post('/api/term/sessions',json={'workspace_id':'demo','name':child['logical_name'],'restore':True}).status_code==409
    run('new-session','-d','-s',child['name'],'/bin/sleep 60')
    wrong = client.post('/api/term/subagents/read',json={'parent':identity,'child_id':ident})
    assert wrong.status_code==409


def test_concurrent_retries_nested_children_and_cross_parent_reads(
        native_creation_tmux, native_creation_client, seed_workspace, agent_binaries):
    run, _, _=native_creation_tmux; client=native_creation_client
    workspace=seed_workspace('demo'); owner, identity=parent(run,client)
    ident=str(uuid.uuid4())
    body={'parent':identity,'request_id':ident,'label':'Reviewer','prompt':'Inspect only'}
    # The real FastAPI client handles parallel requests; skip its index rebuild
    # wrapper here so this test exercises the launch lock, not fixture rebuilding.
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:client._inner.post('/api/term/subagents',json=body),range(2)))
    assert all(row.status_code==200 for row in responses),[row.text for row in responses]
    assert sorted(row.json()['already_launched'] for row in responses)==[False,True]
    child=responses[0].json()['child']
    changed=client.post('/api/term/subagents',json={**body,'prompt':'Different task'})
    assert changed.status_code==409
    grand_id=str(uuid.uuid4())
    grand=client.post('/api/term/subagents',json={**body,'parent':child['terminal'],'request_id':grand_id,'label':'Nested'})
    assert grand.status_code==200,grand.text
    rows=client.get('/api/term/sessions',params={'workspace_id':'demo'}).json()
    nested=next(row for row in rows if row['name']==grand.json()['child']['name'])
    assert nested['parent_terminal']==child['logical_name']
    assert client.post('/api/term/subagents/read',json={'parent':identity,'child_id':grand_id}).status_code==404
    assert client.post('/api/term/subagents/list',json={'parent':identity}).json()['children'][0]['id']==ident
    assert client.post('/api/term/subagents/list',json={'parent':child['terminal']}).json()['children'][0]['id']==grand_id
    other=client.post('/api/term/sessions',json={'workspace_id':'demo','kind':'terminal','name':'other'}).json()
    row=next(row for row in client.get('/api/term/sessions',params={'workspace_id':'demo'}).json() if row['name']==other['name'])
    alternate={key:row[key] for key in identity}
    assert client.post('/api/term/subagents',json={**body,'parent':alternate}).status_code==409
    assert client.post('/api/term/subagents/read',json={'parent':alternate,'child_id':ident}).status_code==404
    # Resolve the runtime location through Lab rather than assuming a layout.
    from lab import paths
    prompt=paths.vault_state_dir(workspace.parent.parent)/'subagents'/(uuid.UUID(ident).hex+'.txt')
    assert prompt.stat().st_mode & 0o777==0o600


def test_subagent_launch_rejects_stale_or_unowned_requests_before_spawn(
        native_creation_tmux, native_creation_client, seed_workspace, agent_binaries, monkeypatch):
    run, _, _ = native_creation_tmux; client=native_creation_client
    seed_workspace('demo'); owner, identity=parent(run,client)
    before=run('list-sessions','-F','#{session_name}').stdout
    base={'parent':identity,'request_id':str(uuid.uuid4()),'label':'Child','prompt':'Read only'}
    for field,value in [('tmux_id','$99999'),('created',1),('tmux_socket','unrelated'),('name','not-owned')]:
        response=client.post('/api/term/subagents',json={**base,'parent':{**identity,field:value}})
        assert response.status_code in (404,409),response.text
    for changes in [{'agent':'invalid'},{'prompt':' '},{'prompt':'x\0y'},{'label':' '}]:
        assert client.post('/api/term/subagents',json={**base,**changes}).status_code==422
    monkeypatch.setattr(term.vault_config,'supported_agents',lambda root:['claude'])
    assert client.post('/api/term/subagents',json=base).status_code==400
    assert run('list-sessions','-F','#{session_name}').stdout==before


def test_output_read_rechecks_identity_atomically_after_discovery(
        native_creation_tmux, native_creation_client, seed_workspace, agent_binaries, monkeypatch):
    from core import subagent_terminals
    run, _, _=native_creation_tmux; client=native_creation_client
    seed_workspace('demo'); _, identity=parent(run,client)
    ident=str(uuid.uuid4())
    response=client.post('/api/term/subagents',json={'parent':identity,'request_id':ident,'label':'Read race','prompt':'Read only'})
    assert response.status_code==200,response.text
    child=response.json()['child']
    original=subagent_terminals._tmux
    def replace_before_capture(row,*args):
        if args[0]=='if-shell':
            run('kill-session','-t',child['name'])
            run('new-session','-d','-s',child['name'],'/bin/sleep 60')
        return original(row,*args)
    monkeypatch.setattr(subagent_terminals,'_tmux',replace_before_capture)
    read=client.post('/api/term/subagents/read',json={'parent':identity,'child_id':ident})
    assert read.status_code==409,read.text


def test_exited_provider_retains_error_output_without_relaunch(
        native_creation_tmux, native_creation_client, seed_workspace, agent_binaries):
    run, _, _=native_creation_tmux;client=native_creation_client
    seed_workspace('demo');_,identity=parent(run,client)
    binary=agent_binaries/'agents/copilot'
    binary.write_text(f'#!{sys.executable}\nprint("PROVIDER_STARTUP_ERROR",flush=True)\nraise SystemExit(2)\n')
    ident=str(uuid.uuid4());body={'parent':identity,'request_id':ident,'label':'Failed startup','prompt':'Read only'}
    response=client.post('/api/term/subagents',json=body)
    assert response.status_code==200,response.text
    deadline=time.monotonic()+5
    while True:
        child=client.post('/api/term/subagents/list',json={'parent':identity}).json()['children'][0]
        if not child['running']:break
        assert time.monotonic()<deadline
        time.sleep(.02)
    assert child['available'] and not child['terminal_status']
    read=client.post('/api/term/subagents/read',json={'parent':identity,'child_id':ident})
    assert read.status_code==200 and 'PROVIDER_STARTUP_ERROR' in read.json()['output']
    repeat=client.post('/api/term/subagents',json=body).json()
    assert repeat['already_launched'] and not repeat['child']['running']
