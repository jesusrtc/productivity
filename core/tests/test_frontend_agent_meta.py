"""Meta is instruction context, not a browser for shared skill mounts."""
from pathlib import Path
import json
import subprocess

SOURCE = Path(__file__).parents[1] / 'src/core/static/js/lab-app.js'


def test_meta_contains_context_and_workspace_instruction_documents_only():
    source = SOURCE.read_text()
    assert "const META_FILES = new Set(['AGENTS.md', 'CLAUDE.md', '.github/copilot-instructions.md'])" in source
    assert 'const metaFiles = otherFiles.filter(f => META_FILES.has(f.path))' in source
    assert 'const mainFiles = otherFiles.filter(f => !META_FILES.has(f.path))' in source
    assert 'Lab agent context' in source
    assert '_vaultProjectionMetaHtml' not in source
    assert '_populateSharedMetaPlaceholders' not in source
    assert 'renderSharedClaudeTree' not in source
    assert '.agents/skills", "mode": "symlink"' not in source
    # File actions carry the selected worktree root, rather than the workspace root.
    assert 'openWorkspaceDoc(${JSON.stringify(f.path)}, {root:${JSON.stringify(fileRoot)}})' in source


def test_context_view_displays_exact_escaped_launcher_context():
    source = SOURCE.read_text()
    helper = source[source.index('  async function openAgentContext()'):source.index('  window.openAgentContext =')]
    script = r'''
const nodes = Object.fromEntries(['docViewModal', 'docModalBody', 'docModalTitle'].map(id => [id,
  {innerHTML: '', textContent: '', classList: {add() {}}}]));
const document = {getElementById: id => nodes[id], addEventListener() {}, removeEventListener() {}};
let _workspaceDocEditing = true, _docModalEscHandler = null;
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
