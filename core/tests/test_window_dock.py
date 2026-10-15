"""Dock controls may affect only a local owner's explicitly registered trial."""
import json

import pytest

from core import window_dock
from core.routes import ui
from .test_external_links import _browser_client

OWNER = 'a' * 32


@pytest.mark.parametrize('host,base_url,origin,platform', [
    ('10.0.0.8', 'http://localhost', 'http://localhost', 'darwin'),
    ('127.0.0.1', 'https://lab.example', 'https://lab.example', 'darwin'),
    ('127.0.0.1', 'http://localhost', 'https://attacker.example', 'darwin'),
    ('127.0.0.1', 'http://localhost', '', 'darwin'),
    ('127.0.0.1', 'http://localhost', 'http://localhost', 'linux'),
])
def test_dock_rejects_nonlocal_and_cross_origin(client, monkeypatch, host, base_url, origin, platform):
    monkeypatch.setattr(ui.sys, 'platform', platform)
    monkeypatch.setattr(window_dock, 'manage', lambda *a, **k: pytest.fail('Must not run native helper'))
    with _browser_client(client, host, base_url) as browser:
        response = browser.post('/api/ui/window-dock', json={'owner': OWNER, 'operation': 'permission'}, headers={'Origin': origin})
    assert response.status_code == 403


@pytest.mark.parametrize('slot', [None, [-1, 0, .5, .5], [.5, 0, .8, .5], [0, 0, 0, .5], [0, 0, .5, 2]])
def test_dock_rejects_invalid_geometry(client, monkeypatch, slot):
    monkeypatch.setattr(ui.sys, 'platform', 'darwin')
    monkeypatch.setattr(window_dock, 'manage', lambda *a, **k: pytest.fail('Must not run native helper'))
    with _browser_client(client) as browser:
        response = browser.post('/api/ui/window-dock', json={'owner': OWNER, 'operation': 'attach', 'slot': slot}, headers={'Origin': 'http://localhost'})
    assert response.status_code == 422


def test_dock_uses_view_identity_and_preserves_bounds(client, monkeypatch):
    calls = []
    monkeypatch.setattr(ui.sys, 'platform', 'darwin')
    monkeypatch.setattr(window_dock, 'manage', lambda *a, **k: calls.append((a, k)) or {'ok': True, 'active': True})
    with _browser_client(client) as browser:
        response = browser.post('/api/ui/window-dock', json={'owner': OWNER, 'operation': 'attach', 'slot': [.1, .2, .8, .7]}, headers={'Origin': 'http://localhost'})
    assert response.status_code == 200
    assert calls == [((OWNER, 'attach'), {'slot': (.1, .2, .8, .7), 'visible': True,
                                        'parentMarker': 'Lab dock parent ' + OWNER,
                                        'childMarker': 'Lab dock popup ' + OWNER})]


def test_dock_no_session_never_targets_arbitrary_windows(monkeypatch):
    monkeypatch.setattr(window_dock, '_sessions', {})
    monkeypatch.setattr(window_dock, '_launch', lambda *a: pytest.fail('Never launch for unknown control target'))
    assert not window_dock.manage(OWNER, 'close')['ok']
    assert not window_dock.manage(OWNER, 'update', slot=[0, 0, 1, 1])['active']
    assert window_dock.manage(OWNER, 'detach')['ok']


def test_dock_heartbeat_keeps_explicit_identity_and_prunes_finished(monkeypatch, tmp_path):
    directory = tmp_path / 'session'; directory.mkdir()
    (directory / 'state.json').write_text(json.dumps({'ok': True, 'active': True}))
    monkeypatch.setattr(window_dock, '_sessions', {OWNER: directory})
    result = window_dock.manage(OWNER, 'update', slot=[0, 0, 1, 1], visible=False)
    assert result['active']
    assert json.loads((directory / 'control.json').read_text())['visible'] is False
    assert (directory / 'control.json').stat().st_mode & 0o777 == 0o600
    (directory / 'state.json').write_text(json.dumps({'ok': True, 'active': False}))
    assert window_dock.manage(OWNER, 'detach')['ok']
    assert not directory.exists()
    assert OWNER not in window_dock._sessions


def test_dock_refuses_duplicate_controller(monkeypatch, tmp_path):
    (tmp_path / 'state.json').write_text(json.dumps({'ok': True, 'active': True}))
    monkeypatch.setattr(window_dock, '_sessions', {OWNER: tmp_path})
    monkeypatch.setattr(window_dock, '_launch', lambda *a: pytest.fail('Duplicate controller'))
    assert not window_dock.manage(OWNER, 'attach')['ok']
