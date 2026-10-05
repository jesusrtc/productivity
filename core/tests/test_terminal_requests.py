"""Full accepted prompts survive provider clears, reloads and projection lag."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from core import terminal_requests as history


@pytest.fixture()
def provider_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('LAB_HOME', str(tmp_path/'lab'))
    monkeypatch.delenv('COPILOT_HOME', raising=False)
    monkeypatch.delenv('CODEX_HOME', raising=False)
    history._CACHE.clear()
    history._TRANSCRIPTS.clear()
    return tmp_path


def write_events(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(event)+'\n' for event in events))


@pytest.mark.parametrize('provider', ['claude', 'copilot', 'codex'])
def test_full_requests_retained_across_clear_and_repeated_polls(provider_home, provider):
    full = 'First line\n\n' + 'long message ' * 150 + '\nFinal line: <script>literal text</script>'
    row = {'name':'terminal-one', 'agent':provider, 'agent_session_id':'thread-one', 'cwd':'/repo'}
    if provider == 'claude':
        path = provider_home/'.claude/projects/-repo/thread-one.jsonl'
        events = [{'type':'user', 'uuid':str(i), 'message':{'content':text}, 'timestamp':'2026-10-05T10:00:00Z'}
                  for i, text in enumerate([full, '/clear', 'after clear', 'after clear'])]
        events += [{'type':'user', 'isSidechain':True, 'message':{'content':'agent sidechain'}},
                   {'type':'user', 'toolUseResult':{}, 'sourceToolAssistantUUID':'tool', 'message':{'content':'tool output'}},
                   {'type':'user', 'message':{'content':'# AGENTS.md instructions for /repo\nnot a request'}}]
    elif provider == 'copilot':
        path = provider_home/'.copilot/session-state/thread-one/events.jsonl'
        events = [{'type':'user.message', 'id':str(i), 'data':{'content':text}} for i, text in enumerate([full, '/clear', 'after clear', 'after clear'])]
        events += [{'type':'assistant.message', 'data':{'content':'response'}}]
    else:
        path = provider_home/'.codex/sessions/rollout.jsonl'
        state = provider_home/'.codex/state_5.sqlite'
        state.parent.mkdir(parents=True)
        with closing(sqlite3.connect(state)) as conn, conn:
            conn.execute('CREATE TABLE threads(id TEXT, rollout_path TEXT)')
            conn.execute('INSERT INTO threads VALUES(?,?)', ('thread-one', str(path)))
        events = [{'type':'event_msg', 'payload':{'type':'user_message','message':text}} for text in [full, '/clear', 'after clear', 'after clear']]
        events += [{'type':'response_item', 'payload':{'type':'message','role':'user','content':[{'type':'input_text','text':full}]}}]
    write_events(path, events)
    history.sync(row)
    for _ in range(3):
        history.sync(row)
    entries = history.history('terminal-one')
    assert [entry['text'] for entry in entries if entry['type'] == 'request'] == [full, 'after clear', 'after clear']
    assert [(entry['text'], entry['command']) for entry in entries if entry['type'] == 'boundary'] == [('Session started', None), ('Session cleared', '/clear')]
    history._CACHE.clear()
    history._TRANSCRIPTS.clear()
    history.sync(row)
    assert history.history('terminal-one') == entries
    assert history.history('other-terminal') == []


def test_input_clear_merges_native_event_and_keeps_old_messages(provider_home):
    row = {'name':'one','agent':'copilot','agent_session_id':'thread-one'}
    path = provider_home/'.copilot/session-state/thread-one/events.jsonl'
    events = [{'type':'user.message','data':{'content':'before clear'}}]
    write_events(path, events)
    history.sync(row)
    history.command(row, '/clear')
    history.command(row, '/clear')
    events += [{'type':'user.message','data':{'content':'/clear'}}, {'type':'user.message','data':{'content':'after clear'}}]
    write_events(path, events)
    history.sync(row)
    entries = history.history('one')
    assert [entry['text'] for entry in entries] == ['Session started', 'before clear', 'Session cleared', 'after clear']
    history.command(row, '/new')
    fresh = {**row, 'agent_session_id':'thread-two'}
    history.sync(fresh)  # Empty new thread, before the next request is saved.
    write_events(provider_home/'.copilot/session-state/thread-two/events.jsonl', [{'type':'user.message','data':{'content':'fresh request'}}])
    history.sync(fresh)
    assert [entry['text'] for entry in history.history('one')] == ['Session started', 'before clear', 'Session cleared', 'after clear', 'New session', 'fresh request']


def test_thread_switches_and_partial_writes(provider_home):
    row = {'name':'one','agent':'copilot','agent_session_id':'thread-one'}
    path = provider_home/'.copilot/session-state/thread-one/events.jsonl'
    write_events(path, [{'type':'user.message','data':{'content':'accepted edit'}}])
    history.sync(row)
    tail = json.dumps({'type':'user.message','data':{'content':'a multiline\nsubmitted paste'}})
    with path.open('a') as handle:
        handle.write(tail[:25])
    history.sync(row)
    assert len(history.history('one')) == 2
    with path.open('a') as handle:
        handle.write(tail[25:]+'\n')
    history.sync(row)
    switched = {**row, 'agent_session_id':'thread-two'}
    history.sync(switched)
    history.command(switched, '/clear')  # Identity discovered ahead of the input signal.
    assert [entry['text'] for entry in history.history('one')] == ['Session started', 'accepted edit', 'a multiline\nsubmitted paste', 'Session cleared']
    assert history.history('one')[-1]['command'] == '/clear'


def test_codex_projection_fallback_deduplicates_when_rollout_arrives(provider_home):
    home = provider_home/'.codex'
    home.mkdir()
    row = {'name':'one','agent':'codex','agent_session_id':'thread-one'}
    with closing(sqlite3.connect(home/'thread_history_1.sqlite')) as conn, conn:
        conn.execute('CREATE TABLE thread_items(thread_id TEXT, item_json TEXT, rollout_ordinal INT, item_type TEXT)')
        for i in range(2):
            conn.execute('INSERT INTO thread_items VALUES(?,?,?,?)', ('thread-one', json.dumps({'content':[{'type':'input_text','text':'repeat'}]}), i, 'userMessage'))
    history.sync(row)
    rollout = home/'rollout.jsonl'
    write_events(rollout, [{'type':'event_msg','payload':{'type':'user_message','message':text}} for text in ['repeat','repeat','new']])
    with closing(sqlite3.connect(home/'state_5.sqlite')) as conn, conn:
        conn.execute('CREATE TABLE threads(id TEXT, rollout_path TEXT)')
        conn.execute('INSERT INTO threads VALUES(?,?)', ('thread-one',str(rollout)))
    history.sync(row)
    assert [entry['text'] for entry in history.history('one') if entry['type'] == 'request'] == ['repeat','repeat','new']


def test_requests_routes_require_terminal_in_authorized_workspace(client, monorepo, monkeypatch):
    from core.routes import term
    row = {'name':'one','agent':'copilot','agent_session_id':'thread-one'}
    calls = []
    def sessions(request, workspace_id, vault):
        calls.append((workspace_id,vault))
        return [row] if workspace_id == 'allowed' else []
    monkeypatch.setattr(term, 'list_sessions', sessions)
    monkeypatch.setattr(history, '_records', lambda row: ([], ()))
    assert client.get('/api/term/requests?name=one&workspace_id=allowed&vault=local').status_code == 200
    assert client.get('/api/term/requests?name=one&workspace_id=other').status_code == 404
    assert client.post('/api/term/requests/command', json={'name':'one','workspace_id':'other','command':'/clear'}).status_code == 404
    assert client.post('/api/term/requests/command', json={'name':'one','workspace_id':'allowed','command':'arbitrary input'}).status_code == 422
    assert client.post('/api/term/requests/command', json={'name':'one','workspace_id':'allowed','command':'/clear'}).status_code == 200
    assert calls[0] == ('allowed','local')
    row['agent'] = None
    assert client.post('/api/term/requests/command', json={'name':'one','workspace_id':'allowed','command':'/clear'}).status_code == 400
