"""Optional navigation tracing must preserve call and promise behavior."""
from pathlib import Path
import subprocess
import sys

import pytest

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


def test_refresh_stress_delivers_once_only_to_its_original_navigation():
    result = _run_node(r'''
(async()=>{
  const {installNavigationRefreshStress}=await import('./scripts/perf/navigation_refresh_probe.mjs');
  const vm=require('vm'),assert=require('assert/strict');
  const root='/tmp/lab-navigation-owned/vault/workspaces',timers=[],calls=[];
  let evaluations=0;
  await assert.rejects(()=>installNavigationRefreshStress(()=>evaluations++,'/not/a/fixture',20),/disposable fixture/);
  for(const delay of [0,-1,1.5,1001,NaN])await assert.rejects(()=>installNavigationRefreshStress(()=>evaluations++,root,delay),/delay must/);
  assert.equal(evaluations,0);
  const promise=Promise.resolve();
  const context={root,promise,calls,performance:{now:()=>10},setTimeout:(fn,delay)=>{assert.equal(delay,20);timers.push(fn);}};
  context.window=context;vm.createContext(context);
  vm.runInContext(`let currentWorkspace={path:root+'/alpha'},_workspaceInfoSequence=0,selectedRoot=null;
    const _sidebarScopedRoot=path=>selectedRoot||path;
    let showWorkspaceInfo=options=>{_workspaceInfoSequence++;calls.push(options);return promise;};`,context);
  await installNavigationRefreshStress(code=>vm.runInContext(code,context),root,20);
  assert.equal(vm.runInContext('showWorkspaceInfo({keepShell:true})',context),promise);
  timers.shift()();assert.equal(calls.length,2);assert.equal(timers.length,0);
  assert.equal(calls[1].backgroundRefresh,true);
  for(const change of ['currentWorkspace={path:root+"/beta"}','selectedRoot="/worktree"','_workspaceInfoSequence++']) {
    vm.runInContext('currentWorkspace={path:root+"/alpha"};selectedRoot=null;showWorkspaceInfo({keepShell:true});'+change,context);
    const before=calls.length;timers.shift()();assert.equal(calls.length,before);
  }
  vm.runInContext('currentWorkspace={path:"/user/vault/workspace"};showWorkspaceInfo({});',context);
  assert.equal(timers.length,0);
  const trace=context.__navigationRefreshStress();
  process.stdout.write(JSON.stringify({count:trace.events.length,delivered:trace.events.filter(event=>event.delivered).length,delay:trace.delayMs}));
})().catch(error=>{console.error(error);process.exitCode=1;});
''')
    assert result == {'count': 4, 'delivered': 1, 'delay': 20}


def test_refresh_stress_coverage_keeps_missed_and_late_deliveries():
    result = _run_node(r'''
(async()=>{
  const {navigationRefreshCoverage}=await import('./scripts/perf/navigation_refresh_probe.mjs');
  const rows=Array.from({length:5},(_,i)=>({sample:i+1,kind:'workspace',target:'alpha',clock:{source:i*100},ms:50}));
  rows.push({sample:6,kind:'document'});
  const events=[
    {path:'/fixture/alpha',started:1,finished:20,delivered:true},
    {path:'/fixture/alpha',started:101,finished:120,delivered:false},
    {path:'/fixture/alpha',started:201,finished:251,delivered:true},
    {path:'/fixture/beta',started:301,finished:320,delivered:true},
    {path:'/fixture/alpha',started:400,finished:450,delivered:true},
  ];
  process.stdout.write(JSON.stringify(navigationRefreshCoverage(rows,events,'/fixture')));
})().catch(error=>{console.error(error);process.exitCode=1;});
''')
    assert result == [{'sample': i, 'delivered': int(i in (1, 5))} for i in range(1, 6)]


@pytest.mark.parametrize('arguments, message', [
    (['--navigation-refresh-delay', '0'], 'between 1 and 1000'),
    (['--navigation-refresh-delay', '1001'], 'between 1 and 1000'),
    (['--navigation-refresh-delay', '20', '--document-edit'], 'standalone navigation'),
    (['--navigation-refresh-delay', '20', '--typing'], 'standalone navigation'),
])
def test_refresh_stress_rejects_invalid_workflows_before_fixture_creation(arguments, message):
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, str(root / 'scripts/perf/lab_navigation_latency.py'), *arguments],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert message in result.stderr
