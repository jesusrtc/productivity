"""Per-checkout links, internal document/tab identity, and allowed link types."""
import pytest

from lab import assistant_records as records, scope_links, settings
from .test_assistant_documents_unified import library, change


def read(client, path):
    response = client.get('/api/scope-links', params={'path': str(path)})
    assert response.status_code == 200, response.text
    return response.json()


def save(client, path, links, expected=None):
    return client.put('/api/scope-links', json={'path':str(path), 'links':links,
                     'expected':expected or read(client,path)['revision']})


def test_allowed_link_types_defaults_custom_and_validation(client, monorepo):
    defaults = client.get('/api/settings/global').json()['scopeLinkTypes']
    assert defaults == [
        {'id':'google-docs','name':'Google Docs','kind':'external'},
        {'id':'internal-docs','name':'Internal docs','kind':'internal'},
        {'id':'jira','name':'Jira tickets','kind':'external'}]
    custom = defaults + [{'id':'design','name':'Design','kind':'external'}]
    assert client.post('/api/settings/global',json={'scopeLinkTypes':custom}).status_code == 200
    for bad in [[], defaults + [defaults[0]], [{'id':'bad','name':'','kind':'external'}],
                [{'id':'BAD','name':'Bad','kind':'internal'}], [{'id':'bad','name':'Bad','kind':{}}]]:
        assert client.post('/api/settings/global',json={'scopeLinkTypes':bad}).status_code == 400
    assert settings.load(monorepo)['scopeLinkTypes'] == custom


def test_exact_scopes_are_independent_and_stale_writes_cannot_lose_links(client, monorepo):
    project, tree = monorepo/'project', monorepo/'trees/feature'
    project.mkdir(); tree.mkdir(parents=True)
    empty = read(client,project)
    google = {'type':'google-docs','url':'https://docs.google.com/document/d/example/edit','label':'Proposal'}
    jira = {'type':'jira','url':'https://tickets.example.invalid/browse/LAB-1'}
    first = save(client,project,[google],empty['revision'])
    assert first.status_code == 200
    assert save(client,tree,[jira]).status_code == 200
    assert read(client,project)['links'][0]['label'] == 'Proposal'
    assert read(client,tree)['links'][0]['type'] == 'jira'
    assert save(client,project,[],empty['revision']).status_code == 409
    assert len(read(client,project)['links']) == 1
    assert save(client,project,[]).status_code == 200
    assert read(client,project)['links'] == []
    assert len(read(client,tree)['links']) == 1
    assert scope_links.file().is_file()


def test_external_urls_infer_services_without_configuring_types(client, monorepo):
    urls = [
        ('https://docs.google.com/document/d/example/edit', 'google-docs', 'Google Docs'),
        ('https://docs.google.com/spreadsheets/d/example/edit', 'google-sheets', 'Google Sheets'),
        ('https://company.slack.com/archives/C123', 'slack', 'Slack'),
        ('https://company.atlassian.net/wiki/spaces/ENG', 'confluence', 'Confluence'),
        ('https://company.atlassian.net/browse/ENG-1', 'jira', 'Jira tickets'),
        ('https://grafana.company.invalid/d/dashboard', 'grafana', 'Grafana'),
        ('https://github.com/org/repo/pulls', 'github', 'GitHub'),
        ('https://example.invalid/article?site=slack.com', 'url', 'Link'),
    ]
    before = settings.load(monorepo)['scopeLinkTypes']
    result = save(client, monorepo, [{'id': str(index), 'url': url} for index, (url, _, _) in enumerate(urls)])
    assert result.status_code == 200, result.text
    links = result.json()['links']
    assert [(row['url'], row['type'], row['type_name']) for row in links] == urls
    assert settings.load(monorepo)['scopeLinkTypes'] == before
    # Editing the URL replaces its inferred service, even with an old type.
    result = save(client, monorepo, [{**links[0], 'kind': 'external', 'url': urls[2][0]}])
    assert result.status_code == 200, result.text
    assert result.json()['links'][0]['type'] == 'slack'
    for url in ['javascript:alert(1)', 'file:///tmp/file', 'https://', 'https://[broken']:
        assert save(client, monorepo, [{'kind': 'external', 'url': url}]).status_code == 400
    assert read(client, monorepo)['links'][0]['type'] == 'slack'


def test_internal_whole_document_and_specific_tab_follow_identity(client, monorepo, library):
    root, _, note, content, _, _, meeting = library
    tab_id = records.read_document(content)[0]['id']
    whole={'type':'internal-docs','assistant_root':str(root),'document_id':note.stem}
    tab={**whole,'tab_id':tab_id,'label':'Reference tab'}
    result = save(client,monorepo,[whole,tab])
    assert result.status_code == 200, result.text
    links = result.json()['links']
    assert links[0]['title'] == 'Guide' and links[0]['tab_id'] is None
    assert links[1]['title'] == 'Guide / Reference' and links[1]['tab_id'] == tab_id
    detail = client.get('/api/assistant/note',params={'path':links[1]['path']}).json()
    assert detail['metadata']['id'] == tab_id
    before = scope_links.file().read_bytes()
    assert save(client,monorepo,[{**tab,'tab_id':meeting.stem}]).status_code == 400
    assert save(client,monorepo,[{**whole,'assistant_root':'/another-library'}]).status_code == 400
    assert scope_links.file().read_bytes() == before
    change(client,root,note,'title','Renamed guide')
    assert read(client,monorepo)['links'][1]['title'] == 'Renamed guide / Reference'


@pytest.mark.parametrize('link',[
    {'type':'google-docs','url':'javascript:alert(1)'}, {'type':'jira','url':'file:///tmp/document'},
    {'type':'jira','url':'https://'}, {'type':'unknown','url':'https://example.invalid'},
    {'type':{},'url':'https://example.invalid'},
])
def test_invalid_links_do_not_write(client, monorepo, link):
    assert save(client,monorepo,[link]).status_code == 400
    assert read(client,monorepo)['links'] == []


def test_links_reject_unregistered_folders_and_readers(client,monorepo,tmp_path):
    from .test_auth_routes import _create_user, _login
    from lab import paths
    outside=tmp_path/'private';outside.mkdir()
    assert client.get('/api/scope-links',params={'path':str(outside)}).status_code == 403
    paths.register_vault(monorepo,name='Main',active=True)
    assert _create_user(client,'reader','test-secret',vaults=['main']).status_code == 200
    client.post('/api/auth/logout');_login(client,'reader','test-secret')
    assert client.get('/api/scope-links',params={'path':str(monorepo),'vault':'main'}).status_code == 403
    assert client.put('/api/scope-links',params={'vault':'main'},json={'path':str(monorepo),'links':[],'expected':'old'}).status_code == 403
    assert client.post('/api/settings',params={'vault':'main'},json={'scopeLinkTypes':[]}).status_code == 403
