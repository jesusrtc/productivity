from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import pytest

from lab.agentic_store import Store, next_cron
from core.agentic_runner import parse_result, redact, result_text, transcript_event
from core.agentic_runtime import provider_argv, process_state
from core.agentic_copilot import is_startup_notice


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def mission(store, **task):
    return store.apply([
        {'type': 'mission-create', 'id': 'm', 'title': 'Analysis', 'objective': 'Explain the evidence'},
        {'type': 'task-create', 'id': 't', 'mission_id': 'm', 'title': 'Analyze',
         'instruction': 'Analyze the supplied data and save a notebook', **task},
    ])[-1]


def test_managed_run_uses_existing_work_and_status_commands_without_tmux(store, monkeypatch):
    from click.testing import CliRunner
    from lab.cli import main as cli
    mission(store)
    run = store.reserve(provider='codex')
    monkeypatch.setenv('LAB_AGENTIC_WORKSPACE', str(store.workspace))
    monkeypatch.setenv('LAB_AGENTIC_RUN', run['id'])
    monkeypatch.delenv('TMUX', raising=False)
    monkeypatch.delenv('TMUX_PANE', raising=False)
    runner = CliRunner()
    output = store.workspace / 'report.md'
    output.write_text('Verified evidence')
    for command in [
        ['agents', 'work', 'start', '--id', run['id'], '--title', 'Analyze data'],
        ['notifications', 'working', 'Inspecting input'],
        ['agents', 'files', 'record', '--operation', 'created', str(output)],
        ['agents', 'work', 'finish', '--summary', 'Report verified'],
        ['notifications', 'finished', 'Report ready'],
        ['agents', 'files', 'list'],
    ]:
        result = runner.invoke(cli, command)
        assert result.exit_code == 0, result.output
    assert store.detail('t')['task']['status'] == 'running'
    events = store.events(run_id=run['id'])
    files = next(e['body']['files'] for e in events if e['kind'] == 'files-reported')
    assert files[0]['path'] == str(output) and files[0]['sha256']
    assert store.run(run['id'])['report']['state'] == 'finished'
    store.finish(run['id'], result={'status': 'completed', 'summary': 'Done'})
    result = runner.invoke(cli, ['notifications', 'working', 'Too late'])
    assert result.exit_code != 0 and 'no longer active' in result.output


def test_parallel_permissions_do_not_deadlock_or_release_active_tools(store):
    mission(store)
    store.configure({'max_workers': 1})
    run = store.reserve(provider='copilot')
    request = {'toolCall': {'title': 'Write proof'}, 'options': [{'optionId': 'once', 'kind': 'allow_once'}]}
    p1 = store.permission(run['id'], request)
    p2 = store.permission(run['id'], request)
    for p in (p1, p2):
        store.apply([{'type': 'permission-respond', 'id': p['id'], 'option_id': 'once'}])
    assert store.take_permission(p1['id'])
    assert store.take_permission(p2['id'])
    p3 = store.permission(run['id'], request, executing_tools=True)
    assert store.run(run['id'])['status'] == 'running'
    store.apply([{'type': 'permission-respond', 'id': p3['id'], 'option_id': 'once'}])
    store.permission_idle(run['id'])
    assert store.run(run['id'])['status'] == 'waiting'
    assert store.take_permission(p3['id'])


def test_managed_cli_cannot_impersonate_user_or_release_approval(seed_workspace, monkeypatch, tmp_path):
    from click.testing import CliRunner
    from lab.cli import main
    folder = seed_workspace('managed')
    metadata = json.loads((folder / 'workspace.json').read_text())
    (folder / 'workspace.json').write_text(json.dumps({**metadata, 'kind': 'agentic'}))
    store = Store(folder)
    mission(store, review_required=True)
    preview = store.reserve(provider='codex')
    store.finish(preview['id'], result={'status': 'completed', 'summary': 'Preview'})
    store.apply([{'type': 'task-create', 'id': 'worker', 'mission_id': 'm', 'title': 'Worker', 'instruction': 'Gather evidence'}])
    coordinator = store.reserve(provider='codex')
    store.finish(coordinator['id'], result={'message': 'Preview ready', 'actions': []})
    run = store.reserve(provider='codex')
    monkeypatch.setenv('LAB_VAULT', str(folder.parent.parent))
    monkeypatch.setenv('LAB_AGENTIC_WORKSPACE', str(folder))
    monkeypatch.setenv('LAB_AGENTIC_RUN', run['id'])
    runner = CliRunner()
    actions = tmp_path / 'actions.json'
    def invoke(*command):
        return runner.invoke(main, ['mission', '--workspace', 'managed', *command])
    actions.write_text(json.dumps([{'type': 'task-approve', 'id': 't'}]))
    assert invoke('apply', '--file', str(actions)).exit_code != 0
    assert invoke('say', 'I approve this preview').exit_code != 0
    assert store.detail('t')['task']['status'] == 'review'
    actions.write_text('{"max_workers":1}')
    assert invoke('settings', '--file', str(actions)).exit_code != 0
    (folder / 'evidence.txt').write_text('Evidence')
    actions.write_text(json.dumps([{'type': 'asset-add', 'task_id': 'worker', 'kind': 'file', 'target': 'evidence.txt', 'title': 'Evidence', 'role': 'support', 'origin': 'agent'}]))
    result = invoke('apply', '--file', str(actions))
    assert result.exit_code == 0, result.output
    assert store.detail('worker')['assets'][0]['run_id'] == run['id']


def test_schedule_reuses_task_and_coalesces_unchanged_result(store):
    store.apply([{'type': 'mission-create', 'id': 'm', 'title': 'Watch', 'objective': 'Watch until merged'},
                 {'type': 'schedule-create', 'id': 's', 'mission_id': 'm', 'title': 'PR',
                  'instruction': 'Inspect PR', 'interval_seconds': 600}])
    store.tick(time.time() + 601)
    first = store.reserve(provider='codex')
    store.finish(first['id'], result={'status': 'completed', 'summary': 'Open', 'fingerprint': 'open-v1'})
    coordinator = store.reserve(provider='codex')
    store.finish(coordinator['id'], result={'message': 'PR is still open', 'actions': []})
    store.tick(time.time() + 1202)
    second = store.reserve(provider='claude')
    assert second['task_id'] == first['task_id'] and second['id'] != first['id']
    store.finish(second['id'], result={'status': 'completed', 'summary': 'Open', 'fingerprint': 'open-v1'})
    assert store.reserve(provider='codex') is None
    assert len(store.snapshot()['tasks']) == 1


def test_notification_review_never_approves_task_and_reminder_reappears(store):
    mission(store, review_required=True)
    run = store.reserve(provider='claude')
    store.finish(run['id'], result={'status': 'completed', 'summary': 'Preview ready'})
    notice = store.notifications()[0]
    assert notice['active'] and notice['state'] == 'attention'
    store.acknowledge(notice['report_id'])
    assert not store.notifications()[0]['active']
    assert store.detail('t')['task']['status'] == 'review'
    store.tick(store.detail('t')['task']['next_reminder'] + 1)
    reminder = store.notifications()[0]
    assert reminder['active'] and reminder['report_id'] != notice['report_id']
    store.acknowledge(notice['report_id'])
    assert store.notifications()[0]['active']


def test_supervisor_retains_unknown_and_live_runs_and_stops_only_owned_orphan(store, monkeypatch):
    from core import agentic_runtime as runtime
    mission(store)
    run = store.reserve(provider='codex')
    store.register_process(run['id'], 123, 100.0)
    store.register_child(run['id'], 124, 101.0)
    store.configure({'enabled': False})
    monkeypatch.setattr(runtime.settings, 'resolve_agent', lambda *args: 'codex')
    monkeypatch.setattr(runtime.settings, 'resolve_model', lambda *args: None)
    monkeypatch.setattr(runtime, 'process_state', lambda row: None)
    supervisor = runtime.Supervisor()
    supervisor.tick_workspace(store.workspace, store.workspace, 'test')
    assert store.run(run['id'])['status'] == 'running'
    monkeypatch.setattr(runtime, 'process_state', lambda row: True)
    supervisor.tick_workspace(store.workspace, store.workspace, 'test')
    assert store.run(run['id'])['status'] == 'running'
    calls = []
    monkeypatch.setattr(runtime, 'process_state', lambda row: row.get('pid') == 124)
    monkeypatch.setattr(runtime.os, 'getpgid', lambda pid: pid)
    monkeypatch.setattr(runtime.os, 'killpg', lambda pid, sig: calls.append((pid, sig)))
    supervisor.tick_workspace(store.workspace, store.workspace, 'test')
    assert calls == [(124, runtime.signal.SIGTERM)]
    assert store.run(run['id'])['status'] == 'running'
    monkeypatch.setattr(runtime, 'process_state', lambda row: False)
    supervisor.tick_workspace(store.workspace, store.workspace, 'test')
    assert store.run(run['id'])['status'] == 'failed'
    assert store.detail('t')['task']['status'] == 'failed'


def test_stalled_vault_does_not_block_other_missions_or_repeat_scans(seed_workspace, monkeypatch, tmp_path):
    import threading
    from core import fsguard, agentic_runtime
    from lab import naming
    folder = seed_workspace('healthy')
    file = folder / 'workspace.json'
    file.write_text(json.dumps({**json.loads(file.read_text()), 'kind': 'agentic'}))
    stalled = tmp_path / 'stalled'
    release = threading.Event()
    scans = []
    original_dir, original_guard = naming.workspaces_dir, fsguard.guarded
    def directory(root):
        if root == stalled:
            scans.append(root)
            release.wait(2)
        return original_dir(root)
    monkeypatch.setattr(naming, 'workspaces_dir', directory)
    monkeypatch.setattr(fsguard, 'guarded', lambda root, fn, *args, **kw:
                        original_guard(root, fn, *args, **{**kw, 'timeout': .03}))
    monkeypatch.setattr(agentic_runtime.paths, 'read_vault_registry', lambda:
                        {'vaults': [{'id': 'healthy', 'path': str(folder.parent.parent)}]})
    supervisor = agentic_runtime.Supervisor()
    try:
        for _ in range(2):
            rows = list(supervisor.workspaces(stalled))
            assert [row[2] for row in rows] == ['healthy']
            assert str(stalled) in supervisor.errors
        assert len(scans) == 1
    finally:
        release.set()


def test_reused_process_identity_is_not_live(monkeypatch):
    from core import agentic_runtime as runtime
    class Process:
        def __init__(self, pid): pass
        def create_time(self): return 200.0
        def is_running(self): raise AssertionError('Never treat a reused PID as ours')
    monkeypatch.setattr(runtime.psutil, 'Process', Process)
    assert process_state({'pid': 123, 'process_started': 100.0}) is False


def test_transaction_rolls_back_entire_invalid_plan(store):
    with pytest.raises(ValueError):
        store.apply([{'type': 'mission-create', 'id': 'm', 'title': 'M', 'objective': 'O'},
                     {'type': 'task-create', 'mission_id': 'm', 'title': 'T', 'instruction': 'I', 'depends_on': ['missing']}])
    assert store.snapshot()['missions'] == []


def test_copilot_startup_banner_is_not_concatenated_with_model_json():
    notice = {'content': {'text': 'Info: Disabled tools: task'}}
    assert is_startup_notice(notice, [])
    assert not is_startup_notice(notice, ['{"message":"'])
    assert not is_startup_notice({'content': {'text': '{"message":"Hello"}'}}, [])


def test_audit_keeps_tools_and_results_without_private_reasoning():
    assert transcript_event({'type': 'acp', 'data': {'params': {'update': {'sessionUpdate': 'agent_thought_chunk', 'content': 'private'}}}}) is None
    assert transcript_event({'type': 'item.completed', 'item': {'type': 'reasoning', 'text': 'private'}}) is None
    event = {'type': 'assistant', 'message': {'content': [{'type': 'thinking', 'thinking': 'private'},
                                                       {'type': 'tool_use', 'name': 'shell', 'input': {'command': 'lab notebook exec'}}]}}
    assert transcript_event(event)['message']['content'] == [event['message']['content'][1]]


def test_concurrent_admission_limits_five_executors_plus_coordinator(store):
    mission(store)
    store.apply([{'type': 'task-create', 'id': f't{i}', 'mission_id': 'm', 'title': str(i), 'instruction': 'Work'} for i in range(20)])
    store.message('Start the work')
    with ThreadPoolExecutor(max_workers=12) as pool:
        runs = list(pool.map(lambda _: store.reserve(provider='codex'), range(30)))
    admitted = [r for r in runs if r]
    assert len(admitted) == 6
    assert sum(r['role'] == 'coordinator' for r in admitted) == 1
    assert len({r['task_id'] for r in admitted if r['task_id']}) == 5
    assert Store(store.workspace).reserve(provider='claude') is None


def test_review_gate_blocks_dependencies_until_user_approval(store):
    mission(store, review_required=True)
    store.apply([{'type': 'task-create', 'id': 'translate', 'mission_id': 'm', 'title': 'Translate',
                  'instruction': 'Translate only after approval', 'depends_on': ['t']}])
    run = store.reserve(provider='claude')
    store.finish(run['id'], result={'status': 'completed', 'summary': 'Sample ready'})
    assert store.detail('t')['task']['status'] == 'review'
    assert store.reserve(provider='codex')['role'] == 'coordinator'
    assert store.reserve(provider='codex') is None
    with pytest.raises(ValueError, match='Only the user'):
        store.apply([{'type': 'task-approve', 'id': 't'}], actor='coordinator')
    store.apply([{'type': 'task-approve', 'id': 't'}])
    assert store.reserve(provider='codex')['task_id'] == 'translate'


def test_blocked_tasks_release_capacity_and_reminders_coalesce(store):
    mission(store)
    run = store.reserve(provider='copilot')
    store.finish(run['id'], result={'status': 'blocked', 'summary': 'Need channel access', 'blocker': 'Authorize the selected channel'})
    state = store.snapshot()
    due = state['tasks'][0]['next_reminder']
    store.tick(due + 86400)
    assert len([m for m in store.snapshot()['messages'] if m['role'] == 'notice']) == 1
    store.tick(due + 86401)
    assert len([m for m in store.snapshot()['messages'] if m['role'] == 'notice']) == 1
    store.apply([{'type': 'task-snooze', 'id': 't', 'seconds': 14400}])
    assert store.detail('t')['task']['next_reminder'] > time.time() + 14390


def test_exact_assignments_are_immutable_and_runs_keep_evidence(store):
    mission(store)
    (store.workspace / 'evidence.csv').write_text('x\n1\n')
    run = store.reserve(provider='codex')
    store.prepare_run(run['id'], 'Exact instruction', {'source': 'original'}, ['codex', 'exec'])
    with pytest.raises(ValueError, match='only be recorded once'):
        store.prepare_run(run['id'], 'Rewritten', {}, [])
    store.apply([{'type': 'task-update', 'id': 't', 'instruction': 'New instruction'}])
    store.finish(run['id'], result={'status': 'completed', 'summary': 'x = 1',
                                   'assets': [{'target': 'evidence.csv', 'role': 'input', 'origin': 'user'}]})
    detail = Store(store.workspace).detail('t')
    assert detail['runs'][0]['prompt'] == 'Exact instruction'
    assert detail['task']['instruction'] == 'New instruction'
    assert detail['assets'][0]['run_id'] == run['id']
    assert len(detail['assets'][0]['sha256']) == 64


def test_failed_result_does_not_partially_finish_or_register_escaping_asset(store, tmp_path):
    mission(store)
    run = store.reserve(provider='codex')
    outside = tmp_path.parent / 'outside-agentic.txt'
    outside.write_text('unrelated')
    with pytest.raises(ValueError, match='inside this workspace'):
        store.finish(run['id'], result={'status': 'completed', 'summary': 'Done', 'assets': [{'target': str(outside)}]})
    assert store.detail('t')['task']['status'] == 'running'
    assert store.snapshot()['assets'] == []


def test_message_ids_deduplicate_without_losing_followups(store):
    first = store.message('Investigate', request_id='req')
    assert store.message('Investigate', request_id='req') == first
    with pytest.raises(ValueError, match='different content'):
        store.message('Different', request_id='req')
    store.message('Automatic event', role='event')
    store.message('Urgent follow-up', request_id='second')
    run = store.reserve(provider='codex')
    assert run['message_id'] == 'req'
    store.finish(run['id'], result={'message': 'Understood', 'actions': []})
    assert store.reserve(provider='codex')['message_id'] == 'second'


def test_pause_requests_stop_owned_run_before_releasing_capacity(store):
    mission(store)
    run = store.reserve(provider='codex')
    store.checkpoint(run['id'], 'Input loaded; next compute the result')
    store.apply([{'type': 'task-pause', 'id': 't'}])
    assert store.run(run['id'])['stop_requested'] == 'pause'
    assert store.detail('t')['task']['status'] == 'running'
    with pytest.raises(ValueError):
        store.apply([{'type': 'task-resume', 'id': 't'}])
    store.finish(run['id'], stopped='pause')
    assert store.detail('t')['task']['status'] == 'paused'
    store.apply([{'type': 'task-resume', 'id': 't'}])
    next_run = store.reserve(provider='claude')
    assert next_run['id'] != run['id']
    assert store.detail('t')['task']['checkpoint'].startswith('Input loaded')


def test_schedules_never_overlap_and_stop_on_condition(store):
    mission(store, status='paused')
    schedule = store.apply([{'type': 'schedule-create', 'id': 's', 'mission_id': 'm', 'title': 'PR check',
                             'instruction': 'Check PR', 'interval_seconds': 600}])[0]
    now = schedule['next_due'] + 86400
    store.tick(now)
    store.tick(now + 10000)
    assert len([t for t in store.snapshot()['tasks'] if t.get('schedule_id')]) == 1
    run = store.reserve(provider='codex')
    store.finish(run['id'], result={'status': 'completed', 'summary': 'Merged', 'fingerprint': 'merge-1', 'schedule_done': True})
    store.tick(now + 100000)
    assert store.snapshot()['schedules'][0]['enabled'] is False
    assert len(store.snapshot()['tasks']) == 2


def test_cron_timezone_and_standard_day_or_semantics():
    after = datetime(2026, 10, 22, 15, 59, tzinfo=timezone.utc).timestamp()
    assert next_cron('0 9 * * 1-5', after, 'America/Los_Angeles') == after + 60
    # Restricted day-of-month and weekday use OR, as standard cron does.
    assert next_cron('0 9 23 * 4', after, 'America/Los_Angeles') == after + 60
    with pytest.raises(ValueError):
        next_cron('99 * * * *', after)


def test_group_completion_and_mission_completion_gate(store):
    mission(store, group=True)
    store.apply([{'type': 'task-create', 'id': 'child', 'parent_id': 't', 'mission_id': 'm', 'title': 'Child', 'instruction': 'Work'}])
    with pytest.raises(ValueError, match='unfinished'):
        store.apply([{'type': 'mission-update', 'id': 'm', 'status': 'completed'}])
    run = store.reserve(provider='codex')
    assert run['task_id'] == 'child'
    store.finish(run['id'], result={'status': 'completed', 'summary': 'Verified result'})
    assert store.detail('t')['task']['status'] == 'completed'
    store.apply([{'type': 'mission-update', 'id': 'm', 'status': 'completed', 'result': 'All verified'}])
    assert store.snapshot()['missions'][0]['status'] == 'completed'


def test_provider_contracts_and_no_blanket_bypass():
    for provider in ('codex', 'claude', 'copilot'):
        argv = provider_argv(provider, None, role='executor', prompt_file=Path('/tmp/prompt'))
        assert argv[0] == provider
        assert not {'--dangerously-skip-permissions', '--dangerously-bypass-approvals-and-sandbox', '--allow-all'} & set(argv)
    assert result_text('codex', {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '{"ok":true}'}}) == '{"ok":true}'
    assert result_text('copilot', {'type': 'assistant.message', 'data': {'content': 'hello'}}) == 'hello'
    assert parse_result('```json\n{"status":"completed"}\n```')['status'] == 'completed'
    with pytest.raises(ValueError):
        result_text('claude', {'type': 'result', 'is_error': True, 'result': 'Not logged in'})
    assert redact({'access_token': 'secret', 'text': 'Bearer abc123'}) == {'access_token': '[redacted]', 'text': 'Bearer [redacted]'}


def test_api_is_admin_only_and_uses_workspace_kind(client, seed_workspace):
    folder = seed_workspace('agentic')
    file = folder / 'workspace.json'
    data = json.loads(file.read_text())
    data['kind'] = 'agentic'
    file.write_text(json.dumps(data))
    assert client.get('/api/agentic/agentic').status_code == 200
    response = client.post('/api/agentic/agentic/messages', json={'content': 'Analyze', 'request_id': 'r'})
    assert response.status_code == 200
    assert client.post('/api/agentic/agentic/messages', json={'content': 'Analyze', 'request_id': 'r'}).json()['id'] == 'r'
    store = Store(folder)
    mission(store)
    store.message('Preview needs input', role='notice', task_id='t')
    alerts = client.get('/api/agentic-notifications').json()['notifications']
    alert = next(row for row in alerts if row['workspace_id'] == 'agentic')
    assert alert['task_id'] == 't' and alert['active']
    reviewed = client.post('/api/agentic/agentic/notifications/' + alert['report_id'] + '/review')
    assert reviewed.status_code == 200
    assert store.detail('t')['task']['status'] == 'queued'
    assert client.get('/api/agentic/agentic/tasks/__coordinator__').json()['coordinator']
    client.post('/api/auth/logout')
    assert client.get('/api/agentic/agentic').status_code in (401, 403)
    assert client.get('/api/agentic-notifications').status_code in (401, 403)


def test_active_mission_run_protects_workspace_location_and_kind(client, seed_workspace, monkeypatch):
    from click.testing import CliRunner
    from lab.cli import main
    folder = seed_workspace('agentic')
    store = Store(folder)
    mission(store)
    run = store.reserve(provider='claude')
    assert client.post('/api/workspaces/agentic/rename', json={'name': 'New name'}).status_code == 409
    monkeypatch.setenv('LAB_VAULT', str(folder.parent.parent))
    for command in (['workspace', 'set', 'agentic', 'kind', 'standard'], ['workspace', 'rm', 'agentic', '--yes']):
        result = CliRunner().invoke(main, command)
        assert result.exit_code != 0 and 'stop its active runs' in result.output
    assert folder.is_dir()
    store.finish(run['id'], stopped='cancel')
    assert client.post('/api/workspaces/agentic/rename', json={'name': 'New name'}).status_code == 200


def test_chat_approval_requires_current_user_and_exact_preview(store):
    mission(store, review_required=True)
    run = store.reserve(provider='claude')
    store.finish(run['id'], result={'status': 'completed', 'summary': 'Sample ready'})
    source = store.message('Apruebo esta muestra')
    action = {'type': 'task-approve', 'id': 't', 'review_run_id': run['id'], 'approval_quote': source['content']}
    with pytest.raises(ValueError, match='Only the user'):
        store.apply([action], actor='coordinator', source={**source, 'role': 'event'})
    with pytest.raises(ValueError, match='current preview'):
        store.apply([{**action, 'review_run_id': 'old'}], actor='coordinator', source=source)
    store.apply([action], actor='coordinator', source=source)
    assert store.detail('t')['task']['status'] == 'completed'


def test_cancel_during_result_race_never_completes_task(store):
    mission(store)
    run = store.reserve(provider='codex')
    store.apply([{'type': 'task-cancel', 'id': 't'}])
    store.finish(run['id'], result={'status': 'completed', 'summary': 'Late success'})
    assert store.detail('t')['task']['status'] == 'cancelled'


def test_permission_wait_releases_and_atomically_reacquires_capacity(store):
    mission(store)
    store.configure({'max_workers': 1})
    run = store.reserve(provider='copilot')
    request = {'toolCall': {'title': 'Create report', 'kind': 'edit'},
               'options': [{'optionId': 'once', 'kind': 'allow_once', 'name': 'Allow once'}]}
    permission = store.permission(run['id'], request)
    store.apply([{'type': 'task-create', 'id': 'other', 'mission_id': 'm', 'title': 'Other', 'instruction': 'Work'}])
    other = store.reserve(provider='codex')
    assert other['task_id'] == 'other'
    decision = {'type': 'permission-respond', 'id': permission['id'], 'option_id': 'once'}
    with pytest.raises(ValueError, match='require the user'):
        store.apply([decision], actor='coordinator')
    store.apply([decision])
    assert store.take_permission(permission['id']) is None
    store.finish(other['id'], result={'status': 'completed', 'summary': 'Done'})
    assert store.take_permission(permission['id'])['option_id'] == 'once'
    assert store.take_permission(permission['id']) is None
    assert store.detail('t')['task']['status'] == 'running'


def test_mission_pause_stops_waiting_permissions_and_cancels_late_decisions(store):
    mission(store)
    run = store.reserve(provider='copilot')
    permission = store.permission(run['id'], {'toolCall': {'title': 'Execute'}, 'options': [{'optionId': 'yes', 'kind': 'allow_once'}]})
    store.apply([{'type': 'mission-update', 'id': 'm', 'status': 'paused'}])
    with pytest.raises(ValueError, match='no longer waiting'):
        store.apply([{'type': 'permission-respond', 'id': permission['id'], 'option_id': 'yes'}])
    store.finish(run['id'], stopped='pause')
    assert store.snapshot()['permissions'][0]['status'] == 'cancelled'


def test_approval_rolls_up_group_and_paused_parent_holds_children(store):
    mission(store, group=True, status='paused')
    store.apply([{'type': 'task-create', 'id': 'child', 'parent_id': 't', 'mission_id': 'm', 'title': 'Child',
                  'instruction': 'Work', 'review_required': True}])
    assert store.reserve(provider='codex') is None
    store.apply([{'type': 'task-resume', 'id': 't'}])
    run = store.reserve(provider='codex')
    store.finish(run['id'], result={'status': 'completed', 'summary': 'Preview'})
    store.apply([{'type': 'task-approve', 'id': 'child'}])
    assert store.detail('t')['task']['status'] == 'completed'


def test_storage_symlink_rejected_before_writing_outside_workspace(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    (workspace / '.lab').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='inside the workspace'):
        Store(workspace)
    assert not list(outside.iterdir())


def test_recent_event_window_and_older_pagination(store):
    mission(store)
    for i in range(550):
        store.append_event('work', {'i': i}, task_id='t')
    recent = store.detail('t')['events']
    assert len(recent) == 500
    assert recent[-1]['body']['i'] == 549
    older = store.events(task_id='t', before=recent[0]['seq'], latest=True)
    assert older[0]['kind'] == 'task-create'
    assert older[-1]['seq'] < recent[0]['seq']


def test_invalid_coordinator_plan_replans_only_three_times(store):
    source = store.message('Do work')
    for attempt in range(3):
        run = store.reserve(provider='claude')
        assert run['message_id'] == source['id']
        store.coordinator_error(run['id'], 'A task changed')
    assert store.reserve(provider='claude') is None
    assert store.snapshot()['messages'][0]['status'] == 'failed'
    assert store.notifications()[0]['active']
    store.message('Please summarize the recorded state')
    run = store.reserve(provider='claude')
    store.finish(run['id'], result={'message': 'Coordinator recovered', 'actions': []})
    assert not store.notifications()[0]['active']
