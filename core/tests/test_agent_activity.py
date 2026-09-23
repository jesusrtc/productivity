import json
from pathlib import Path
import sqlite3

import pytest

from core import agent_activity as activity

STAMP = '2026-09-22T12:00:00.123Z'


def event(kind, **extra):
    return {'type': kind, 'timestamp': STAMP, **extra}


def codex(kind, **extra):
    return event('event_msg', payload={'type': kind, 'turn_id': 'turn-1', **extra})


def claude(reason, **extra):
    return event('assistant', message={'stop_reason': reason}, **extra)


def copilot(kind, **extra):
    return event(kind, data={'turnId': 'turn-1', **extra})


CASES = [
    ('codex', [codex('task_started')], [codex('task_complete')]),
    ('claude', [event('user'), claude('tool_use')], [claude('end_turn')]),
    ('copilot', [copilot('assistant.turn_start')], [
        copilot('assistant.message', content='Finished', toolRequests=[]),
        copilot('assistant.turn_end'),
    ]),
]


@pytest.mark.parametrize('agent,working,finished', CASES)
def test_explicit_response_completion_and_next_request(agent, working, finished):
    assert activity.response_state(agent, working) == {'state': 'working'}
    result = activity.response_state(agent, working + finished)
    assert result['state'] == 'completed'
    assert result['completed_at'] > 0 and result['completion_id']
    assert activity.response_state(agent, working + finished + working) == {'state': 'working'}
    assert activity.response_state(agent, []) == {'state': 'unknown'}


@pytest.mark.parametrize('agent,working,finished', CASES)
def test_subagent_completions_do_not_complete_parent(agent, working, finished):
    children = [dict(e, **({'agentId': 'child'} if agent == 'copilot' else {'isSidechain': True})) for e in finished]
    assert activity.response_state(agent, working + children)['state'] == 'working'
    if agent == 'copilot':
        children = [dict(e, data={**e['data'], 'parentToolCallId': 'child'}) for e in finished]
        assert activity.response_state(agent, working + children)['state'] == 'working'


def test_copilot_tool_turn_is_not_a_completed_response():
    events = [copilot('assistant.turn_start'),
              copilot('assistant.message', content='Checking', toolRequests=[{'toolCallId': 'tool'}]),
              copilot('tool.execution_start'), copilot('tool.execution_complete'),
              copilot('assistant.turn_end')]
    assert activity.response_state('copilot', events) == {'state': 'working'}
    assert activity.response_state('copilot', [copilot('assistant.turn_end')]) == {'state': 'unknown'}
    assert activity.response_state('copilot', [
        copilot('assistant.message', content='Done'),
        event('assistant.turn_end', data={'turnId': 'other'}),
    ]) == {'state': 'working'}


@pytest.mark.parametrize('agent,events,expected', [
    ('codex', [codex('task_started'), codex('turn_aborted')], 'interrupted'),
    ('codex', [codex('task_complete', error={'message': 'failed'})], 'error'),
    ('codex', [codex('exec_approval_request')], 'waiting'),
    ('codex', [codex('task_started'), event('event_msg', payload={'type': 'task_complete', 'turn_id': 'other'})], 'working'),
    ('claude', [claude('tool_use'), event('system', subtype='turn_duration')], 'unknown'),
    ('claude', [claude('end_turn', isApiErrorMessage=True)], 'error'),
    ('claude', [claude('max_tokens')], 'working'),
    ('claude', [event('user', isMeta=True, message={'content': '<local-command-caveat>Local CLI command</local-command-caveat>'}),
                event('user', message={'content': '<command-name>/usage</command-name>'}),
                event('system', subtype='local_command')], 'unknown'),
    ('claude', [event('user', isCompactSummary=True, message={'content': 'Previous context'})], 'unknown'),
    ('claude', [claude('tool_use'), event('user', message={'content': '[Request interrupted by user]'})], 'interrupted'),
    ('claude', [claude('tool_use'), event('user', message={'content': [{'type': 'text', 'text': '[Request interrupted by user for tool use]'}]})], 'interrupted'),
    ('claude', [event('user', message={'content': '<command-name>/custom-skill</command-name>'}), claude('tool_use')], 'working'),
    ('copilot', [copilot('assistant.message', content='Done'), copilot('permission.requested'), copilot('assistant.turn_end')], 'waiting'),
    ('copilot', [copilot('assistant.message', content='Done'), copilot('abort'), copilot('assistant.turn_end')], 'interrupted'),
    ('copilot', [copilot('session.shutdown')], 'interrupted'),
    ('copilot', [copilot('assistant.turn_start'), copilot('session.shutdown')], 'interrupted'),
    ('copilot', [copilot('session.error')], 'error'),
    ('copilot', [copilot('session.resume'), copilot('session.context_changed')], 'unknown'),
    ('copilot', [copilot('assistant.turn_start'), copilot('session.resume')], 'unknown'),
    ('copilot', [copilot('assistant.turn_start'), copilot('session.context_changed')], 'working'),
])
def test_non_completion_boundaries(agent, events, expected):
    assert activity.response_state(agent, events) == {'state': expected}


def test_completion_requires_a_valid_timestamp():
    assert activity.response_state('claude', [{'type': 'assistant', 'message': {'stop_reason': 'end_turn'}}]) == {'state': 'unknown'}


@pytest.mark.parametrize('agent,events', [
    ('claude', [claude('end_turn'), event('system', subtype='turn_duration')]),
    ('claude', [claude('end_turn'), event('user', isMeta=True),
                event('user', message={'content': [{'type': 'text', 'text': '<command-name>/usage</command-name>'}]}),
                event('system', subtype='local_command')]),
    ('copilot', [copilot('assistant.message', content='Done'), copilot('assistant.turn_end'),
                 copilot('session.resume'), copilot('session.context_changed')]),
    ('copilot', [copilot('assistant.message', content='Done'), copilot('assistant.turn_end'), copilot('session.shutdown')]),
])
def test_idle_bookkeeping_preserves_a_confirmed_completion(agent, events):
    assert activity.response_state(agent, events)['state'] == 'completed'


def write_events(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(e) + '\n' for e in events))


def test_reader_handles_partial_append_rotation_and_missing_files(tmp_path, monkeypatch):
    path = tmp_path / 'events.jsonl'
    assert activity.read_activity('codex', path)['state'] == 'unknown'
    write_events(path, [codex('task_complete')])
    completed = activity.read_activity('codex', path)
    assert completed['state'] == 'completed'
    original = Path.open
    def forbid_open(*args, **kwargs):
        raise AssertionError('unchanged file should use the cache')
    with monkeypatch.context() as m:
        m.setattr(Path, 'open', forbid_open)
        assert activity.read_activity('codex', path) == completed
    with original(path, 'ab') as stream:
        stream.write(b'{"type":')
    assert activity.read_activity('codex', path) == {'state': 'unknown'}
    write_events(path, [codex('task_started')])
    assert activity.read_activity('codex', path)['state'] == 'working'
    path.unlink()
    write_events(path, [codex('task_complete')])
    assert activity.read_activity('codex', path)['state'] == 'completed'
    path.write_text('not json\n')
    assert activity.read_activity('codex', path) == {'state': 'unknown'}


def test_reader_is_bounded_and_does_not_promote_a_tool_result(tmp_path, monkeypatch):
    path = tmp_path / 'events.jsonl'
    monkeypatch.setattr(activity, 'TAIL_BYTES', 300)
    write_events(path, [codex('task_complete'), codex('task_started'),
                        event('padding', content='x' * 400), codex('exec_command_end')])
    assert activity.read_activity('codex', path) == {'state': 'unknown'}
    with path.open('a') as stream:
        stream.write(json.dumps(codex('task_complete')) + '\n')
    assert activity.read_activity('codex', path)['state'] == 'completed'


@pytest.mark.parametrize('kind', ['reasoning', 'function_call', 'custom_tool_call', 'message'])
def test_long_codex_run_stays_working_after_start_leaves_the_tail(tmp_path, monkeypatch, kind):
    path = tmp_path / 'events.jsonl'
    monkeypatch.setattr(activity, 'TAIL_BYTES', 400)
    ongoing = event('response_item', payload={'type': kind, 'role': 'assistant'})
    write_events(path, [codex('task_started'), event('padding', content='x' * 1000), ongoing])
    assert activity.read_activity('codex', path)['state'] == 'working'
    with path.open('a') as stream:
        stream.write(json.dumps(codex('task_complete')) + '\n')
    assert activity.read_activity('codex', path)['state'] == 'completed'


def test_codex_activity_does_not_promote_user_or_tool_output_to_completion():
    for kind in ['function_call_output', 'custom_tool_call_output', 'message']:
        output = event('response_item', payload={'type': kind, 'role': 'user'})
        assert activity.response_state('codex', [output]) == {'state': 'unknown'}
        assert activity.response_state('codex', [codex('task_complete'), output])['state'] == 'completed'


def test_activity_timestamp_tracks_the_state_event_not_later_bookkeeping(tmp_path):
    path = tmp_path / 'events.jsonl'
    write_events(path, [codex('task_complete'), {
        **codex('token_count'), 'timestamp': '2026-09-22T12:01:00Z'}])
    result = activity.read_activity('codex', path)
    assert result['updated_at'] == result['completed_at']


def test_enrichment_uses_exact_session_ids_for_all_providers(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('COPILOT_HOME', str(tmp_path / 'custom-copilot'))
    rows = []
    for agent, working, finished in CASES:
        identifier = agent + '-id'
        if agent == 'claude':
            path = tmp_path / '.claude/projects/-repo' / (identifier + '.jsonl')
        elif agent == 'copilot':
            path = tmp_path / 'custom-copilot/session-state' / identifier / 'events.jsonl'
        else:
            path = tmp_path / '.codex/session.jsonl'
        write_events(path, working + finished)
        rows.append({'agent': agent, 'agent_session_id': identifier, 'cwd': '/repo'})
    with sqlite3.connect(tmp_path / '.codex/state_5.sqlite') as conn:
        conn.execute('CREATE TABLE threads (id TEXT, rollout_path TEXT)')
        conn.execute('INSERT INTO threads VALUES (?, ?)', ('codex-id', str(tmp_path / '.codex/session.jsonl')))
    rows += [{'agent': 'claude', 'agent_session_id': 'missing', 'cwd': '/repo'}, {'kind': 'terminal'}]
    activity.enrich(rows)
    assert [r['agent_activity']['state'] for r in rows[:4]] == ['completed'] * 3 + ['unknown']
    assert 'agent_activity' not in rows[4]


def test_unresolved_codex_tty_never_uses_stale_saved_conversation(monkeypatch):
    from core.routes import term
    monkeypatch.setattr(term, '_codex_session_metadata_by_tty', lambda *a: {})
    rows = [{'agent': 'codex', 'agent_session_id': 'previous-thread', 'pane_tty': 'ttys-test'}]
    term._enrich_agent_session_names(rows)
    activity.enrich(rows)
    assert rows[0]['agent_activity'] == {'state': 'unknown'}
    assert not rows[0].get('agent_session_id')
