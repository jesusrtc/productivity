"""Client-owned icon configuration round trips and applies to existing URLs."""
import base64
from pathlib import Path

import pytest
from lab import settings

from .test_scope_links import read, save


ICON='data:image/png;base64,'+base64.b64encode((Path(__file__).parents[1]/'src/core/static/img/link-icons/google-docs.png').read_bytes()).decode()


def test_configured_domains_apply_to_existing_and_new_links(client,monorepo):
    existing=save(client,monorepo,[{'url':'https://mygrafana.mycompany.com/d/errors','label':'Errors'},
                                    {'url':'https://console.mycompany.com/page'}])
    assert existing.status_code==200,existing.text
    assert all(row['type']=='url' for row in existing.json()['links'])
    mappings=[{'domain':'MyGrafana.MyCompany.COM.','service':'grafana'},
              {'domain':'console.mycompany.com','service':'custom','name':'Operations console','icon':ICON}]
    result=client.post('/api/settings/global',json={'linkDomainMappings':mappings})
    assert result.status_code==200,result.text
    normalized=result.json()['linkDomainMappings']
    assert normalized[0]=={'domain':'mygrafana.mycompany.com','service':'grafana','name':'','includeSubdomains':False}
    data=read(client,monorepo)
    assert [row['type_name'] for row in data['links']]==['Grafana','Operations console']
    assert data['linkDomainMappings']==normalized
    assert client.get('/api/settings/global').json()['linkDomainMappings']==normalized
    other=monorepo/'other';other.mkdir()
    assert settings.load(other)['linkDomainMappings']==normalized
    result=save(client,monorepo,[{'url':'https://mygrafana.mycompany.com/d/traffic'},
                               {'url':'https://console.mycompany.com/new'}])
    assert result.status_code==200,result.text
    assert [row['type'] for row in result.json()['links']]==['grafana','url']
    assert [row['type_name'] for row in result.json()['links']]==['Grafana','Operations console']
    assert client.post('/api/settings/global',json={'linkDomainMappings':[]}).status_code==200
    cleared=read(client,monorepo)
    assert cleared['linkDomainMappings']==[]
    assert [row['type'] for row in cleared['links']]==['url','url']


@pytest.mark.parametrize('mappings',[
    None,
    [{'domain':'https://mycompany.com/path','service':'grafana'}],
    [{'domain':'*.mycompany.com','service':'grafana'}],
    [{'domain':'mycompany.com:3000','service':'grafana'}],
    [{'domain':'mycompany.com','service':'missing-icon'}],
    [{'domain':'mycompany.com','service':{}}],
    [{'domain':'mycompany.com','service':'grafana','includeSubdomains':'yes'}],
    [{'domain':'mycompany.com','service':'custom','icon':'data:image/svg+xml,<svg onload="alert(1)"/>'}],
    [{'domain':'mycompany.com','service':'custom','icon':'data:image/png;base64,bm90IGEgcG5n'}],
    [{'domain':'mycompany.com','service':'grafana','icon':ICON}],
    [{'domain':'mycompany.com','service':'grafana'},{'domain':'MYCOMPANY.COM.','service':'slack'}],
])
def test_invalid_icon_config_never_replaces_saved_mappings(client,monorepo,mappings):
    valid=[{'domain':'mygrafana.mycompany.com','service':'grafana'}]
    assert client.post('/api/settings/global',json={'linkDomainMappings':valid}).status_code==200
    before=settings.client_settings_file().read_bytes()
    response=client.post('/api/settings/global',json={'linkDomainMappings':mappings})
    assert response.status_code==400,response.text
    assert settings.client_settings_file().read_bytes()==before


def test_domain_config_requires_admin_on_both_settings_routes(client,monorepo):
    from .test_auth_routes import _create_user,_login
    assert _create_user(client,'reader','test-secret').status_code==200
    client.post('/api/auth/logout');_login(client,'reader','test-secret')
    for path in ['/api/settings/global','/api/settings']:
        assert client.post(path,json={'linkDomainMappings':[{'domain':'mycompany.com','service':'grafana'}]}).status_code==403
