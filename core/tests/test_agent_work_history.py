"""Real tmux identity, CLI attribution, API previews and bounded child context."""
import json
import time
import uuid

from click.testing import CliRunner
from fastapi import HTTPException
import pytest

from lab import agent_work
from lab.cli import main
from core import agent_work_history
from .test_subagent_terminals import parent, agent_binaries  # noqa: F401
from .test_term_creation_native import native_creation_tmux, native_creation_client  # noqa: F401


def test_cli_to_history_and_preview_preserves_exact_session_and_status(
        native_creation_tmux,native_creation_client,seed_workspace,tmp_path,monkeypatch):
    run,_,_=native_creation_tmux;client=native_creation_client;workspace=seed_workspace('demo')
    owner,identity=parent(run,client)
    address=run('display-message','-p','-t',owner['name'],'#{socket_path},#{pid},0').stdout.strip()
    monkeypatch.setenv('TMUX',address);monkeypatch.setenv('TMUX_PANE',owner['pane_id'])
    runner=CliRunner()
    def cli(*args):
        result=runner.invoke(main,['agents',*args]);assert result.exit_code==0,result.output
        return json.loads(result.output)
    assignment=cli('work','start','--title','Document request')
    image=workspace/'figure.png';image.write_bytes(b'\x89PNG\r\n\x1a\n')
    md=workspace/'report.md';md.write_text('# Current report\n![Figure](figure.png)')
    html=workspace/'page.html';html.write_text('<script>window.evil=true</script>')
    binary=workspace/'data.bin';binary.write_bytes(b'\x00\xff\xfe')
    pdf=workspace/'report.pdf';pdf.write_bytes(b'%PDF-1.4\n')
    large=workspace/'large.txt';large.write_text('x'*2_000_001)
    cli('files','record','--operation','created',*[str(path) for path in [md,image,html,binary,pdf,large]])
    cli('work','finish','--summary','Created and validated')
    status=run('show-options','-qv','-t',owner['name'],'@lab_status').stdout.strip()
    history=client.post('/api/term/work/history',json={'parent':identity}).json()
    assert history==cli('work','show')
    assert history['assignments'][0]['id']==assignment['id'] and len(history['assignments'][0]['files'])==6
    records={row['path']:row['id'] for row in history['assignments'][0]['files']}
    url=lambda path:'/api/term/work/files/'+records[str(path)]
    md.write_text('# Current preview\n![Figure](figure.png)')
    assert client.get(url(md)).json()['content'].startswith('# Current preview')
    for path,kind in [(md,'markdown'),(image,'image'),(html,'text'),(binary,'binary'),(pdf,'pdf'),(large,'binary')]:
        assert client.get(url(path)).json()['kind']==kind
    assert 'attachment' in client.get(url(html)+'/content').headers['content-disposition']
    assert 'sandbox' in client.get(url(image)+'/content').headers['content-security-policy']
    assert client.get(url(md)+'/asset',params={'file':'figure.png'}).content==image.read_bytes()
    assert client.get(url(md)+'/asset',params={'file':str(image)}).status_code==400
    assert client.get(url(md)+'/asset',params={'file':'page.html'}).status_code==404
    md.unlink()
    assert client.get(url(md)).status_code==404
    assert len(client.post('/api/term/work/history',json={'parent':identity}).json()['assignments'][0]['files'])==6
    assert client.post('/api/term/work/history',json={'parent':{**identity,'created':1}}).status_code==409
    assert run('show-options','-qv','-t',owner['name'],'@lab_status').stdout.strip()==status
    def deny(request):raise HTTPException(403,'Administrator required')
    monkeypatch.setattr(agent_work_history.auth,'require_admin',deny)
    assert client.get(url(image)).status_code==403
    assert client.get(url(image)+'/content').status_code==403
    assert client.post('/api/term/work/history',json={'parent':identity}).status_code==403


@pytest.mark.parametrize('provider',['copilot','codex','claude'])
def test_parent_context_and_reference_reach_each_provider_with_linked_file_history(
        provider,native_creation_tmux,native_creation_client,seed_workspace,agent_binaries):
    run,_,_=native_creation_tmux;client=native_creation_client;workspace=seed_workspace('demo')
    owner,identity=parent(run,client,provider)
    root=agent_work.start(agent_work_history.canonical(owner),'Parent petition',
        request='Private raw conversation that is not automatically copied',context='Decision: use CSV; permitted scope: docs/')
    reference=workspace/'reference.md';reference.write_text('# Authorized reference\nKnown result: 42')
    ident=str(uuid.uuid4());body={'parent':identity,'request_id':ident,'label':'Write report','prompt':'Write report only',
        'context':'User needs a short report. Expected result: findings and validation.',
        'context_files':[str(reference)]}
    response=client.post('/api/term/subagents',json=body)
    assert response.status_code==200,response.text
    child=response.json()['child'];receipt=agent_binaries/(provider+'.json');deadline=time.monotonic()+12
    while not receipt.exists():
        assert time.monotonic()<deadline
        time.sleep(.03)
    prompt=json.loads(receipt.read_text())['argv'][-1]
    for text in ['Parent petition',root['id'],'Decision: use CSV',str(reference),'Known result: 42','Expected result: findings',
                 'work start --id '+ident,'files record','Write report only']:
        assert text in prompt
    assert 'Private raw conversation' not in prompt
    child_identity=agent_work_history.canonical(child['terminal'])
    report=workspace/'child-output.md';report.write_text('# Findings')
    agent_work.record(child_identity,[report],'created')
    own=client.post('/api/term/work/history',json={'parent':identity}).json()['assignments']
    all_work=client.post('/api/term/work/history',json={'parent':identity,'include_children':True}).json()['assignments']
    assert len(own)==1 and own[0]['files']==[] and len(all_work)==2
    delegated=next(row for row in all_work if row['id']==ident)
    assert delegated['parent_id']==root['id'] and delegated['files'][0]['path']==str(report)
    # Request replay is idempotent and cannot silently replace its briefing.
    assert client.post('/api/term/subagents',json=body).json()['already_launched']
    assert client.post('/api/term/subagents',json={**body,'context':'Different scope'}).status_code==409


def test_invalid_context_never_launches_a_child(
        native_creation_tmux,native_creation_client,seed_workspace,agent_binaries):
    run,_,_=native_creation_tmux;client=native_creation_client;workspace=seed_workspace('demo')
    _,identity=parent(run,client);before=run('list-sessions','-F','#{session_name}').stdout
    too_big=workspace/'big.txt';too_big.write_text('x'*32001)
    binary=workspace/'binary';binary.write_bytes(b'\xff\xfe')
    for context,files in [('x\x00y',[]),('x'*64001,[]),('',[str(too_big)]),('',[str(binary)]),('',[str(workspace/'missing')])]:
        result=client.post('/api/term/subagents',json={'parent':identity,'request_id':str(uuid.uuid4()),
            'label':'Reject','prompt':'Read only','context':context,'context_files':files})
        assert result.status_code==422,result.text
    assert run('list-sessions','-F','#{session_name}').stdout==before
    assert agent_work.history(agent_work_history.canonical(identity))['assignments']==[]
