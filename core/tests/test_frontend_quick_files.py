from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "core/src/core/static/js/lab-app.js"


def run_picker(script: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for file picker tests")
    source = SOURCE.read_text()
    extensions = source[source.index("function _sidebarFileExtension("):
                        source.index("function _sidebarRememberAvailableExtensions(")]
    accepted = source[source.index("function _sidebarRecentTypeAllowed("):
                      source.index("function _sidebarRecentFiles(")]
    helpers = source[source.index("let _quickFilePicker = null;"):
                     source.index("function openWorkspaceDocFromFileClick(")]
    result = subprocess.run(
        [node, "-e", HARNESS + extensions + accepted + helpers + "\n(async () => {\n" + script + "\n})()"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


HARNESS = """
let currentWorkspace = {path: '/vault-a/workspaces/demo'};
let currentRepo = null, _repoFileRoot = null;
let folderRoot = '/projects/demo', worktreeFolder = '/branches';
let availableRoot = '/branches/feature', showWorkspaceDotFiles = true;
const _sidebarFileConfig = {selectedWorktrees: {'/projects/demo': '/branches/feature'}};
function _sidebarWorktreeBaseRoot() { return currentRepo || currentWorkspace?.path || ''; }
function _sidebarWorkspaceRoot() { return folderRoot; }
function _sidebarActiveWorktreeFolder() { return worktreeFolder; }
function _sidebarScopedRoot() { return availableRoot; }
async function _sidebarEnsureWorktrees() {}
const opens = [], requests = [], cancellations = [];
async function openWorkspaceDoc(path, options) { opens.push({path, root: options.root}); }
async function openWorkspaceFile(path) { opens.push({path, root: _repoFileRoot, repo: true}); }
function _termCancelPendingLinkedFileOpen() { cancellations.push(true); }
let fetchFiles = async () => [{path: 'README.md', type: 'file'}];
async function fetch(url, options) {
  requests.push({url, signal: options.signal});
  return {ok: true, json: fetchFiles};
}
function element() {
  const children = new Map();
  return {value: '', textContent: '', innerHTML: '', listeners: {},
    setAttribute() {}, removeAttribute() {}, focus() {}, select() {},
    addEventListener(name, callback) { this.listeners[name] = callback; },
    querySelector(selector) {
      if (!children.has(selector)) children.set(selector, element());
      return children.get(selector);
    },
    querySelectorAll() { return []; },
    showModal() {}, close() {}, remove() {},
  };
}
const keyListeners = [];
const document = {
  body: {appendChild() {}}, createElement: element,
  addEventListener(name, handler, capture) { keyListeners.push({name, handler, capture}); },
};
const window = {};
const esc = text => String(text), escAttr = esc, fileIconHtml = () => '';
"""


def test_filter_matches_names_and_paths_case_insensitively() -> None:
    result = run_picker("""
const files = [
  {path: 'readme/other.md'}, {path: 'docs/README.md'}, {path: 'README-draft.md'},
  {path: 'src/test/README.md'}, {path: 'src/utils.js'},
  {path: 'README-folder', type: 'dir'}, {path: 'README-broken', broken: true},
];
process.stdout.write(JSON.stringify({
  names: _quickFileMatches(files, 'README.md').map(file => file.path),
  paths: _quickFileMatches(files, 'SRC readme').map(file => file.path),
  all: _quickFileMatches(files, ' ').map(file => file.path),
  empty: _quickFileMatches(files, 'missing'),
}));
""")
    assert result["names"] == ["docs/README.md", "src/test/README.md"]
    assert result["paths"] == ["src/test/README.md"]
    assert len(result["all"]) == 5
    assert result["empty"] == []


def test_recently_updated_formats_sort_first_then_newest_modified() -> None:
    result = run_picker("""
_sidebarFileConfig.trackMode = 'extensions';
_sidebarFileConfig.extensions = ['md', 'ipynb'];
const files = [
  {path: 'report.txt', mtime: 100},
  {path: 'old-report.md', mtime: 10},
  {path: 'new-report.IPYNB', mtime: 30},
  {path: 'middle-report.md', mtime: 20},
  {path: 'unknown-report.md'},
  {path: 'broken-time-report.txt', mtime: 'not-a-number'},
  {path: 'report.csv', mtime: 90},
];
files.forEach(file => file.git_tracked = true);
const preferred = _quickFileMatches(files, '').map(file => file.path);
const filtered = _quickFileMatches(files, 'report').map(file => file.path);
_sidebarFileConfig.extensions = ['csv'];
const changedFormats = _quickFileMatches(files, '').map(file => file.path);
_sidebarFileConfig.trackMode = 'all';
const allFormats = _quickFileMatches(files, '').map(file => file.path);
process.stdout.write(JSON.stringify({preferred, filtered, changedFormats, allFormats}));
""")
    assert result["preferred"] == result["filtered"] == [
        "new-report.IPYNB", "middle-report.md", "old-report.md", "unknown-report.md",
        "report.txt", "report.csv", "broken-time-report.txt",
    ]
    assert result["changedFormats"][:3] == ["report.csv", "report.txt", "new-report.IPYNB"]
    assert result["allFormats"] == [
        "report.txt", "report.csv", "new-report.IPYNB", "middle-report.md",
        "old-report.md", "broken-time-report.txt", "unknown-report.md",
    ]


@pytest.mark.parametrize("repository", [False, True])
def test_search_and_open_keep_the_selected_worktree(repository: bool) -> None:
    result = run_picker(f"currentRepo = {'folderRoot' if repository else 'null'};\n" + """
const before = JSON.stringify(_quickFileScope());
await openQuickFilePicker();
await _quickFileOpenResult(0);
process.stdout.write(JSON.stringify({opens, cancelled: cancellations.length,
  unchanged: before === JSON.stringify(_quickFileScope()),
  root: new URL(requests[0].url, 'http://lab').searchParams.get('path'),
  hidden: new URL(requests[0].url, 'http://lab').searchParams.get('include_dotfiles'),
  closed: _quickFilePicker === null,
}));
""")
    expected = {"path": "README.md", "root": "/branches/feature"}
    if repository:
        expected["repo"] = True
    assert result["opens"] == [expected]
    assert result["root"] == "/branches/feature"
    assert result["hidden"] == "true"
    assert result["unchanged"] and result["closed"]
    assert result["cancelled"] == 1


@pytest.mark.parametrize("change", [
    "currentWorkspace = {path: '/vault-b/workspaces/demo'};",
    "folderRoot = '/projects/other';",
    "_sidebarFileConfig.selectedWorktrees[folderRoot] = '/branches/other';",
    "currentRepo = '/projects/other';",
])
def test_stale_result_cannot_open_after_context_changes(change: str) -> None:
    result = run_picker("await openQuickFilePicker();\n" + change + """
await _quickFileOpenResult(0);
process.stdout.write(JSON.stringify({opens, closed: _quickFilePicker === null}));
""")
    assert result == {"opens": [], "closed": True}


def test_main_folder_and_unavailable_worktree_do_not_fall_back_to_other_roots() -> None:
    result = run_picker("""
availableRoot = folderRoot;
await openQuickFilePicker();
const unavailable = {error: _quickFilePicker.error, requests: requests.length};
_quickFileClose();
_sidebarFileConfig.selectedWorktrees = {};
await openQuickFilePicker();
await _quickFileOpenResult(0);
process.stdout.write(JSON.stringify({unavailable, opens}));
""")
    assert "unavailable" in result["unavailable"]["error"]
    assert result["unavailable"]["requests"] == 0
    assert result["opens"] == [{"path": "README.md", "root": "/projects/demo"}]


def test_closed_request_cannot_replace_a_new_search() -> None:
    result = run_picker("""
let finishOld;
fetchFiles = () => new Promise(resolve => { finishOld = resolve; });
const oldSearch = openQuickFilePicker();
await new Promise(resolve => setImmediate(resolve));
_quickFileClose();
_sidebarFileConfig.selectedWorktrees[folderRoot] = availableRoot = '/branches/other';
fetchFiles = async () => [{path: 'other.md'}];
await openQuickFilePicker();
finishOld([{path: 'stale.md'}]);
await oldSearch;
process.stdout.write(JSON.stringify({
  files: _quickFilePicker.matches.map(file => file.path),
  root: _quickFilePicker.scope.root, aborted: requests[0].signal.aborted,
}));
""")
    assert result == {"files": ["other.md"], "root": "/branches/other", "aborted": True}


def test_loading_failure_is_visible_and_has_no_openable_results() -> None:
    result = run_picker("""
fetchFiles = async () => { throw new Error('Connection lost'); };
await openQuickFilePicker();
await _quickFileOpenResult(0);
process.stdout.write(JSON.stringify({status: _quickFilePicker.status.textContent, opens}));
""")
    assert result == {"status": "Connection lost", "opens": []}


def test_command_and_control_k_capture_the_shortcut_from_editors() -> None:
    result = run_picker("""
const events = [];
openQuickFilePicker = async () => { events.push('open'); };
for (const modifier of ['metaKey', 'ctrlKey']) {
  keyListeners[0].handler({key: 'k', [modifier]: true,
    target: {tagName: 'TEXTAREA'},
    preventDefault() { events.push('prevent'); },
    stopImmediatePropagation() { events.push('stop'); },
  });
}
keyListeners[0].handler({key: 'k'});
process.stdout.write(JSON.stringify({events, capture: keyListeners[0].capture}));
""")
    assert result == {"events": ["prevent", "stop", "open"] * 2, "capture": True}
