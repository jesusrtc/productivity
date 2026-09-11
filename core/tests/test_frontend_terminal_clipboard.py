"""Terminal file identity, shell-safe drops, and clean selection copy."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / 'src/core/static/js/lab-app.js'


def helpers():
    source = APP.read_text()
    return source[source.index('  function _termDropPaths('):source.index('  function _termReadFileAsDataUrl(')]


def run(code):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required')
    result = subprocess.run([node, '-e', helpers() + code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_drop_preserves_exact_paths_quotes_shell_characters_and_never_submits():
    result = run(r'''
const pastes = [], notices = [];
const termXterm = {paste: text => pastes.push(text), focus() {}};
const termWS = {readyState: 1}, WebSocket = {OPEN: 1};
const _termDragState = null, workspaceTabsDragId = null;
const explorerToast = text => notices.push(text);
const paths = ['/vault one/tree/notes.md', "/repo/it's $(touch bad).txt"];
const data = values => ({types: Object.keys(values), getData: key => values[key] || ''});
const event = dataTransfer => ({dataTransfer, preventDefault() {}, stopPropagation() {}});
_termHandleDrop(event(data({'application/x-lab-file-path': JSON.stringify(paths)})));
_termHandleDrop(event({...data({}), files: [{name:'notes.md'}]}));
termWS.readyState = 3;
_termHandleDrop(event(data({'text/plain':'/another/file'})));
console.log(JSON.stringify({pastes, notices, paths: _termDropPaths(data({'application/x-lab-file-path':JSON.stringify(paths)})),
  uri: _termDropPaths(data({'text/uri-list':'# file\r\nfile:///repo/hello%20world.md'})),
  remote: _termDropPaths(data({'text/uri-list':'file://remote/repo/a'})),
  web: _termDropPaths(data({'text/uri-list':'https://example.com/a'})),
  relative: _termDropPaths(data({'text/plain':'notes.md'})),
  injection: _termDropPaths(data({'text/plain':'/repo/a\nwhoami'}))}));
''')
    assert result['paths'] == ['/vault one/tree/notes.md', "/repo/it's $(touch bad).txt"]
    assert result['pastes'] == ["'/vault one/tree/notes.md' '/repo/it'\\''s $(touch bad).txt'"]
    assert result['uri'] == ['/repo/hello world.md']
    assert result['remote'] == result['web'] == result['relative'] == result['injection'] == []
    assert len(result['notices']) == 2


@pytest.mark.parametrize('text,expected', [
    ('│ hello │\n│ world │', 'hello\nworld'),
    ('╭──────╮\n│ hello│\n╰──────╯', 'hello'),
    ('| hello |\n| world |', 'hello\nworld'),
    ('+-------+\n| hello |\n+-------+', 'hello'),
    ('│   indented\n│     code', '  indented\n    code'),
    ('echo one | cat\nprintf two | cat', 'echo one | cat\nprintf two | cat'),
    ('cat file |', 'cat file |'),
    ('| a | b |\n| -- | -- |', '| a | b |\n| -- | -- |'),
    ('| Column |\n| --- |\n| value |', '| Column |\n| --- |\n| value |'),
])
def test_clean_copy_removes_borders_without_changing_content(text, expected):
    assert run('console.log(JSON.stringify(_termCleanSelection(' + json.dumps(text) + ')));') == expected


def test_copy_overrides_xterm_and_empty_selection_keeps_native_copy():
    result = run(r'''
let selection = '│ echo one | cat │';
const termXterm = {getSelection: () => selection};
const calls = [];
const event = {clipboardData: {setData: (...args) => calls.push(args)},
  preventDefault: () => calls.push('prevent'), stopImmediatePropagation: () => calls.push('stop')};
_termHandleCopy(event);
selection = '';
_termHandleCopy(event);
console.log(JSON.stringify(calls));
''')
    assert result == [['text/plain', 'echo one | cat'], 'prevent', 'stop']


def test_drag_uses_source_root_and_preserves_filename_whitespace():
    source = APP.read_text()
    start = source.index("  document.addEventListener('dragstart', event => {")
    handler = source[start:source.index('  function _termDropPaths(', start)]
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required')
    result = subprocess.run([node, '-e', r'''
let handler;
const document = {addEventListener: (type, fn) => handler = fn};
const _explorerContextFromRow = row => row;
''' + handler + r'''
const written = {};
const dataTransfer = {setData: (key, value) => written[key] = value};
handler({target:{closest: () => ({root:'/other vault/worktree/',path:'docs/ file.md '})},dataTransfer});
console.log(JSON.stringify(written));
'''], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert json.loads(data['application/x-lab-file-path']) == ['/other vault/worktree/docs/ file.md ']
    assert data['text/plain'] == '/other vault/worktree/docs/ file.md '
