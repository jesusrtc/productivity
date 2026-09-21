"""Real xterm lifecycle in Chrome; fake transport prevents agent/API calls."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import pytest
from .test_assistant_documents_unified import library

ROOT=Path(__file__).resolve().parents[2]
STATIC=ROOT/'core/src/core/static'


@pytest.mark.parametrize('viewport', [1440, 390])
def test_document_terminal_browser(client, library, tmp_path, viewport):
    chrome=os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node=shutil.which('node')
    if not Path(chrome).is_file() or not node:pytest.skip('Chrome and Node required')
    root,task,note,tab,*_=library
    paths={key:path.relative_to(root).as_posix() for key,path in [('task',task),('note',note),('tab',tab)]}
    details={path:client.get('/api/assistant/note',params={'path':path}).json() for path in paths.values()}
    fixtures={'paths':paths,'details':details,'index':client.get('/api/assistant').json()}
    checks=r'''
const assert=(value,message)=>{if(!value)throw new Error(message)};
const until=async fn=>{for(let i=0;i<250;i++){if(fn())return;await new Promise(r=>setTimeout(r,5));}throw new Error('Timed out: '+fn)};
const counters={terminals:0,sockets:0,peakTerminals:0,peakSockets:0,created:0,opened:0,activity:0};
const intervals=new Map(),activityTimers=new Map();let timerId=50000;
const realInterval=window.setInterval,realClearInterval=window.clearInterval;
window.setInterval=(fn,delay)=>{if(delay===30000){intervals.set(++timerId,fn);return timerId;}return realInterval(fn,delay)};
window.clearInterval=id=>{intervals.delete(id);realClearInterval(id)};
const realTimeout=window.setTimeout,realClearTimeout=window.clearTimeout;
window.setTimeout=(fn,delay,...args)=>{if(delay===30000){activityTimers.set(++timerId,fn);return timerId;}return realTimeout(fn,delay,...args)};
window.clearTimeout=id=>{activityTimers.delete(id);realClearTimeout(id)};
const OriginalTerminal=Terminal;
window.Terminal=class extends OriginalTerminal {
 constructor(options){super(options);++counters.terminals;++counters.created;counters.peakTerminals=Math.max(counters.terminals,counters.peakTerminals);window.latestTerminal=this;}
 dispose(){--counters.terminals;super.dispose();}
};
window.ensureTerminalLibs=async()=>{};
let latestSocket;
window.WebSocket=class {
 static OPEN=1;
 constructor(url){this.url=url;this.readyState=1;this.messages=[];latestSocket=this;++counters.sockets;counters.peakSockets=Math.max(counters.sockets,counters.peakSockets);queueMicrotask(()=>this.onmessage?.({data:JSON.stringify({type:'data',data:'Document agent ready.\r\n> '})}));}
 send(data){this.messages.push(JSON.parse(data));}
 close(){if(this.readyState===1){this.readyState=3;--counters.sockets;}}
};
let hidden=false;Object.defineProperty(document,'hidden',{get:()=>hidden});
let policy={enabled:true,sleepMinutes:60,expireHours:36,maxRunning:3},forcedError='',savedSettings=0;
const managed=new Map();
window.fetch=async(url,options={})=>{
 const u=new URL(url,'https://lab.example');
 if(u.pathname==='/api/assistant/document-terminal/settings'){
  if(options.method==='POST'){policy=JSON.parse(options.body);++savedSettings;}
  return {ok:true,json:async()=>({...policy})};
 }
 if(u.pathname==='/api/assistant/document-terminal'){
  const {path,action}=JSON.parse(options.body),detail=FIX.details[path],key=detail.root_path||path;
  if(action==='open'){
   ++counters.opened;
   if(forcedError)return {ok:false,json:async()=>({detail:forcedError})};
   managed.set(key,{key,name:'managed-'+key,state:policy.enabled?'running':'disabled',agent:'codex',policy});
  }
  if(action==='sleep')managed.get(key).state='sleeping';
  if(action==='activity')++counters.activity;
  return {ok:true,json:async()=>({...managed.get(key),policy})};
 }
 if(u.pathname==='/api/assistant')return {ok:true,json:async()=>structuredClone(FIX.index)};
 const detail=FIX.details[u.searchParams.get('path')];
 return {ok:!!detail,json:async()=>structuredClone(detail||{detail:'Missing record'})};
};
const host=()=>document.getElementById('assistantDocumentTerminal');
const poll=async()=>{for(const fn of intervals.values())fn();await new Promise(r=>realTimeout(r,10));};
(async()=>{
 AssistantView.init({section:'documents'});
 await until(()=>document.querySelector('[data-assistant-document]'));
 assert(counters.opened===0,'dashboard never spawns agents');
 document.querySelector('[data-assistant-view="all"]').click();
 document.querySelector(`[data-assistant-document="${FIX.paths.note}"]`).click();
 await until(()=>counters.sockets===1);
 assert(counters.terminals===1&&latestSocket.url.includes('cols=')&&latestSocket.url.includes('rows='),'one renderer and real connection geometry');
 const initialName=latestSocket.url,initialCreated=counters.created;
 const bounds=host().getBoundingClientRect();assert(bounds.width>200&&bounds.right<=innerWidth+1&&bounds.left>=0,'terminal fits viewport');
 host().querySelector('.xterm-helper-textarea').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
 assert(document.querySelector('#assistantDocumentModal.active'),'Escape belongs to terminal while typing');
 document.querySelector(`#assistantDocumentNav [data-record-path="${FIX.paths.tab}"]`).click();
 await until(()=>counters.opened===2);
 assert(counters.created===initialCreated&&latestSocket.url===initialName,'subtabs share terminal');
 latestTerminal.paste('hello');
 await until(()=>latestSocket.messages.some(message=>message.type==='input'&&message.data==='hello'));
 host().querySelector('.assistant-terminal-screen').dispatchEvent(new WheelEvent('wheel',{deltaY:100,bubbles:true,cancelable:true}));
 assert(latestSocket.messages.some(message=>message.data?.startsWith('\x1b[<65;')),'wheel reaches tmux');
 for(let i=0;i<100;i++)host().dispatchEvent(new Event('pointerdown'));
 assert(activityTimers.size===1&&counters.activity===0,'input coalesces without immediate HTTP');
 for(const [id,fn] of activityTimers){activityTimers.delete(id);fn();}
 await until(()=>counters.activity===1);
 const opensBefore=counters.opened;
 await poll();await poll();assert(counters.opened===opensBefore,'status polling never starts agents');
 host().querySelector('[data-terminal-sleep]').click();
 await until(()=>counters.sockets===0);
 assert(counters.terminals===0&&host().textContent.includes('memory released'),'sleep disposes renderer');
 host().querySelector('[data-terminal-wake]').click();await until(()=>counters.sockets===1);
 hidden=true;document.dispatchEvent(new Event('visibilitychange'));
 assert(counters.sockets===0&&counters.terminals===0,'hidden page releases browser resources');
 hidden=false;document.dispatchEvent(new Event('visibilitychange'));await until(()=>counters.sockets===1);
 latestSocket.onclose();assert(counters.sockets===0,'closed socket released');
 const disconnected=counters.created;await poll();await poll();
 assert(counters.created===disconnected&&!host().querySelector('[data-terminal-wake]').hidden,'closed connection requires deliberate retry');
 host().querySelector('[data-terminal-wake]').click();await until(()=>counters.sockets===1);
 for(let i=0;i<24;i++){
  LabDocumentTerminal.open(FIX.details[i%2?FIX.paths.note:FIX.paths.task]);
  await until(()=>counters.sockets===1);
 }
 assert(counters.peakSockets===1&&counters.peakTerminals===1,'document switches never accumulate renderers or sockets');
 LabDocumentTerminal.close();
 assert(!counters.sockets&&!counters.terminals&&!intervals.size&&!activityTimers.size,'closing disposes timers too');
 forcedError='All three agents are working. Try again later.';
 LabDocumentTerminal.open(FIX.details[FIX.paths.note]);
 await until(()=>host().textContent.includes('All three'));
 assert(!counters.sockets&&!host().querySelector('[data-terminal-wake]').hidden,'capacity errors are retryable');
 forcedError='';host().querySelector('[data-terminal-wake]').click();await until(()=>counters.sockets===1);
 host().querySelector('[data-terminal-settings]').click();
 await until(()=>document.querySelector('#documentTerminalSettings [type="submit"]:not([disabled])'));
 const form=document.querySelector('#documentTerminalSettings form');
 assert(form.elements.sleepMinutes.value==='60'&&form.elements.expireHours.value==='36'&&form.elements.maxRunning.value==='3','conservative configurable defaults');
 form.elements.sleepMinutes.value='20';form.elements.maxRunning.value='2';form.requestSubmit();
 await until(()=>savedSettings===1&&!document.getElementById('documentTerminalSettings'));
 assert(policy.sleepMinutes===20&&policy.maxRunning===2,'settings saved in Assistant scope');
 AssistantView.closeDocument();assert(!counters.sockets&&!counters.terminals,'document close releases everything');
 policy.enabled=false;LabDocumentTerminal.open(FIX.details[FIX.paths.note]);
 await until(()=>host().textContent.includes('are off'));
 assert(!counters.sockets,'disabled policy never attaches');
 LabDocumentTerminal.close();policy.enabled=true;
 document.querySelector(`[data-assistant-document="${FIX.paths.note}"]`).click();
 await until(()=>counters.sockets===1);
 latestTerminal.write('This terminal follows the document.\r\nSleep after 1 hour · Remove after 36 hours\r\n');
 document.getElementById('result').textContent='PASS '+JSON.stringify(counters);
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    scripts='\n'.join('<script>'+ (STATIC/path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js','vendor/dompurify@3.4.15/purify.min.js',
        'vendor/xterm@5.3.0/xterm.min.js','vendor/xterm-addon-fit@0.8.0/xterm-addon-fit.min.js',
        'js/lib/markdown-content.js','js/views/assistant.js','js/lib/document-terminal.js'])
    app=(STATIC/'js/lab-app.js').read_text()
    guard=app[app.index('  function _termGuardViewportDisposal('):app.index('  function termEnsureXterm(')]
    page=tmp_path/'document-terminal.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>'+ (STATIC/'css/lab-shell.css').read_text()+(STATIC/'vendor/xterm@5.3.0/xterm.min.css').read_text()+
       '</style><body class="assistant-active"><div id="repoTabs"></div><div id="content"></div><pre id="result">PENDING</pre>'+scripts+'<script>'+guard+'\nconst FIX='+json.dumps(fixtures).replace('</','<\\/')+';\n'+checks+'</script>')
    profile=tmp_path/'chrome-profile'
    process=subprocess.Popen([chrome,'--headless','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check','--allow-file-access-from-files','--user-data-dir='+str(profile),'--remote-debugging-port=0','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline
            time.sleep(.05)
        driver=tmp_path/'browser.mjs'
        driver.write_text((ROOT/'scripts/chrome-dump-auth.mjs').read_text().replace('width: 1440,','width: '+str(viewport)+','))
        result=subprocess.run([node,str(driver),str(profile),page.as_uri(),str(tmp_path/'dom.html'),str(tmp_path/'document-terminal.png')],capture_output=True,text=True,timeout=30,env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        assert result.returncode==0,result.stderr
        html=(tmp_path/'dom.html').read_text()
    finally:
        process.terminate();process.wait(timeout=5)
    result=re.search(r'<pre id="result">(.*?)</pre>',html,re.S)
    assert result and result[1].startswith('PASS '),result[1] if result else html[-1500:]
    print(tmp_path/'document-terminal.png',result[1])
