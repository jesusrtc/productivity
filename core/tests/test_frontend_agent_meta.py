"""Meta is instruction context, not a browser for shared skill mounts."""
from pathlib import Path
import json
import subprocess

SOURCE = Path(__file__).parents[1] / 'src/core/static/js/lab-app.js'


def test_meta_contains_context_and_workspace_instruction_documents_only():
    source = SOURCE.read_text()
    assert "const META_FILES = new Set(['AGENTS.md', 'CLAUDE.md', '.github/copilot-instructions.md'])" in source
    assert 'const mainFiles = otherFiles.filter(f => !META_FILES.has(f.path))' in source
    assert 'Lab agent context' in source
    assert '_vaultProjectionMetaHtml' not in source
    assert '_populateSharedMetaPlaceholders' not in source
    assert 'renderSharedClaudeTree' not in source
    assert '.agents/skills", "mode": "symlink"' not in source
    # File actions carry the selected worktree root, rather than the workspace root.
    assert 'openWorkspaceDoc(${JSON.stringify(f.path)}, {root:${JSON.stringify(root)}})' in source
    assert "isAssistant ? 'Assistant instructions' : 'Workspace instructions'" in source
    assert 'if (!isAssistant) sbHtml += _agentContextMetaHtml' not in source


def test_meta_keeps_workspace_and_selected_folder_independent():
    source = SOURCE.read_text()
    helpers = source[source.index('  function _agentContextMetaHtml('):source.index('  async function openAgentContext()')]
    highlight = source[source.index('    // Match both root and path:'):source.index('    // preserveScroll early-return:')]
    script = r'''
const esc = value => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;');
const escAttr = value => esc(value).replaceAll('"', '&quot;');
const fileIconHtml = () => '', symlinkClass = () => '', symlinkTitle = () => '';
let _workspaceDocRoot = '/workspace', _workspaceDocPath = 'AGENTS.md';
''' + helpers + r'''
(async () => {
  const base = '/workspace', folder = '/worktree';
  const initial = _agentContextMetaHtml(base, base, 'Assistant instructions');
  const selected = _agentContextMetaHtml(base, folder);
  const files = [{name: 'AGENTS.md', path: 'AGENTS.md'}];
  const baseRows = _agentInstructionRowsHtml(files, base);
  const folderRows = _agentInstructionRowsHtml(files, folder);
  const rows = [base, folder].map(root => ({dataset: {entryRoot: root}, active: true,
    classList: {remove() {rows.find(row => row.classList === this).active = false;},
      add() {rows.find(row => row.classList === this).active = true;}}}));
  const document = {querySelectorAll: () => rows}, CSS = {escape: value => value};
  const filepath = 'AGENTS.md', docRoot = base;
''' + highlight + r'''
  let finish;
  global.fetch = () => new Promise(resolve => {finish = resolve;});
  const slot = {dataset: {agentInstructionsRoot: base}, isConnected: true, innerHTML: 'original'};
  const pending = _populateAgentContextMeta({querySelectorAll: () => [slot]});
  slot.isConnected = false;
  finish({ok: true, json: async () => files});
  await pending;
  console.log(JSON.stringify({initial, selected, baseRows, folderRows,
    active: rows.map(row => row.active), stale: slot.innerHTML}));
})().catch(error => {console.error(error); process.exit(1);});
'''
    result = subprocess.run(['node', '-e', script], text=True, capture_output=True, check=True)
    data = json.loads(result.stdout)
    assert 'Lab agent context' in data['initial']
    assert data['initial'].count('data-agent-instructions-root=') == 1
    assert 'Assistant instructions' in data['initial']
    assert 'data-agent-instructions-root="/workspace"' in data['selected']
    assert 'data-agent-instructions-root="/worktree"' in data['selected']
    assert 'data-entry-root="/workspace"' in data['baseRows']
    assert 'data-entry-root="/worktree"' in data['folderRows']
    assert 'sidebar-file-meta active' in data['baseRows']
    assert 'sidebar-file-meta active' not in data['folderRows']
    assert data['stale'] == 'original'
    assert data['active'] == [True, False]


def test_context_view_displays_exact_escaped_launcher_context():
    source = SOURCE.read_text()
    helper = source[source.index('  async function openAgentContext()'):source.index('  window.openAgentContext =')]
    script = r'''
const nodes = Object.fromEntries(['docViewModal', 'docModalBody', 'docModalTitle', 'docModalFiles'].map(id => [id,
  {innerHTML: '', textContent: '', classList: {add() {}}}]));
const document = {getElementById: id => nodes[id], addEventListener() {}, removeEventListener() {}};
let _workspaceDocEditing = true, _docModalEscHandler = null, _docModalFilesGeneration = 0;
const closeDocModal = () => {};
const esc = value => value.replaceAll('<', '&lt;').replaceAll('>', '&gt;');
const fetch = async url => {
  if (url !== '/api/agents/context/guide') throw Error('wrong source');
  return {ok: true, json: async () => ({content: '# Actual launch context\n<instructions>'})};
};
''' + helper + r'''
(async () => {
  await openAgentContext();
  console.log(JSON.stringify({body: nodes.docModalBody.innerHTML,
    title: nodes.docModalTitle.textContent, editing: _workspaceDocEditing}));
})().catch(error => {console.error(error); process.exit(1);});
'''
    result = subprocess.run(['node', '-e', script], text=True, capture_output=True, check=True)
    data = json.loads(result.stdout)
    assert '# Actual launch context\n&lt;instructions&gt;' in data['body']
    assert data['title'] == 'Lab agent context'
    assert data['editing'] is False
