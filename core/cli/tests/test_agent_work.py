"""Persistent attribution is explicit, incarnation-scoped and separate from tasks."""
import json
from concurrent.futures import ThreadPoolExecutor
import uuid

from click.testing import CliRunner
import pytest

from lab import agent_work, terminal_context
from lab.cli import main


@pytest.fixture
def owner(monorepo):
    return dict(name='parent',tmux_socket='/tmp/private-agent-socket',tmux_id='$1',created=10)


def test_requests_files_rename_delete_and_incarnation_isolation(owner,tmp_path):
    first=agent_work.start(owner,'First request',request='User request',context='Scope')
    file=tmp_path/'résumé.md';file.write_text('# First')
    agent_work.record(owner,[file],'created')
    file.write_text('# Updated');agent_work.record(owner,[file])
    history=agent_work.history(owner)['assignments']
    assert len(history)==1 and len(history[0]['files'])==1
    reported=history[0]['files'][0]
    assert reported['operation']=='created' and reported['sha256']
    agent_work.finish(owner,'Tested')
    assert agent_work.current(owner)['status']=='finished'
    second=agent_work.start(owner,'Second request')
    moved=tmp_path/'new.md';file.rename(moved)
    agent_work.record(owner,[moved],'renamed',str(file))
    moved.unlink();agent_work.record(owner,[moved],'deleted')
    history=agent_work.history(owner)['assignments']
    assert [row['id'] for row in history]==[second['id'],first['id']]
    assert history[0]['files'][0]['previous_path']==str(file)
    assert history[0]['files'][0]['operation']=='deleted'
    assert agent_work.history({**owner,'tmux_id':'$2'})['assignments']==[]
    assert agent_work.history({**owner,'created':11})['assignments']==[]
    assert agent_work.history({**owner,'tmux_socket':'/tmp/other'})['assignments']==[]
    # Unreported files from a concurrent editor never appear.
    (tmp_path/'unrelated.md').write_text('Other agent')
    assert len(history[1]['files'])==1


def test_delegated_rollup_registration_race_and_parent_cycles(owner,tmp_path):
    root=agent_work.start(owner,'Chief of staff',context='Decisions and constraints')
    child={**owner,'name':'child','tmux_id':'$2'}
    ident=str(uuid.uuid4())
    agent_work.start(child,'Child started',assignment_id=ident)
    agent_work.finish(child,'Already verified')
    next_request=agent_work.start(child,'Next request')
    agent_work.start(child,'Delegated analysis',request='Expected result',context='Relevant context',
        parent_id=root['id'],assignment_id=ident,register=True)
    assert agent_work.current(child)['id']==next_request['id']
    delegated=next(row for row in agent_work.history(child)['assignments'] if row['id']==ident)
    assert delegated['status']=='finished' and delegated['summary']=='Already verified'
    assert delegated['context']=='Relevant context' and delegated['parent_id']==root['id']
    grand={**owner,'name':'grandchild','tmux_id':'$3'}
    agent_work.start(grand,'Sub-assignment',parent_id=ident)
    assert len(agent_work.history(owner)['assignments'])==1
    assert len(agent_work.history(owner,True)['assignments'])==3
    newer=agent_work.start(owner,'New user request')
    assert [row['id'] for row in agent_work.history(owner,True)['assignments']][:3]==[newer['id'],root['id'],ident]
    with pytest.raises(ValueError,match='cycle'):
        agent_work.start(owner,'Cycle',assignment_id=root['id'],parent_id=ident)
    with pytest.raises(ValueError,match='different agent'):
        agent_work.start(child,'Steal',assignment_id=root['id'])
    with pytest.raises(ValueError,match='own request'):
        agent_work.record(child,[tmp_path/'missing'],assignment_id=root['id'])


def test_batch_validation_is_atomic_and_parallel_requests_remain_separate(owner,tmp_path):
    agent_work.start(owner,'Own request')
    file=tmp_path/'report.txt';file.write_text('Shared file, distinct attribution')
    with pytest.raises(ValueError,match='not found'):
        agent_work.record(owner,[file,tmp_path/'missing'])
    assert agent_work.history(owner)['assignments'][0]['files']==[]
    def report(index):
        terminal={**owner,'name':f'agent-{index}','tmux_id':f'${index+2}'}
        agent_work.start(terminal,f'Request {index}')
        agent_work.record(terminal,[file])
        return agent_work.history(terminal)['assignments']
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(report,range(8)))
    assert len({row[0]['id'] for row in rows})==8
    assert all(len(row)==1 and len(row[0]['files'])==1 for row in rows)
    from lab import paths
    assert (paths.global_config_dir()/'agent-work.sqlite3').stat().st_mode & 0o777==0o600


def test_cli_workflow_does_not_rewrite_objective_or_terminal_status(owner,seed_workspace,tmp_path,monkeypatch):
    workspace=seed_workspace('demo')
    before={path:path.read_bytes() for path in workspace.iterdir() if path.is_file()}
    monkeypatch.setattr(agent_work,'identity',lambda:owner)
    runner=CliRunner();prompt=tmp_path/'brief.txt';prompt.write_text('Literal <request> `no shell`')
    def run(*args):
        result=runner.invoke(main,['agents',*args])
        assert result.exit_code==0,result.output
        return json.loads(result.output)
    assignment=run('work','start','--title','User petition','--request-file',str(prompt))
    file=tmp_path/'changed.md';file.write_text('# Document')
    run('files','record','--operation','created',str(file))
    assert run('files','list')['assignments'][0]['files'][0]['path']==str(file)
    run('work','finish','--summary','Verified result')
    resumed=run('work','start','--id',assignment['id'],'--title','Resume')
    assert resumed['request']=='Literal <request> `no shell`' and resumed['status']=='working'
    assert before=={path:path.read_bytes() for path in before}
    result=runner.invoke(main,['agents','files','record','--operation','renamed',str(file)])
    assert result.exit_code!=0 and '--previous-path' in result.output
    monkeypatch.setattr(agent_work,'identity',lambda:(_ for _ in ()).throw(terminal_context.TerminalContextError('No owning Lab tmux terminal')))
    assert runner.invoke(main,['agents','work','show']).exit_code!=0


def test_spawn_cli_passes_brief_and_absolute_reference(owner,tmp_path,monkeypatch):
    from lab import api_client
    from lab.commands import subagents
    monkeypatch.setattr(subagents,'parent_identity',lambda:owner)
    monkeypatch.chdir(tmp_path)
    brief=tmp_path/'brief.txt';brief.write_text('Scope and expected output')
    calls=[]
    monkeypatch.setattr(api_client,'request',lambda *a,**kw:calls.append(kw['body']) or {})
    result=CliRunner().invoke(main,['agents','spawn','--name','Child','--prompt','Assignment',
        '--context-file',str(brief),'--include-file','reference.md'])
    assert result.exit_code==0,result.output
    assert calls[0]['context']=='Scope and expected output'
    assert calls[0]['context_files']==[str(tmp_path/'reference.md')]
