#!/usr/bin/env node
// Browser stage of lab_navigation_latency.py; run the Python wrapper.
// Timestamped CDP input -> rendered content -> animation-frame task.
// This is a browser paint opportunity estimate, not physical display latency.
import {spawn} from 'node:child_process';
import {mkdtemp, readFile, rm, stat, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {checkSidebarGitFixture} from './sidebar_git_fixture.mjs';
import {captureInputClock,validateInputClock} from './input_clock.mjs';
import {installTerminalTabProbe} from './terminal_tab_probe.mjs';
import {terminalCreationActions,verifyTerminalCreation} from './terminal_creation_workload.mjs';
import {runQuickFileWorkload} from './quick_file_workload.mjs';
import {compareSidebarIdentity} from './sidebar_identity_probe.mjs';
import {documentEditActions,verifyEditedDocuments,verifyDocumentHistory} from './document_edit_workload.mjs';
import {runDocumentTyping} from './document_typing_probe.mjs';
import {notebookViewActions} from './notebook_view_workload.mjs';
import {runNotebookTyping} from './notebook_typing_probe.mjs';
import {installNavigationRefreshProbe,installNavigationRefreshStress,navigationRefreshCoverage} from './navigation_refresh_probe.mjs';
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
  let client,evaluate;
  let traceActive=false,profileActive=false,diagnostics;
  const traceCategories=process.env.LAB_PERF_TRACE_CATEGORIES||'devtools.timeline,blink,blink.user_timing,disabled-by-default-blink.debug.display_lock,disabled-by-default-devtools.timeline.invalidationTracking';
  let traceStartedEpoch;
  const finishDiagnostics=()=>diagnostics||=(async()=>{
    const jobs=[];
    if(profileActive)jobs.push((async()=>{
      const {profile}=await client.send('Profiler.stop');
      await writeFile(process.env.LAB_PERF_CPU_PROFILE,JSON.stringify(profile));
    })());
    if(traceActive)jobs.push((async()=>{
      let timer;
      const complete=Promise.race([client.once('Tracing.tracingComplete'),new Promise((_,reject)=>{
        timer=setTimeout(()=>reject(new Error('Trace completion timed out')),15000);
      })]);
      let stream;
      try {
        const endedEpoch=Date.now();
        const results=await Promise.all([client.send('Tracing.end'),complete]);
        stream=results[1].stream;
        let trace='';
        while(true){const chunk=await client.send('IO.read',{handle:stream});trace+=chunk.data;if(chunk.eof)break;}
        await writeFile(process.env.LAB_PERF_TRACE,trace);
        await writeFile(process.env.LAB_PERF_TRACE+'.metadata.json',JSON.stringify({categories:traceCategories,startedEpoch:traceStartedEpoch,endedEpoch,completion:results[1]}));
      } finally {
        clearTimeout(timer);
        if(stream)await client.send('IO.close',{handle:stream});
      }
    })());
    if(process.env.LAB_PERF_REFRESH_TRACE && evaluate)jobs.push((async()=>{
      const trace=await evaluate('window.__navigationRefreshProbe?.()||null');
      await writeFile(process.env.LAB_PERF_REFRESH_TRACE,JSON.stringify(trace));
    })());
    return (await Promise.allSettled(jobs)).filter(result=>result.status==='rejected').map(result=>String(result.reason));
  })();
  const rows=[],inputSetups=[],documentTyping=[],documentHistory=[],notebookTyping=[];
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
    evaluate=async expression=>{
      const r=await client.send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
      if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);
      return r.result.value;
    };
    if(process.env.LAB_PERF_TRACE){traceStartedEpoch=Date.now();await client.send('Tracing.start',{categories:traceCategories,transferMode:'ReturnAsStream'});traceActive=true;}
    await client.send('Page.navigate',{url:baseUrl+'/?view=productivity'});
    const until=Date.now()+15000;
    while(!await evaluate('document.querySelectorAll(".workspace-tab[data-kind=workspace]").length === 2 && document.readyState === "complete"')) {
      if(Date.now()>until)throw new Error('Fixture UI did not load');
      await sleep(25);
    }
    // Start immediately: early user navigation must not inherit boot delays.
    // No ui_check, mocked fetch, disabled polling, or cache flush.
    await evaluate('performance.setResourceTimingBufferSize(10000)');
    const timeOrigin=await evaluate('performance.timeOrigin');
    if(process.env.LAB_PERF_REFRESH_TRACE)await installNavigationRefreshProbe(evaluate,workspaceRoot);
    if(process.env.LAB_PERF_NAVIGATION_REFRESH_DELAY)await installNavigationRefreshStress(evaluate,workspaceRoot,Number(process.env.LAB_PERF_NAVIGATION_REFRESH_DELAY));
    if(process.env.LAB_PERF_CPU_PROFILE) {
      await client.send('Profiler.enable');
      await client.send('Profiler.start');
      profileActive=true;
    }
    const actions=[];
    const createWorkspaces=process.env.LAB_PERF_CREATE_WORKSPACES==='1';
    const settings=process.env.LAB_PERF_SETTINGS==='1';
    const pins=process.env.LAB_PERF_PINS==='1';
    const quickFiles=process.env.LAB_PERF_QUICK_FILES==='1';
    const documentEdit=process.env.LAB_PERF_DOCUMENT_EDIT==='1';
    const notebookView=process.env.LAB_PERF_NOTEBOOK_VIEW==='1';
    const terminalTabs=JSON.parse(process.env.LAB_PERF_TERMINAL_TABS||'[]');
    const terminalCreation=JSON.parse(process.env.LAB_PERF_TERMINAL_CREATE||'null');
    if(terminalTabs.length)await installTerminalTabProbe(evaluate,terminalTabs,{diagnostics:!!process.env.LAB_PERF_TRACE});
    const initialWorkspaceTabs=createWorkspaces
      ? await evaluate(`Array.from(document.querySelectorAll('.workspace-tab[data-kind="workspace"]'),row=>row.dataset.key)`)
      : [];
    if(createWorkspaces) {
      for(let i=0;i<samples;i++) {
        const name='Latency workspace '+String(i+1).padStart(3,'0');
        const id=name.toLowerCase().replaceAll(' ','-');
        actions.push(
          {kind:'create-picker',target:id,selector:'#workspaceTabsPlusBtn',ready:`document.getElementById('workspaceTabsPicker')?.classList.contains('open')`},
          {kind:'create-vaults',target:id,selector:'#workspaceTabsPicker [data-action="create"]',ready:`!!document.querySelector('#workspaceTabsPicker [data-create-vault]')`},
          {kind:'create-form',target:id,selector:'#workspaceTabsPicker [data-create-vault]',ready:`document.getElementById('vaultWorkspaceModal')?.classList.contains('active') && document.activeElement?.id==='vaultWorkspaceName'`},
          {kind:'create-workspace',target:id,selector:'#vaultWorkspaceSubmit',input:name,
            ready:`currentWorkspace?.path===${JSON.stringify(workspaceRoot+'/'+id)} && document.querySelector('#content [data-workspace-display-title]')?.textContent===${JSON.stringify(name)} && !document.getElementById('vaultWorkspaceModal')?.classList.contains('active') && !!document.querySelector('.workspace-tab[data-workspace-id="${id}"]')`},
        );
      }
    } else if(terminalCreation) {
      actions.push(...await terminalCreationActions(evaluate,workspaceRoot,samples,terminalCreation));
    } else if(notebookView) {
      actions.push(...await notebookViewActions(evaluate,workspaceRoot,samples,{typing:process.env.LAB_PERF_NOTEBOOK_TYPING==='1'}));
    } else if(documentEdit) {
      actions.push(...await documentEditActions(workspaceRoot,samples,{inputMode:process.env.LAB_PERF_DOCUMENT_EDIT_INPUT||'replace',typing:process.env.LAB_PERF_DOCUMENT_TYPING==='1'}));
    } else if(quickFiles) {
      actions.push({kind:'workspace',target:'alpha',selector:'.workspace-tab[data-workspace-id="alpha"]',
        ready:`document.querySelector('#content [data-workspace-display-title]')?.textContent==='Alpha'`});
    } else if(terminalTabs.length) {
      actions.push({kind:'workspace',target:'alpha',selector:'.workspace-tab[data-workspace-id="alpha"]',
        ready:`document.querySelector('#content [data-workspace-display-title]')?.textContent==='Alpha'`});
      const terminalAction=(index,phase)=>{
        const {name}=terminalTabs[index];
        return {kind:'terminal-'+phase,target:name,terminal:true,selector:'.sess[data-name='+JSON.stringify(name)+']',
          ready:`__terminalTabs.ready(${JSON.stringify(name)})`};
      };
      for(let i=0;i<terminalTabs.length;i++)actions.push(terminalAction(i,'first'));
      actions.push(terminalAction(terminalTabs.length-1,'mounted'));
      for(let i=0;i<samples;i++)actions.push(terminalAction(terminalTabs.length-2+i%2,'warm'));
      for(let i=0;i<samples;i++)actions.push(terminalAction(i%terminalTabs.length,'cycle'));
    } else if(pins) {
      actions.push({kind:'workspace',target:'alpha',selector:'.workspace-tab[data-workspace-id="alpha"]',
        ready:`document.querySelector('#content [data-workspace-display-title]')?.textContent==='Alpha'`});
      const path='docs/review-1.md';
      const ordinary='#sidebar .sidebar-file[data-open-file]:not(.sidebar-file-recent)[data-filepath="'+path+'"]';
      const shortcut='#sidebar > .sidebar-file[data-filepath="'+path+'"]';
      for(let i=0;i<samples;i++)for(const pinned of [true,false]) {
        const row=pinned||i%2===0?ordinary:shortcut;
        actions.push({kind:pinned?'pin':'unpin',target:row===ordinary?'file':'shortcut',selector:row+' button',hover:row,pinned,path,
          ready:`document.querySelectorAll(${JSON.stringify(shortcut)}).length===${pinned?1:0} && document.querySelector(${JSON.stringify(ordinary+' button')})?.title===${JSON.stringify(pinned?'Unpin':'Pin to top')} && _workspaceSidebarCache.get(${JSON.stringify(workspaceRoot+'/alpha')})?.pinned.includes(${JSON.stringify(path)})===${pinned} && document.querySelector('#content [data-workspace-display-title]')?.textContent==='Alpha'`});
      }
    } else if(settings) {
      actions.push({kind:'workspace',target:'alpha',selector:'.workspace-tab[data-workspace-id="alpha"]',
        ready:`document.querySelector('#content [data-workspace-display-title]')?.textContent==='Alpha'`});
      for(let i=0;i<samples;i++) {
        const model='latency-model-'+String(i+1).padStart(3,'0');
        const recentMode=i%2?'mtime':'none';
        actions.push(
          {kind:'settings-open',target:'global',selector:'#settingsBtn',ready:`!!document.querySelector('#labSettingsCenter form [name="defaultAgent"]')`},
          {kind:'settings-scope',target:'beta',selector:'#labSettingsCenter [data-scope='+JSON.stringify(workspaceRoot+'/beta')+']',
            ready:`document.querySelector('#labSettingsCenter [data-scope-caption]')?.textContent===${JSON.stringify(workspaceRoot+'/beta')} && !!document.querySelector('#labSettingsCenter form [name="agent"]')`},
          {kind:'settings-save',target:'beta',selector:'#labSettingsCenter .settings-save',input:model,inputSelector:'#labSettingsCenter form [name="model"]',
            ready:`document.querySelector('#labSettingsCenter [data-message]')?.textContent==='Saved' && document.querySelector('#labSettingsCenter form [name="model"]')?.value===${JSON.stringify(model)}`},
          {kind:'settings-active-scope',target:'alpha',selector:'#labSettingsCenter [data-scope='+JSON.stringify(workspaceRoot+'/alpha')+']',
            ready:`document.querySelector('#labSettingsCenter [data-scope-caption]')?.textContent===${JSON.stringify(workspaceRoot+'/alpha')} && !!document.querySelector('#labSettingsCenter form [name="agent"]')`},
          {kind:'settings-files',target:'alpha',selector:'#labSettingsCenter [data-section="files"]',ready:`!!document.querySelector('#labSettingsCenter form [name="recentMode"]')`},
          {kind:'settings-files-save',target:recentMode,selector:'#labSettingsCenter .settings-save',choice:{selector:'#labSettingsCenter form [name="recentMode"]',value:recentMode},
            ready:`document.querySelector('#labSettingsCenter [data-message]')?.textContent==='Saved' && _sidebarFileConfig.recentMode===${JSON.stringify(recentMode)} && document.querySelectorAll('#sidebar .sidebar-file-recent').length===${recentMode==='none'?'0':'window.__settingsExpectedRecentRows'}`},
          {kind:'settings-close',target:'dialog',selector:'#labSettingsCenter [data-done]',ready:`!document.getElementById('labSettingsCenter')`},
        );
      }
    } else {
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
    }
    for(const [i,action] of actions.entries()) {
      const {selector}=action;
      const until=Date.now()+10000;
      while(!await evaluate(`!!document.querySelector(${JSON.stringify(selector)})`)) {
        if(Date.now()>until)throw new Error('Click target did not appear: '+selector);
        await sleep(10);
      }
      if(action.hover) {
        // Reveal the normal hover-only control before timing its click. This
        // preparation is not reported as a measurement of pointer hover.
        const point=await evaluate(`(async()=>{
          let row=document.querySelector(${JSON.stringify(action.hover)});row.scrollIntoView({block:'center'});
          await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
          row=document.querySelector(${JSON.stringify(action.hover)});const rect=row.getBoundingClientRect();
          return {x:rect.x+30,y:rect.y+rect.height/2};
        })()`);
        await client.send('Input.dispatchMouseEvent',{type:'mouseMoved',...point});
        await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
      }
      if(action.input) {
        if(action.inputSelector) {
          await evaluate(`(()=>{const input=document.querySelector(${JSON.stringify(action.inputSelector)});if(!input)throw Error('Action input is not ready');input.focus();${action.inputAppend?'input.setSelectionRange(input.value.length,input.value.length);':'input.select();'}})()`);
        } else if(!await evaluate(`document.activeElement?.id==='vaultWorkspaceName' && !document.getElementById('vaultWorkspaceName').value`))throw new Error('New workspace name field is not ready');
        // Record preparation separately from the timed click. Multiline IME
        // insertion can be slow even in a plain textarea; never conceal it.
        const setup={sample:i+1,kind:action.kind,target:action.target,mode:action.inputAppend?'append':'replace',characters:action.input.length,startedEpoch:Date.now(),completed:false};
        inputSetups.push(setup);
        const started=performance.now();
        try {await client.send('Input.insertText',{text:action.input});setup.completed=true;}
        finally {setup.ms=performance.now()-started;setup.finishedEpoch=Date.now();}
      }
      if(action.typingInput)await runDocumentTyping(client,evaluate,documentTyping,{workspaceRoot,action,sample:i+1});
      if(action.choice) {
        // Prepare the form before measuring its native Save click. Native
        // macOS select popups do not accept the page's CDP keyboard events;
        // this setup is deliberately not reported as dropdown input latency.
        await evaluate(`(()=>{
          const input=document.querySelector(${JSON.stringify(action.choice.selector)});
          input.value=${JSON.stringify(action.choice.value)};
          if(input.value!==${JSON.stringify(action.choice.value)})throw Error('Settings option is missing');
          input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
        })()`);
      }
      let sentEpoch;
      const cacheState=action.terminal?await evaluate(`__terminalTabs.cacheState(${JSON.stringify(action.target)})`):null;
      await evaluate(`(async()=>{
        const captureInputClock=${captureInputClock.toString()};
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
          __probe.clock=captureInputClock(event);
          __probe.start=__probe.clock.source;
          __probe.sourceEpoch=__probe.clock.sourceEpoch;
          __probe.queue=__probe.clock.handlerAt-event.timeStamp;
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
      if(row.error) {
        const state=action.terminal?await evaluate(`__terminalTabs.snapshot()`):pins?await evaluate(`({workspace:currentWorkspace?.path,pinned:_workspaceSidebarCache.get(currentWorkspace?.path)?.pinned,rows:Array.from(document.querySelectorAll('#sidebar .sidebar-file[data-filepath="docs/review-1.md"]'),el=>({html:el.outerHTML,parent:el.parentElement.className})),dashboard:document.querySelector('#content [data-workspace-display-title]')?.textContent})`):null;
        throw new Error(row.error+' '+JSON.stringify({probe:row,state}));
      }
      const clockCheck=validateInputClock(row.clock,sentEpoch);
      const terminalState=action.terminal?await evaluate(`__terminalTabs.state(${JSON.stringify(action.target)})`):null;
      rows.push({sample:i+1,kind:action.kind,target:action.target,ms:row.ms,queue:row.queue,sourceEpoch:row.sourceEpoch,sentEpoch,clock:row.clock,clockCheck,requests:row.requests,...(action.terminal?{cacheState,terminalState}:{})});
      if(!clockCheck.valid)throw new Error('Mouse input clock validation failed: '+clockCheck.reason);
      const pendingNotebooks=JSON.parse(process.env.LAB_PERF_PENDING_NOTEBOOKS||'[]');
      if(pendingNotebooks.length && action.kind==='workspace') {
        const expected=pendingNotebooks.filter(path=>path.startsWith(action.target+'/')).map(path=>path.slice(action.target.length+1)).sort();
        const pendingState=await evaluate(`(()=>{
          const cached=(_workspaceSidebarCache.get(currentWorkspace?.path)?.files||[]).filter(row=>row.pending).map(row=>row.path).sort();
          const rendered=[...document.querySelectorAll('#sidebar .sidebar-file[data-open-file]:not(.sidebar-file-recent)')]
            .filter(row=>row.querySelector('.nb-running-dot[title="A cell is currently running"]'))
            .map(row=>row.dataset.filepath).sort();
          return {workspace:currentWorkspace?.path,cached,rendered};
        })()`);
        if(pendingState.workspace!==workspaceRoot+'/'+action.target || JSON.stringify(pendingState.cached)!==JSON.stringify(expected)
            || JSON.stringify(pendingState.rendered)!==JSON.stringify(expected))throw new Error('Pending notebook indicators differ: '+JSON.stringify({expected,pendingState}));
        rows.at(-1).pendingVerification=pendingState;
      }
      if(action.kind==='terminal-create')rows.at(-1).creationVerification=await verifyTerminalCreation(client,evaluate,workspaceRoot,action.target);
      if(action.expectedDocuments)rows.at(-1).documentVerification=await verifyEditedDocuments(action.expectedDocuments);
      if(action.notebookTyping) {
        await runNotebookTyping(client,evaluate,notebookTyping,{workspaceRoot,action,sample:i+1});
        rows.at(-1).draftVerification=await verifyEditedDocuments(action.expectedDocuments);
      }
      if(action.terminal) {
        if(terminalState.cacheSize>3||terminalState.panes>4)throw new Error('Terminal pane retention exceeded its production bound');
        if(action.kind==='terminal-first') {
          // Write one real key after the measured attach. Later switches must
          // retain it through both warm restoration and tmux replay.
          const index=terminalTabs.findIndex(row=>row.name===action.target),key=String.fromCharCode(97+index);
          await evaluate(`__terminalTabs.expectInput(${JSON.stringify(action.target)},${JSON.stringify(key)})`);
          await client.send('Input.dispatchKeyEvent',{type:'keyDown',key,code:'Key'+key.toUpperCase(),text:key,unmodifiedText:key,windowsVirtualKeyCode:65+index});
          await client.send('Input.dispatchKeyEvent',{type:'keyUp',key,code:'Key'+key.toUpperCase(),windowsVirtualKeyCode:65+index});
          const deadline=Date.now()+10000;
          while(!await evaluate(`__terminalTabs.ready(${JSON.stringify(action.target)})`)) {
            if(Date.now()>deadline)throw new Error('Terminal did not preserve fixture input: '+JSON.stringify(await evaluate('__terminalTabs.snapshot()')));
            await sleep(10);
          }
        }
      }
      if(pins&&action.kind!=='workspace') {
        const metadata=JSON.parse(await readFile(join(workspaceRoot,'alpha','workspace.json'),'utf8'));
        const other=JSON.parse(await readFile(join(workspaceRoot,'beta','workspace.json'),'utf8'));
        if((metadata.pinned||[]).includes(action.path)!==action.pinned || (other.pinned||[]).length)throw new Error('Pin state was not persisted in the correct workspace');
        if(!await evaluate(`currentWorkspace?.path===${JSON.stringify(workspaceRoot+'/alpha')} && document.querySelectorAll('#sidebar .sidebar-file[data-open-file]:not(.sidebar-file-recent)[data-filepath="docs/review-1.md"]').length===1`))throw new Error('Pin changed the active workspace or removed its ordinary file row');
      }
      if(settings&&action.kind==='workspace') {
        const count=await evaluate(`window.__settingsExpectedRecentRows=document.querySelectorAll('#sidebar .sidebar-file-recent').length`);
        if(!count)throw new Error('Settings fixture has no recent-file rows');
      }
      if(settings&&action.kind!=='workspace'&&!await evaluate(`currentWorkspace?.path===${JSON.stringify(workspaceRoot+'/alpha')}`))throw new Error('Settings navigated away from the active workspace');
      await sleep(100);
    }
    if(documentEdit && process.env.LAB_PERF_DOCUMENT_HISTORY==='1')await verifyDocumentHistory(client,evaluate,actions.at(-1).expectedDocuments,workspaceRoot,documentHistory);
    if(quickFiles)await runQuickFileWorkload(client,evaluate,rows,{workspaceRoot,samples,
      extraFiles:Number(process.env.LAB_PERF_EXTRA_FILES||0),
      fileTypes:(process.env.LAB_PERF_EXTRA_FILE_TYPES||'md').split(','),
      layout:process.env.LAB_PERF_EXTRA_FILE_LAYOUT||'folders'});
    if(settings) {
      const active=JSON.parse(await readFile(join(workspaceRoot,'alpha','workspace.json'),'utf8'));
      const edited=JSON.parse(await readFile(join(workspaceRoot,'beta','workspace.json'),'utf8'));
      if(active.model||edited.model!=='latency-model-'+String(samples).padStart(3,'0')||active.agent||edited.agent)throw new Error('Settings wrote to the wrong workspace or changed the agent');
      const saved=await evaluate(`JSON.parse(localStorage.getItem('labSidebarFileConfig-v2:'+encodeURIComponent(${JSON.stringify(workspaceRoot+'/alpha')})))`);
      if(saved?.recentMode!==(samples%2?'none':'mtime'))throw new Error('Sidebar preference was not persisted');
    }
    if(createWorkspaces) {
      const tabs=await evaluate(`Array.from(document.querySelectorAll('.workspace-tab[data-kind="workspace"]'),row=>row.dataset.key)`);
      const expectedTabs=[...initialWorkspaceTabs,...Array.from({length:samples},(_,i)=>workspaceRoot+'/latency-workspace-'+String(i+1).padStart(3,'0'))];
      if(JSON.stringify(tabs)!==JSON.stringify(expectedTabs))throw new Error('Creation changed existing tab order or duplicated a tab');
      const created=await evaluate(`workspacesList.filter(row=>row.path?.startsWith(${JSON.stringify(workspaceRoot+'/latency-workspace-')})).map(row=>({id:row.name,path:row.path}))`);
      if(created.length!==samples||new Set(created.map(row=>row.path)).size!==samples)throw new Error('Created workspace catalog count or identity mismatch');
      for(let i=0;i<samples;i++) {
        const id='latency-workspace-'+String(i+1).padStart(3,'0');
        if(!created.some(row=>row.id===id&&row.path===workspaceRoot+'/'+id))throw new Error('Created workspace escaped its fixture vault');
        const metadata=JSON.parse(await readFile(join(workspaceRoot,id,'workspace.json'),'utf8'));
        const tasks=JSON.parse(await readFile(join(workspaceRoot,id,'tasks.json'),'utf8'));
        if(metadata.id!==id||metadata.name!=='Latency workspace '+String(i+1).padStart(3,'0')||metadata.tab_open!==true||tasks.next_id!==1||tasks.tasks.length)throw new Error('Created workspace storage is incomplete');
        for(const folder of ['docs','notes','assets'])if(!(await stat(join(workspaceRoot,id,folder))).isDirectory())throw new Error('Created workspace folder is missing');
      }
    }
    if(process.env.LAB_PERF_SIDEBAR_RESIZE==='1') {
      // Compare steady-state drags as well as the early navigation above.
      // Input timestamps cover mouse-down through release, without waiting for
      // renderer acknowledgments between the three native events.
      const readyDeadline=Date.now()+5000;
      while(!await evaluate(`typeof _sidebarLayoutJobs==='undefined' || !_sidebarLayoutJobs.has(document.getElementById('sidebar'))`)) {
        if(Date.now()>readyDeadline)throw new Error('Sidebar layout preparation did not finish');
        await sleep(20);
      }
      for(let i=0;i<samples;i++) {
        const width=i%2?340:200;
        const point=await evaluate(`(()=>{
          const captureInputClock=${captureInputClock.toString()};
          const resizer=document.getElementById('sidebarResizer'),r=resizer.getBoundingClientRect();
          const x=r.x+r.width/2,y=r.y+r.height/2;
          if(document.elementFromPoint(x,y)!==resizer)throw new Error('Sidebar resizer is not hittable');
          window.__resizeProbe={done:false};
          resizer.addEventListener('mousedown',event=>{
            __resizeProbe.clock=captureInputClock(event);
            __resizeProbe.start=__resizeProbe.clock.source;__resizeProbe.sourceEpoch=__resizeProbe.clock.sourceEpoch;
            __resizeProbe.queue=__resizeProbe.clock.handlerAt-event.timeStamp;
          },{capture:true,once:true});
          document.addEventListener('mouseup',()=>requestAnimationFrame(()=>setTimeout(()=>{
            __resizeProbe.width=document.getElementById('sidebar').getBoundingClientRect().width;
            __resizeProbe.dragging=document.body.classList.contains('sidebar-resizing');
            __resizeProbe.ms=performance.now()-__resizeProbe.start;__resizeProbe.done=true;
          },0)),{capture:true,once:true});
          return {x,y};
        })()`);
        const sentEpoch=Date.now();
        await Promise.all([
          client.send('Input.dispatchMouseEvent',{type:'mousePressed',timestamp:sentEpoch/1000,...point,button:'left',clickCount:1}),
          client.send('Input.dispatchMouseEvent',{type:'mouseMoved',timestamp:sentEpoch/1000,x:width,y:point.y,button:'left',buttons:1}),
          client.send('Input.dispatchMouseEvent',{type:'mouseReleased',timestamp:sentEpoch/1000,x:width,y:point.y,button:'left',clickCount:1}),
        ]);
        const deadline=Date.now()+5000;
        while(!await evaluate('__resizeProbe.done')) {
          if(Date.now()>deadline)throw new Error('Sidebar drag did not complete');
          await sleep(10);
        }
        const row=await evaluate('__resizeProbe');
        const clockCheck=validateInputClock(row.clock,sentEpoch);
        rows.push({sample:i+1,kind:'resize',target:width,ms:row.ms,queue:row.queue,sourceEpoch:row.sourceEpoch,sentEpoch,clock:row.clock,clockCheck,width:row.width});
        if(row.dragging || Math.abs(row.width-width)>2 || !clockCheck.valid)throw new Error('Sidebar drag failed: '+JSON.stringify({row,clockCheck}));
        await sleep(100);
      }
    }
    if(process.env.LAB_PERF_FILE_IDENTITY_PROFILE)await compareSidebarIdentity(evaluate,process.env.LAB_PERF_FILE_IDENTITY_PROFILE);
    const diagnosticsErrors=await finishDiagnostics();
    if(diagnosticsErrors.length)throw new Error('Could not save browser diagnostics: '+diagnosticsErrors.join('; '));
    const stats={};
    for(const kind of new Set(rows.map(row=>row.kind))) {
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
    const requests=await evaluate(`performance.getEntriesByType('resource').filter(r=>r.name.includes('/api/')).map(r=>({route:new URL(r.name).pathname,workspace:new URL(r.name).searchParams.get('workspace_id'),startEpoch:performance.timeOrigin+r.startTime,ms:r.duration,status:r.responseStatus,serverId:r.serverTiming?.find(t=>t.name==='lab-perf')?.description||null}))`);
    const requestMisses=requests.filter(r=>r.ms>=200);
    const requestErrors=requests.filter(r=>r.status>=400);
    const fixture={workflow:terminalCreation?'terminal-create':notebookView?'notebook-view':documentEdit?'document-edit':quickFiles?'quick-files':terminalTabs.length?'terminal-tabs':pins?'pins':settings?'settings':createWorkspaces?'create':'navigation',documentSections:Number(process.env.LAB_PERF_DOCUMENT_SECTIONS||30),documentEditInput:process.env.LAB_PERF_DOCUMENT_EDIT_INPUT||'replace',extraFilesPerWorkspace:Number(process.env.LAB_PERF_EXTRA_FILES || 0),extraFileTypes:(process.env.LAB_PERF_EXTRA_FILE_TYPES || 'md').split(','),extraFileLayout:process.env.LAB_PERF_EXTRA_FILE_LAYOUT || 'folders',gitChanges:Number(process.env.LAB_PERF_GIT_CHANGES||0)};
    const git=createWorkspaces?null:await checkSidebarGitFixture(evaluate);
    if(notebookView)fixture.notebookCells=await evaluate('__notebookViewExpected.alpha.cells.length');
    fixture.notebookTyping=process.env.LAB_PERF_NOTEBOOK_TYPING==='1';
    fixture.pendingNotebooks=JSON.parse(process.env.LAB_PERF_PENDING_NOTEBOOKS||'[]');
    fixture.pendingTrackerOnly=true;
    fixture.notebookCodeLines=Number(process.env.LAB_PERF_NOTEBOOK_CODE_LINES||0);
    fixture.documentTyping=process.env.LAB_PERF_DOCUMENT_TYPING==='1';
    fixture.documentHistory=process.env.LAB_PERF_DOCUMENT_HISTORY==='1';
    const sidebar=await evaluate(`({elements:document.getElementById('sidebar').querySelectorAll('*').length,templates:[..._sidebarMarkupCache.values()].map(entry=>({elements:entry.elements,markupChars:entry.markup.length})),retainedElements:_sidebarMarkupCacheElements})`);
    const terminals=terminalCreation?await evaluate('__terminalCreation.snapshot()'):terminalTabs.length?await evaluate('__terminalTabs.snapshot()'):null;
    const refreshStress=process.env.LAB_PERF_NAVIGATION_REFRESH_DELAY?await evaluate('__navigationRefreshStress()'):null;
    if(refreshStress){
      refreshStress.coverage=navigationRefreshCoverage(rows,refreshStress.events,workspaceRoot);
      refreshStress.misses=refreshStress.coverage.filter(row=>!row.delivered);
    }
    const inputSetupMisses=inputSetups.filter(row=>!row.completed||row.ms>=200);
    const documentTypingMisses=documentTyping.filter(row=>!row.done||!row.clockCheck.valid||row.ms>=200);
    const notebookTypingMisses=notebookTyping.filter(row=>!row.done||!row.clockCheck.valid||row.ms>=200);
    const documentHistoryMisses=documentHistory.filter(row=>!row.verified||row.ms>=200);
    console.log(JSON.stringify({fixture,git,sidebar,terminals,refreshStress,timeOrigin,stats,misses,inputSetups,inputSetupMisses,documentTyping,documentTypingMisses,notebookTyping,notebookTypingMisses,documentHistory,documentHistoryMisses,requestMisses,requestErrors,requestFailures,browserErrors,requests,rows},null,2));
    if(misses.length || inputSetupMisses.length || documentTypingMisses.length || notebookTypingMisses.length || documentHistoryMisses.length || requestMisses.length || requestErrors.length || requestFailures.length || browserErrors.length || git?.errors.length || refreshStress?.misses.length)process.exitCode=1;
  } catch(error) {
    // A failed click must retain earlier samples, not erase the run's evidence.
    const diagnosticsErrors=await finishDiagnostics();
    console.log(JSON.stringify({error:error.message,cause:String(error.cause||''),stack:error.stack,diagnosticsErrors,inputSetups,documentTyping,notebookTyping,documentHistory,rows},null,2));
    process.exitCode=1;
  } finally {
    if(client){await client.send('Page.close').catch(()=>{});client.ws.close();}
    if(chrome.exitCode===null){chrome.kill();await new Promise(r=>chrome.once('exit',r));}
    await rm(profile,{recursive:true,force:true}).catch(()=>{});
  }
}
main().catch(e=>{console.error(e);process.exitCode=1;});
