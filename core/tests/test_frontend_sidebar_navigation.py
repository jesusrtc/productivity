"""Slow sidebar reads cannot overwrite a newer workspace or selected file root."""
import pytest
from .test_frontend_terminal_ui import _js_between, _run_node


@pytest.mark.parametrize('phase', ['worktrees', 'files', 'info'])
@pytest.mark.parametrize('change', ['workspace', 'newer', 'worktree'])
def test_slow_sidebar_response_keeps_latest_navigation(phase, change):
    refresh = _js_between('  async function _refreshWorkspaceSidebar(', '  function paintWorkspaceShell(')
    result = _run_node(r'''
const phase = PHASE, change = CHANGE;
let currentWorkspace = {path:'/alpha',name:'alpha',is_workspace:true};
let fileRoot = '/alpha', _workspaceDocRoot = null, _workspaceDocPath = null;
let _workspaceSidebarRefreshSequence = 0;
const _workspaceSidebarCache = new Map(), requests = [], paints = [], errors = [];
const sidebar = {scrollTop:0,children:[{}]};
const document = {getElementById:()=>sidebar,body:{classList:{contains:()=>false}}};
console.error = (...args)=>errors.push(args.join(' '));
let release, reached;
const blocked = new Promise(r=>reached=r), gate = new Promise(r=>release=r);
let pauseNext = true;
async function pause(where) {if (where === phase && pauseNext) {pauseNext=false;reached();await gate;}}
const _sidebarEnsureWorktrees = async ()=>pause('worktrees');
const _sidebarScopedRoot = ()=>fileRoot;
const _sidebarFetchWorkspaceFiles = async ()=>{await pause('files');return []};
const _sidebarResolveRecentFiles = async files=>files;
const fetch = async url=>{
  requests.push(url);
  const marker = String(requests.length);
  await pause('info');
  return {ok:true,json:async()=>({pinned:[marker]})};
};
const _rememberNotebookFolders = ()=>{}, _sidebarRememberAvailableExtensions = ()=>{};
const _sidebarMaybeLogRecentDiagnostics = ()=>{}, _sidebarFileConfigCogHtml = ()=>'';
const _sidebarRecentSelectorsHtml = ()=>'', _sidebarFileScopeButtonsHtml = ()=>'';
const _sidebarWorktreePickerHtml = ()=>'', symlinkLegendHtml = ()=>'';
const _sidebarWorktreeScopeStartHtml = ()=>'', _sidebarWorktreeScopeEndHtml = ()=>'';
const _sidebarRecentSectionHtml = ()=>'', _sidebarFilesTitle = ()=>'';
const _agentContextMetaHtml = ()=>'', _populateAgentContextMeta = ()=>{};
const renderRepoTabs = ()=>{}, _sidebarGitStatusRefresh = ()=>{};
const _replaceWorkspaceSidebarMarkup = (el,markup,scope)=>paints.push(scope);
''' .replace('PHASE', repr(phase)).replace('CHANGE', repr(change)) + refresh + r'''
(async()=>{
  const older = _refreshWorkspaceSidebar();
  await blocked;
  if(change === 'workspace') currentWorkspace = {path:'/beta',name:'beta',is_workspace:true};
  else if(change === 'worktree') fileRoot = '/trees/feature';
  else await _refreshWorkspaceSidebar();
  release();
  await older;
  await new Promise(r=>setTimeout(r,0));
  console.log(JSON.stringify({requests,paints,errors,cache:[..._workspaceSidebarCache]}));
})();
''')
    assert result['errors'] == []
    assert all('path=%2Falpha' in url for url in result['requests'])
    if change == 'newer':
        assert result['paints'] == ['/alpha']
        assert result['cache'][0][1]['pinned'] == [str(len(result['requests']))]
    elif change == 'worktree' and phase == 'worktrees':
        # Worktree discovery resolves the selected root after its await.
        assert result['paints'] == ['/alpha']
        assert result['cache'][0][1]['fileRoot'] == '/trees/feature'
    else:
        assert result['paints'] == []
        assert result['cache'] == []
