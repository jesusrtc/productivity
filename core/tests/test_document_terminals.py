"""Lifecycle guarantees with a deterministic clock; no real agents are launched."""
from datetime import datetime, timezone
import json
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from lab import assistant_records as records, settings, tmux_sockets
from core import document_terminals as dm
from core.routes import term
from .test_assistant_documents_unified import library


@pytest.fixture()
def engine(monkeypatch, library, tmp_path):
    root = library[0]
    clock = SimpleNamespace(now=1_800_000_000.)
    monkeypatch.setattr(dm, 'time', SimpleNamespace(time=lambda:clock.now))
    monkeypatch.setattr(dm, '_INPUT', {})
    monkeypatch.setattr(term, '_active_tmux_socket', lambda:tmux_sockets.DEFAULT_SOCKET)
    monkeypatch.setattr(term, '_configure_tmux_wheel_scrolling', lambda *a:None)
    monkeypatch.setattr(term, '_invalidate_workspace_term_caches', lambda:None)
    monkeypatch.setattr(dm.shutil, 'which', lambda name:'/fake/'+name)
    live, calls = {}, []
    serial = [100]
    def tmux(entry, *args):
        calls.append((entry['name'], args))
        name, command = entry['name'], args[0]
        if command == 'new-session':
            assert name not in live
            serial[0] += 1
            live[name] = dict(created=int(clock.now), pid=serial[0], tty='/dev/ttys999',dead=False,marker=entry['key'])
        elif command == 'display-message':
            p = live.get(name)
            if not p:
                return CompletedProcess(args, 1, '', "can't find session: "+name)
            return CompletedProcess(args, 0, f"{p['created']}|{p['pid']}|{p['tty']}|{int(p['dead'])}", '')
        elif command == 'kill-session':
            live.pop(name,None)
        elif command == 'show-environment':
            return CompletedProcess(args,0,'LAB_DOCUMENT_KEY='+live[name]['marker'],'')
        return CompletedProcess(args,0,'','')
    monkeypatch.setattr(dm, '_tmux', tmux)
    def transcript(entry, probe):
        return tmp_path/(entry['key']+'.jsonl')
    monkeypatch.setattr(dm, '_transcript', transcript)
    settings.update(root, {'defaultAgent':'codex'})
    return SimpleNamespace(root=root,clock=clock,live=live,calls=calls,transcript=transcript,library=library)


def open_doc(e, source=None):
    return dm.operate(e.root, (source or e.library[2]).relative_to(e.root).as_posix())


def entry(e, result):
    return dm._load(e.root)[result['key']]


def event(e, result, kind, *, stamp=None):
    item = entry(e,result)
    path = e.transcript(item,None)
    with path.open('a') as stream:
        stream.write(json.dumps({'type':'event_msg','timestamp':datetime.fromtimestamp(stamp or e.clock.now,timezone.utc).isoformat(), 'payload':{'type':kind}})+'\n')


def test_one_terminal_per_root_and_no_content_writes(engine):
    e=engine
    originals={p:p.read_bytes() for p in e.root.rglob('*.md')}
    result=open_doc(e)
    again=open_doc(e,e.library[3])
    assert result['name']==again['name'] and len(e.live)==1
    context=json.loads(dm._context_path(e.root,result['key']).read_text())
    assert context['tab_id']==records.read_document(e.library[3])[0]['id']
    assert Path(context['path'])==e.library[2]
    assert {p:p.read_bytes() for p in originals}==originals
    assert not list((e.root/'workspaces').glob('*/workspace.json'))
    assert term._load_meta(e.root)[result['name']]['document_key']==result['key']


def test_sleep_frees_process_resume_and_36_hour_expiry(engine):
    e=engine; result=open_doc(e); name=result['name']
    entries=dm._load(e.root); entries[result['key']]['conversation_id']='exact-conversation'; dm._save(e.root,entries)
    e.clock.now+=3599; dm.sweep(e.root); assert name in e.live
    e.clock.now+=1; dm.sweep(e.root)
    assert name not in e.live and entry(e,result)['state']=='sleeping'
    assert name not in term._load_meta(e.root) and dm._context_path(e.root,result['key']).is_file()
    assert 'exact-conversation' in dm._argv(e.root,entry(e,result))
    assert '--last' not in dm._argv(e.root,entry(e,result))
    reopened=open_doc(e); assert reopened['name']==name and name in e.live
    e.clock.now+=36*3600; dm.sweep(e.root)
    assert not e.live and not dm._load(e.root) and not dm._context_path(e.root,result['key']).exists()
    assert e.library[2].is_file()


def test_busy_turn_and_permission_wait_survive_both_deadlines(engine):
    e=engine; result=open_doc(e)
    dm.input_callback(result['name'])('do a long task\r')
    event(e,result,'task_started')
    e.clock.now+=40*3600; dm.sweep(e.root)
    assert result['name'] in e.live and entry(e,result)['work_state']=='busy'
    with pytest.raises(HTTPException) as failure:
        dm.operate(e.root,e.library[2].stem,'sleep')
    assert failure.value.status_code==409
    event(e,result,'task_complete')
    dm.sweep(e.root)  # work completion starts a fresh idle window
    assert result['name'] in e.live
    e.clock.now+=3600; dm.sweep(e.root)
    assert entry(e,result)['state']=='sleeping'


def test_recent_submission_beats_stale_finished_trace_and_unknown_is_protected(engine):
    e=engine; result=open_doc(e)
    event(e,result,'task_complete')
    e.clock.now+=10; dm.input_callback(result['name'])('next task\r')
    e.clock.now+=40*3600; dm.sweep(e.root)
    assert result['name'] in e.live
    e.transcript(entry(e,result),None).write_text('{"type":"unrecognized_future_event"}\n')
    dm.sweep(e.root)
    assert result['name'] in e.live


def test_capacity_reclaims_old_idle_and_never_starts_fourth_busy_agent(engine):
    e=engine
    rows=[open_doc(e,source) for source in [e.library[1],e.library[2],e.library[5]]]
    fourth=e.library[6]
    with pytest.raises(HTTPException) as failure: open_doc(e,fourth)
    assert failure.value.status_code==409 and len(e.live)==3
    for row in rows:event(e,row,'task_started')
    e.clock.now+=100
    with pytest.raises(HTTPException):open_doc(e,fourth)
    assert len(e.live)==3
    event(e,rows[0],'task_complete')
    e.clock.now+=61
    new=open_doc(e,fourth)
    assert new['name'] in e.live and rows[0]['name'] not in e.live and len(e.live)==3


def test_capacity_recovers_manually_closed_session(engine):
    e=engine
    rows=[open_doc(e,source) for source in [e.library[1],e.library[2],e.library[5]]]
    e.live.pop(rows[0]['name'])
    assert open_doc(e,e.library[6])['state']=='running' and len(e.live)==3


def test_interrupted_spawn_is_adopted_once_and_unknown_name_is_untouched(engine):
    e=engine; result=open_doc(e)
    entries=dm._load(e.root); entries[result['key']]['state']='starting'; entries[result['key']].pop('pane_pid'); dm._save(e.root,entries)
    dm._INPUT.clear()
    reopened=open_doc(e)
    assert reopened['name']==result['name'] and len(e.live)==1 and dm.input_callback(reopened['name'])
    entries=dm._load(e.root); entries[result['key']]['state']='starting'; dm._save(e.root,entries)
    e.live[result['name']]['marker']='not-ours'
    e.clock.now+=40*3600; dm.sweep(e.root)
    assert result['name'] in e.live and entry(e,result)['work_state']=='unknown'


def test_pid_reuse_and_unmanaged_terminals_are_never_killed(engine):
    e=engine; result=open_doc(e)
    e.live[result['name']]['pid']+=1
    e.live['unrelated-user-terminal']={}
    e.clock.now+=40*3600; dm.sweep(e.root)
    assert result['name'] in e.live and 'unrelated-user-terminal' in e.live


def test_input_restored_before_startup_connections_and_status_never_keeps_alive(engine):
    e=engine; result=open_doc(e)
    dm._INPUT.clear(); dm._restore_input_slots(e.root)
    callback=dm.input_callback(result['name']); assert callback
    e.clock.now+=100; callback('x')
    assert entry(e,result)['last_used']<e.clock.now  # no disk write on a keystroke
    status=dm.operate(e.root,e.library[2].stem,'status')
    assert status['last_used']==e.clock.now
    dm.sweep(e.root)
    e.clock.now+=3600; dm.operate(e.root,e.library[2].stem,'status'); dm.sweep(e.root)
    assert result['name'] not in e.live


def test_disabled_policy_and_empty_registry_do_no_terminal_work(engine):
    e=engine
    settings.update(e.root,{'documentTerminals':{'enabled':False}})
    assert open_doc(e)['state']=='disabled'
    dm.sweep(e.root)
    assert not e.calls and not dm.registry_path(e.root).exists()


@pytest.mark.parametrize('agent,busy,finished',[
    ('codex',{'type':'event_msg','payload':{'type':'task_started'}},{'type':'event_msg','payload':{'type':'task_complete'}}),
    ('claude',{'type':'assistant','message':{'stop_reason':'tool_use'}},{'type':'assistant','message':{'stop_reason':'end_turn'}}),
    ('copilot',{'type':'permission.requested'},{'type':'assistant.turn_end'}),
])
def test_explicit_provider_turn_boundaries(agent,busy,finished):
    stamp='2026-09-21T12:00:00Z'
    busy['timestamp']=stamp; finished['timestamp']=stamp
    assert dm.trace_state(agent,[busy])[0]=='busy'
    assert dm.trace_state(agent,[busy,finished])[0]=='idle'
    assert dm.trace_state(agent,[finished,busy])[0]=='busy'
    assert dm.trace_state(agent,[finished],last_submit=dm._timestamp(stamp)+.1)[0]=='busy'
    assert dm.trace_state(agent,[busy,{**finished,'isSidechain':True}])[0]=='busy'


def test_document_policy_is_client_wide_and_validated(client,engine,monorepo):
    policy='/api/assistant/document-terminal/settings'
    assert client.get(policy).json()==settings.DEFAULTS['documentTerminals']
    result=client.post(policy,json={'sleepMinutes':20,'maxRunning':2})
    assert result.status_code==200 and result.json()['sleepMinutes']==20
    assert settings.load(engine.root)['documentTerminals']['maxRunning']==2
    assert settings.load(monorepo)['documentTerminals']['maxRunning']==2
    for value in [{'maxRunning':0},{'sleepMinutes':True},{'enabled':'yes'},{'expireHours':-1},{'other':2},{'sleepMinutes':3000}]:
        assert client.post(policy,json=value).status_code==400
    path=engine.library[2].relative_to(engine.root).as_posix()
    assert client.post('/api/assistant/document-terminal',json={'path':path,'action':'status'}).json()['state']=='absent'
    result=client.post('/api/assistant/document-terminal',json={'path':path})
    assert result.status_code==200 and result.json()['state']=='running'
    assert client.post('/api/assistant/document-terminal',json={'path':'../../etc/passwd'}).status_code in {400,404}


def test_provider_launches_use_exact_ids_and_preserve_settings(engine, monkeypatch, tmp_path):
    import re
    e=engine
    monkeypatch.setenv('HOME',str(tmp_path/'home'))
    item={'agent':'claude','conversation_id':'saved-id','cwd':str(e.root)}
    args=dm._argv(e.root,item)
    assert args[-4:]==['--session-id','saved-id','--permission-mode','auto']
    transcript=Path.home()/'.claude/projects'/re.sub(r'[^A-Za-z0-9]','-',str(e.root))/'saved-id.jsonl'
    transcript.parent.mkdir(parents=True); transcript.write_text('{}')
    assert '--resume' in dm._argv(e.root,item) and '--session-id' not in dm._argv(e.root,item)
    item['agent']='copilot'
    assert dm._argv(e.root,item)[-2:]==['--session-id','saved-id']
    item['agent']='codex'
    assert dm._argv(e.root,item)[-2:]==['resume','saved-id']
    assert '--last' not in dm._argv(e.root,item)


def test_bootstrap_can_sleep_but_truncated_or_corrupt_unknown_logs_cannot(engine):
    e=engine; result=open_doc(e); item=entry(e,result); probe=dm._probe(item)
    trace=e.transcript(item,probe)
    trace.write_text('{"type":"session_meta"}\n')
    assert dm._idle(item,probe)
    trace.write_text('not-json\n')
    assert not dm._idle(item,probe)
    trace.write_text('{"type":"session_meta"}\n'*(dm.TAIL_BYTES//10))
    assert not dm._idle(item,probe)


def test_document_terminal_endpoints_require_admin(client, engine):
    from .test_auth_routes import _create_user, _login
    assert _create_user(client,'doc-reader','test-secret').status_code==200
    client.post('/api/auth/logout')
    assert _login(client,'doc-reader','test-secret').status_code==200
    assert client.get('/api/assistant/document-terminal/settings').status_code==403
    assert client.post('/api/assistant/document-terminal',json={'path':engine.library[2].stem}).status_code==403
    assert not engine.live


def test_input_arriving_during_cleanup_prevents_retirement(engine, monkeypatch):
    e=engine; result=open_doc(e)
    callback=dm.input_callback(result['name'])
    def input_during_inspection(item, probe):
        callback('new task\r')
        return True
    monkeypatch.setattr(dm,'_idle',input_during_inspection)
    e.clock.now+=3600
    dm.sweep(e.root)
    assert result['name'] in e.live
    assert entry(e,result)['last_submit']==e.clock.now


def test_concurrent_document_opens_launch_once(engine):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(lambda _:open_doc(engine), range(12)))
    assert len({r['name'] for r in results})==1 and len(engine.live)==1
    assert sum(args[0]=='new-session' for _,args in engine.calls)==1


def test_live_thread_is_checkpointed_before_sleep_deadline(engine, monkeypatch):
    e=engine; result=open_doc(e)
    def discovered_thread(item, probe):
        item['conversation_id']='current-exact-thread'
        return None
    monkeypatch.setattr(dm,'_transcript',discovered_thread)
    e.clock.now+=60; dm.sweep(e.root)
    assert result['name'] in e.live
    assert entry(e,result)['conversation_id']=='current-exact-thread'
    e.live.pop(result['name'])
    dm.sweep(e.root)
    assert 'current-exact-thread' in dm._argv(e.root,entry(e,result))
