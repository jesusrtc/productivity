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
