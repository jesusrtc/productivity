"""Detail benchmarks require owned resources and the actual terminal render."""
from pathlib import Path

import pytest

from .test_frontend_logging import _run_node


def test_terminal_fixture_rejects_unowned_paths_before_creating_resources(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'scripts/perf'))
    from assistant_terminal_fixture import assistant_terminal_fixture
    before = list(tmp_path.iterdir())
    with pytest.raises(ValueError, match='disposable navigation fixture'):
        with assistant_terminal_fixture(tmp_path / 'assistant'):
            pytest.fail('Accepted an unowned root')
    monkeypatch.setenv('LAB_HOME', str(tmp_path / 'user-config'))
    with pytest.raises(ValueError, match='fixture-owned'):
        with assistant_terminal_fixture(tmp_path / 'lab-navigation-owned' / 'assistant'):
            pytest.fail('Accepted user configuration')
    assert list(tmp_path.iterdir()) == before


@pytest.mark.parametrize('diagnostics', [False, True])
def test_terminal_observer_requires_visible_owned_marker_render_and_preserves_hook(diagnostics):
    result = _run_node(r'''
(async()=>{
  const {installAssistantTerminal}=await import('./scripts/perf/assistant_workload.mjs');
  const vm=require('vm'),assert=require('assert/strict'),calls=[];
  const marker='detail-123456abcdef',receiver={},returned={},failure=new Error('original failure');
  const diagnostics=__DIAGNOSTICS__;
  let host,callbacks=new Map(),parsed=new Map(),text='';
  const status={textContent:'Running',classList:{contains:()=>false}};
  const current={element:{closest:()=>true},buffer:{active:{viewportY:3,baseY:5,cursorY:1,cursorX:marker.length-1,
    getLine:row=>({translateToString:(trim,start,end)=>row===6?text.slice(start,end):''})}},
    onRender:callback=>callbacks.set(current,callback),onWriteParsed(callback){parsed.set(this,callback)}};
  const outside={...current,element:{closest:()=>false},onRender:callback=>callbacks.set(outside,callback)};
  host={hidden:false,contains:element=>element===current.element,querySelector:()=>status};
  const context={WeakRef,performance:{now:()=>42},document:{getElementById:()=>host},
    _termGuardViewportDisposal:function(...args){calls.push({receiver:this,args});if(args[0]==='fail')throw failure;return returned;}};
  context.window=context;vm.createContext(context);
  vm.runInContext(`(${installAssistantTerminal.toString()})(${JSON.stringify(marker)},${JSON.stringify({diagnostics})})`,context);
  const hook=context._termGuardViewportDisposal,observer=context.__assistantTerminal;
  assert.equal(hook.call(receiver,current,'extra'),returned);
  assert.equal(calls[0].receiver,receiver);assert.deepEqual(calls[0].args,[current,'extra']);
  if(diagnostics)parsed.get(current)();else assert.equal(parsed.size,0);
  assert.throws(()=>hook('fail'),error=>error===failure);
  assert(!observer.ready());
  hook(outside);text=marker;callbacks.get(outside)({start:0,end:20});
  assert(!observer.ready());assert.equal(observer.snapshot().records.length,0);
  text='wrong';callbacks.get(current)({start:3,end:3});assert(!observer.ready());
  text=marker;callbacks.get(current)({start:0,end:2});assert(!observer.ready());
  callbacks.get(current)({start:4,end:5});assert(!observer.ready());
  callbacks.get(current)({start:3,end:3});assert(observer.ready(),'right-margin marker in rendered cursor row');
  text='changed';assert(!observer.ready());text=marker;
  host.hidden=true;assert(!observer.ready());host.hidden=false;
  status.textContent='Starting';assert(!observer.ready());status.textContent='Running';
  status.classList.contains=()=>true;assert(!observer.ready());status.classList.contains=()=>false;
  const originalHost=host;host={...host,contains:()=>false};assert(!observer.ready());
  host=null;assert(!observer.ready());host=originalHost;
  const snapshot=observer.snapshot();
  assert(snapshot.ready);assert.equal(snapshot.records.length,1);
  assert.deepEqual(Object.keys(snapshot.records[0]).sort(),diagnostics
    ?['createdAt','dropped','renderAt','rendered','renders','stages']:['renderAt','rendered','renders']);
  if(diagnostics){
    const record=snapshot.records[0];assert.equal(record.createdAt,42);
    assert.equal(record.stages.length,5);assert.equal(record.stages[0].phase,'parse');assert(!record.stages[0].marker);
    assert(record.stages[2].marker && !record.stages[2].cursorRendered);
    assert(record.stages[4].marker && record.stages[4].cursorRendered);
    for(let i=0;i<1000;i++)parsed.get(current)();
    assert.equal(record.stages.length,1000);assert.equal(record.dropped,5);
  }
  process.stdout.write(JSON.stringify({ready:snapshot.ready,renders:snapshot.records[0].renders}));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''.replace('__DIAGNOSTICS__', str(diagnostics).lower()))
    assert result == {'ready': True, 'renders': 4}
