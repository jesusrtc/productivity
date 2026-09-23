"""Dashboard reads overlap rendering and cannot overwrite newer navigation."""
import pytest
from .test_frontend_terminal_ui import _js_between, _run_node


@pytest.mark.parametrize('background', [False, True])
@pytest.mark.parametrize('outcome', ['success', 'error', 'document', 'workspace'])
def test_dashboard_overlaps_sidebar_and_keeps_latest_owner(outcome, background):
    function = _js_between('  let _workspaceInfoSequence =', '  // ─── Theme + Settings')
    result = _run_node(r'''
let currentWorkspace={path:'/alpha',name:'alpha',is_workspace:true,repos:[]};
let currentRepo=null, _workspaceDocPath=null;
const _sidebarScopedRoot=path=>path;
const content={innerHTML:'original',scrollTop:0};
const document={getElementById:()=>content,title:''};
const _setWorkspaceDisplayName=()=>{},workspaceTabsRender=()=>{};
const esc=String,escAttr=String;
const requests=[],errors=[],sidebarOptions=[];
process.on('unhandledRejection',error=>errors.push(String(error)));
let finishSidebar,finishOld,rejectOld, sidebarReady;
const blocked=new Promise(r=>sidebarReady=r);
const sidebarGate=new Promise(r=>finishSidebar=r);
const oldInfo=new Promise((ok,fail)=>{finishOld=ok;rejectOld=fail});
let round=0;
const _refreshWorkspaceSidebar=async options=>{
 round++;sidebarOptions.push(options.backgroundRefresh);
 options._beforeRender();options._beforeRender();
 if(round===1){sidebarReady();await sidebarGate;}
};
const info=title=>({id:'alpha',name:title,status:'active',created:'today',updated:'today'});
const fetch=async url=>{
 requests.push({round,url});
 if(url.includes('/api/workspace-info'))return {json:()=>round===1?oldInfo:Promise.resolve(info('Latest'))};
 if(url.includes('/api/workspace-onepager'))return {json:async()=>({content:''})};
 return {json:async()=>[]};
};
''' + function + r'''
(async()=>{
 const old=showWorkspaceInfo({keepShell:true,backgroundRefresh:BACKGROUND});await blocked;
 const beforeRender=requests.length;
 finishSidebar();await new Promise(r=>setTimeout(r,0));
 const outcome=OUTCOME;
 if(outcome==='document'){_workspaceDocPath='docs/open.md';content.innerHTML='Document';rejectOld(Error('Old failure'));}
 else if(outcome==='workspace'){currentWorkspace={path:'/beta',is_workspace:true};content.innerHTML='Beta';rejectOld(Error('Old failure'));}
 else{
   await showWorkspaceInfo({keepShell:true});
   if(outcome==='error')rejectOld(Error('Old failure'));
   else finishOld(info('Obsolete'));
 }
 await old;await new Promise(r=>setTimeout(r,0));
 console.log(JSON.stringify({sidebarOptions,beforeRender,requests:requests.length,errors,html:content.innerHTML,title:document.title}));
})();
'''.replace('OUTCOME', repr(outcome)).replace('BACKGROUND', str(background).lower()))
    assert result['sidebarOptions'][0] is background
    assert all(option is False for option in result['sidebarOptions'][1:])
    assert result['beforeRender'] == 5  # one batch, even if callback fires twice
    assert result['errors'] == []
    if outcome in {'success', 'error'}:
        assert result['requests'] == 10
        assert 'Latest' in result['html'] and 'Obsolete' not in result['html']
        assert result['title'] == 'Latest'
    else:
        assert result['html'] == ('Document' if outcome == 'document' else 'Beta')


@pytest.mark.parametrize('change', ['none', 'first-error', 'workspace', 'worktree', 'newer', 'revisit', 'document'])
def test_background_refresh_waits_for_navigation_then_reads_fresh_once(change):
    function = _js_between('  let _workspaceInfoSequence =', '  // ─── Theme + Settings')
    result = _run_node(r'''
const assert=require('assert/strict');
let currentWorkspace={path:'/alpha',name:'alpha',is_workspace:true,repos:[]};
let currentRepo=null,_workspaceDocPath=null,selectedRoot=null;
const _sidebarScopedRoot=path=>selectedRoot||path;
const content={innerHTML:'original',scrollTop:42};
const document={getElementById:()=>content,title:''};
const _setWorkspaceDisplayName=()=>{},workspaceTabsRender=()=>{};
const esc=String,escAttr=String,requests=[],sidebarOptions=[],errors=[];
process.on('unhandledRejection',error=>errors.push(String(error)));
let finishSidebar,finishInitial,rejectInitial,finishFresh;
const sidebarGate=new Promise(resolve=>finishSidebar=resolve);
const initialInfo=new Promise((resolve,reject)=>{finishInitial=resolve;rejectInitial=reject;});
const freshInfo=new Promise(resolve=>finishFresh=resolve);
let round=0;
const _refreshWorkspaceSidebar=async options=>{
  const thisRound=++round;sidebarOptions.push({...options});
  options._beforeRender();options._beforeRender();
  if(thisRound===1)await sidebarGate;
};
const info=title=>({id:'alpha',name:title,status:'active',created:'today',updated:'today'});
const fetch=async url=>{
  const thisRound=round;requests.push({round:thisRound,url});
  if(url.includes('/api/workspace-info'))return {json:()=>thisRound===1?initialInfo:sidebarOptions[thisRound-1].backgroundRefresh?freshInfo:Promise.resolve(info('Newer '+thisRound))};
  if(url.includes('/api/workspace-onepager'))return {json:async()=>({content:''})};
  return {json:async()=>[]};
};
const settle=()=>new Promise(resolve=>setImmediate(resolve));
''' + function + r'''
(async()=>{
  const navigation=showWorkspaceInfo({keepShell:true});
  const eventOptions={backgroundRefresh:true,preserveScroll:true};
  const updates=[showWorkspaceInfo(eventOptions),showWorkspaceInfo({...eventOptions,keepShell:true}),showWorkspaceInfo(eventOptions)];
  assert.equal(requests.length,5,'background events must not restart in-flight navigation');
  // Every background caller shares completion of one fresh follow-up.
  assert.equal(updates[0],updates[1]);assert.equal(updates[0],updates[2]);
  eventOptions.preserveScroll=false;
  finishSidebar();await settle();
  assert.equal(requests.length,5,'navigation still owns its pending dashboard data');
  const change=CHANGE;
  if(change==='workspace'){currentWorkspace={path:'/beta',is_workspace:true};content.innerHTML='Beta';}
  if(change==='worktree')selectedRoot='/alpha/worktree';
  if(change==='newer')await showWorkspaceInfo({keepShell:true});
  if(change==='revisit'){
    currentWorkspace={path:'/beta',name:'beta',is_workspace:true,repos:[]};await showWorkspaceInfo({keepShell:true});
    currentWorkspace={path:'/alpha',name:'alpha',is_workspace:true,repos:[]};await showWorkspaceInfo({keepShell:true});
  }
  if(change==='document'){_workspaceDocPath='docs/open.md';content.innerHTML='Document';}
  if(change==='first-error')rejectInitial(Error('Initial failed'));else finishInitial(info('Initial'));
  await navigation;await settle();
  const beforeFresh={html:content.innerHTML,requests:requests.length,round};
  finishFresh(info('Fresh'));await Promise.all(updates);await settle();
  console.log(JSON.stringify({beforeFresh,html:content.innerHTML,scroll:content.scrollTop,requests:requests.length,sidebarOptions:sidebarOptions.map(({backgroundRefresh,preserveScroll})=>({backgroundRefresh,preserveScroll})),errors,pending:!!_workspaceInfoNavigation}));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''.replace('CHANGE', repr(change)))
    assert not result['errors'] and not result['pending']
    assert result['scroll'] == 42
    if change in {'none', 'first-error', 'document'}:
        assert result['requests'] == 10
        assert result['sidebarOptions'] == [
            {'backgroundRefresh': False, 'preserveScroll': False},
            {'backgroundRefresh': True, 'preserveScroll': True},
        ]
        if change == 'document':
            assert result['beforeFresh']['html'] == result['html'] == 'Document'
        else:
            assert ('Initial' if change == 'none' else 'Initial failed') in result['beforeFresh']['html']
            assert 'Fresh' in result['html'] and 'Initial' not in result['html']
    elif change in {'workspace', 'worktree'}:
        assert result['requests'] == 5
        if change == 'workspace':
            assert result['html'] == 'Beta'
    else:
        assert result['requests'] == (10 if change == 'newer' else 15)
        assert ('Newer 2' if change == 'newer' else 'Newer 3') in result['html']
        assert all(not options['backgroundRefresh'] for options in result['sidebarOptions'])


def test_old_navigation_completion_cannot_clear_newer_pending_navigation():
    wrapper = _js_between('  let _workspaceInfoSequence =', '  async function _loadWorkspaceInfo(')
    result = _run_node(r'''
const assert=require('assert/strict');
let currentWorkspace={path:'/alpha',is_workspace:true};
const _sidebarScopedRoot=path=>path,loads=[],release=[];
const _loadWorkspaceInfo=options=>{
  _workspaceInfoSequence++;
  loads.push({path:currentWorkspace.path,background:!!options.backgroundRefresh});
  return new Promise(resolve=>release.push(resolve));
};
''' + wrapper + r'''
(async()=>{
  const alpha=showWorkspaceInfo({});
  currentWorkspace={path:'/beta',is_workspace:true};
  const beta=showWorkspaceInfo({});
  const refresh=showWorkspaceInfo({backgroundRefresh:true,preserveScroll:true});
  release[0]();await alpha;
  assert.equal(loads.length,2);
  assert.equal(showWorkspaceInfo({backgroundRefresh:true,preserveScroll:true}),refresh);
  release[1]();await beta;await new Promise(resolve=>setImmediate(resolve));
  assert.equal(loads.length,3);release[2]();await refresh;
  console.log(JSON.stringify({loads,pending:!!_workspaceInfoNavigation}));
})().catch(error=>{console.error(error);process.exitCode=1;});
''')
    assert result == {'loads': [
        {'path': '/alpha', 'background': False},
        {'path': '/beta', 'background': False},
        {'path': '/beta', 'background': True},
    ], 'pending': False}


def test_background_refresh_does_not_queue_behind_an_already_obsolete_navigation():
    wrapper = _js_between('  let _workspaceInfoSequence =', '  async function _loadWorkspaceInfo(')
    result = _run_node(r'''
const assert=require('assert/strict');
let currentWorkspace={path:'/alpha',is_workspace:true},root='/alpha';
const _sidebarScopedRoot=()=>root,loads=[],release=[];
const _loadWorkspaceInfo=options=>{
  _workspaceInfoSequence++;
  loads.push({root,background:!!options.backgroundRefresh});
  return new Promise(resolve=>release.push(resolve));
};
''' + wrapper + r'''
(async()=>{
  const navigation=showWorkspaceInfo({});
  root='/alpha/worktree';const differentRoot=showWorkspaceInfo({backgroundRefresh:true});
  root='/alpha';const restoredRoot=showWorkspaceInfo({backgroundRefresh:true});
  assert.equal(loads.length,3,'an obsolete same-path owner must not swallow the latest event');
  release.forEach(resolve=>resolve());await Promise.all([navigation,differentRoot,restoredRoot]);
  console.log(JSON.stringify({loads,pending:!!_workspaceInfoNavigation}));
})().catch(error=>{console.error(error);process.exitCode=1;});
''')
    assert result == {'loads': [
        {'root': '/alpha', 'background': False},
        {'root': '/alpha/worktree', 'background': True},
        {'root': '/alpha', 'background': True},
    ], 'pending': False}
