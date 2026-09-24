// Full application, native CDP mouse input, real authenticated Git API.
// Dropdown selection uses its DOM change event (explicitly labeled in results).
// Record input dispatch through matching rows and a browser paint opportunity.
import {spawn, execFileSync} from 'node:child_process';
import {mkdtemp, readFile, writeFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const [base, output] = process.argv.slice(2);
const fixtures = JSON.parse(process.env.LAB_PROJECT_FIXTURES);
const root = process.env.LAB_BENCHMARK_ROOT;
const workspace = root + '/workspaces/sidebar-benchmark';
const profile = await mkdtemp(join(tmpdir(), 'lab-large-chrome-'));
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
  '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank',
], {stdio:'ignore'});
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const result = {samples:[], errors:[], timing:'CDP dispatch to matching content and paint opportunity'};
let ws;
try {
  let port;
  for (let i=0; i<100; i++) {
    try { port = (await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]; break; } catch {}
    await sleep(100);
  }
  if (!port) throw new Error('Chrome did not start');
  const target = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'}).then(r=>r.json());
  ws = new WebSocket(target.webSocketDebuggerUrl);
  let id=0; const pending=new Map();
  ws.onmessage = event => {
    const message=JSON.parse(event.data);
    if(message.id) {const p=pending.get(message.id);pending.delete(message.id);message.error?p.reject(message.error):p.resolve(message.result);}
    if(message.method==='Runtime.exceptionThrown') result.errors.push(message.params.exceptionDetails);
    if(message.method==='Runtime.consoleAPICalled' && message.params.type==='error') result.errors.push(message.params.args);
  };
  await new Promise(resolve=>ws.onopen=resolve);
  const send=(method,params={})=>new Promise((resolve,reject)=>{const key=++id;pending.set(key,{resolve,reject});ws.send(JSON.stringify({id:key,method,params}));});
  const evaluate=async expression=>{
    const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
    if(r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails));
    return r.result.value;
  };
  await send('Runtime.enable'); await send('Network.enable'); await send('Page.enable');
  await send('Network.setCookie',{name:'lab_session',value:process.env.LAB_PROBE_COOKIE,url:base,httpOnly:true});
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  const config={recentMode:'local-main',showRecent:true,worktreeColorsVersion:2,
    folderScopes:fixtures.map(f=>({path:f.path,label:f.name,worktreeFolder:root+'/.worktrees'}))};
  await send('Page.addScriptToEvaluateOnNewDocument',{source:`localStorage.setItem(${JSON.stringify('labSidebarFileConfig-v2:'+encodeURIComponent(workspace))},${JSON.stringify(JSON.stringify(config))});`});
  await send('Page.navigate',{url:base+'/?workspace='+encodeURIComponent(workspace)});
  const wait=async expression=>{
    const end=Date.now()+30000;
    while(Date.now()<end){if(await evaluate(expression))return;await sleep(25);}
    throw new Error('Timeout: '+expression+' sidebar='+await evaluate('document.getElementById("sidebar")?.textContent'));
  };
  await wait('!!document.querySelector(".sidebar-file-scope-button[data-folder-path]")');
  async function action(name,selector,expected,meta={},keys=[]) {
    const box=await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el)throw Error('Missing control');el.scrollIntoView({block:'center'});const r=el.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
    if(keys.length) await evaluate(`document.querySelector(${JSON.stringify(selector)}).focus();void 0;`);
    await evaluate(`window.__paintReady=new Promise(resolve=>{const started=Date.now();function check(){if(${expected})requestAnimationFrame(()=>setTimeout(()=>resolve(Date.now()),0));else if(Date.now()-started>30000)resolve(null);else requestAnimationFrame(check);}requestAnimationFrame(check);});void 0;`);
    const start=Date.now();
    if(!keys.length){
      await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...box,timestamp:start/1000});
      await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...box,timestamp:Date.now()/1000});
    }
    if(keys.length) await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});el.value=${JSON.stringify(keys[0])};el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    const end=await evaluate('window.__paintReady');
    if(end===null){
      result.failure=await evaluate('({sidebar:document.getElementById("sidebar")?.outerHTML,content:document.getElementById("content")?.textContent,url:location.href,workspace:currentWorkspace,body:document.body.className})');
      result.debugRefresh=await evaluate('(async()=>{try{await _refreshSidebarAfterFileConfig();return {repo:currentRepo,config:_sidebarFileConfig,base:_sidebarWorktreeBaseRoot(),root:_sidebarScopedRoot(currentWorkspace.path),view:document.getElementById("sidebar").innerHTML, direct:_sidebarProjectView(currentWorkspace.path,_sidebarScopedRoot(currentWorkspace.path))};}catch(e){return e.stack;}})()');
      const shot=await send('Page.captureScreenshot',{format:'png'});
      await writeFile(output.replace('.json','.failure.png'),Buffer.from(shot.data,'base64'));
      throw new Error('Content never appeared: '+name);
    }
    result.samples.push({action:name,input:keys.length?'select-change':'mouse',ms:end-start,...meta});
    console.log(JSON.stringify(result.samples.at(-1)));
  }
  const ready=path=>`document.querySelector('[data-project-sidebar]')?.dataset.projectSidebar===${JSON.stringify(path)} && !!document.querySelector('[data-project-directory="."] > [data-project-entry]')`;
  const recent=(path,mode)=>`document.querySelector('[data-project-sidebar]')?.dataset.projectSidebar===${JSON.stringify(path)} && document.querySelector('.sidebar-recent-selector.active')?.dataset.recentMode===${JSON.stringify(mode)} && !!document.querySelector('[data-project-recent] [data-filepath="lab-benchmark-staged.txt"]') && !!document.querySelector('[data-project-recent] [data-filepath="lab-benchmark-unstaged.txt"]') ${mode==='local-main'?`&& !!document.querySelector('[data-project-recent] [data-filepath="lab-benchmark-committed.txt"]')`:''}`;
  for(let round=0;round<3;round++)for(const f of fixtures){
    const meta={repo:f.name,round};
    await action('project',`.sidebar-file-scope-button[data-folder-path="${f.path}"]`,ready(f.path)+' && '+recent(f.path,'local-main'),meta);
    for(const mode of ['uncommitted','local-main']){
      // Starting each project at the previous mode may make its first button a toggle-off.
      if(await evaluate(`document.querySelector('.sidebar-recent-selector.active')?.dataset.recentMode===${JSON.stringify(mode)}`))
        await action('hide-recent',`.sidebar-recent-selector[data-recent-mode="${mode}"]`,`!document.querySelector('.sidebar-recent-selector.active')`,meta);
      await action(mode,`.sidebar-recent-selector[data-recent-mode="${mode}"]`,recent(f.path,mode),meta);
    }
    await action('history','.sidebar-repo-history',`document.querySelector('#explorerHistoryModal.active') && document.querySelector('#explorerHistoryList')?.textContent.includes('Lab benchmark branch change')`,meta);
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape'});
    await action('worktree','select[aria-label="File worktree"]',ready(f.worktree)+' && '+recent(f.worktree,'local-main'),meta,[f.worktree]);
    await action('worktree-uncommitted','.sidebar-recent-selector[data-recent-mode="uncommitted"]',recent(f.worktree,'uncommitted'),meta);
    await action('worktree-local-main','.sidebar-recent-selector[data-recent-mode="local-main"]',recent(f.worktree,'local-main'),meta);
    await action('worktree-history','.sidebar-repo-history',`document.querySelector('#explorerHistoryModal.active') && document.querySelector('#explorerHistoryList')?.textContent.includes('Lab benchmark branch change')`,meta);
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape'});
    await action('return-main','select[aria-label="File worktree"]',ready(f.path)+' && '+recent(f.path,'local-main'),meta,['']);
  }
  const screenshot=await send('Page.captureScreenshot',{format:'png'});
  await writeFile(output.replace('.json','.png'),Buffer.from(screenshot.data,'base64'));
  result.domElements=await evaluate('document.querySelectorAll("#sidebar *").length');
  result.heap=await send('Runtime.getHeapUsage');
  const llvm=fixtures.find(row=>row.name==='llvm-project');
  await action('large-time-project',`.sidebar-file-scope-button[data-folder-path="${llvm.path}"]`,ready(llvm.path),{repo:llvm.name});
  await action('large-time-filter','.sidebar-recent-selector[data-recent-mode="mtime:1440"]',
    `document.querySelectorAll('[data-project-recent] .sidebar-file-recent').length===200 && !!document.querySelector('[data-project-recent] > button')`,{repo:llvm.name});
  await action('large-time-next-page','[data-project-recent] > button',
    `document.querySelectorAll('[data-project-recent] .sidebar-file-recent').length===400`,{repo:llvm.name});
  result.largeTimeHeap=await send('Runtime.getHeapUsage');
  await action('return-refresh-project',`.sidebar-file-scope-button[data-folder-path="${fixtures.at(-1).path}"]`,ready(fixtures.at(-1).path),{repo:fixtures.at(-1).name});
  // A real staged file appears through the ordinary minute refresh. No cache
  // timestamp manipulation or forced refresh is used for this check.
  const f=fixtures.at(-1), marker='lab-benchmark-refresh-' + Date.now() + '.txt';
  await action('refresh-baseline','.sidebar-recent-selector[data-recent-mode="uncommitted"]',recent(f.path,'uncommitted'),{repo:f.name});
  const changed=Date.now();
  await writeFile(join(f.path,marker),'minute refresh\n');
  execFileSync('git',['-C',f.path,'add','--',marker]);
  const deadline=Date.now()+125000;
  while(!await evaluate(`!!document.querySelector('[data-project-recent] [data-filepath="${marker}"]')`)){
    if(Date.now()>deadline)throw new Error('Minute refresh did not show staged addition');
    await sleep(250);
  }
  result.backgroundRefreshMs=Date.now()-changed;
  execFileSync('git',['-C',f.path,'rm','--cached','--',marker]);
  await rm(join(f.path,marker));
} finally {
  await writeFile(output,JSON.stringify(result,null,2)+'\n');
  ws?.close();chrome.kill('SIGTERM');await sleep(500);
  await rm(profile,{recursive:true,force:true});
}
