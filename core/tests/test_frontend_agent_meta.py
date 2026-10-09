"""Meta is instruction context, not a browser for shared skill mounts."""
from pathlib import Path
import json
import subprocess

from .test_frontend_project_cache import _check_project_html

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
    helpers = source[source.index('  function _agentContextSource('):source.index('  async function openAgentContext(')]
    highlight = source[source.index('    // Match both root and path:'):source.index('    // preserveScroll early-return:')]
    script = r'''
const esc = value => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;');
const escAttr = value => esc(value).replaceAll('"', '&quot;');
const fileIconHtml = () => '', symlinkClass = () => '', symlinkTitle = () => '';
let _workspaceDocRoot = '/workspace', _workspaceDocPath = 'AGENTS.md';
const currentWorkspace = null, _vaultForWorkspace = () => null;
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
    helper = source[source.index('  function _agentContextSourceFromRow('):source.index('  function _agentInstructionRowsHtml(')]
    helper += source[source.index('  async function openAgentContext('):source.index('  window.openAgentContext =')]
    script = r'''
const nodes = Object.fromEntries(['docViewModal', 'docModalBody', 'docModalTitle', 'docModalFiles'].map(id => [id,
  {innerHTML: '', textContent: '', querySelector: () => ({}), classList: {add() {}, contains: () => true}}]));
const document = {querySelector: () => null, getElementById: id => nodes[id], addEventListener() {}, removeEventListener() {}};
let _workspaceDocEditing = true, _docModalEscHandler = null, _docModalFilesGeneration = 0;
const closeDocModal = () => {};
const esc = value => value.replaceAll('<', '&lt;').replaceAll('>', '&gt;');
const escAttr = esc;
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


def test_project_workspaces_expose_context_and_drop_its_full_text_in_chrome(tmp_path):
    source = SOURCE.read_text()
    def section(start, end):
        at = source.index(start)
        return source[at:source.index(end, at)]
    helpers = section('  function _sidebarProjectView(', '  function _sidebarProjectOwnsView(')
    helpers += section('  function _sidebarFilesTitle(', '  function _explorerContextFromRow(')
    helpers += section('  function _sidebarRecentSectionHtml(', '  function _sidebarConfigFolderCardHtml(')
    helpers += section('  function _agentContextSource(', '  // ─── Keep Alive and Lid Awake')
    helpers += section("  document.addEventListener('dragstart', event => {", '  function _termReflowSelection(')
    setup = r'''
const assert=(ok,message)=>{if(!ok)throw Error(message)};
let now=100000;Date.now=()=>now;
let base='/workspace-one',folder='/tree-one',vault='/vault-one',objectiveRoot=base+'/objectives/first',currentRepo=null,currentWorkspace={name:'one',path:base,is_workspace:true};
const VAULT_ROOT='/shell-vault',_vaultForWorkspace=()=>({path:vault,id:vault.slice(1)});
const _sidebarWorktreeBaseRoot=()=>base,_sidebarScopedRoot=()=>folder,_sidebarScopeTransition=null;
let _sidebarProjectTimer=1,_sidebarProjectGeneration=0;
const _sidebarMarkPainted=()=>{},_sidebarProjectDirectory=host=>{host.innerHTML='<a class="sidebar-file" data-entry-kind="file">File one</a><a class="sidebar-file" data-entry-kind="file">File two</a>'};
const _sidebarProjectRecent=view=>{view.querySelector('[data-project-recent]').innerHTML=['/one','/two'].map(root=>_sidebarRecentSectionHtml([{path:'updated.md'}],null,root,{resolved:true})).join('')};
const _sidebarFileScopeButtonsHtml=()=>'<section data-objectives-sidebar></section>',_sidebarRecentSelectorsHtml=()=>'<div class="sidebar-recent-selectors"></div>';
const _sidebarFileConfigCogHtml=()=>'',_sidebarWorktreePickerHtml=()=>'';
const _canCreateExecutableNotebook=()=>false,_sidebarSortSelectHtml=()=>'',_sidebarScanStates=new Map(),_sidebarScanLabel=()=>'';
const _sidebarRecentTreeModel=files=>({folders:[],files}),symlinkClass=()=>'',symlinkTitle=()=>'',symlinkMarker=()=>'',_sidebarGitHistoryButtonHtml=()=>'';
const esc=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),escAttr=value=>esc(value).replaceAll('"','&quot;').replaceAll("'",'&#39;');
const fileIconHtml=()=>'<span class="ft-icon ft-md"></span>';
window.LabObjectives={active:()=>true,instructionRoot:()=>objectiveRoot,terminalLaunchContext:()=>({id:objectiveRoot.split('/').at(-1),context:{path:base}})};
let _workspaceDocEditing=false,_docModalEscHandler=null,_docModalFilesGeneration=0,_workspaceDocRoot=base,_workspaceDocPath=null;
const opened=[];window.openWorkspaceDoc=(path,{root})=>opened.push({root,path});
window.openWorkspaceDocModal=()=>{};
const closeDocModal=()=>document.getElementById('docViewModal').classList.remove('active');
const guide='# Lab framework capabilities\n\nUse `lab` for tasks & notebooks.\n<instructions>\n';
let reads=0,guideRequests=[];
window.fetch=async url=>{
 if(url.startsWith('/api/agents/context/files?'))return {ok:true,json:async()=>[{name:'AGENTS.md',path:'AGENTS.md'}]};
 reads++;return {ok:true,json:async()=>({content:guide})};
};
let _termDragState=null,workspaceTabsDragId=null,termCurrentSession='one',termCurrentWorkspaceId='one';
const pastes=[],notices=[],termXterm={modes:{bracketedPasteMode:true},paste:text=>pastes.push(text),focus(){}};
const termWS={readyState:WebSocket.OPEN},explorerToast=(...args)=>notices.push(args);
(async()=>{try{
 for(const suffix of ['one','two']){
  base='/workspace-'+suffix;folder='/tree-'+suffix;vault='/vault-'+suffix;objectiveRoot=base+'/objectives/first';currentWorkspace.path=base;currentWorkspace.name=suffix;
  assert(_sidebarProjectView(base,folder),'project sidebar mounts');
  await new Promise(resolve=>setTimeout(resolve,0));
  assert(document.querySelectorAll('#sidebar [data-lab-agent-context]').length===1,'each workspace has one draggable Lab context item');
  for(const [scope,root] of [['Vault',vault],['Workspace',base],['Objective',objectiveRoot]]){
   const row=document.querySelector(`[data-agent-instructions-scope="${scope}"] a`);
   assert(row?.textContent===scope+' AGENTS.md'&&row.dataset.entryRoot===root,'scoped instruction links retain the owning roots');
   row.click();assert(opened.at(-1).path==='AGENTS.md'&&opened.at(-1).root===root,'instruction click opens the correct file');
  }
  assert(document.querySelector('[data-agent-instructions-root="'+folder+'"] a'),'selected worktree instructions stay separate');
 }
 const scopedView=document.querySelector('[data-project-sidebar]'),oldObjectiveRoot=objectiveRoot;
 objectiveRoot=base+'/objectives/second';_sidebarProjectAgentContext(scopedView,base,folder);
 await new Promise(resolve=>setTimeout(resolve,0));
 assert(document.querySelector('[data-agent-instructions-scope="Objective"] a').dataset.entryRoot===objectiveRoot&&!document.querySelector('[data-agent-instructions-root="'+oldObjectiveRoot+'"]'),'Objective switches update instructions even when Files keeps the same worktree');
 window.fetch=async()=>({ok:true,json:async()=>[{name:'AGENTS.md',path:'AGENTS.md',broken:true}]});
 await _populateAgentContextMeta(scopedView.querySelector('[data-project-agent-context]'));
 assert([...document.querySelectorAll('[data-agent-instructions-scope]:not([data-agent-instructions-scope=""])')].every(slot=>!slot.textContent.trim()),'missing instruction files and broken links have no scoped shortcut or placeholder');
 window.fetch=async()=>({ok:true,json:async()=>[{name:'AGENTS.md',path:'AGENTS.md'}]});
 now+=5000;_sidebarProjectAgentContext(scopedView,base,folder);
 await new Promise(resolve=>setTimeout(resolve,0));
 assert(document.querySelectorAll('[data-agent-instructions-scope] a').length===4&&!document.querySelector('[data-agent-instructions-scope] [aria-disabled="true"]'),'newly created instruction files become clickable on the next refresh without switching roots');
 window.fetch=async url=>{reads++;guideRequests.push(new URL(url,'http://lab').searchParams);return {ok:true,json:async()=>({content:guide})};};
 const icons=()=>[...document.querySelectorAll('#sidebar [data-sidebar-section-shortcut]')].filter(row=>row.getClientRects().length);
 const project=document.querySelector('[data-project-sidebar]');project.dataset.objectiveSidebarMode='worktree';project.dataset.objectiveRecentScopes='2';
 assert(icons().length===2&&icons().map(row=>row.getAttribute('aria-label')).sort().join(',')==='Files,Recently updated','one Files icon and one icon for the entire two-worktree recent union');
 assert(![...document.querySelectorAll('#sidebar [data-entry-kind=file]:not(.sidebar-file-meta),#sidebar .sidebar-file-recent')].some(row=>row.getClientRects().length),'compact project view hides individual files in both lists');
 assert([...document.querySelectorAll('[data-agent-instructions-scope] .sidebar-file-meta')].every(row=>row.getClientRects().length),'instruction shortcuts remain visible in the compact sidebar');
 project.dataset.objectiveSidebarMode='task';assert(icons().length===1&&icons()[0].dataset.sidebarSectionShortcut==='recent','task mode keeps only the available recent list icon');
 project.dataset.objectiveRecentScopes='0';assert(icons().length===0,'empty task scopes do not leave an orphan recent icon');
 project.dataset.objectiveSidebarMode='worktree';project.dataset.objectiveRecentScopes='2';document.body.classList.add('sidebar-drawer-open');
 assert(icons().length===0&&[...document.querySelectorAll('#sidebar [data-entry-kind=file],#sidebar .sidebar-file-recent')].every(row=>row.getClientRects().length),'expanded project view restores all files from both checkouts');
 const transfer=new DataTransfer(),row=document.querySelector('#sidebar [data-lab-agent-context]');
 row.dispatchEvent(new DragEvent('dragstart',{bubbles:true,dataTransfer:transfer}));
 assert(transfer.getData('application/x-lab-agent-context')==='overview','context drag carries the full-content action');
 const captured=JSON.parse(transfer.getData('application/x-lab-agent-context-source')).source;
 assert(captured.path===folder&&captured.workspace_id==='two'&&captured.objective_id==='second'&&captured.vault==='vault-two','drag captures checkout and all owning scope identities');
 objectiveRoot=base+'/objectives/third';folder='/another-tree';
 const drop=()=>_termHandleDrop({dataTransfer:transfer,preventDefault(){},stopPropagation(){}});
 await drop();assert(pastes[0]===guide,'cold drag fetches and pastes exact context with line breaks, without Enter');
 assert(guideRequests[0].get('path')===captured.path&&guideRequests[0].get('objective_id')==='second','dropping after a scope switch fetches the captured source');
 await openAgentContext();
 assert(document.querySelector('#docModalBody pre').textContent===guide,'read view uses the same context content');
 const viewed=new DataTransfer();document.querySelector('#docModalBody [data-lab-agent-context]').dispatchEvent(new DragEvent('dragstart',{bubbles:true,dataTransfer:viewed}));
 await new Promise(resolve=>setTimeout(resolve,0));
 assert(viewed.getData('text/plain')===guide&&!document.getElementById('docViewModal').classList.contains('active'),'drag from reader exposes the terminal and carries the full text');
 termXterm.modes.bracketedPasteMode=false;await drop();
 assert(pastes[1]===guide.replace(/\n/g,' ')&&reads===1,'plain shell receives one unsent line and context requests are shared');
 _readAgentContextGuide.cache.clear();let release;
 window.fetch=()=>new Promise(resolve=>release=resolve);
 const pending=drop();termCurrentSession='elsewhere';release({ok:true,json:async()=>({content:guide})});await pending;
 assert(pastes.length===2,'a delayed context load cannot paste into a newly selected terminal');
 termCurrentSession='one';
 window.fetch=async url=>{guideRequests.push(new URL(url,'http://lab').searchParams);return {ok:true,json:async()=>({content:guide+'New scope'})};};
 _sidebarProjectAgentContext(scopedView,base,folder);await new Promise(resolve=>setTimeout(resolve,0));
 await openAgentContext();
 assert(guideRequests.at(-1).get('path')===folder&&guideRequests.at(-1).get('objective_id')==='third'&&document.querySelector('#docModalBody pre').textContent===guide+'New scope','a new Objective and checkout receive their own guide instead of a global cached copy');
 assert(!notices.length,'no context errors');document.body.dataset.result='pass';
}catch(error){document.body.dataset.result='fail';document.body.append(String(error.stack||error));}})();
'''
    css = (SOURCE.parents[1] / 'css/lab-shell.css').read_text() + (SOURCE.parents[1] / 'css/workspace-objectives.css').read_text()
    html = '<!doctype html><meta charset="utf-8"><style>'+css+'</style><body class="workspace-active sidebar-drawer-enabled"><aside id="sidebar" class="sidebar"></aside><div id="docViewModal"><div id="docModalTitle"></div><div id="docModalFiles"></div><div id="docModalBody"></div></div><script>'+helpers+setup+'</script>'
    _check_project_html(tmp_path, html)
