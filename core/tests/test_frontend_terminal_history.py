"""Request history uses native dialogs and expandable, bounded previews."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT/'core/src/core/static'


def helpers():
    app = (STATIC/'js/lab-app.js').read_text()
    start = app.index('  let _termRequestHistoryModal =')
    return app[start:app.index('  function _termSessionContext(', start)]


def test_only_submitted_known_slash_commands_are_captured():
    if not shutil.which('node'):
        pytest.skip('Node required')
    driver = r'''
const window={}, fetches=[];let queue=[];
const setTimeout=(f,t)=>{queue.push(f);return queue.length},clearTimeout=()=>{};
const fetch=(url,options)=>{fetches.push({url,options});return Promise.resolve({})};
const _termSessionMeta=name=>({name,agent:name==='shell'?null:'codex'}),_termVaultId=()=> 'local';
HELPERS
const assert=(ok,message)=>{if(!ok)throw Error(message)};
_termRequestSubmitted('one','workspace','Draft text');assert(!fetches.length&&!queue.length,'draft has no capture');
_termRequestSubmitted('one','workspace','\r');assert(!fetches.length&&queue.length===2,'ordinary Enter reconciles provider logs only');
_termRequestSubmitted('one','workspace','/cleaz');_termRequestSubmitted('one','workspace','\x7fr\r');
assert(JSON.parse(fetches[0].options.body).command==='/clear','backspace-edited command');
_termRequestSubmitted('one','workspace','\x1b[200~/new\x1b[201~');assert(fetches.length===1,'paste is unsent');
_termRequestSubmitted('one','workspace','\r');assert(JSON.parse(fetches[1].options.body).command==='/new','pasted command sent');
_termRequestSubmitted('one','workspace','\x1b[200~line one\n/clear\x1b[201~');
_termRequestSubmitted('one','workspace','\r');assert(fetches.length===2,'multiline text containing command is not clear');
_termRequestSubmitted('one','workspace','old text\x1b[D/clear\r');assert(fetches.length===2,'unknown cursor edits are not guessed');
_termRequestSubmitted('one','workspace','more than twenty characters');_termRequestSubmitted('one','workspace','/clear\r');
assert(fetches.length===2,'unknown draft persists across data chunks');
_termRequestSubmitted('one','workspace','discarded\x15/clear\r');assert(fetches.length===3,'Ctrl U resets command draft');
_termRequestSubmitted('shell','workspace','/clear\r');assert(fetches.length===3,'shell input is not agent history');
queue.forEach(f=>f());assert(fetches.filter(row=>!row.options).length>0,'Enter refreshes accepted logs');
assert(fetches.every(row=>!row.options||!row.options.body.includes('Draft text')),'typed drafts are never posted');
console.log('PASS');
'''.replace('HELPERS', helpers())
    result = subprocess.run(['node','-e',driver], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout+result.stderr


@pytest.mark.parametrize('width', [1440,390])
def test_history_dialog_native_click_keyboard_and_update(tmp_path, width):
    chrome = os.environ.get('CHROME_BIN') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    css = (STATIC/'css/lab-shell.css').read_text()
    setup = r'''
let termCurrentSession='one';const sessions={one:{name:'one',label:'Objective terminal'},two:{name:'two',label:'Other terminal'}};
const _termSessionMeta=name=>sessions[name],_termActiveWorkspaceId=()=> 'workspace',_termVaultId=()=> 'local',_termHideSessionTooltip=()=>{};
const _termSessionDisplay=s=>s.label,termSessEsc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const full='Line one\n\n'+('Long submitted text. '.repeat(80))+'\nFULL MESSAGE END <scr'+'ipt>literal</scr'+'ipt>';
const histories={one:[{id:1,type:'boundary',text:'Session started'},
 {id:2,type:'request',text:'Older request'},{id:3,type:'boundary',text:'Session cleared',command:'/clear'},
 {id:4,type:'request',text:full,timestamp:'2026-10-05T10:00:00Z'}],two:[{id:5,type:'request',text:'Only terminal two'}]};
const reads=[];window.errors=[];addEventListener('error',e=>errors.push(e.message));
const fetch=async url=>{const q=new URL(url,location.href).searchParams;reads.push(q.get('name'));return{ok:true,json:async()=>({entries:histories[q.get('name')]})}};
'''
    page = tmp_path/'history.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>'+css+
                    ':root{--bg-primary:#0d1117;--bg-secondary:#161b22;--text-primary:#e6edf3;--text-secondary:#8b949e;--border:#30363d;--accent:#58a6ff}body{background:#0d1117}</style>'+
                    '<button id="requests" class="term-status-summary-label" onclick="termOpenRequestHistory()">Requests</button><script>'+setup+helpers()+'</script>')
    driver = r'''
const fs=require('node:fs');
(async()=>{
 const assert=(ok,message)=>{if(!ok)throw Error(message)},sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const [port]=fs.readFileSync(process.argv[1]+'/DevToolsActivePort','utf8').split('\n');
 const target=await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'}).then(r=>r.json());
 const ws=new WebSocket(target.webSocketDebuggerUrl),pending=new Map();let sequence=0;
 ws.onmessage=event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
 await new Promise(r=>ws.addEventListener('open',r,{once:true}));
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||'Browser assertion');return r.result.value;}
 async function click(selector){const p=await evaluate(`(()=>{const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);await send('Input.dispatchMouseEvent',{type:'mousePressed',...p,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...p,button:'left',clickCount:1});}
 async function key(key,code,vk){await send('Input.dispatchKeyEvent',{type:'keyDown',key,code,windowsVirtualKeyCode:vk,...(key==='Enter'?{text:'\r',unmodifiedText:'\r'}:{})});await send('Input.dispatchKeyEvent',{type:'keyUp',key,code,windowsVirtualKeyCode:vk});}
 await send('Emulation.setDeviceMetricsOverride',{width:Number(process.argv[3]),height:900,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:process.argv[2]});await send('Page.bringToFront');await sleep(100);
 await click('#requests');await sleep(50);
 assert(await evaluate('!!document.querySelector("dialog:modal")'),'Requests click opens modal');
 assert(await evaluate('document.querySelector(".term-request-boundary:last-of-type")?.textContent.includes("/clear")||document.querySelector(".term-request-list").textContent.includes("Session cleared · /clear")'),'clear divider shown');
 assert(await evaluate('(()=>{const d=document.querySelector("dialog").getBoundingClientRect();return d.left>=0&&d.right<=innerWidth&&d.height<innerHeight})()'),'dialog fits viewport');
 assert(await evaluate('getComputedStyle(document.querySelector("[data-request-id=\\"4\\"] .term-request-preview")).webkitLineClamp==="3"'),'three line preview');
 await click('[data-request-id="4"] summary');
 assert(await evaluate('document.querySelector("[data-request-id=\\"4\\"]").open'),'native click unfolds full message');
 assert(await evaluate('document.querySelector("[data-request-id=\\"4\\"] pre").textContent===full'),'full original multiline text retained');
 assert(await evaluate('!document.querySelector("dialog script")'),'message HTML stays literal');
 await evaluate('histories.one.push({id:6,type:"request",text:"New submitted request"});_termLoadRequestHistory(_termRequestHistoryModal)');
 assert(await evaluate('document.querySelector("[data-request-id=\\"4\\"]").open'),'refresh preserves expanded request');
 await evaluate('termCurrentSession="two";_termLoadRequestHistory(_termRequestHistoryModal)');
 assert(await evaluate('reads.at(-1)==="one"'),'open modal remains tied to original terminal');
 await key('Escape','Escape',27);await sleep(50);assert(await evaluate('!document.querySelector("dialog")&&document.activeElement.id==="requests"'),'Escape closes and restores focus');
 await key('Enter','Enter',13);await sleep(30);
 assert(await evaluate('document.querySelector("dialog").textContent.includes("Only terminal two")&&!document.querySelector("dialog").textContent.includes("Older request")'),'keyboard opens selected terminal only');
 await click('.term-request-heading button');await sleep(30);assert(await evaluate('!document.querySelector("dialog")'),'close button works');
 assert(await evaluate('!errors.length'),'no browser exceptions');ws.close();console.log('PASS');
})().catch(error=>{console.error(error.stack);process.exit(1)});
'''
    profile = tmp_path/'profile'
    process = subprocess.Popen([chrome,'--headless=new','--no-first-run','--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'], stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline, 'Chrome did not start'
            time.sleep(.05)
        result = subprocess.run(['node','-e',driver,str(profile),page.as_uri(),str(width)],capture_output=True,text=True,timeout=20)
        assert result.returncode == 0, result.stdout+result.stderr
        assert 'PASS' in result.stdout
    finally:
        process.terminate();process.wait(timeout=10)
