"""Slow sidebar reads cannot overwrite a newer workspace or selected file root."""
import pytest
from .test_frontend_terminal_ui import _js_between, _run_node


_RENDER_STUBS = r'''
const _rememberNotebookFolders = ()=>{}, _sidebarRememberAvailableExtensions = ()=>{};
const _sidebarMaybeLogRecentDiagnostics = ()=>{}, _sidebarFileConfigCogHtml = ()=>'';
const _sidebarRecentSelectorsHtml = ()=>'', _sidebarFileScopeButtonsHtml = ()=>'';
const _sidebarWorktreePickerHtml = ()=>'', symlinkLegendHtml = ()=>'';
const _sidebarWorktreeScopeStartHtml = ()=>'', _sidebarWorktreeScopeEndHtml = ()=>'';
const _sidebarRecentSectionHtml = ()=>'', _sidebarFilesTitle = ()=>'';
const _agentContextMetaHtml = ()=>'', _populateAgentContextMeta = ()=>{};
const renderRepoTabs = ()=>{}, _sidebarGitStatusRefresh = ()=>{};
const _replaceWorkspaceSidebarMarkup = (el,markup,scope)=>paints.push(scope);
'''


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
''' .replace('PHASE', repr(phase)).replace('CHANGE', repr(change)) + _RENDER_STUBS + refresh + r'''
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


@pytest.mark.parametrize('background', [False, True])
@pytest.mark.parametrize('outcome', ['changed', 'equal', 'failure'])
@pytest.mark.parametrize('change', ['none', 'workspace', 'newer', 'worktree'])
def test_cached_refresh_renders_once_after_background_read(background, outcome, change):
    refresh = _js_between('  async function _refreshWorkspaceSidebar(', '  function paintWorkspaceShell(')
    result = _run_node(r'''
const background = BACKGROUND, outcome = OUTCOME, change = CHANGE;
let currentWorkspace = {path:'/alpha',name:'alpha',is_workspace:true};
let fileRoot = '/alpha', _workspaceDocRoot = null, _workspaceDocPath = null;
let _workspaceSidebarRefreshSequence = 0;
const cached = {files:[],recentFiles:[],pinned:[],references:[],proxies:[],fileRoot:'/alpha'};
const _workspaceSidebarCache = new Map([['/alpha',cached]]), paints = [], errors = [];
const sidebar = {scrollTop:17,children:[{}]};
const document = {getElementById:()=>sidebar,body:{classList:{contains:()=>false}}};
console.error = (...args)=>errors.push(args.join(' '));
let release, reached, beforeRender = 0, reading = 0;
const blocked = new Promise(r=>reached=r), gate = new Promise(r=>release=r);
const _sidebarEnsureWorktrees = async ()=>{};
const _sidebarScopedRoot = ()=>fileRoot;
const _sidebarFetchWorkspaceFiles = async ()=>{
  if (++reading === 1) {
    reached();await gate;
    if (outcome === 'failure') throw Error('Read failed');
  }
  return [];
};
const _sidebarResolveRecentFiles = async files=>files;
const fetch = async ()=>({ok:true,json:async()=>({pinned:outcome==='equal'?[]:['fresh']})});
'''.replace('BACKGROUND', str(background).lower()).replace('OUTCOME', repr(outcome)).replace('CHANGE', repr(change)) + _RENDER_STUBS + refresh + r'''
(async()=>{
  await _refreshWorkspaceSidebar({preserveScroll:true,backgroundRefresh:background,_beforeRender:()=>beforeRender++});
  await blocked;
  const before = paints.slice();
  if (change === 'workspace') currentWorkspace = {path:'/beta',name:'beta',is_workspace:true};
  else if (change === 'worktree') fileRoot = '/trees/feature';
  else if (change === 'newer') {
    await _refreshWorkspaceSidebar({preserveScroll:true,backgroundRefresh:true});
    await new Promise(r=>setTimeout(r,0));
  }
  const beforeRelease = paints.length;
  release();await new Promise(r=>setTimeout(r,0));
  console.log(JSON.stringify({before,beforeRelease,paints,beforeRender,errors,scrollTop:sidebar.scrollTop,cache:[..._workspaceSidebarCache]}));
})();
''')
    assert result['before'] == ([] if background else ['/alpha'])
    assert result['beforeRender'] == 1
    assert result['scrollTop'] == 17
    assert len(result['errors']) == (1 if outcome == 'failure' else 0)
    if change == 'none':
        # Equal data still gets one fresh render for selection, folder state and
        # expiring notebook markers. Failed reads fall back to the cached tree.
        assert result['paints'] == ['/alpha'] * (2 if not background and outcome == 'changed' else 1)
        assert result['cache'][0][1]['pinned'] == (['fresh'] if outcome == 'changed' else [])
    else:
        # An obsolete fresh response or fallback cannot paint over a later scope
        # or refresh, nor replace the newest cache payload.
        assert len(result['paints']) == result['beforeRelease']
        assert result['cache'][0][1]['pinned'] == (['fresh'] if change == 'newer' and outcome != 'equal' else [])
