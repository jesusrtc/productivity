"""Central defaults are client-wide; workspace overrides and documents survive."""
import json
from pathlib import Path

import pytest
from lab import settings, paths, storage
from core.routes import settings as route
from core import document_terminals as dm
from .test_document_terminals import engine, open_doc, entry
from .test_assistant_documents_unified import library


def test_global_default_applies_to_all_roots_preserving_overrides(client, monorepo, seed_workspace, monkeypatch, tmp_path):
    monkeypatch.setattr(route.shutil,'which',lambda name:'/bin/'+name if name in {'codex','copilot'} else None)
    workspace=seed_workspace('demo')
    data=json.loads((workspace/'workspace.json').read_text());data['agent']='copilot';storage.write_json(workspace/'workspace.json',data)
    other=tmp_path/'other';other.mkdir()
    settings.update(other,{'defaultAgent':'claude','theme':'light'})
    before=(other/'.agents/config.json').read_bytes()
    response=client.post('/api/settings/global',json={'defaultAgent':'codex'})
    assert response.status_code==200,response.text
    assert settings.resolve_agent(monorepo)=='codex' and settings.resolve_agent(other)=='codex'
    assert settings.resolve_agent(monorepo,'demo')=='copilot'
    assert settings.load(other)['theme']=='light'  # unrelated legacy choice preserved
    assert (other/'.agents/config.json').read_bytes()==before
    assert client.post('/api/workspaces/demo/agent',json={'agent':None,'model':None}).status_code==200
    assert settings.resolve_agent(monorepo,'demo')=='codex'
    assert json.loads(settings.client_settings_file().read_text())=={'defaultAgent':'codex'}


def test_global_policy_is_validated_and_cannot_choose_missing_agent(client, monorepo, monkeypatch):
    monkeypatch.setattr(route.shutil,'which',lambda name:'/bin/codex' if name=='codex' else None)
    assert client.post('/api/settings/global',json={'defaultAgent':'claude'}).status_code==400
    assert not settings.client_settings_file().exists()
    for body in [{'documentTerminals':{'maxRunning':0}},{'documentTerminals':{'sleepMinutes':3000}},{'theme':'unknown'},{'documentTerminals':None}]:
        assert client.post('/api/settings/global',json=body).status_code==400
    assert client.post('/api/settings/global',json={'documentTerminals':{'sleepMinutes':30}}).status_code==200
    assert settings.load(monorepo)['documentTerminals']=={'enabled':True,'sleepMinutes':30,'expireHours':36,'maxRunning':3}


def test_global_read_does_not_migrate_legacy_config(client,monorepo):
    settings.update(monorepo,{'defaultAgent':'codex'})
    old=(monorepo/'.agents/config.json').read_bytes()
    assert client.get('/api/settings/global').json()['defaultAgent']=='codex'
    assert not settings.client_settings_file().exists()
    assert (monorepo/'.agents/config.json').read_bytes()==old


def test_failed_first_launch_uses_corrected_global_default(engine,monkeypatch):
    e=engine
    settings.update(e.root,{'defaultAgent':'claude'})
    monkeypatch.setattr(dm.shutil,'which',lambda name:None if name=='claude' else '/fake/'+name)
    with pytest.raises(Exception) as failure:open_doc(e)
    assert 'Settings' in str(failure.value) and not e.live
    settings.update_global(e.root,{'defaultAgent':'codex'})
    result=open_doc(e)
    assert result['agent']=='codex' and len(e.live)==1
    saved=entry(e,result)
    e.clock.now+=3600;dm.sweep(e.root)
    settings.update_global(e.root,{'defaultAgent':'copilot'})
    assert open_doc(e)['agent']=='codex'  # existing conversation stays with its provider


def test_global_settings_require_admin(client):
    from .test_auth_routes import _create_user,_login
    assert _create_user(client,'reader','test-secret').status_code==200
    client.post('/api/auth/logout');_login(client,'reader','test-secret')
    assert client.get('/api/settings/global').status_code==403
    assert client.post('/api/settings/global',json={'theme':'light'}).status_code==403
