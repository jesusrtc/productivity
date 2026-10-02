"""Default-browser reuse selects tabs without navigating or reloading them."""
import json
import subprocess

import pytest

from core import browser_tabs
from .test_frontend_terminal_ui import _run_node


@pytest.mark.parametrize('url,prefix', [
    ('https://docs.google.com/document/d/doc_123/edit?usp=sharing', 'https://docs.google.com/document/d/doc_123'),
    ('https://docs.google.com/spreadsheets/d/sheet-123/', 'https://docs.google.com/spreadsheets/d/sheet-123'),
    ('https://docs.google.com/presentation/d/slides123', 'https://docs.google.com/presentation/d/slides123'),
    ('https://docs.google.com/document/d/doc/edit?tab=t.2', ''),
    ('https://docs.google.com/document/d/doc/edit?%74ab=t.2', ''),
    ('https://docs.google.com/document/d/doc/edit#heading=h.2', ''),
    ('https://docs.google.com/spreadsheets/d/doc/edit?gid=2', ''),
    ('https://docs.google.com/spreadsheets/d/doc/edit?range=A1', ''),
    ('https://docs.google.com.evil.test/document/d/doc/edit', ''),
    ('https://docs.google.com/other/doc', ''),
    ('https://example.com/docs', ''),
])
def test_document_prefix_preserves_explicit_destinations(url, prefix):
    assert browser_tabs.document_prefix(url) == prefix


@pytest.mark.parametrize('bundle,windows,target,prefix,expected', [
    ('com.google.Chrome', [['https://example.com/other'], ['https://example.com/other', 'https://example.com/?x=1#part']], 'https://example.com/?x=1#part', '', [1, 1]),
    # Exact matches take priority over a same-document match in an earlier window.
    ('com.microsoft.edgemac', [['https://docs.google.com/document/d/id/edit?authuser=1'], ['https://docs.google.com/document/d/id/edit']], 'https://docs.google.com/document/d/id/edit', 'https://docs.google.com/document/d/id', [1, 0]),
    ('com.brave.Browser', [['https://docs.google.com/document/d/id-long/edit', None], ['https://docs.google.com/document/d/id/edit?authuser=2']], 'https://docs.google.com/document/d/id', 'https://docs.google.com/document/d/id', [1, 0]),
    ('com.apple.Safari', [['https://example.com/other', 'https://example.com/target']], 'https://example.com/target', '', [0, 1]),
    ('com.google.Chrome', [['https://docs.google.com/document/d/id-long/edit']], 'https://docs.google.com/document/d/id', 'https://docs.google.com/document/d/id', None),
    ('com.google.Chrome', [['https://example.com/target/other']], 'https://example.com/target', '', None),
    ('org.mozilla.firefox', [['https://example.com/target']], 'https://example.com/target', '', None),
])
def test_browser_tab_search_and_focus(bundle, windows, target, prefix, expected):
    setup = {'bundle': bundle, 'windows': windows, 'target': target, 'prefix': prefix}
    result = _run_node('const fixture = ' + json.dumps(setup) + ';\n' + r'''
const actions = [];
const windows = fixture.windows.map((urls, wi) => {
  const tabs = urls.map((url, ti) => ({url:()=>url, ti}));
  return {tabs:()=>tabs,
    set activeTabIndex(value){actions.push(['tab', wi, value-1])},
    set currentTab(value){actions.push(['tab', wi, value.ti])},
    set index(value){actions.push(['front', wi, value])},
    set minimized(value){actions.push(['restore', wi, value])},
    set miniaturized(value){actions.push(['restore', wi, value])}};
});
const app = {running:()=>true, windows:()=>windows, activate:()=>actions.push(['activate'])};
const ObjC = {import(){}, unwrap:value=>value};
const $ = {NSWorkspace:{sharedWorkspace:{URLForApplicationToOpenURL:()=>({path:'/Applications/Browser.app'})}},
  NSURL:{URLWithString:value=>value}, NSBundle:{bundleWithURL:()=>({bundleIdentifier:fixture.bundle})}};
const Application = ()=>app;
''' + browser_tabs.SCRIPT + r'''
console.log(JSON.stringify({result:JSON.parse(run([fixture.target, fixture.prefix])), actions}));
''')
    assert result['result'] == {'handled': expected is not None, 'reused': expected is not None}
    if expected is None:
        assert result['actions'] == []
    else:
        assert result['actions'] == [
            ['tab', *expected], ['restore', expected[0], False], ['front', expected[0], 1], ['activate'],
        ]


def test_browser_script_treats_url_as_data(monkeypatch):
    url = 'https://example.com/?q=";$(touch%20bad)`whoami`&next=1#part'
    calls = []
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, '{"handled":true,"reused":true}\n')
    monkeypatch.setattr(browser_tabs.subprocess, 'run', run)
    assert browser_tabs.focus_existing(url)
    argv, kwargs = calls[0]
    assert argv == ['/usr/bin/osascript', '-l', 'JavaScript', '-e', browser_tabs.SCRIPT, '--', url, '']
    assert url not in browser_tabs.SCRIPT
    assert not kwargs.get('shell')
    assert kwargs['timeout'] == 6


@pytest.mark.parametrize('result', ['not json', '{}', '{"handled":"true"}', '[]'])
def test_invalid_automation_result_is_reported(monkeypatch, result):
    monkeypatch.setattr(browser_tabs.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess([], 0, result))
    with pytest.raises(ValueError):
        browser_tabs.focus_existing('https://example.com/')
