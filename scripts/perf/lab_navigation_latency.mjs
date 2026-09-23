#!/usr/bin/env node
// Browser stage of lab_navigation_latency.py; run the Python wrapper.
// Timestamped CDP mouse release -> rendered content -> animation-frame task.
// This is a browser paint opportunity estimate, not physical display latency.
import {spawn} from 'node:child_process';
import {mkdtemp, readFile, rm, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const baseUrl = process.argv[2];
if (!baseUrl || !process.env.LAB_PROBE_COOKIE || new URL(baseUrl).hostname !== '127.0.0.1') throw new Error('Run through lab_navigation_latency.py');
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
  const workspaceRoot=process.argv[3], samples=Number(process.argv[4] || 20);
  const profile=await mkdtemp(join(tmpdir(),'lab-navigation-chrome-'));
  const chrome=spawn(chromePath,['--headless=new','--no-first-run','--disable-background-networking','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{stdio:'ignore'});
  let client;
  const rows=[];
  try {
    // Let Chrome reserve its own free port; a random fixed-range choice can
    // collide with another local browser. Read only this fixture's profile.
    let port;
    const startupDeadline=Date.now()+10000;
    while(!port) {
      if(chrome.exitCode!==null)throw new Error('Chrome exited before opening DevTools: '+chrome.exitCode);
      try {port=Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split(/\s+/)[0]);}
      catch(error) {if(error.code!=='ENOENT')throw error;}
      if(!port) {
        if(Date.now()>startupDeadline)throw new Error('Chrome did not publish its DevTools port');
        await sleep(50);
      }
    }
    await waitForChrome(port); ({client}=await newPage(port));
    await client.send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
    const browserErrors=[], requestFailures=[], pendingRequests=new Map();
    client.ws.addEventListener('message', event=>{
      const msg=JSON.parse(event.data);
      if(msg.method==='Runtime.exceptionThrown')browserErrors.push(msg.params.exceptionDetails.text);
      if(msg.method==='Network.requestWillBeSent' && msg.params.request.url.startsWith(baseUrl+'/api/')) {
        pendingRequests.set(msg.params.requestId,new URL(msg.params.request.url).pathname);
      }
      if(msg.method==='Network.loadingFinished' || msg.method==='Network.loadingFailed') {
        if(msg.method==='Network.loadingFailed' && pendingRequests.has(msg.params.requestId)) {
          requestFailures.push({route:pendingRequests.get(msg.params.requestId),error:msg.params.errorText});
        }
        pendingRequests.delete(msg.params.requestId);
      }
    });
    await client.send('Network.setCookie',{name:'lab_session',value:process.env.LAB_PROBE_COOKIE,url:baseUrl,httpOnly:true,sameSite:'Strict'});
    const evaluate=async expression=>{
      const r=await client.send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
      if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);
      return r.result.value;
    };
    await client.send('Page.navigate',{url:baseUrl+'/?view=productivity'});
    const until=Date.now()+15000;
    while(!await evaluate('document.querySelectorAll(".workspace-tab[data-kind=workspace]").length === 2 && document.readyState === "complete"')) {
      if(Date.now()>until)throw new Error('Fixture UI did not load');
      await sleep(25);
    }
    // Start immediately: early user navigation must not inherit boot delays.
    // No ui_check, mocked fetch, disabled polling, or cache flush.
    await evaluate('performance.setResourceTimingBufferSize(10000)');
    if(process.env.LAB_PERF_CPU_PROFILE) {
      await client.send('Profiler.enable');
      await client.send('Profiler.start');
    }
    const actions=[];
    for(let i=0;i<samples;i++) {
      const name=i%2?'beta':'alpha';
      actions.push({kind:'workspace', target:name,
        selector:'.workspace-tab[data-workspace-id='+JSON.stringify(name)+']',
        ready:`document.querySelector('#content [data-workspace-display-title]')?.textContent === ${JSON.stringify(name==='alpha'?'Alpha':'Beta')}`});
    }
    const lastWorkspace=samples%2?'Alpha':'Beta';
    for(let i=0;i<samples;i++) {
      const number=i%2+1;
      actions.push({kind:'document', target:'review-'+number,
        selector:'.sidebar-file[data-filepath="docs/review-'+number+'.md"]',
        ready:`Array.from(document.querySelectorAll('#content h1')).some(h=>h.textContent === ${JSON.stringify(lastWorkspace+' review '+number)})`});
    }
    for(const [i,action] of actions.entries()) {
      const {selector}=action;
      const until=Date.now()+10000;
      while(!await evaluate(`!!document.querySelector(${JSON.stringify(selector)})`)) {
        if(Date.now()>until)throw new Error('Click target did not appear: '+selector);
        await sleep(10);
      }
      let sentEpoch;
      await evaluate(`(async()=>{
        let tab=document.querySelector(${JSON.stringify(selector)});
        if(tab.dataset.kind==='workspace' && !tab.dataset.key.startsWith(${JSON.stringify(workspaceRoot + '/')})) throw new Error('Unexpected fixture workspace');
        tab.scrollIntoView({block:'center'});
        // Scrolling can schedule layout and anchoring; target the settled row.
        await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
        // A normal sidebar reconcile may replace rows during the scroll.
        tab=document.querySelector(${JSON.stringify(selector)});
        if(!tab) throw new Error('Click target disappeared after scrolling');
        const rect=tab.getBoundingClientRect();
        const x=rect.x+rect.width/2, y=rect.y+rect.height/2;
        const hit=document.elementFromPoint(x,y);
        window.__probe={start:null,done:false,hitMatches:!!hit && tab.contains(hit),x,y};
        document.addEventListener('click',event=>{
          if(!event.target.closest(${JSON.stringify(selector)})) {
            __probe.error='Click reached another target: '+event.target.tagName+'.'+event.target.className;
            __probe.done=true;return;
          }
          __probe.start=event.timeStamp;
          __probe.sourceEpoch=performance.timeOrigin+event.timeStamp;
          __probe.queue=performance.now()-event.timeStamp;
          const check=()=>{
            if(${action.ready}) {
              requestAnimationFrame(()=>setTimeout(()=>{__probe.ms=performance.now()-__probe.start;__probe.done=true;},0));
            } else if(performance.now()-__probe.start>10000) { __probe.error='Content did not finish';__probe.done=true; }
            else requestAnimationFrame(check);
          };requestAnimationFrame(check);
        },{once:true,capture:true});
        return {x,y};
      })()`).then(async({x,y})=>{
        sentEpoch=Date.now();
        // A fast real click does not wait for the renderer to acknowledge
        // mouse-down before mouse-up arrives. Keep queued input measurable.
        await Promise.all([
          client.send('Input.dispatchMouseEvent',{type:'mousePressed',timestamp:sentEpoch/1000,x,y,button:'left',clickCount:1}),
          client.send('Input.dispatchMouseEvent',{type:'mouseReleased',timestamp:sentEpoch/1000,x,y,button:'left',clickCount:1}),
        ]);
      });
      const clickDeadline=Date.now()+12000;
      while(!await evaluate('__probe.done')) {
        if(Date.now()>clickDeadline)throw new Error('Click did not complete: '+selector+' '+JSON.stringify(await evaluate('__probe')));
        await sleep(10);
      }
      const row=await evaluate(`({...__probe,requests:performance.getEntriesByType('resource').filter(r=>r.startTime>=__probe.start && r.name.includes('/api/')).map(r=>({route:new URL(r.name).pathname,start:r.startTime-__probe.start,ms:r.duration}))})`);
      if(row.error)throw new Error(row.error);
      rows.push({sample:i+1,kind:action.kind,target:action.target,ms:row.ms,queue:row.queue,sourceEpoch:row.sourceEpoch,sentEpoch,requests:row.requests});
      if(Math.abs(row.sourceEpoch-sentEpoch)>2)throw new Error('Mouse event timestamp did not match dispatched source time');
      await sleep(100);
    }
    if(process.env.LAB_PERF_CPU_PROFILE) {
      const {profile}=await client.send('Profiler.stop');
      await writeFile(process.env.LAB_PERF_CPU_PROFILE,JSON.stringify(profile));
    }
    const stats={};
    for(const kind of ['workspace','document']) {
      const group=rows.filter(r=>r.kind===kind), times=group.map(r=>r.ms).sort((a,b)=>a-b);
      stats[kind]={samples:group.length,first:group[0].ms,p50:times[Math.floor(times.length*.5)],p95:times[Math.ceil(times.length*.95)-1],max:times.at(-1)};
    }
    const misses=rows.filter(r=>r.ms>=200);
    // Include API requests that finish after content paints, and startup work.
    const idleDeadline=Date.now()+5000;
    while(pendingRequests.size) {
      if(Date.now()>idleDeadline)throw new Error('API requests still pending: '+[...pendingRequests.values()].join(', '));
      await sleep(10);
    }
    const requests=await evaluate(`performance.getEntriesByType('resource').filter(r=>r.name.includes('/api/')).map(r=>({route:new URL(r.name).pathname,workspace:new URL(r.name).searchParams.get('workspace_id'),startEpoch:performance.timeOrigin+r.startTime,ms:r.duration,status:r.responseStatus}))`);
    const requestMisses=requests.filter(r=>r.ms>=200);
    const requestErrors=requests.filter(r=>r.status>=400);
    const fixture={extraFilesPerWorkspace:Number(process.env.LAB_PERF_EXTRA_FILES || 0),extraFileTypes:(process.env.LAB_PERF_EXTRA_FILE_TYPES || 'md').split(','),extraFileLayout:process.env.LAB_PERF_EXTRA_FILE_LAYOUT || 'folders'};
    console.log(JSON.stringify({fixture,stats,misses,requestMisses,requestErrors,requestFailures,browserErrors,requests,rows},null,2));
    if(misses.length || requestMisses.length || requestErrors.length || requestFailures.length || browserErrors.length)process.exitCode=1;
  } catch(error) {
    // A failed click must retain earlier samples, not erase the run's evidence.
    console.log(JSON.stringify({error:error.message,cause:String(error.cause||''),stack:error.stack,rows},null,2));
    process.exitCode=1;
  } finally {
    if(client){await client.send('Page.close').catch(()=>{});client.ws.close();}
    if(chrome.exitCode===null){chrome.kill();await new Promise(r=>chrome.once('exit',r));}
    await rm(profile,{recursive:true,force:true}).catch(()=>{});
  }
}
main().catch(e=>{console.error(e);process.exitCode=1;});
