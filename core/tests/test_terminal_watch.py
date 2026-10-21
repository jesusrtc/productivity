"""Persistent user watches over the real session API and an isolated tmux server."""
import time
import uuid

from core import terminal_watch
from core.routes import term
from lab import terminal_status
from .test_term_creation_native import native_creation_tmux, native_creation_client  # noqa: F401


def report(state, revision, message='Latest result'):
    return dict(version=1, state=state, id=uuid.uuid4().hex, revision=revision,
                updated_at=time.time(), message=message)


def test_watch_retains_latest_alert_and_rejects_invalid_tokens():
    old, newer = report('finished', 1), report('attention', 2)
    row = {'terminal_status': old}
    watch = terminal_watch.create(row, 'pin', now=time.time())
    assert watch['report'] == old
    assert terminal_watch.decode(terminal_status.encode(watch)) == watch
    row.update(terminal_notification=newer, terminal_status=report('working', 3))
    assert terminal_watch.view(watch, row)['report'] == newer
    for value in ('bad', terminal_status.encode({**watch, 'due_at': float('nan')}),
                  terminal_status.encode({**watch, 'report': None})):
        assert terminal_watch.decode(value) is None
    shell = terminal_watch.create({}, 'remind', now=time.time(), due_at=time.time()+600)
    assert shell['report']['kind'] == 'watch' and shell['report']['state'] == 'attention'
    assert terminal_watch.view(shell, row)['report'] == newer


def test_native_watch_pin_remind_close_cancel_and_incarnation_guards(
        native_creation_tmux, native_creation_client, seed_workspace):
    run, socket, _ = native_creation_tmux
    seed_workspace('demo')
    client = native_creation_client
    name = client.post('/api/term/sessions', json={'workspace_id':'demo', 'kind':'terminal'}).json()['name']

    def read():
        return client.get('/api/term/sessions', params={'workspace_id':'demo'}).json()[0]

    row = read()
    identity = {key:row[key] for key in ('name', 'tmux_socket', 'tmux_id', 'created')}
    initial = report('attention', 1, 'Review | <preview> ; #{session_name}')
    run('set-option', '-t', name, '@lab_status', terminal_status.encode(initial))
    run('set-option', '-t', name, '@lab_notification', terminal_status.encode(initial))
    result = client.post('/api/term/watch', json={**identity, 'mode':'pin'})
    assert result.status_code == 200, result.text
    pinned = result.json()['watch']
    assert pinned['mode'] == 'pin' and pinned['report'] == initial
    assert read()['terminal_status'] == initial
    assert run('show-options','-qv','-t','anchor','@lab_watch').stdout == ''
    # Both fresh reads and the cross-workspace batch retain the same watch.
    assert read()['terminal_watch'] == pinned
    batch = client.get('/api/workspace-documents/attention').json()
    shared = next(row for rows in batch.values() for row in rows if row['name'] == name)
    assert shared['terminal_watch'] == pinned
    assert '/api/term/watch' in client.get('/api/commands').json()['paths']
    working = report('working', 2)
    run('set-option', '-t', name, '@lab_status', terminal_status.encode(working))
    assert read()['terminal_watch']['report'] == initial
    newer = report('finished', 3)
    run('set-option', '-t', name, '@lab_status', terminal_status.encode(newer))
    run('set-option', '-t', name, '@lab_notification', terminal_status.encode(newer))
    assert read()['terminal_watch']['report'] == newer
    assert client.post('/api/term/watch', json={**identity, 'mode':'close', 'watch_id':pinned['id'],
                                              'report_id':initial['id']}).status_code == 409
    result = client.post('/api/term/watch', json={**identity, 'mode':'close', 'watch_id':pinned['id'],
                                               'report_id':newer['id']})
    assert result.status_code == 200, result.text
    assert read()['terminal_watch']['closed_report_id'] == newer['id']
    assert read()['terminal_status'] == newer, 'closing only affects the watch'
    for due in (0, time.time()-1, time.time()+8*86400):
        assert client.post('/api/term/watch', json={**identity, 'mode':'remind', 'due_at':due}).status_code == 422
    result = client.post('/api/term/watch', json={**identity, 'mode':'remind', 'due_at':time.time()+600})
    assert result.status_code == 200, result.text
    reminder = result.json()['watch']
    assert read()['terminal_watch'] == reminder
    assert client.post('/api/term/watch', json={**identity, 'mode':'cancel', 'watch_id':pinned['id']}).status_code == 409
    assert client.post('/api/term/watch', json={**identity, 'mode':'cancel', 'watch_id':reminder['id']}).status_code == 200
    assert read()['terminal_watch'] is None
    run('kill-session', '-t', name)
    run('new-session', '-d', '-s', name, '/bin/sleep 60')
    assert read()['terminal_watch'] is None
    assert client.post('/api/term/watch', json={**identity, 'mode':'pin'}).status_code == 409


def test_native_watch_does_not_close_a_report_that_changes_during_save(
        native_creation_tmux, native_creation_client, seed_workspace, monkeypatch):
    run, socket, _ = native_creation_tmux
    seed_workspace('demo')
    client = native_creation_client
    name = client.post('/api/term/sessions', json={'workspace_id':'demo', 'kind':'terminal'}).json()['name']
    row = client.get('/api/term/sessions', params={'workspace_id':'demo'}).json()[0]
    identity = {key:row[key] for key in ('name', 'tmux_socket', 'tmux_id', 'created')}
    pinned = client.post('/api/term/watch', json={**identity, 'mode':'pin'}).json()['watch']
    original_run = term.subprocess.run
    newer = report('attention', 10)

    def raced(args, *a, **kw):
        if 'if-shell' in args:
            original_run(term._tmux_command(socket, 'set-option', '-t', name, '@lab_status',
                         terminal_status.encode(newer)), capture_output=True, env=term._tmux_child_env(), check=True)
        return original_run(args, *a, **kw)

    monkeypatch.setattr(term.subprocess, 'run', raced)
    response = client.post('/api/term/watch', json={**identity, 'mode':'close', 'watch_id':pinned['id'],
                                                 'report_id':pinned['report']['id']})
    assert response.status_code == 409, response.text
    watch = client.get('/api/term/sessions', params={'workspace_id':'demo'}).json()[0]['terminal_watch']
    assert watch['mode'] == 'pin' and watch['report'] == newer
