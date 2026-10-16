// Browser stage of lab_notification_latency.py. No terminal input is sent.
import {spawn} from 'node:child_process';
import {mkdtemp, readFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

const [base, count] = process.argv.slice(2);
if (!process.env.LAB_PROBE_COOKIE || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname))
  throw Error('Run through lab_notification_latency.py');
const profile = await mkdtemp(join(tmpdir(), 'lab-notification-'));
const chrome = spawn(process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ['--headless=new', '--no-first-run', '--disable-background-networking', '--remote-debugging-port=0',
    `--user-data-dir=${profile}`, 'about:blank'], {stdio:'ignore'});
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let ws;
try {
  let port;
  for (let i=0; i<100 && !port; i++) {
    if (chrome.exitCode !== null) throw Error('Owned Chrome exited before startup');
    try { port = Number((await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); } catch {}
    if (!port) await sleep(50);
  }
  if (!port) throw Error('Chrome did not publish its debugging port');
  const page = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {method:'PUT'}).then(r => r.json());
  ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, {once:true}); ws.addEventListener('error', reject, {once:true});
  });
  let sequence=0;
  const pending = new Map();
  ws.addEventListener('message', event => {
    const message = JSON.parse(event.data), request = pending.get(message.id);
    if (!request) return;
    pending.delete(message.id); clearTimeout(request.timer);
    if (message.error) request.reject(Error(message.error.message)); else request.resolve(message.result);
  });
  const send = (method, params={}) => new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => {pending.delete(id); reject(Error('CDP timeout: '+method));}, 20000);
    pending.set(id, {resolve, reject, timer}); ws.send(JSON.stringify({id, method, params}));
  });
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate', {expression, awaitPromise:true, returnByValue:true});
    if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  };
  await send('Network.enable');
  await send('Network.setCookie', {name:'lab_session', value:process.env.LAB_PROBE_COOKIE, url:base, httpOnly:true, sameSite:'Strict'});
  await send('Page.addScriptToEvaluateOnNewDocument', {source:"localStorage.setItem('labTermAutoSpawn','0');"});
  await send('Emulation.setDeviceMetricsOverride', {width:1440, height:1000, deviceScaleFactor:1, mobile:false});
  await send('Emulation.setFocusEmulationEnabled', {enabled:true});
  await send('Page.navigate', {url:base+'/?view=productivity'});
  let ready=false;
  for (let i=0; i<150 && !ready; i++) {
    ready = await evaluate('typeof LabTerminalNotifications!=="undefined" && LabTerminalNotifications.items().some(i=>i.owner.workspace_id==="__self__") && typeof termWS!=="undefined" && termWS?.readyState===1');
    if (!ready) await sleep(100);
  }
  if (!ready) throw Error('A live Home notification and terminal are required for this probe');
  const rows=[];
  for (let i=0; i<Number(count); i++) {
    const setup = await evaluate(`(async()=>{
      // Only this disposable browser's green-review state is reset.
      const saved=JSON.parse(localStorage.getItem('labTerminalReports-v1')||'{}');
      for(const row of Object.values(saved)){delete row.seen;delete row.seen_at;}
      localStorage.setItem('labTerminalReports-v1',JSON.stringify(saved));
      window.dispatchEvent(new StorageEvent('storage',{key:'labTerminalReports-v1'}));
      LabTerminalNotifications.render();
      const items=LabTerminalNotifications.items().filter(i=>i.owner.workspace_id==='__self__');
      const item=items.find(i=>i.state==='attention')||items[0];
      if(!item)throw Error('Home notification is no longer available');
      const other=termSessions.find(s=>s.name!==item.session.name);
      if(!other)throw Error('A second Home terminal is needed to measure a real switch');
      await _termActivateTab(other.name);
      await new Promise(resolve=>setTimeout(resolve,200));
      _termClearNotificationHighlight();
      const button=[...document.querySelectorAll('.term-notification')].find(n=>n.dataset.key===item.key);
      button.scrollIntoView({block:'nearest'});
      const box=button.getBoundingClientRect();
      window.__notificationProbe={name:item.session.name,key:item.key,start:performance.now()};
      return {x:box.x+box.width/2,y:box.y+box.height/2,state:item.state,
        cold:!_termCache.has(_termCacheKey('__self__',item.session.name))};
    })()`);
    await send('Input.dispatchMouseEvent', {type:'mousePressed',x:setup.x,y:setup.y,button:'left',clickCount:1});
    await send('Input.dispatchMouseEvent', {type:'mouseReleased',x:setup.x,y:setup.y,button:'left',clickCount:1});
    const result = await evaluate(`new Promise((resolve,reject)=>{
      const probe=window.__notificationProbe;
      const timeout=setTimeout(()=>reject(Error('Notification did not display its exact terminal')),15000);
      function output(xt){const b=xt.buffer.active;for(let r=b.viewportY;r<Math.min(b.length,b.viewportY+xt.rows);r++)if(b.getLine(r)?.translateToString(true))return true;return false;}
      function check(){
        const tab=document.querySelector('.term-notification-target');
        if(tab&&termCurrentSession===probe.name&&termCurrentWorkspaceId==='__self__'
            &&termWS?.readyState===1&&termContainer?.getClientRects().length
            &&LabTerminalCompletion.key(termSessions.find(s=>s.name===probe.name))===probe.key&&output(termXterm)){
          const xt=termXterm;
          // rAF + task observes a paint opportunity after real terminal output.
          requestAnimationFrame(()=>setTimeout(()=>{
            clearTimeout(timeout);resolve({ms:performance.now()-probe.start,
              focused:document.activeElement===xt.textarea,output:output(xt)});
          },0));return;
        }
        if(performance.now()-probe.start<15000)setTimeout(check,5);
      }check();
    })`);
    rows.push({sample:i,cold:setup.cold,state:setup.state,...result});
  }
  process.stdout.write(JSON.stringify(rows));
} finally {
  ws?.close();
  if (chrome.exitCode===null) {
    const exited=new Promise(resolve=>chrome.once('exit',resolve));chrome.kill('SIGTERM');await exited;
  }
  await rm(profile,{recursive:true,force:true});
}
