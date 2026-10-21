"""Bounded reconnects persist across restarts without touching live/manual work."""
import copy
import os
import signal
import time
import uuid

from core import automation_recovery as recovery, automation_reminders as reminders
from core import terminal_automation_lifecycle as lifecycle, terminal_automations
from core.routes import term
from lab import terminal_status
from .test_term_creation_native import native_creation_tmux, native_creation_client  # noqa: F401
from .test_terminal_automations import _save, _launch
from .test_terminal_automation_lifecycle import _status


def test_retry_cadence_confirmation_unknown_observations_and_new_generations():
    live = {'tmux_socket':'owned','tmux_id':'$1','created':1,'pane_id':'%1'}
    run = {'launch_id':'original'}
    state, attempt = recovery.transition(run, live, 'stopped', 100)
    assert attempt and state['attempts'] == 0
    for number, now in enumerate((100, 220, 340), 1):
        state = {**state, 'phase':'verifying', 'attempts':number, 'verify_at':now+30, 'next_at':now+120}
        run['recovery'] = copy.deepcopy(state)
        assert recovery.transition(run, live, 'stopped', now+29) == (state, False)
        assert recovery.transition(run, live, 'unknown', now+60) == (state, False)
        waiting, attempt = recovery.transition(run, live, 'stopped', now+30)
        assert not attempt and waiting['phase'] == ('failed' if number == 3 else 'waiting')
        run['recovery'] = waiting
        assert not recovery.transition(run, live, 'stopped', now+119)[1]
        state, attempt = recovery.transition(run, live, 'stopped', now+120)
        assert attempt == (number < 3)
    assert state['attempts'] == 3 and not recovery.transition(run, live, 'stopped', 10000)[1]
    assert recovery.transition(run, live, 'running', 10000) == (None, False)
    run['launch_id'] = 'manual-renewal'
    assert recovery.transition(run, live, 'stopped', 10000)[0]['attempts'] == 0
    monitor = recovery.Supervisor(now=0)
    assert monitor.tick(None, now=119)['attempted'] == 0
    assert monitor.tick(None, now=1000)['grace_until'] == 1120, 'resume grace prevents catch-up bursts'
    assert not recovery.decode('invalid')


def test_native_three_failed_reconnects_notify_only_main_then_manual_recovery_clears_alert(
        native_creation_tmux, native_creation_client, seed_workspace, monorepo, monkeypatch):
    run, _, _ = native_creation_tmux
    monkeypatch.setenv('SHELL','/bin/sh')
    run('set-option','-g','default-shell','/bin/sh')
    client = native_creation_client
    folder = seed_workspace('demo')
    ssh = folder / 'ssh'
    ssh.write_text('#!/bin/sh\nprintf x >> attempts\nif [ -f connected ]; then exec sleep 60; fi\nexit 1\n')
    ssh.chmod(0o700)
    parent = client.post('/api/term/sessions', json={'workspace_id':'demo','kind':'terminal'}).json()
    catalog = _save(client,'demo',[
        {'label':'Remote connection','command':str(ssh)+' fixture'},
        {'label':'Finite command','command':'printf x >> finite-count'},
        {'label':'Live process','command':'sleep 60'},
    ],launch_delay_seconds=0)
    rows = client.post('/api/term/automations/launch', json=_launch(client,parent,catalog)).json()['sessions']
    logical = rows[0]['logical_name']
    _status(client,logical,'stopped')
    _status(client,rows[1]['logical_name'],'stopped')
    alive = _status(client,rows[2]['logical_name'],'running')
    pid = run('display-message','-p','-t',alive['name'],'#{pane_pid}').stdout
    now = time.time()
    monitor = recovery.Supervisor(now=now-120)
    roots = [{'id':'fixture','path':monorepo}]

    def scan(offset):
        listing = term._tmux_list('lab-owned-',progress=True)
        groups,_,warnings = reminders.groups(roots,listing)
        assert not warnings
        result = {'attempted':0,'failed':0}
        snapshot = lifecycle.processes(listing)
        for group in groups:
            monitor._group(group,snapshot,recovery._owner_context(monorepo,'demo'),now+offset,result)
        return result

    def main():
        return next(row for row in client.get('/api/term/sessions',params={'workspace_id':'demo'}).json()
                    if row['name'] == parent['name'])

    assert scan(0)['attempted'] == 1
    _status(client,logical,'stopped')
    assert (folder/'attempts').read_text() == 'xx'
    assert not scan(20)['attempted'] and main()['terminal_recovery_alert'] is None
    assert not scan(31)['attempted'] and main()['terminal_recovery_alert'] is None
    assert not scan(119)['attempted']
    assert scan(121)['attempted'] == 1
    _status(client,logical,'stopped')
    # The retry budget and absolute next-at survive replacing the supervisor.
    monitor = recovery.Supervisor(now=now+140)
    assert not scan(160)['attempted'] and main()['terminal_recovery_alert'] is None
    assert scan(242)['attempted'] == 1
    _status(client,logical,'stopped')
    assert not scan(260)['attempted'] and main()['terminal_recovery_alert'] is None
    assert scan(273)['failed'] == 1
    alert = main()['terminal_recovery_alert']
    assert alert['active'] and alert['kind'] == 'reconnect' and '3 attempts' in alert['message']
    assert len(alert['targets']) == 1 and alert['targets'][0]['logical_name'] == logical
    assert main()['terminal_status'] is None
    assert (folder/'attempts').read_text() == 'xxxx' and (folder/'finite-count').read_text() == 'x'
    assert run('display-message','-p','-t',alive['name'],'#{pane_pid}').stdout == pid
    assert not scan(500)['attempted'] and not scan(501)['failed']
    batch = client.get('/api/workspace-documents/attention').json()
    notices = [row for rows in batch.values() for row in rows if row.get('terminal_recovery_alert',{} )]
    assert len(notices) == 1 and notices[0]['name'] == parent['name']
    assert any(path.read_text() for path in (folder/'.lab/terminal-automation-logs').glob('*.txt'))
    # Explicit reconnect starts a fresh cycle and reuses the same terminal.
    (folder/'connected').touch()
    response = client.post('/api/term/automations/relaunch',json={'workspace_id':'demo',
        'request_id':str(uuid.uuid4()),'targets':alert['targets']})
    assert response.status_code == 200 and len(response.json()['sessions']) == 1, response.text
    _status(client,logical,'running')
    scan(510)
    assert not main()['terminal_recovery_alert']['active']
    assert not lifecycle.read(folder)[logical].get('recovery')
    assert (folder/'attempts').read_text() == 'xxxxx'
    assert main()['terminal_status'] is None
    assert client.get('/api/term/automations/recovery').json()['retry_seconds'] == 120


def test_native_reconnect_respects_latest_recipe_delay_and_duplicate_requests(
        native_creation_tmux, native_creation_client, seed_workspace, monkeypatch):
    run,_,_ = native_creation_tmux
    monkeypatch.setenv('SHELL','/bin/sh')
    run('set-option','-g','default-shell','/bin/sh')
    client = native_creation_client
    folder = seed_workspace('demo')
    parent = client.post('/api/term/sessions',json={'workspace_id':'demo','kind':'terminal'}).json()
    catalog = _save(client,'demo',[{'label':'One','command':'exit 1'}, {'label':'Two','command':'exit 1'}],launch_delay_seconds=0)
    rows = client.post('/api/term/automations/launch',json=_launch(client,parent,catalog)).json()['sessions']
    targets = []
    for row in rows:
        status = _status(client,row['logical_name'],'stopped')
        targets.append({'logical_name':row['logical_name'],'launch_id':status['automation']['launch_id']})
    _save(client,'demo',[{'label':'One','command':'exit 1'},{'label':'Two','command':'exit 1'}],launch_delay_seconds=.05)
    assert lifecycle.launch_delay(folder, {'command':'exit 1','label':'One'}) == .05
    with lifecycle.recovery_queue(folder) as acquired:
        assert acquired
        with lifecycle.recovery_queue(folder, blocking=False) as duplicate:
            assert not duplicate, 'a second file-lock holder cannot start another recovery queue'
    waits = []
    def wait(seconds):
        assert not terminal_automations.lock._is_owned(), 'catalog lock is released during configured wait'
        waits.append(seconds)
        time.sleep(seconds)
    monkeypatch.setattr(terminal_automations,'sleep',wait)
    body = {'workspace_id':'demo','request_id':str(uuid.uuid4()),'targets':targets}
    response = client.post('/api/term/automations/relaunch',json=body)
    assert response.status_code == 200 and len(response.json()['sessions']) == 2, response.text
    assert len(waits) == 1 and 0 < waits[0] <= .05
    assert not client.post('/api/term/automations/relaunch',json=body).json()['sessions']
    assert len(waits) == 1, 'repeated requests do not sleep or replay commands'


def test_native_successful_auto_reconnects_are_spaced_and_paused_manual_closed_or_recreated_panes_are_preserved(
        native_creation_tmux, native_creation_client, seed_workspace, monorepo, monkeypatch):
    run,_,_ = native_creation_tmux
    monkeypatch.setenv('SHELL','/bin/sh')
    run('set-option','-g','default-shell','/bin/sh')
    client = native_creation_client
    folder = seed_workspace('demo')
    ssh = folder/'ssh'
    ssh.write_text('#!/bin/sh\nprintf x >> attempts\nif [ -f connected ]; then exec sleep 60; fi\nexit 1\n')
    ssh.chmod(0o700)
    parent = client.post('/api/term/sessions',json={'workspace_id':'demo','kind':'terminal'}).json()
    catalog = _save(client,'demo',[{'label':'One','command':str(ssh)+' one'}, {'label':'Two','command':str(ssh)+' two'}],launch_delay_seconds=.05)
    launch = _launch(client,parent,catalog)
    rows = client.post('/api/term/automations/launch',json=launch).json()['sessions']
    for row in rows:
        _status(client,row['logical_name'],'stopped')
    monitor = recovery.Supervisor()
    roots = [{'id':'fixture','path':monorepo}]
    now = time.time()
    waits = []
    def wait(seconds):
        assert not terminal_automations.lock._is_owned()
        waits.append(seconds)
        time.sleep(seconds)
        return False
    monkeypatch.setattr(monitor.stop,'wait',wait)

    def scan(offset, unknown=False):
        listing = term._tmux_list('lab-owned-',progress=True)
        groups,_,_ = reminders.groups(roots,listing)
        result = {'attempted':0,'failed':0}
        for group in groups:
            monitor._group(group,None if unknown else lifecycle.processes(listing),
                           recovery._owner_context(monorepo,'demo'),now+offset,result)
        return result

    assert not scan(0,unknown=True)['attempted'], 'unknown process reads do not replay commands'
    (folder/'connected').touch()
    assert scan(1)['attempted'] == 2
    assert len(waits) == 1 and 0 < waits[0] <= .05
    for row in rows:
        _status(client,row['logical_name'],'running')
    scan(32)
    assert all(not row.get('recovery') for row in lifecycle.read(folder).values())
    assert (folder/'attempts').read_text() == 'xxxx'
    assert all(not row.get('terminal_recovery_alert') for row in client.get('/api/term/sessions',params={'workspace_id':'demo'}).json())
    client.post('/api/objectives',json={'workspace_id':'demo','action':{'type':'task-update',
        'objective_id':launch['objective_id'],'task_id':launch['task_id'],'status':'paused'}})
    for row in rows:
        live = next(item for item in term._tmux_list('lab-owned-') if item['name'] == row['name'])
        processes = lifecycle.processes([live])
        for pid, process in processes.items():
            if process['comm'].rsplit('/',1)[-1] == 'sleep':
                os.kill(pid, signal.SIGTERM)
        stopped = _status(client,row['logical_name'],'stopped')
        assert not stopped['automation_missing'], 'only the owned connection process exits'

    assert not scan(40)['attempted'], 'paused task cannot restart its automation'
    client.post('/api/objectives',json={'workspace_id':'demo','action':{'type':'task-update',
        'objective_id':launch['objective_id'],'task_id':launch['task_id'],'status':'in_progress'}})
    run('send-keys','-t',rows[0]['name'],'sleep 60','Enter')
    _status(client,rows[0]['logical_name'],'running')
    run('split-window','-d','-t',rows[1]['name'],'sleep 60')
    assert not scan(50)['attempted'], 'manual foreground work and multi-pane sessions remain intact'
    run('kill-session','-t',rows[1]['name'])
    run('new-session','-d','-s',rows[1]['name'],'/bin/sh')
    assert not scan(60)['attempted'], 'a recreated session cannot inherit a saved reconnect loop'
    client.delete('/api/term/sessions/'+rows[0]['name'])
    assert not scan(70)['attempted'], 'closed terminal is not automatically recreated'
    assert (folder/'attempts').read_text() == 'xxxx'
