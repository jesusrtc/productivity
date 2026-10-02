"""Browser and backend agree on real service URLs and hostname boundaries."""
import json

from core.link_services import SERVICES, infer
from .test_frontend_terminal_ui import ROOT, _run_node


def test_service_registry_matches_in_browser_and_backend():
    cases = [
        ('https://DOCS.GOOGLE.COM/document/d/example', 'google-docs'),
        ('https://docs.google.com/spreadsheets/d/example', 'google-sheets'),
        ('https://docs.google.com/presentation/d/example', 'google-slides'),
        ('https://docs.google.com/forms/d/example', 'google-forms'),
        ('https://drive.google.com/file/d/example', 'google-drive'),
        ('https://workspace.slack.com/archives/C123', 'slack'),
        ('https://company.atlassian.net/wiki/spaces/ENG', 'confluence'),
        ('https://company.atlassian.net/browse/ENG-1', 'jira'),
        ('https://jira.company.test/browse/ENG-1', 'jira'),
        ('https://confluence-internal.company.test/pages/1', 'confluence'),
        ('https://grafana.company.test/d/example', 'grafana'),
        ('https://github.com./org/repo/pulls', 'github'),
        ('https://gitlab.company.test/org/repo', 'gitlab'),
        ('https://name.notion.site/page', 'notion'),
        ('https://figma.com/design/example', 'figma'),
        ('https://linear.app/company/issue/ENG-1', 'linear'),
        ('https://trello.com/b/example', 'trello'),
        ('https://bitbucket.org/org/repo', 'bitbucket'),
        ('https://youtu.be/example', 'youtube'),
        ('https://teams.microsoft.com/l/message/example', 'teams'),
        ('https://company.atlassian.net/wikipedia/page', 'jira'),
        ('https://slack.com.example.test/path', None),
        ('https://fakeslack.com/path', None),
        ('https://example.test/?url=https://github.com', None),
        ('https://github.com@example.test/', None),
        ('javascript:alert(1)', None),
        ('not a URL', None),
    ]
    expected = [identifier for _, identifier in cases]
    assert [(infer(url) or {}).get('id') for url, _ in cases] == expected
    module = (ROOT/'core/src/core/static/js/lib/scope-links.js').read_text()
    result = _run_node('const document={addEventListener(){}};\nwindow.LAB_LINK_SERVICES=' + json.dumps(SERVICES) + ';\n'
                       + module + '\nprocess.stdout.write(JSON.stringify(' + json.dumps(cases)
                       + '.map(([url])=>window.LabScopeLinks.serviceFor({url},false)?.id||null)));')
    assert result == expected


def test_legacy_types_identify_company_hosted_links_but_never_internal_documents():
    module = (ROOT/'core/src/core/static/js/lib/scope-links.js').read_text()
    links = [
        {'type': 'jira', 'url': 'https://tickets.company.test/browse/ENG-1'},
        {'type_name': 'Google Docs', 'url': 'https://example.test'},
        {'kind': 'internal', 'type': 'google-docs'},
        {'type': 'jira', 'url': 'https://workspace.slack.com/archives/C123'},
    ]
    result = _run_node('const document={addEventListener(){}};\nwindow.LAB_LINK_SERVICES=' + json.dumps(SERVICES) + ';\n'
                       + module + '\nprocess.stdout.write(JSON.stringify(' + json.dumps(links)
                       + '.map(link=>window.LabScopeLinks.serviceFor(link)?.id||null)));')
    assert result == ['jira', 'google-docs', None, 'slack']


def test_domain_mappings_override_heuristics_and_match_specific_hosts_first():
    import base64
    from lab.link_icons import validate_mappings
    icon='data:image/png;base64,'+base64.b64encode((ROOT/'core/src/core/static/img/link-icons/google-docs.png').read_bytes()).decode()
    mappings=validate_mappings([
        {'domain':'mycompany.com','service':'grafana','includeSubdomains':True},
        {'domain':'chat.mycompany.com','service':'slack'},
        {'domain':'tool.mycompany.com','service':'custom','name':'Custom console','icon':icon},
        {'domain':'github.com','service':'notion'},
    ])
    cases=[
        ('https://mygrafana.mycompany.com/d/errors', ['grafana','Grafana',False]),
        ('https://chat.mycompany.com/archives/C123', ['slack','Slack',False]),
        ('https://child.chat.mycompany.com/archives/C123', ['grafana','Grafana',False]),
        ('https://tool.mycompany.com/run', ['url','Custom console',True]),
        ('https://tool.mycompany.com.evil.test/run', None),
        ('https://github.com/org/repo', ['notion','Notion',False]),
        ('https://mycompany.com.evil.test/d/errors', None),
        ('https://example.test/?next=mygrafana.mycompany.com', None),
    ]
    def summarize(service):
        return [service['id'],service['name'],bool(service.get('iconData'))] if service else None
    assert [summarize(infer(url,mappings)) for url,_ in cases] == [expected for _,expected in cases]
    module=(ROOT/'core/src/core/static/js/lib/scope-links.js').read_text()
    result=_run_node('const document={addEventListener(){},querySelectorAll(){return []}};\nwindow.LAB_LINK_SERVICES='+json.dumps(SERVICES)+';\n'
                     +module+'\nwindow.LabScopeLinks.setDomainMappings('+json.dumps(mappings)+');\nprocess.stdout.write(JSON.stringify('
                     +json.dumps(cases)+'.map(([url])=>{const s=window.LabScopeLinks.serviceFor({url},false);return s?[s.id,s.name,!!s.iconData]:null})));')
    assert result == [expected for _,expected in cases]


def test_removed_mapping_does_not_reuse_its_name_as_a_legacy_icon_hint():
    module=(ROOT/'core/src/core/static/js/lib/scope-links.js').read_text()
    result=_run_node('const document={addEventListener(){}};window.LAB_LINK_SERVICES='+json.dumps(SERVICES)+';\n'+module+r'''
const link={kind:'external',type:'url',url:'https://company.test/page',type_name:'Google Docs',base_type_name:'Link'};
process.stdout.write(JSON.stringify({service:window.LabScopeLinks.serviceFor(link)?.id||null,label:window.LabScopeLinks.label(link)}));
''')
    assert result=={'service':None,'label':'Link'}

    result=_run_node('const document={addEventListener(){}};window.LAB_LINK_SERVICES='+json.dumps(SERVICES)+';\n'+module+r'''
const link={kind:'external',type:'grafana',url:'https://company.test/page',type_name:'Grafana',auto_type:true};
process.stdout.write(JSON.stringify({service:window.LabScopeLinks.serviceFor(link)?.id||null,label:window.LabScopeLinks.label(link)}));
''')
    assert result=={'service':None,'label':'Link'}
