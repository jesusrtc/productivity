"""Terminal failures must retain independent CPU/trace output and coverage."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_terminal_diagnostics_export_once_and_keep_other_outputs_after_failure():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required')
    script = r'''
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=await readFile(PROBE,'utf8');
const start=source.indexOf('  let traceActive=false,profileActive=false,diagnostics,traceStartedEpoch;');
const end=source.indexOf('  const sent=[], phases=[]',start);
assert.ok(start>=0 && end>start);
const build=new Function('client','writeFile','process','setTimeout','clearTimeout',source.slice(start,end)+`
  return {finishDiagnostics,activate(trace,cpu){traceActive=trace;profileActive=cpu;traceStartedEpoch=123;}};
`);
for(const failure of [null,'profile','stream']) {
  const calls=[],files=new Map(),timers=[],cleared=[];
  let reads=0;
  const client={
    once(method){assert.equal(method,'Tracing.tracingComplete');return Promise.resolve({stream:'owned-stream',dataLossOccurred:false});},
    async send(method,params){
      calls.push([method,params]);
      if(method==='Profiler.stop'){
        if(failure==='profile')throw Error('profile failed');
        return {profile:{samples:[1,2]}};
      }
      if(method==='IO.read'){
        assert.equal(params.handle,'owned-stream');
        if(failure==='stream')throw Error('stream failed');
        return ++reads===1?{data:'{"traceEvents":',eof:false}:{data:'[]}',eof:true};
      }
      return {};
    }
  };
  const probe=build(client,async(path,data)=>files.set(path,JSON.parse(data)),
    {env:{LAB_PERF_CPU_PROFILE:'cpu',LAB_PERF_TRACE:'trace',LAB_PERF_TRACE_CATEGORIES:'devtools.timeline'}},
    (callback,ms)=>{assert.equal(ms,15000);timers.push(callback);return timers.length;},
    id=>cleared.push(id));
  probe.activate(true,true);
  const first=probe.finishDiagnostics(),second=probe.finishDiagnostics();
  assert.equal(first,second,'normal and exception cleanup share one export');
  const errors=await first;
  assert.deepEqual(errors,failure?[`Error: ${failure} failed`]:[]);
  assert.equal(calls.filter(([m])=>m==='Profiler.stop').length,1);
  assert.equal(calls.filter(([m])=>m==='Tracing.end').length,1);
  assert.equal(calls.filter(([m])=>m==='IO.close').length,1,'close the stream after failed reads too');
  assert.deepEqual(cleared,[1]);
  if(failure!=='profile')assert.deepEqual(files.get('cpu'),{samples:[1,2]});
  if(failure!=='stream') {
    assert.deepEqual(files.get('trace'),{traceEvents:[]});
    const metadata=files.get('trace.metadata.json');
    assert.equal(metadata.startedEpoch,123);assert.ok(metadata.endedEpoch>=123);
    assert.equal(metadata.categories,'devtools.timeline');
    assert.equal(metadata.completion.dataLossOccurred,false);
  }
}
const disabled=build({send(){throw Error('disabled diagnostics must not call CDP');}},
  ()=>{throw Error('disabled diagnostics must not write');},{env:{}},setTimeout,clearTimeout);
assert.deepEqual(await disabled.finishDiagnostics(),[]);
// Both the normal result and thrown-workload path await the same exporter.
assert.equal((source.match(/const diagnosticsErrors=await finishDiagnostics\(\);/g)||[]).length,2);
assert.match(source,/catch\(error\) \{\s*const diagnosticsErrors=await finishDiagnostics\(\);/);
console.log('PASS');
'''.replace('PROBE', json.dumps(str(ROOT / 'scripts/perf/lab_terminal_interactive_latency.mjs')))
    result = subprocess.run([node, '--input-type=module', '-e', script],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'PASS'
