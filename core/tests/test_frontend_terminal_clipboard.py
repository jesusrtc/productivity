"""Terminal file/folder identity, shell-safe drops, and clean selection copy."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / 'src/core/static/js/lab-app.js'
COPY_CASES = json.loads((Path(__file__).parent / 'fixtures/terminal-copy.json').read_text())


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
const paths = ['/vault one/tree/notes.md', "/repo/it's $(touch bad).txt", '/other worktree/folder with spaces/'];
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
    assert result['paths'] == ['/vault one/tree/notes.md', "/repo/it's $(touch bad).txt", '/other worktree/folder with spaces/']
    assert result['pastes'] == ["'/vault one/tree/notes.md' '/repo/it'\\''s $(touch bad).txt' '/other worktree/folder with spaces/'"]
    assert result['uri'] == ['/repo/hello world.md']
    assert result['remote'] == result['web'] == result['relative'] == result['injection'] == []
    assert len(result['notices']) == 2


def test_reference_drops_keep_urls_tabs_and_registry_targets_as_unsent_arguments():
    result = run(r'''
const pastes = [], notices = [];
const termXterm = {paste: text => pastes.push(text), focus() {}};
const termWS = {readyState: 1}, WebSocket = {OPEN: 1};
const _termDragState = null, workspaceTabsDragId = null;
const explorerToast = text => notices.push(text);
const data = values => ({types: Object.keys(values), getData: key => values[key] || ''});
const event = dataTransfer => ({dataTransfer, preventDefault() {}, stopPropagation() {}});
const references = ['/other vault/Notes.md#tab=child-id', '/workspace/.lab/objectives.json#objective=id&view=tasks', "https://example.com/path?q=one&other=$(bad)#it's-a-tab"];
_termHandleDrop(event(data({'application/x-lab-reference':JSON.stringify(references),'text/plain':'/wrong/current-workspace.md'})));
_termHandleDrop(event(data({'text/uri-list':'https://example.com/a?x=1&y=2'})));
_termHandleDrop(event(data({'text/plain':'https://example.com/b'})));
for(const value of ['javascript:alert(1)','relative.md','/repo/a\nwhoami','https://example.com/\nwhoami'])
  _termHandleDrop(event(data({'application/x-lab-reference':JSON.stringify([value]),'text/plain':'/fallback-must-not-paste'})));
_termHandleDrop(event(data({'application/x-lab-reference':'bad json','text/plain':'/fallback-must-not-paste'})));
_termHandleDrop(event(data({'text/uri-list':'file://remote/repo/a'})));
_termHandleDrop(event(data({'application/x-lab-terminal':'session','application/x-lab-reference':JSON.stringify(['/wrong'])})));
console.log(JSON.stringify({pastes,notices}));
''')
    assert result['pastes'] == [
        "'/other vault/Notes.md#tab=child-id' '/workspace/.lab/objectives.json#objective=id&view=tasks' 'https://example.com/path?q=one&other=$(bad)#it'\\''s-a-tab'",
        "'https://example.com/a?x=1&y=2'", 'https://example.com/b']
    assert result['notices'] == []


@pytest.mark.parametrize('bracketed', [True, False])
def test_task_drop_pastes_labelled_scope_prompt_and_keeps_invalid_context_out(bracketed):
    formatter = (APP.parent/'lib/task-context.js').read_text()
    result = run('globalThis.window={};\n'+formatter+'\nconst bracketed='+json.dumps(bracketed)+r''';
const pastes=[],notices=[],sends=[];
const termXterm={modes:{bracketedPasteMode:bracketed},paste:text=>pastes.push(text),focus(){}};
const termWS={readyState:1,send:data=>sends.push(data)},WebSocket={OPEN:1};
const _termDragState=null,workspaceTabsDragId=null;
const explorerToast=message=>notices.push(message);
const payload={version:1,objective:{title:'Recover SMS',purpose:'Restore verification',assets:[
  {title:'Volume analysis.ipynb',type:'Notebook',reference:'/project/volume analysis.ipynb'}]},
  parents:[{title:'Fix phone parsing',assets:[{title:'Tasks.md · Fix phone parsing',type:'Task specification',reference:'/project/Tasks.md#tab=parent'}]}],
  task:{title:'Verify recovery',assets:[{title:'Tasks.md · Verify recovery',type:'Task specification',reference:'/project/Tasks.md#tab=child'},
    {title:'Volume analysis.ipynb',type:'Notebook',reference:'/project/volume analysis.ipynb'},
    {title:'Feature checkout',type:'Worktree',reference:'/trees/feature'},
    {title:'Recovery report',type:'Sublink',reference:'https://example.com/report?tab=recovery'}]}};
const refs=window.LabTaskContext.references(payload),prompt=window.LabTaskContext.format(payload);
const drop=(model,references=refs)=>_termHandleDrop({dataTransfer:{types:['application/x-lab-task-context','application/x-lab-reference'],getData:key=>
  key==='application/x-lab-task-context'?JSON.stringify(model):key==='application/x-lab-reference'?JSON.stringify(references):''},preventDefault(){},stopPropagation(){}});
drop(payload);
drop({...payload,version:0});
drop(payload,refs.slice(1));
drop({...payload,task:{...payload.task,assets:[{title:'Invalid',type:'File',reference:'/file\nexecute'}]}});
termWS.readyState=3;drop(payload);
console.log(JSON.stringify({pastes,notices,sends,refs,prompt}));
''')
    prompt = result['prompt']
    assert prompt.startswith('Context:\nObjective: "Recover SMS"\nObjective outcome: Restore verification')
    assert 'Parent task: "Fix phone parsing"' in prompt
    assert 'This task: "Verify recovery"' in prompt
    assert 'Work only on This task: "Verify recovery"' in prompt
    assert 'Task specification: "Tasks.md · Verify recovery"' in prompt
    assert 'Notebook: "Volume analysis.ipynb"' in prompt
    assert 'Worktree: "Feature checkout"' in prompt and 'Sublink: "Recovery report"' in prompt
    assert 'read-only unless also listed under This task' in prompt
    assert 'same reference as above' in prompt
    for ref in result['refs']:
        assert sum(line.endswith(' — '+ref) for line in prompt.splitlines()) == 1
    assert result['pastes'] == [prompt if bracketed else prompt.replace('\n',' ')]
    assert result['sends'] == [] and len(result['notices']) == 4


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


@pytest.mark.parametrize('case', [case for case in COPY_CASES if case['name'] != 'native terminal wrapping'],
                         ids=lambda case: case['name'])
def test_reflow_application_wraps_without_changing_structured_content(case):
    result = run('console.log(JSON.stringify(_termCleanSelection('
                 + json.dumps(case['text']) + ', ' + str(case['cols']) + ')));')
    assert result == case['expected']


@pytest.mark.parametrize('objectives_enabled', [False, True])
def test_drag_uses_source_root_and_preserves_filename_whitespace(objectives_enabled):
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
const currentWorkspace = {path:'/active/workspace'};
''' + 'const window={LabObjectives:{active:()=>'+json.dumps(objectives_enabled)+'}};\n' + handler + r'''
const written = {};
const dataTransfer = {setData: (key, value) => written[key] = value};
handler({target:{closest: () => ({root:'/other vault/worktree/',path:'docs/ file.md ',kind:'file'})},dataTransfer});
written.effect = dataTransfer.effectAllowed;
console.log(JSON.stringify(written));
'''], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert json.loads(data['application/x-lab-file-path']) == ['/other vault/worktree/docs/ file.md ']
    assert data['text/plain'] == '/other vault/worktree/docs/ file.md '
    assert json.loads(data['application/x-lab-file-context']) == {'root':'/other vault/worktree/','path':'docs/ file.md ','kind':'file'}
    assert data['effect'] == ('copyLink' if objectives_enabled else 'copy')
