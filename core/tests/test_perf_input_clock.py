"""Native latency clocks must retain queued input and reject bad timestamps."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'scripts/perf/input_clock.mjs'


def test_input_clock_validation_accounts_for_drift_without_changing_durations():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required')
    script = r'''
import assert from 'node:assert/strict';
import {validateInputClock} from HELPER;
for(const drift of [-10000,-2.9,0,0.4,2.9,10000]) {
  const clock={source:100,sourceEpoch:100000,handlerAt:180,wallEpoch:100080+drift,wallSampleEnd:180.1};
  const original=structuredClone(clock),sent=100000+drift;
  const check=validateInputClock(clock,sent);
  assert.equal(check.valid,true,'valid input with wall/monotonic offset '+drift);
  assert.ok(Math.abs(check.rawDeltaMs+drift)<0.001);
  assert.ok(Math.abs(check.mappedDeltaMs+0.05)<0.001);
  assert.deepEqual(clock,original,'validation must never rewrite measurements');
  assert.equal(clock.handlerAt-clock.source,80,'queued input remains over budget');
  for(const shift of [-500,-25,25,500])assert.equal(validateInputClock(clock,sent+shift).valid,false,'bad dispatch timestamp '+shift);
}
const good={source:100,sourceEpoch:100000,handlerAt:100.2,wallEpoch:100000,wallSampleEnd:100.3};
assert.equal(validateInputClock(good,100000).valid,true);
for(const key of Object.keys(good))for(const value of [undefined,null,NaN,Infinity,'100']) {
  assert.equal(validateInputClock({...good,[key]:value},100000).valid,false,'invalid '+key);
}
for(const sent of [undefined,null,NaN,Infinity,'100000'])assert.equal(validateInputClock(good,sent).valid,false);
assert.equal(validateInputClock(null,100000).valid,false);
assert.equal(validateInputClock({...good,wallSampleEnd:110},100000).valid,false,'uncertain clock bracket rejected');
assert.equal(validateInputClock({...good,wallSampleEnd:99},100000).valid,false,'backward clock bracket rejected');
console.log('PASS');
'''.replace('HELPER', json.dumps(HELPER.as_uri()))
    result = subprocess.run([node, '--input-type=module', '-e', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'PASS'


def test_input_clock_with_native_queued_keys_clicks_and_bad_timestamps(tmp_path):
    chrome = (os.environ.get('CHROME_BIN') or shutil.which('chromium')
              or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node required')
    script = r'''
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {captureInputClock,validateInputClock} from HELPER;
const port=(await readFile(process.argv[2]+'/DevToolsActivePort','utf8')).split(/\s+/)[0];
const target=await fetch('http://127.0.0.1:'+port+'/json/new?about:blank',{method:'PUT'}).then(r=>r.json());
const ws=new WebSocket(target.webSocketDebuggerUrl),pending=new Map();
let nextId=0,blockStarted;
ws.addEventListener('message',event=>{
  const message=JSON.parse(String(event.data));
  if(message.method==='Runtime.bindingCalled' && message.params.name==='blockStarted')blockStarted?.();
  const waiter=pending.get(message.id);if(!waiter)return;
  pending.delete(message.id);clearTimeout(waiter.timer);
  if(message.error)waiter.reject(Error(JSON.stringify(message.error)));else waiter.resolve(message.result);
});
await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true})});
const send=(method,params={})=>new Promise((resolve,reject)=>{
  const id=++nextId,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timed out: '+method))},5000);
  pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));
});
const evaluate=async expression=>{
  const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
};
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms)),results=[];
try {
  await send('Runtime.enable');await send('Runtime.addBinding',{name:'blockStarted'});
  await evaluate(`
    document.body.innerHTML='<input id="text"><button style="position:absolute;left:50px;top:55px;width:200px;height:50px">Click</button>';
    window.events=[];
    const captureInputClock=${captureInputClock.toString()};
    for(const type of ['keydown','mousedown','click'])document.addEventListener(type,event=>{
      const row={type,target:event.target.id,...captureInputClock(event)};events.push(row);
      requestAnimationFrame(()=>row.renderAt=performance.now());
    },true);
  `);
  async function sample(kind,busy=false,shift=0) {
    await evaluate('events=[];document.getElementById("text").focus()');
    if(busy) {
      let timer;
      const started=new Promise((resolve,reject)=>{blockStarted=resolve;timer=setTimeout(()=>reject(Error('Controlled renderer block did not start')),5000)});
      try {
        await evaluate('setTimeout(()=>{blockStarted("start");const end=performance.now()+250;while(performance.now()<end){}},20);true');
        await started;
      } finally {clearTimeout(timer);blockStarted=null;}
    }
    const sentEpoch=Date.now(),timestamp=(sentEpoch+shift)/1000;
    if(kind==='key')await Promise.all([
      send('Input.dispatchKeyEvent',{type:'keyDown',timestamp,key:'a',code:'KeyA',text:'a',unmodifiedText:'a',windowsVirtualKeyCode:65}),
      send('Input.dispatchKeyEvent',{type:'keyUp',timestamp,key:'a',code:'KeyA',windowsVirtualKeyCode:65}),
    ]);
    else await Promise.all([
      send('Input.dispatchMouseEvent',{type:'mousePressed',timestamp,x:100,y:80,button:'left',clickCount:1}),
      send('Input.dispatchMouseEvent',{type:'mouseReleased',timestamp,x:100,y:80,button:'left',clickCount:1}),
    ]);
    const deadline=Date.now()+5000;
    while(!await evaluate('events.length>0 && events.every(e=>Number.isFinite(e.renderAt))')) {
      assert.ok(Date.now()<deadline,'native input did not finish');await pause(10);
    }
    const rows=await evaluate('events');
    assert.deepEqual(rows.map(row=>row.type),kind==='key'?['keydown']:['mousedown','click']);
    for(const row of rows) {
      const check=validateInputClock(row,sentEpoch);
      assert.equal(check.valid,shift===0,JSON.stringify({row,sentEpoch,check}));
      if(busy) {
        assert.ok(row.handlerAt-row.source>=100,'main-thread queue delay was concealed');
        assert.ok(row.renderAt-row.source>=100,'render duration lost the queue delay');
      }
      if(kind==='key')assert.equal(row.target,'text','native key lost input focus');
      results.push({kind,busy,shift,queue:row.handlerAt-row.source,total:row.renderAt-row.source,check});
    }
  }
  await sample('key');await sample('key',true);
  await sample('mouse');await sample('mouse',true);
  await sample('key',false,-500);await sample('key',false,500);
  assert.equal(await evaluate('document.getElementById("text").value'),'aaaa','native keys were dropped');
  console.log(JSON.stringify(results));
} finally {await send('Page.close').catch(()=>{});ws.close();}
'''.replace('HELPER', json.dumps(HELPER.as_uri()))
    runner = tmp_path / 'input-clock.mjs'
    runner.write_text(script)
    profile = tmp_path / 'chrome'
    process = subprocess.Popen([
        chrome, '--headless', '--no-sandbox', '--no-first-run', '--disable-background-networking',
        '--user-data-dir=' + str(profile), '--remote-debugging-port=0', 'about:blank',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic() < deadline, 'Chrome did not start'
            time.sleep(.05)
        result = subprocess.run([node, str(runner), str(profile)], capture_output=True, text=True, timeout=25)
        (tmp_path / 'native-clock.json').write_text(result.stdout)
        assert result.returncode == 0, result.stderr
        assert len(json.loads(result.stdout)) == 8
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
