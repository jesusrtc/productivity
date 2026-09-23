"""Optional navigation tracing must preserve call and promise behavior."""
from .test_frontend_logging import _run_node


def test_refresh_trace_rejects_unowned_scope_and_preserves_results():
    result = _run_node(r'''
(async()=>{
  const {installNavigationRefreshProbe}=await import('./scripts/perf/navigation_refresh_probe.mjs');
  const vm=require('vm'),assert=require('assert/strict');
  let evaluations=0;
  for(const root of ['/vault/workspaces','/tmp/lab-navigation-owned/vault/workspaces/../workspaces']){
    await assert.rejects(()=>installNavigationRefreshProbe(()=>evaluations++,root),/disposable fixture/);
  }
  assert.equal(evaluations,0);
  const promise=Promise.resolve('done'),asyncError=new Error('async failure'),syncError=new Error('sync failure');
  const context={performance:{now:()=>1},promise,asyncError,syncError};context.window=context;
  vm.createContext(context);
  vm.runInContext(`
    let currentWorkspace={path:'/fixture'},_workspaceDocPath='doc.md',_workspaceInfoSequence=2,_workspaceSidebarRefreshSequence=3;
    let showWorkspaceInfo=function(options){this.received=options;return promise;};
    let _refreshWorkspaceSidebar=()=>Promise.reject(asyncError);
    let _sidebarFetchWorkspaceFiles=path=>path;
    let openWorkspaceDoc=()=>{throw syncError;};
    let renderWorkspaceDoc=()=>undefined;
  `,context);
  await installNavigationRefreshProbe(code=>vm.runInContext(code,context),'/tmp/lab-navigation-owned/vault/workspaces');
  assert.equal(vm.runInContext('showWorkspaceInfo({keepShell:true,secret:"not recorded"})',context),promise);
  await assert.rejects(vm.runInContext('_refreshWorkspaceSidebar({backgroundRefresh:true})',context),error=>error===asyncError);
  assert.throws(()=>vm.runInContext('openWorkspaceDoc("doc.md")',context),error=>error===syncError);
  assert.equal(vm.runInContext('_sidebarFetchWorkspaceFiles("/fixture")',context),'/fixture');
  assert.equal(vm.runInContext('renderWorkspaceDoc("doc.md",{id:"content"})',context),undefined);
  await promise;
  const trace=context.__navigationRefreshProbe();
  assert.equal(trace.events.length,10);
  assert.equal(trace.events.filter(row=>row.phase==='begin').length,5);
  assert.equal(trace.events.filter(row=>row.phase==='error').length,2);
  assert(!JSON.stringify(trace).includes('not recorded'));
  assert.equal(context.received.keepShell,true);
  for(const row of trace.events){assert.equal(row.workspace,'/fixture');assert.equal(row.doc,'doc.md');assert.equal(row.infoSequence,2);assert.equal(row.sidebarSequence,3);}
  vm.runInContext('for(let i=0;i<6000;i++)renderWorkspaceDoc("doc.md")',context);
  const bounded=context.__navigationRefreshProbe();
  process.stdout.write(JSON.stringify({events:trace.events.length,bounded:bounded.events.length,limitReached:bounded.limitReached}));
})().catch(error=>{console.error(error);process.exitCode=1;});
''')
    # Both snapshots refer to the bounded live event array.
    assert result == {'events': 10000, 'bounded': 10000, 'limitReached': True}
