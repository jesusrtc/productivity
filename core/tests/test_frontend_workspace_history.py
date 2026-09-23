"""Workspace history captures the outgoing view and keeps resource ownership."""
from .test_frontend_terminal_ui import _js_between, _run_node


def test_history_captures_the_old_view_before_teardown_and_preserves_navigation():
    result = _run_node(r'''
const assert=require('node:assert/strict');
const a={path:'/one/workspaces/same',name:'same',vault:'one'};
const b={...a,path:'/two/workspaces/same',vault:'two'};
let currentWorkspace=a,currentRepo='/old-repo',currentRepoInWorkspace={},_workspaceDeleteTarget={path:a.path};
let workspacesList=[a,b],reads=0;
const calls=[],snapshots=[],classes=new Set(['workspace-active','has-diff-tabs']);
const document={body:{classList:{contains:key=>classes.has(key),remove:(...keys)=>keys.forEach(key=>classes.delete(key))}},
  getElementById:()=>({style:{}})};
const window={location:new URL('http://127.0.0.1/?workspace=old&repo=old&view=assistant&path=old&file=x&tail=1&vault=one&subview=notes&custom=keep#anchor'),
  AssistantView:{closeDocument(updateHistory){assert.equal(updateHistory,false);calls.push(['close',currentWorkspace?.path]);}}};
const closeVaultWorkspaceMenu=()=>calls.push(['menu',currentWorkspace?.path]);
const _termHomeViewActive=()=>false;
const termDetach=soft=>{assert.equal(soft,true);calls.push(['park',currentWorkspace?.path,currentWorkspace?.vault]);};
const history={pushState(state,title,url){
  snapshots.push({workspace:currentWorkspace?.path,classes:[...classes],state,title});
  window.location=new URL(url,window.location);
}};
const selectRepo=path=>{
  assert.equal(currentWorkspace,null,'previous workspace clears before selection');
  currentWorkspace=workspacesList.find(row=>row.path===path);classes.add('workspace-active');
  calls.push(['select',path]);
};
const fetchRepos=async()=>{reads++;return [a,b];};
''' + _js_between('  function _swapViewState(', '  // Navigate to a real workspace')
        + _js_between('  function goToWorkspace(path', '  // Navigate to a workspace by its id') + r'''
(async()=>{
  goToWorkspace(b.path);
  assert.deepEqual(snapshots,[{workspace:a.path,classes:['workspace-active','has-diff-tabs'],
    state:{nav:'workspace',path:b.path},title:''}]);
  assert.deepEqual(calls,[['menu',a.path],['close',a.path],['park',a.path,'one'],['select',b.path]]);
  assert.equal(window.location.search,'?workspace=%2Ftwo%2Fworkspaces%2Fsame&custom=keep');
  assert.equal(window.location.hash,'#anchor');
  assert.equal(_workspaceDeleteTarget,null);
  assert.equal(currentRepo,null);assert.equal(currentRepoInWorkspace,null);
  window.location=new URL('http://127.0.0.1/?workspace='+encodeURIComponent(a.path));
  goToWorkspace(a.path,{replace:true,deleteTarget:{path:b.path}});
  assert.equal(snapshots.length,1);assert.equal(currentWorkspace,a);
  assert.equal(_workspaceDeleteTarget,null);
  assert(calls.some(row=>row[0]==='park'&&row[1]===b.path&&row[2]==='two'));
  const target={path:b.path,id:'same',vault:'two'};
  goToWorkspace(b.path,{deleteTarget:target});
  assert.equal(_workspaceDeleteTarget,target);
  const count=calls.length;goToWorkspace('');assert.equal(calls.length,count);
  workspacesList=[];
  goToWorkspace(a.path);
  assert.equal(currentWorkspace,null);
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(reads,1);assert.equal(currentWorkspace,a);
  assert.equal(snapshots.length,3);
  console.log(JSON.stringify({passed:true,historyEntries:snapshots.length,catalogReads:reads}));
})().catch(error=>{console.error(error);process.exitCode=1;});
''')
    assert result == {'passed': True, 'historyEntries': 3, 'catalogReads': 1}
