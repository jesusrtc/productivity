#!/usr/bin/env node
// Run through lab_navigation_latency.py --typing. A fresh, normally polling UI,
// an owned raw-echo terminal, CDP timestamps before dispatch, and exact rendered
// character matching. xterm onRender is not physical display scanout.
import {spawn} from 'node:child_process';
import {mkdtemp, readFile, rm, stat, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const [baseUrl,name,marker,sampleArg,workspace,intervalArg] = process.argv.slice(2);
const samples=Number(sampleArg), interval=Number(intervalArg)*1000;
const changeFiles=process.env.LAB_PERF_TYPING_UPDATES==='1';
if(!baseUrl || new URL(baseUrl).hostname!=='127.0.0.1' || !name || !marker || !workspace || !process.env.LAB_PROBE_COOKIE) throw new Error('Run through lab_navigation_latency.py --typing');
if(!Number.isInteger(samples) || samples<20 || !Number.isFinite(interval) || interval<0) throw new Error('Invalid samples/interval');
if(changeFiles && (!workspace.includes('/lab-navigation-') || !workspace.endsWith('/vault/workspaces/alpha')))throw new Error('File updates require the disposable navigation fixture');
const chromePath=process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
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
function stats(values) {
  const sorted=[...values].sort((a,b)=>a-b);
  return {samples:values.length,first:values[0],p50:sorted[Math.floor(sorted.length*.5)],p95:sorted[Math.ceil(sorted.length*.95)-1],max:sorted.at(-1)};
}
async function main() {
  const profile=await mkdtemp(join(tmpdir(),'lab-interactive-input-'));
  const chrome=spawn(chromePath,['--headless=new','--no-first-run','--disable-background-networking','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{stdio:'ignore'});
  let client,evaluate;
  const sent=[], phases=[], updates=[], browserErrors=[],requestFailures=[],pendingRequests=new Map();
  try {
    let port;
    const startupDeadline=Date.now()+10000;
    while(!port) {
      if(chrome.exitCode!==null)throw new Error('Chrome exited before DevTools: '+chrome.exitCode);
      try {port=Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split(/\s+/)[0]);}
      catch(error) {if(error.code!=='ENOENT')throw error;}
      if(!port) {
        if(Date.now()>startupDeadline)throw new Error('Chrome did not publish its DevTools port');
        await sleep(50);
      }
    }
    const browserVersion=await waitForChrome(port); ({client}=await newPage(port));
    await client.send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
    await client.send('Network.setCookie',{name:'lab_session',value:process.env.LAB_PROBE_COOKIE,url:baseUrl,httpOnly:true,sameSite:'Strict'});
    client.ws.addEventListener('message',event=>{
      const m=JSON.parse(event.data),p=m.params;
      if(m.method==='Runtime.exceptionThrown')browserErrors.push(p.exceptionDetails.exception?.description||p.exceptionDetails.text);
      if(m.method==='Network.requestWillBeSent' && p.request.url.startsWith(baseUrl+'/api/'))pendingRequests.set(p.requestId,new URL(p.request.url).pathname);
      if(m.method==='Network.loadingFinished' || m.method==='Network.loadingFailed') {
        if(m.method==='Network.loadingFailed' && pendingRequests.has(p.requestId))requestFailures.push({route:pendingRequests.get(p.requestId),error:p.errorText});
        pendingRequests.delete(p.requestId);
      }
    });
    evaluate=async expression=>{
      const r=await client.send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
      if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);
      return r.result.value;
    };
    const wait=async(expression,description)=>{
      const deadline=Date.now()+15000;
      while(!await evaluate(expression)) {
        if(Date.now()>deadline)throw new Error(description);
        await sleep(20);
      }
    };
    await client.send('Page.navigate',{url:baseUrl+'/?workspace='+encodeURIComponent(workspace)});
    await wait(`typeof termAttach==='function' && currentWorkspace?.path===${JSON.stringify(workspace)} && termSessions.some(s=>s.name===${JSON.stringify(name)})`,'Owned terminal did not appear in fixture UI');
    await evaluate(`(async()=>{
      performance.setResourceTimingBufferSize(10000);
      document.body.classList.add('term-open');
      if(document.body.classList.contains('term-collapsed'))termToggleCollapse();
      await termAttach(${JSON.stringify(name)},_termActiveWorkspaceId());
    })()`);
    await wait(`termCurrentSession===${JSON.stringify(name)} && termWS?.readyState===1 && termXterm && Array.from({length:termXterm.buffer.active.length},(_,i)=>termXterm.buffer.active.getLine(i)?.translateToString(true)||'').join('').includes(${JSON.stringify(marker)})`,'Owned echo app did not become ready');
    const expected=Array.from({length:samples*2},(_,i)=>String.fromCharCode(97+i%26)).join('');
    const fixtureDocuments=changeFiles?await Promise.all([1,2].map(async number=>{
      const path=join(workspace,'docs',`review-${number}.md`);
      return {path,content:await readFile(path,'utf8')};
    })):[];
    await evaluate(`(()=>{
      const expected=${JSON.stringify(expected)}, marker=${JSON.stringify(marker)};
      const input=termXterm.element.querySelector('textarea');
      const probe=window.__typing={rows:[],events:[],errors:[],longtasks:[],refreshes:[],parsed:[],skippedRenders:[],phase:null,loadTimer:null,inflight:null};
      probe.observer=new PerformanceObserver(list=>{for(const e of list.getEntries())probe.longtasks.push({at:e.startTime,ms:e.duration});});
      probe.observer.observe({type:'longtask',buffered:false});
      document.addEventListener('keydown',e=>{
        if(!/^[a-z]$/.test(e.key))return;
        const index=probe.events.length;
        if(e.target!==input)probe.errors.push('Input focus lost at '+index);
        if(e.key!==expected[index])probe.errors.push('Unexpected key at '+index+': '+e.key);
        probe.events.push({index,char:e.key,phase:probe.phase,source:e.timeStamp,sourceEpoch:performance.timeOrigin+e.timeStamp,handlerAt:performance.now()});
      },true);
      const echoed=()=>{
        const buffer=termXterm.buffer.active;
        // tmux may draw a status bar below the app. Read only through the
        // echo process's cursor, retaining exact text and wrapped lines.
        let text='';for(let i=0;i<=buffer.baseY+buffer.cursorY;i++)text+=buffer.getLine(i)?.translateToString(true,0,i===buffer.baseY+buffer.cursorY?buffer.cursorX:undefined)||'';
        const offset=text.lastIndexOf(marker);
        if(offset<0){probe.errors.push('Echo marker disappeared');return '';}
        const tail=text.slice(offset+marker.length);
        if(!expected.startsWith(tail)){probe.errors.push('Unexpected echo text: '+JSON.stringify(tail));return '';}
        return tail;
      };
      probe.parseListener=termXterm.onWriteParsed(()=>{
        const at=performance.now(),tail=echoed();
        while(probe.parsed.length<tail.length)probe.parsed.push(at);
      });
      probe.listener=termXterm.onRender(range=>{
        const renderAt=performance.now(),buffer=termXterm.buffer.active,tail=echoed();
        const cursorRow=buffer.baseY+buffer.cursorY-buffer.viewportY;
        if(range.start>cursorRow || range.end<cursorRow){
          if(tail.length>probe.rows.length)probe.skippedRenders.push({at:renderAt,range,cursorRow,tailLength:tail.length,cols:termXterm.cols,rows:termXterm.rows});
          return;
        }
        while(probe.rows.length<tail.length && probe.rows.length<probe.events.length) {
          const e=probe.events[probe.rows.length];
          probe.rows.push({...e,renderAt,parsedAt:probe.parsed[e.index],total:renderAt-e.source,queue:e.handlerAt-e.source,handlerToRender:renderAt-e.handlerAt});
        }
      });
      probe.refresh=()=>{
        if(probe.inflight)return;
        const at=performance.now();
        probe.inflight=_refreshWorkspaceSidebar({preserveScroll:true}).then(()=>probe.refreshes.push({at,ms:performance.now()-at}),e=>probe.errors.push(String(e))).finally(()=>{probe.inflight=null;});
      };
      probe.start=loaded=>{
        probe.phase=loaded?'sidebar-refresh':'normal';input.focus();
        if(document.activeElement!==input)throw new Error('Cannot focus echo terminal');
        if(loaded){probe.refresh();probe.loadTimer=setInterval(probe.refresh,500);}
      };
      probe.stop=async()=>{clearInterval(probe.loadTimer);await probe.inflight;};
      probe.snapshot=()=>({rows:probe.rows,events:probe.events,errors:probe.errors,longtasks:probe.longtasks,refreshes:probe.refreshes,skippedRenders:probe.skippedRenders,webgl:!!termXterm?._webglAddon});
    })()`);
    if(process.env.LAB_PERF_CPU_PROFILE){await client.send('Profiler.enable');await client.send('Profiler.start');}
    if(process.env.LAB_PERF_TRACE)await client.send('Tracing.start',{categories:'devtools.timeline,blink,blink.user_timing,disabled-by-default-blink.debug.display_lock,disabled-by-default-devtools.timeline.invalidationTracking',transferMode:'ReturnAsStream'});
    for(const loaded of [false,true]) {
      await evaluate(`__typing.start(${loaded})`);
      const phase=loaded?'sidebar-refresh':'normal', phaseStart=performance.now(), commands=[];
      const writes=[];let nextWrite=phaseStart;
      for(let i=0;i<samples;i++) {
        if(loaded && changeFiles && performance.now()>=nextWrite) {
          const index=writes.length, doc=fixtureDocuments[index%2];
          const write=writeFile(doc.path,doc.content+`\n<!-- typing fixture update ${index} -->\n`).then(async()=>updates.push({path:doc.path,epoch:Date.now(),mtime:(await stat(doc.path)).mtimeMs/1000}));
          write.catch(()=>{});writes.push(write);nextWrite+=500;
        }
        const char=expected[sent.length], timestamp=Date.now()/1000;
        sent.push({index:sent.length,char,phase,epoch:timestamp*1000,postingSlip:performance.now()-phaseStart-i*interval});
        // Do not wait for renderer acknowledgments between keys: that would
        // hide queued input during a blocked main thread. Attach rejection
        // handlers immediately; Promise.all below checks every command.
        const down=client.send('Input.dispatchKeyEvent',{type:'keyDown',timestamp,key:char,code:'Key'+char.toUpperCase(),text:char,unmodifiedText:char,windowsVirtualKeyCode:char.toUpperCase().charCodeAt(0)});
        const up=client.send('Input.dispatchKeyEvent',{type:'keyUp',timestamp,key:char,code:'Key'+char.toUpperCase(),windowsVirtualKeyCode:char.toUpperCase().charCodeAt(0)});
        down.catch(()=>{});up.catch(()=>{});commands.push(down,up);
        await sleep(Math.max(0,phaseStart+(i+1)*interval-performance.now()));
      }
      await Promise.all(commands);
      await Promise.all(writes);
      await evaluate('__typing.stop()');
      await wait(`__typing.rows.length===${sent.length}`,'Keys failed to echo/render');
      if(loaded && changeFiles) {
        const latest=[...new Map(updates.map(u=>[u.path,u])).values()].map(u=>({path:u.path.slice(workspace.length+1),mtime:u.mtime}));
        await wait(`${JSON.stringify(latest)}.every(expected=>{
          const file=_workspaceSidebarCache.get(${JSON.stringify(workspace)})?.files.find(f=>f.path===expected.path);
          return file && Math.abs(file.mtime-expected.mtime)<0.01;
        })`,'Changed fixture files did not reach the sidebar cache');
        if(latest.length===2) {
          const newest=latest.sort((a,b)=>b.mtime-a.mtime).map(u=>u.path);
          await wait(`(()=>{
            const rows=Array.from(document.querySelectorAll('#sidebar .sidebar-file-recent')).map(el=>el.dataset.filepath);
            return rows.indexOf(${JSON.stringify(newest[0])})>=0 && rows.indexOf(${JSON.stringify(newest[0])})<rows.indexOf(${JSON.stringify(newest[1])});
          })()`,'Updated recent-file ordering did not render');
        }
      }
      const snapshot=await evaluate('__typing.snapshot()');
      const rows=snapshot.rows.filter(r=>r.phase===phase);
      phases.push({phase,total:stats(rows.map(r=>r.total)),queue:stats(rows.map(r=>r.queue)),handlerToRender:stats(rows.map(r=>r.handlerToRender))});
    }
    if(process.env.LAB_PERF_CPU_PROFILE){const {profile}=await client.send('Profiler.stop');await writeFile(process.env.LAB_PERF_CPU_PROFILE,JSON.stringify(profile));}
    if(process.env.LAB_PERF_TRACE){
      const complete=client.once('Tracing.tracingComplete');await client.send('Tracing.end');
      const {stream}=await complete;let trace='';
      while(true){const chunk=await client.send('IO.read',{handle:stream});trace+=chunk.data;if(chunk.eof)break;}
      await client.send('IO.close',{handle:stream});await writeFile(process.env.LAB_PERF_TRACE,trace);
    }
    const result=await evaluate('__typing.observer.disconnect(); __typing.listener.dispose(); __typing.parseListener.dispose(); __typing.snapshot()');
    result.browserVersion=browserVersion.Browser;
    result.timestampErrors=result.events.flatMap((e,i)=>Math.abs(e.sourceEpoch-sent[i]?.epoch)>2?[{index:i,sourceEpoch:e.sourceEpoch,sentEpoch:sent[i]?.epoch}]:[]);
    const deadline=Date.now()+5000;
    while(pendingRequests.size){if(Date.now()>deadline)throw new Error('API requests still pending: '+[...pendingRequests.values()].join(', '));await sleep(10);}
    result.requests=await evaluate(`performance.getEntriesByType('resource').filter(r=>r.name.includes('/api/')).map(r=>({route:new URL(r.name).pathname,ms:r.duration,status:r.responseStatus}))`);
    result.requestMisses=result.requests.filter(r=>r.ms>=200);
    result.requestErrors=result.requests.filter(r=>r.status>=400);
    result.misses=result.rows.filter(r=>r.total>=50);
    result.phases=phases;result.sent=sent;result.browserErrors=browserErrors;result.requestFailures=requestFailures;
    result.fixture={extraFiles:Number(process.env.LAB_PERF_EXTRA_FILES||0),types:process.env.LAB_PERF_EXTRA_FILE_TYPES,layout:process.env.LAB_PERF_EXTRA_FILE_LAYOUT,changeFiles};
    result.updates=updates;
    await client.send('Page.navigate',{url:baseUrl+'/api/ping'});
    await wait(`location.pathname==='/api/ping' && !document.getElementById('termPanel') && document.body.textContent.includes('status')`,'Frame control failed to load');
    result.emptyPageFrames=stats(await evaluate(`(async()=>{const frames=[];let last=await new Promise(requestAnimationFrame);for(let i=0;i<100;i++){const next=await new Promise(requestAnimationFrame);frames.push(next-last);last=next;}return frames;})()`));
    console.log(JSON.stringify(result,null,2));
    if(result.errors.length || result.timestampErrors.length || result.misses.length || result.requestMisses.length || result.requestErrors.length || browserErrors.length || requestFailures.length)process.exitCode=1;
  } catch(error) {
    const partial=evaluate?await evaluate('window.__typing?.snapshot()').catch(()=>null):null;
    console.log(JSON.stringify({error:error.message,cause:String(error.cause||''),stack:error.stack,partial,phases,sent,updates,browserErrors,requestFailures},null,2));
    process.exitCode=1;
  } finally {
    if(client){await client.send('Page.close').catch(()=>{});client.ws.close();}
    if(chrome.exitCode===null){chrome.kill();await new Promise(r=>chrome.once('exit',r));}
    await rm(profile,{recursive:true,force:true}).catch(()=>{});
  }
}
main().catch(e=>{console.error(e);process.exitCode=1;});
