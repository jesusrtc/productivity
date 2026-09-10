#!/usr/bin/env node
// Browser stage of lab_terminal_latency.py --browser; use that wrapper so the
// terminal is created and removed safely. Measures synthetic keyboard events
// through Lab, tmux, and xterm's render callback, then empty-page frame cadence.
// It does not measure physical keyboard hardware or display scanout.
// Optional LAB_PERF_CPU_PROFILE=/tmp/trace.cpuprofile enables CPU profiling.
import {spawn, execFileSync} from 'node:child_process';
import {mkdtemp, readFile, writeFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const baseUrl = (process.argv[2] || execFileSync('scripts/lab-url.sh', {encoding:'utf8'}).trim()).replace(/\/$/, '');
const chromePath = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
}

async function fetchJson(url, options = {}) {
  let lastErr = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await fetch(url, options);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${url}`);
      return res.json();
    } catch (err) {
      lastErr = err;
      await sleep(100);
    }
  }
  throw lastErr;
}

async function waitForChrome(port) {
  const url = `http://127.0.0.1:${port}/json/version`;
  const deadline = Date.now() + 10000;
  let lastErr = null;
  while (Date.now() < deadline) {
    try {
      return await fetchJson(url);
    } catch (err) {
      lastErr = err;
      await sleep(100);
    }
  }
  throw lastErr || new Error('timed out waiting for Chrome');
}

function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let nextId = 1;
  const pending = new Map();
  const listeners = new Map();

  ws.addEventListener('message', (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve: ok, reject, timer } = pending.get(msg.id);
      clearTimeout(timer);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(JSON.stringify(msg.error)));
      else ok(msg.result || {});
      return;
    }
    if (msg.method && listeners.has(msg.method)) {
      for (const fn of listeners.get(msg.method)) fn(msg.params || {});
    }
  });

  function send(method, params = {}) {
    const id = nextId++;
    ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolveSend, reject) => {
      const timer = setTimeout(() => {
        if (!pending.has(id)) return;
        pending.delete(id);
        reject(new Error(`CDP timeout: ${method}`));
      }, 15000);
      pending.set(id, { resolve: resolveSend, reject, timer });
    });
  }

  function once(method) {
    return new Promise((resolveOnce) => {
      const fn = (params) => {
        const arr = listeners.get(method) || [];
        listeners.set(method, arr.filter((x) => x !== fn));
        resolveOnce(params);
      };
      const arr = listeners.get(method) || [];
      arr.push(fn);
      listeners.set(method, arr);
    });
  }

  return new Promise((resolveConnect, reject) => {
    ws.addEventListener('open', () => resolveConnect({ ws, send, once }));
    ws.addEventListener('error', reject, { once: true });
  });
}

async function newPage(port) {
  const target = await fetchJson(`http://127.0.0.1:${port}/json/new`, { method: 'PUT' });
  const client = await connect(target.webSocketDebuggerUrl);
  await client.send('Page.enable');
  await client.send('Runtime.enable');
  await client.send('Network.enable');
  return { target, client };
}


async function main() {
  const name=process.argv[3], marker=process.argv[4];
  const samples=Number(process.argv[5] || 100);
  if(!Number.isInteger(samples) || samples<20)throw new Error("Requires at least 20 samples");
  if(!name || !marker) throw new Error('Requires an owned disposable test session and ready marker');
  const cookie=execFileSync('core/.venv/bin/python',['-c','from core import auth; print(auth.issue_session(auth.get_user("admin")))'],{encoding:'utf8'}).trim();
  const profile=await mkdtemp(join(tmpdir(),'lab-input-render-'));
  const port=9700+Math.floor(Math.random()*200);
  const chrome=spawn(chromePath,['--headless=new','--no-first-run','--disable-background-networking',`--remote-debugging-port=${port}`,`--user-data-dir=${profile}`,'about:blank'],{stdio:'ignore'});
  let client;
  try {
    await waitForChrome(port); ({client}=await newPage(port));
    await client.send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
    await client.send('Network.setCookie',{name:'lab_session',value:cookie,url:baseUrl,httpOnly:true,sameSite:'Strict'});
    await client.send('Page.navigate',{url:baseUrl+'/?view=productivity&ui_check=1'});
    const evaluate=async expression=>{
      const r=await client.send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
      if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);
      return r.result.value;
    };
    const readyUntil=Date.now()+15000;
    while(!await evaluate('typeof termAttach === "function"')) {
      if(Date.now()>readyUntil)throw new Error('Lab failed to load: '+await evaluate('location.href+" "+document.title'));
      await sleep(50);
    }
    await evaluate(`(async()=>{
      window.__resizeFrames=[];
      const originalSend=WebSocket.prototype.send;
      WebSocket.prototype.send=function(data){
        try{const m=JSON.parse(data);if(m.type==='resize')__resizeFrames.push([m.cols,m.rows]);}catch{}
        return originalSend.call(this,data);
      };
      document.body.classList.add('term-open');document.body.classList.remove('term-collapsed');
      termSessions=[{name:${JSON.stringify(name)},logical_name:'input-render-probe',kind:'terminal'}];
      await termAttach(${JSON.stringify(name)},_termActiveWorkspaceId());
      const deadline=performance.now()+12000;
      while(performance.now()<deadline){
        if(termXterm && termWS?.readyState===1){
          let text='';for(let i=0;i<termXterm.buffer.active.length;i++)text+=termXterm.buffer.active.getLine(i)?.translateToString(true)||'';
          if(text.includes(${JSON.stringify(marker)}))return;
        }
        await new Promise(r=>setTimeout(r,20));
      }
      throw new Error('Echo app not ready');
    })()`);
    if(process.env.LAB_PERF_CPU_PROFILE){
      await client.send('Profiler.enable');
      await client.send('Profiler.start');
    }
    const results=await evaluate(`(async()=>{
      const rows=[];const longtasks=[];
      const observer=new PerformanceObserver(list=>{for(const e of list.getEntries())longtasks.push({at:e.startTime,ms:e.duration});});
      observer.observe({type:'longtask',buffered:false});
      const rawWrite=termXterm.write.bind(termXterm);
      let pending=null;
      termXterm.write=(data,cb)=>{
        if(pending && data.includes(pending.char))pending.received=performance.now();
        return rawWrite(data,()=>{
          if(pending && pending.received && data.includes(pending.char))pending.parsed=performance.now();
          if(cb)cb();
        });
      };
      const listener=termXterm.onRender(()=>{
        if(pending?.parsed){
          const p=pending;pending=null;
          p.resolve({transport:p.received-p.start,parse:p.parsed-p.received,render:performance.now()-p.parsed,total:performance.now()-p.start});
        }
      });
      const input=termXterm.element.querySelector('textarea'); input.focus();
      for(let i=0;i<${samples};i++){
        const char=String.fromCharCode(97+i%26);
        const result=new Promise((resolve,reject)=>{
          const timer=setTimeout(()=>{pending=null;reject(new Error('Echo/render timed out'));},3000);
          pending={char,start:performance.now(),resolve:r=>{clearTimeout(timer);resolve(r);}};
        });
        input.dispatchEvent(new KeyboardEvent('keydown',{key:char,code:'Key'+char.toUpperCase(),keyCode:char.toUpperCase().charCodeAt(0),bubbles:true,cancelable:true}));
        input.dispatchEvent(new KeyboardEvent('keypress',{key:char,charCode:char.charCodeAt(0),keyCode:char.charCodeAt(0),bubbles:true,cancelable:true}));
        input.dispatchEvent(new KeyboardEvent('keyup',{key:char,code:'Key'+char.toUpperCase(),bubbles:true}));
        rows.push(await result);
        await new Promise(r=>setTimeout(r,25));
      }
      listener.dispose(); observer.disconnect();
      const stats={};
      for(const key of ['transport','parse','render','total']){
        const values=rows.map(r=>r[key]).sort((a,b)=>a-b);
        stats[key]={p50:values[Math.round((values.length-1)*.5)],p95:values[Math.round((values.length-1)*.95)],max:values[values.length-1]};
      }
      return {samples:rows.length,stats,webgl:!!termXterm._webglAddon,resizes:__resizeFrames,longtasks};
    })()`);
    if(process.env.LAB_PERF_CPU_PROFILE){
      const profileData=await client.send('Profiler.stop');
      await writeFile(process.env.LAB_PERF_CPU_PROFILE,JSON.stringify(profileData.profile));
    }
    await client.send('Page.navigate',{url:baseUrl+'/api/ping'});
    const controlDeadline=Date.now()+15000;
    while(!await evaluate('location.pathname === "/api/ping" && !document.getElementById("termPanel") && document.body.textContent.includes("status")')) {
      if(Date.now()>controlDeadline)throw new Error('Empty-page control did not load');
      await sleep(50);
    }
    results.emptyPageFrames=await evaluate(`(async()=>{
      const samples=[];let previous;
      for(let i=0;i<100;i++)await new Promise(resolve=>requestAnimationFrame(t=>{
        if(previous!==undefined)samples.push(t-previous);previous=t;resolve();
      }));
      samples.sort((a,b)=>a-b);return {p50:samples[49],p95:samples[94],max:samples[98]};
    })()`);
    console.log(JSON.stringify(results,null,2));
  } finally {
    if(client){await client.send('Page.close').catch(()=>{});client.ws.close();}
    if(chrome.exitCode===null){chrome.kill();await new Promise(r=>chrome.once('exit',r));}
    await rm(profile,{recursive:true,force:true}).catch(()=>{});
  }
}
main().catch(e=>{console.error(e);process.exitCode=1;});
