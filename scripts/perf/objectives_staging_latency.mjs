// Mouse release source timestamp -> final content + animation-frame task.
// This estimates a browser paint opportunity, not physical display latency.
import {spawn} from 'node:child_process';
import {mkdtemp,readFile,rm,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {captureInputClock,validateInputClock} from './input_clock.mjs';

const [base,workspace,output='/private/tmp/objectives-staging-latency.json']=process.argv.slice(2);
if(!process.env.LAB_PROBE_COOKIE||new URL(base).hostname!=='127.0.0.1')throw new Error('Run the Python staging wrapper');
const profile=await mkdtemp(join(tmpdir(),'lab-objectives-chrome-'));
const chrome=spawn(process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ['--headless=new','--no-first-run','--disable-background-networking','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{stdio:'ignore'});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let ws;
const rows=[],errors=[];
try {
  let port;
  for(let i=0;i<200;i++){try{port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break;}catch{await sleep(50);}}
  if(!port)throw new Error('Chrome did not start');
  const target=await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'}).then(r=>r.json());
  ws=new WebSocket(target.webSocketDebuggerUrl);let sequence=0;const pending=new Map();
  ws.addEventListener('message',event=>{const m=JSON.parse(event.data);if(m.id){const task=pending.get(m.id);pending.delete(m.id);m.error?task.reject(new Error(m.error.message)):task.resolve(m.result);}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.exception?.description||m.params.exceptionDetails.text);});
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
  function send(method,params={}){const id=++sequence;return new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});}
  async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value;}
  async function until(expression){const end=Date.now()+15000;while(!await evaluate(expression)){if(Date.now()>end)throw new Error('UI did not become ready: '+expression);await sleep(10);}}
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  await send('Network.setCookie',{name:'lab_session',value:process.env.LAB_PROBE_COOKIE,url:base,httpOnly:true,sameSite:'Strict'});
  await send('Emulation.setDeviceMetricsOverride',{width:1550,height:1050,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:base+'/?workspace='+encodeURIComponent(workspace)});
  await until(`!!document.querySelector('[data-select-objective]') && window.marked && window.DOMPurify && termSessions.some(t=>t.logical_name==='objective-staging-phone')`);
  const scope=await evaluate(`(({workspace_id,vault})=>({workspace_id,...(vault?{vault}:{})}))(window.LabTaskTerminalBridge.context())`);
  const objectiveUrl='/api/objectives?'+new URLSearchParams(scope);
  const fixture=await evaluate(`fetch(${JSON.stringify(objectiveUrl)}).then(r=>r.json())`);
  const focused=fixture.focused.filter(Boolean).map(id=>fixture.objectives.find(o=>o.id===id)).filter(o=>['Staging · phone recovery','Staging · repository navigation','Staging · release verification'].includes(o.name));
  if(focused.length!==3||focused.some(o=>!o.name.startsWith('Staging ·')))throw new Error('Run the owned staging fixture first');
  async function click(label,selector,ready){
    await until(`!!document.querySelector(${JSON.stringify(selector)})`);
    const point=await evaluate(`(async()=>{let t=document.querySelector(${JSON.stringify(selector)});t.scrollIntoView({block:'center'});await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));t=document.querySelector(${JSON.stringify(selector)});const box=t.getBoundingClientRect();window.__objectiveProbe={done:false};const capture=${captureInputClock.toString()};document.addEventListener('click',event=>{const p=window.__objectiveProbe;p.clock=capture(event);p.queueMs=p.clock.handlerAt-event.timeStamp;if(!event.target.closest(${JSON.stringify(selector)})){p.error='Wrong click target';p.done=true;return;}const check=()=>{if(${ready})requestAnimationFrame(()=>setTimeout(()=>{p.ms=performance.now()-p.clock.source;p.done=true;},0));else if(performance.now()-p.clock.source>10000){p.error='Final content timed out';p.done=true;}else requestAnimationFrame(check);};requestAnimationFrame(check);},{once:true,capture:true});return {x:box.x+box.width/2,y:box.y+box.height/2};})()`);
    const sentEpoch=Date.now();await Promise.all([
      send('Input.dispatchMouseEvent',{type:'mousePressed',timestamp:sentEpoch/1000,...point,button:'left',clickCount:1}),
      send('Input.dispatchMouseEvent',{type:'mouseReleased',timestamp:sentEpoch/1000,...point,button:'left',clickCount:1})]);
    try{await until('window.__objectiveProbe.done');}catch(error){const probe=await evaluate('window.__objectiveProbe');const screenshot=await send('Page.captureScreenshot',{format:'png'});await writeFile(output+'.png',Buffer.from(screenshot.data,'base64'));throw new Error(label+': '+error+' '+JSON.stringify({point,probe,layout:await evaluate('({sidebar:document.querySelector("#sidebar").getBoundingClientRect().toJSON(),scroll:document.querySelector("#sidebar").scrollLeft,hit:document.elementFromPoint('+point.x+','+point.y+')?.outerHTML.slice(0,500)})')}));}const row=await evaluate('window.__objectiveProbe');
    row.label=label;row.inputClock=validateInputClock(row.clock,sentEpoch);rows.push(row);
    if(row.error||!row.inputClock.valid)throw new Error(label+': '+JSON.stringify(row));
  }
  const q=JSON.stringify;
  for(let cycle=0;cycle<3;cycle++)for(const o of focused){
    const doc=o.resources.find(r=>r.title==='Incident notes.md'),nb=o.resources.find(r=>r.kind==='notebook'),tab=doc.content.tabs[1];
    await click(`All objectives ${cycle}`,'[data-all-objectives]',`document.querySelectorAll('.objective-library-row').length===${fixture.objectives.length}`);
    await click(`objective ${o.name} ${cycle}`,`[data-select-objective="${o.id}"]`,
      `document.querySelector('.objective-working h2')?.textContent==='Tasks' && document.querySelector('.objective-purpose')?.textContent.startsWith(${q(o.name)}) && !document.querySelector('#content').inert`);
    await click(`document ${cycle}`,`[data-objective-resource="${doc.id}"]:not([data-objective-tab])`,
      `document.querySelector('.objective-working h2')?.textContent===${q(doc.title)} && document.querySelector('.workspace-doc-body .cm-content[contenteditable=true]') && document.querySelector('.workspace-doc-body')?.textContent.includes('simulated staging content') && document.querySelectorAll('[data-resource-group="${doc.id}"] [data-objective-tab]').length===3`);
    await click(`nested subtab ${cycle}`,`[data-objective-tab="${tab.id}"]`,
      `document.querySelector('.objective-working h2')?.textContent===${q(tab.title)} && document.querySelector('.workspace-doc-body')?.textContent.includes('Preserve country code')`);
    await click(`pin subtab ${cycle}`,`[data-pin-tab="${tab.id}"]`,
      `document.querySelector('[data-pin-tab="${tab.id}"]')?.getAttribute('aria-pressed')==='true'`);
    await click(`tasks and pinned-only tree ${cycle}`,'[data-open-objective-tasks]',
      `document.querySelector('.objective-working h2')?.textContent==='Tasks' && document.querySelectorAll('[data-resource-group="${doc.id}"] [data-objective-tab]').length===1`);
    const task=o.tasks.at(-1),checked=await evaluate(`document.querySelector('[data-task-done="${task.id}"]').checked`);
    await click(`task checkbox ${cycle}`,`[data-task-done="${task.id}"]`,
      `document.querySelector('[data-task-done="${task.id}"]')?.checked===${!checked}`);
    await until(`fetch(${q(objectiveUrl)}).then(r=>r.json()).then(d=>d.objectives.find(o=>o.id===${q(o.id)}).tasks.find(t=>t.id===${q(task.id)}).done===${!checked})`);
    await click(`workspace Root final files ${cycle}`,'[data-select-worktree="workspace-root"]',
      `document.querySelector('[data-select-worktree="workspace-root"]')?.getAttribute('aria-pressed')==='true' && document.querySelector('[data-new-file-root]')?.dataset.newFileRoot===${q(workspace)} && document.querySelector('#sidebar .sidebar-file[data-open-file]') && !document.querySelector('#sidebar').classList.contains('sidebar-scope-switching')`);
    await click(`Objective folder final files ${cycle}`,'[data-select-worktree="objective-root"]',
      `document.querySelector('[data-select-worktree="objective-root"]')?.getAttribute('aria-pressed')==='true' && document.querySelector('[data-new-file-root]')?.dataset.newFileRoot===${q(o.path)} && document.querySelector('#sidebar .sidebar-file[data-open-file]') && !document.querySelector('#sidebar').classList.contains('sidebar-scope-switching')`);
    if(o.worktrees[1])await click(`worktree final files ${cycle}`,`[data-select-worktree="${o.worktrees[1].id}"]`,
      `document.querySelector('[data-select-worktree="${o.worktrees[1].id}"]')?.getAttribute('aria-pressed')==='true' && document.querySelector('[data-project-sidebar]')?.dataset.projectSidebar===${q(o.worktrees[1].path)} && document.querySelector('[data-project-directory="."] [data-project-entry]') && !document.querySelector('#sidebar').classList.contains('sidebar-scope-switching')`);
    await click(`notebook final cells ${cycle}`,`[data-objective-resource="${nb.id}"]`,
      `document.querySelector('.nb-notebook-path')?.textContent===${q(nb.path)} && document.querySelectorAll('#content .nb-cell').length>=2 && document.querySelector('#content .nb-cell[data-cell-type=code]')`);
    const reference=o.resources.find(r=>r.kind==='assistant'&&r.content?.tabs.length);
    if(reference){
      await click(`Assistant reference ${cycle}`,`[data-objective-resource="${reference.id}"]:not([data-objective-tab])`,
        `document.querySelector('.assistant-document-inline.active #assistantModalTitle')?.textContent===${q(reference.title)} && document.querySelector('#sidebar').getBoundingClientRect().width>0`);
      await click(`Assistant subtab ${cycle}`,`[data-objective-tab="${reference.content.tabs[0].id}"]`,
        `document.querySelector('.assistant-document-inline.active #assistantModalTitle')?.textContent===${q(reference.content.tabs[0].title)} && document.querySelector('#sidebar').getBoundingClientRect().width>0`);
    }
    const own='objective-staging-'+o.name.split(' · ')[1].split(' ')[0];
    if(o===focused[0])await click(`linked terminal and document ${cycle}`,`[data-logical="${own}"]`,
      `termSessions.find(t=>t.name===termCurrentSession)?.logical_name===${q(own)} && document.querySelector('.objective-working h2')?.textContent==='Incident notes.md'`);
    // Reset pin by a separate measured click so every next trial starts unpinned.
    await click(`unpin subtab ${cycle}`,`[data-pin-tab="${tab.id}"]`,
      `document.querySelector('[data-pin-tab="${tab.id}"]')?.getAttribute('aria-pressed')==='false' || !document.querySelector('[data-pin-tab="${tab.id}"]')`);
  }
  const fonts=await evaluate(`({selector:getComputedStyle(document.querySelector('.objective-tab')).fontSize,resource:getComputedStyle(document.querySelector('.objective-resource')).fontSize,file:getComputedStyle(document.querySelector('.sidebar-file')).fontSize})`);
  const layout=await evaluate(`({tasksAtSidebarTop:document.querySelector('[data-objectives-sidebar]').firstElementChild.hasAttribute('data-open-objective-tasks'),focusSlots:document.querySelectorAll('[data-objective-slot]').length,sidebarSelectors:document.querySelectorAll('.objective-selectors').length,roots:[...document.querySelectorAll('[data-objective-root]')].map(n=>({label:n.querySelector('button').textContent.trim(),color:n.style.getPropertyValue('--sidebar-workspace-color')})),terminalBorders:[...document.querySelectorAll('.objective-terminal-group')].map(n=>({top:getComputedStyle(n).borderTopWidth,right:getComputedStyle(n).borderRightWidth,bottom:getComputedStyle(n).borderBottomWidth,left:getComputedStyle(n).borderLeftWidth})),worktreeLabels:document.querySelectorAll('.objective-terminal-worktree > span:not(.sess)').length})`);
  if(!layout.tasksAtSidebarTop||layout.focusSlots!==5||layout.sidebarSelectors||layout.roots.length!==2||layout.roots.some(r=>r.color!=='#8b949e')||layout.worktreeLabels||layout.terminalBorders.some(b=>b.top!=='0px'||b.right!=='0px'||b.bottom!=='0px'||b.left!=='2px'))throw Error('Objective layout requirements failed: '+JSON.stringify(layout));
  const network=await evaluate(`performance.getEntriesByType('resource').filter(r=>['/api/objectives','/api/sidebar-directory','/api/sidebar-recent-files'].some(path=>new URL(r.name).pathname===path)).map(r=>({url:new URL(r.name).pathname,ms:r.duration}))`);
  const max=Math.max(...rows.map(r=>r.ms)),failures=rows.filter(r=>r.ms>=200);
  const report={workspace,normalPolling:true,physicalDisplayLatency:false,fonts,layout,clicks:rows,network,errors,maxMs:max,failures:failures.map(r=>({label:r.label,ms:r.ms}))};
  await writeFile(output,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({samples:rows.length,maxMs:max,over200ms:failures.length,errors,fonts,report:output}));
  if(failures.length||errors.length)process.exitCode=1;
} catch(error){await writeFile(output,JSON.stringify({clicks:rows,errors,error:String(error)},null,2));throw error;}
finally{ws?.close();chrome.kill();await sleep(200);await rm(profile,{recursive:true,force:true});}
