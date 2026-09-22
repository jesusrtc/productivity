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
    monkeypatch.setattr(dm, '_memory_available', lambda:(16 * 1024**3, 12 * 1024**3))
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
        elif command == 'list-panes':
            p = live.get(name)
            if not p:
                return CompletedProcess(args, 1, '', "can't find session: "+name)
            return CompletedProcess(args, 0, f"{p['created']}|{p['pid']}|{p['tty']}|{int(p['dead'])}|{p.get('attached',0)}", '')
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
    items = dm._load(e.root)
    items[result['key']]['conversation_id'] = 'thread-' + result['key']
    dm._save(e.root, items)
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


def test_sleep_frees_process_and_conversation_survives_bookmark_expiry(engine):
    e=engine; result=open_doc(e); name=result['name']
    entries=dm._load(e.root); entries[result['key']]['conversation_id']='exact-conversation'; dm._save(e.root,entries)
    e.clock.now+=299; dm.sweep(e.root); assert name in e.live
    e.clock.now+=1; dm.sweep(e.root)
    assert name not in e.live and entry(e,result)['state']=='sleeping'
    assert name not in term._load_meta(e.root) and dm._context_path(e.root,result['key']).is_file()
    assert 'exact-conversation' in dm._argv(e.root,entry(e,result))
    assert '--last' not in dm._argv(e.root,entry(e,result))
    reopened=open_doc(e); assert reopened['name']==name and name in e.live
    e.clock.now+=36*3600; dm.sweep(e.root)
    assert not e.live and entry(e,result)['conversation_id']=='exact-conversation'
    assert dm._context_path(e.root,result['key']).exists()
    assert open_doc(e)['state']=='running'
    assert 'exact-conversation' in dm._argv(e.root,entry(e,result))
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


def test_idle_cache_reclaims_unused_processes_without_a_hard_active_limit(engine):
    e=engine
    first=open_doc(e,e.library[1])
    second=open_doc(e,e.library[2])
    assert first['name'] not in e.live and len(e.live)==1
    event(e,second,'task_started')
    rows=[second]
    for source in [e.library[1],e.library[5],e.library[6]]:
        row=open_doc(e,source)
        event(e,row,'task_started')
        rows.append(row)
    assert len(e.live)==4  # real work is not limited to three documents
    e.clock.now+=100
    event(e,rows[0],'task_complete')
    event(e,rows[1],'task_complete')
    dm.sweep(e.root)
    assert len(e.live)==3  # two working + one idle cached process
    assert rows[2]['name'] in e.live and rows[3]['name'] in e.live


def test_memory_pressure_waits_then_recovers_without_losing_conversation(engine,monkeypatch):
    e=engine;first=open_doc(e)
    event(e,first,'task_started')
    monkeypatch.setattr(dm,'_memory_available',lambda:(16*1024**3, 512*1024**2))
    result=open_doc(e,e.library[1])
    assert result['state']=='waiting' and result['reason']=='memory' and len(e.live)==1
    event(e,first,'task_complete')
    dm.sweep(e.root)
    assert not e.live and entry(e,first)['conversation_id']
    monkeypatch.setattr(dm,'_memory_available',lambda:(16*1024**3,12*1024**3))
    assert open_doc(e)['state']=='running'
    assert entry(e,first)['conversation_id']=='thread-'+first['key']


def test_memory_inspection_failure_does_not_launch_unbounded_agents(engine,monkeypatch):
    def failed():raise OSError('unavailable')
    monkeypatch.setattr(dm,'_memory_available',failed)
    assert open_doc(engine)['reason']=='memory_check' and not engine.live


def test_missing_sessions_are_reconciled_without_display_message_false_success(engine,monkeypatch):
    e=engine;row=open_doc(e)
    e.live.pop(row['name'])
    tmux=dm._tmux
    def with_display_quirk(item,*args):
        if args[0]=='display-message':return CompletedProcess(args,0,'|||','')
        return tmux(item,*args)
    monkeypatch.setattr(dm,'_tmux',with_display_quirk)
    status=dm.operate(e.root,e.library[2].stem,'status')
    assert status['state']=='sleeping'
    assert open_doc(e)['state']=='running' and len(e.live)==1
    assert all(args[0]!='display-message' for _,args in e.calls)


def test_visible_idle_and_unsent_drafts_are_not_discarded(engine):
    e=engine;row=open_doc(e)
    e.live[row['name']]['attached']=1
    e.clock.now+=3600;dm.sweep(e.root)
    assert row['name'] in e.live
    e.live[row['name']]['attached']=0
    callback=dm.input_callback(row['name'])
    callback('\x1b[200~draft\nwith another line\x1b[201~')
    e.clock.now+=3600;dm.sweep(e.root)
    assert row['name'] in e.live and entry(e,row)['work_state']=='draft'
    assert entry(e,row)['unsent_input'] and not entry(e,row)['last_submit']
    dm._INPUT.clear();dm._restore_input_slots(e.root)
    dm.sweep(e.root);assert row['name'] in e.live
    dm.input_callback(row['name'])('\r')
    event(e,row,'task_complete')
    e.clock.now+=300;dm.sweep(e.root)
    assert row['name'] not in e.live


def test_missing_resume_id_keeps_completed_agent_alive(engine):
    e=engine;row=open_doc(e)
    event(e,row,'task_complete')
    entries=dm._load(e.root);entries[row['key']]['conversation_id']=None;dm._save(e.root,entries)
    e.clock.now+=3600;dm.sweep(e.root)
    assert row['name'] in e.live


def test_unused_bookmark_expires_without_touching_document(engine):
    e=engine;row=open_doc(e)
    e.clock.now+=36*3600;dm.sweep(e.root)
    assert not e.live and not dm._load(e.root)
    assert e.library[2].is_file()


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
    e.clock.now+=100; callback('\x1b[<65;1;1M')
    callback('\r')
    event(e,result,'task_complete')
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


def test_terminal_protocol_replies_do_not_create_phantom_drafts(engine):
    e=engine;row=open_doc(e);callback=dm.input_callback(row['name'])
    for reply in ['\x1b[?1;2c','\x1b[>0;276;0c','\x1b[12;30R','\x1b[I','\x1b[O','\x1b]11;rgb:0000/0000/0000\x1b\\']:
        callback(reply)
    e.clock.now+=300;dm.sweep(e.root)
    assert row['name'] not in e.live


def test_exited_pane_reopens_instead_of_attaching_a_dead_terminal(engine):
    e=engine;row=open_doc(e);event(e,row,'task_complete')
    previous=e.live[row['name']]['pid']
    e.live[row['name']]['dead']=True
    result=open_doc(e)
    assert result['state']=='running' and e.live[row['name']]['pid']!=previous
    assert entry(e,result)['conversation_id']=='thread-'+row['key']


def test_startup_reservation_prevents_burst_launches(engine,monkeypatch):
    e=engine
    monkeypatch.setattr(dm,'_memory_available',lambda:(8*1024**3,2*1024**3))
    first=open_doc(e);event(e,first,'task_started')
    second=open_doc(e,e.library[1]);event(e,second,'task_started')
    assert open_doc(e,e.library[5])['state']=='waiting'
    e.clock.now+=dm.STARTUP_GRACE_SECONDS
    assert open_doc(e,e.library[5])['state']=='running'


def test_normal_server_shutdown_checkpoints_unsent_input(engine,monkeypatch):
    from lab import paths
    e=engine;row=open_doc(e)
    monkeypatch.setattr(paths,'assistant_root',lambda:e.root)
    monkeypatch.setattr(dm,'_WORKER',None)
    dm.input_callback(row['name'])('unfinished thought')
    dm.stop_supervisor()
    assert entry(e,row)['unsent_input']
    dm._INPUT.clear();dm._restore_input_slots(e.root)
    e.clock.now+=3600;dm.sweep(e.root)
    assert row['name'] in e.live


def test_macos_memory_pressure_sample_and_measurement_failure(monkeypatch):
    monkeypatch.setattr(dm.sys,'platform','darwin')
    sample='The system has 17179869184 (1048576 pages with a page size of 16384).\nSystem-wide memory free percentage: 49%\n'
    monkeypatch.setattr(dm.subprocess,'run',lambda *a,**kw:CompletedProcess(a,0,sample,''))
    assert dm._memory_available()==(17179869184,17179869184*49//100)
    monkeypatch.setattr(dm.subprocess,'run',lambda *a,**kw:CompletedProcess(a,0,'unexpected output',''))
    assert dm._memory_ready({},0)==(False,'memory_check')
