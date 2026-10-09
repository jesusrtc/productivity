"""Local window ownership, persistence, and bounded native failures."""
import json
import subprocess

import pytest

from core import resource_windows
from core.routes import ui
from .test_external_links import _browser_client

OWNER = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
OTHER = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'


def test_resource_window_state_keeps_url_identity_and_parent_ownership(tmp_path, monkeypatch):
    monkeypatch.setattr(resource_windows.paths, 'find_framework_root', lambda: tmp_path)
    monkeypatch.setattr(resource_windows, '_retry_after', 0)
    calls = []
    url = 'https://example.com/a?one=1&two=2#part'
    group = {'parent': {'pid':42, 'id':10, 'started':1},
             'resources':[{'url':url, 'window':{'pid':42, 'id':11, 'started':1}}]}
    def invoke(payload):
        calls.append(payload)
        return {'ok':True, 'trusted':True, 'reused':payload['operation']=='focus',
                'group':group if payload['operation']=='register' else payload['group']}
    monkeypatch.setattr(resource_windows, '_invoke', invoke)
    assert resource_windows.manage(OWNER, 'register', url=url)['urls'] == [url]
    # A page/backend reload recovers the owned window ID; it never navigates it.
    assert resource_windows.manage(OWNER, 'focus', url=url)['reused'] is True
    assert calls[-1]['group'] == group
    assert resource_windows.manage(OTHER, 'raise')['urls'] == []
    assert calls[-1]['group'] == {'resources':[]}
    saved = json.loads((tmp_path/'.lab/state/resource-windows.json').read_text())
    assert saved[OWNER] == group and saved[OTHER] == {'resources':[]}


def test_native_helper_timeout_backs_off_without_launching_another_window(tmp_path, monkeypatch):
    monkeypatch.setattr(resource_windows.paths, 'find_framework_root', lambda: tmp_path)
    monkeypatch.setattr(resource_windows, '_retry_after', 0)
    now = [100.0]; calls = []
    monkeypatch.setattr(resource_windows.time, 'monotonic', lambda: now[0])
    def unavailable(payload):
        calls.append(payload)
        raise subprocess.TimeoutExpired('window helper', 6)
    monkeypatch.setattr(resource_windows, '_invoke', unavailable)
    for operation in ['register','focus','raise']:
        result = resource_windows.manage(OWNER, operation)
        assert result['ok'] is False and 'did not respond' in result['detail']
    assert len(calls) == 1
    assert not (tmp_path/'.lab/state/resource-windows.json').exists()
    now[0] += 31
    monkeypatch.setattr(resource_windows, '_invoke', lambda p: {'ok':True,'group':p['group'],'reused':False})
    assert resource_windows.manage(OWNER, 'focus')['ok'] is True


def test_resource_helper_uses_background_bundle_and_json_files(tmp_path, monkeypatch):
    app = tmp_path/'Lab Resource Windows.app'
    monkeypatch.setattr(resource_windows, 'helper_app', lambda: app)
    payload = {'operation':'register','url':'https://example.com/?q=`whoami`&next=$(test)', 'group':{'resources':[]}}
    def run(argv, **kwargs):
        assert argv[:4] == ['/usr/bin/open','-g','-n',str(app)]
        assert argv[4] == '--args' and kwargs['timeout'] == 5 and not kwargs.get('shell')
        from pathlib import Path
        assert json.loads(Path(argv[5]).read_text()) == payload
        Path(argv[6]).write_text(json.dumps({'ok':True,'group':payload['group']}))
    monkeypatch.setattr(resource_windows.subprocess, 'run', run)
    assert resource_windows._invoke(payload)['ok'] is True


@pytest.mark.parametrize('host,base,origin,platform', [
    ('10.0.0.8','http://localhost','http://localhost','darwin'),
    ('127.0.0.1','https://lab.example','https://lab.example','darwin'),
    ('127.0.0.1','http://localhost','https://example.com','darwin'),
    ('127.0.0.1','http://localhost','http://localhost','linux'),
])
def test_resource_window_control_rejects_remote_cross_origin_and_nonmac(client, monkeypatch, host, base, origin, platform):
    monkeypatch.setattr(ui.sys, 'platform', platform)
    monkeypatch.setattr(resource_windows, 'manage', lambda *a, **kw: pytest.fail('Desktop control must stay local'))
    with _browser_client(client, host, base) as browser:
        response = browser.post('/api/ui/resource-windows', json={'owner':OWNER,'operation':'raise'}, headers={'Origin':origin})
    assert response.status_code == 403


def test_resource_window_api_validates_identity_and_passes_exact_url(client, monkeypatch):
    monkeypatch.setattr(ui.sys, 'platform', 'darwin')
    calls=[]
    monkeypatch.setattr(resource_windows, 'manage', lambda *a, **kw: calls.append((a,kw)) or {'ok':True,'urls':[]})
    with _browser_client(client) as browser:
        def post(payload):
            return browser.post('/api/ui/resource-windows', json=payload, headers={'Origin':'http://localhost'})
        for payload in [
            {'owner':OWNER,'operation':'register'},
            {'owner':OWNER,'operation':'focus','url':'file:///tmp/test'},
            {'owner':'--help','operation':'raise'},
            {'owner':OWNER,'operation':'register','url':'https://example.com','marker':'unowned'},
        ]:
            assert post(payload).status_code == 422
        url='https://example.com/?one=1&two=2#part'
        assert post({'owner':OWNER,'operation':'focus','url':url}).status_code == 200
    assert calls == [((OWNER,'focus'), {'url':url})]


def test_resource_window_api_requires_admin(client, monkeypatch):
    monkeypatch.setattr(ui.sys, 'platform', 'darwin')
    client.post('/api/admin/users', json={'username':'reader','password':'reader','role':'user','vaults':[]})
    client.post('/api/auth/logout')
    payload={'json':{'owner':OWNER,'operation':'permission'},'headers':{'Origin':'http://localhost'}}
    assert client.post('/api/ui/resource-windows', **payload).status_code == 401
    client.post('/api/auth/login', json={'username':'reader','password':'reader'})
    assert client.post('/api/ui/resource-windows', **payload).status_code == 403
