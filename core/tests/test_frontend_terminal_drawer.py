"""Native pointer events distinguish a quick crossing from deliberate tab use."""
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'core/src/core/static'


def test_terminal_drawer_keeps_names_until_console_click(tmp_path):
    chrome = os.environ.get('CHROME_BIN') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    app = (STATIC/'js/lab-app.js').read_text()
    def between(start, end):
        at = app.index(start)
        return app[at:app.index(end, at)]
    helpers = between("  const _TERM_SESSION_ORIENTATION_KEY", '  function _termRecentWindowLabel')
    helpers += between('  function termSetSessionView(', '  // Apply before the initial route dispatch')
    template = (ROOT/'core/src/core/templates/index.html').read_text()
    switcher = template[template.index('    <div class="term-session-switcher"'):template.index('    <div class="term-console">')]
    rows = ''.join('<span class="sess" role="tab" tabindex="0"><span class="sess-icon">🧠</span>'
                   '<span class="sess-label">Terminal '+str(i)+'</span><span class="sess-activity sess-working"></span></span>' for i in range(30))
    switcher = switcher.replace('aria-orientation="vertical"></div>', 'aria-orientation="vertical">'+rows+'</div>', 1)
    css = ''.join((STATIC/path).read_text() for path in ['css/lab-shell.css','vendor/xterm@5.3.0/xterm.min.css'])
    scripts = ''.join('<script>'+(STATIC/path).read_text()+'</script>' for path in ['vendor/xterm@5.3.0/xterm.min.js','vendor/xterm-addon-fit@0.8.0/xterm-addon-fit.min.js'])
    setup = r'''
window.errors=[];addEventListener('error',e=>errors.push(e.message));
const termXterm=new Terminal({fontSize:14}),termFitAddon=new FitAddon.FitAddon();
let fits=0;const fit=termFitAddon.fit.bind(termFitAddon);termFitAddon.fit=()=>{fits++;fit()};
const termSendResize=()=>{},_termHideSessionTooltip=()=>{};
termXterm.loadAddon(termFitAddon);termXterm.open(document.getElementById('termBody'));
termXterm.onData(text=>termXterm.write(text));termXterm.write('Terminal width stays fixed.\r\n$ ');
document.getElementById('termSessionList').addEventListener('click',()=>termXterm.focus());
'''
    page = tmp_path/'drawer.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>'+css+
                    ' .term-panel{width:680px}.term-body{overflow:hidden}</style><body class="term-open">'
                    '<button id="files">Files</button><section id="termPanel" class="term-panel"><div class="term-header">Terminal</div><div class="term-stage">'+
                    switcher+'<div class="term-console"><div class="term-status">Attached</div><div id="termBody" class="term-body"></div></div></div></section>'+
                    scripts+'<script>'+setup+helpers+'_termApplySessionView(false);_termInitSessionDrawer();_termInitSessionResize();termFitAddon.fit();</script>')
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
 const move=p=>send('Input.dispatchMouseEvent',{type:'mouseMoved',...p});
 async function click(p){await move(p);await send('Input.dispatchMouseEvent',{type:'mousePressed',...p,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...p,button:'left',clickCount:1});}
 const state=()=>evaluate(`(()=>{const rail=document.getElementById('termSessionList'),switcher=document.getElementById('termSessionSwitcher'),console=document.querySelector('.term-console');return{open:switcher.classList.contains('term-tabs-open'),pinned:switcher.classList.contains('term-tabs-pinned'),width:rail.getBoundingClientRect().width,consoleX:console.getBoundingClientRect().x,cols:termXterm.cols,errors}})()`);
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:process.argv[2]});await send('Page.bringToFront');
 for(let i=0;i<200;i++){if(await evaluate('!!document.querySelector(".xterm-screen")'))break;await sleep(20)}
 await sleep(100);
 const points=await evaluate(`(()=>{const rail=document.getElementById('termSessionList').getBoundingClientRect(),body=document.getElementById('termBody').getBoundingClientRect(),files=document.getElementById('files').getBoundingClientRect();return{rail:{x:rail.x+20,y:rail.y+20},console:{x:body.right-80,y:body.y+80},files:{x:files.x+20,y:files.y+10}}})()`);
 const baseline=await state();assert(baseline.width===62&&!baseline.open,'initial icon rail');
 assert(await evaluate('termTabHoverPinSeconds===3'),'three second default');
 await move(points.rail);assert((await state()).open,'hover shows names immediately');
 await sleep(200);await move(points.files);assert(!(await state()).open,'quick crossing to Files closes names');
 await sleep(3100);assert(!(await state()).open,'leaving cancels delayed keep-open');
 await click(points.rail);await move(points.files);
 assert((await state()).pinned&&(await state()).open,'tab click keeps names while moving to Files');
 await evaluate('document.getElementById("files").focus()');assert((await state()).open,'focus outside rail preserves deliberate open state');
 const edge=await evaluate(`(()=>{const r=document.getElementById('termSessionList').getBoundingClientRect();return{x:r.right-2,y:r.y+80}})()`);
 await move(edge);await click(edge);assert((await state()).open,'full right edge and scrollbar stay active');
 await click(points.console);assert(!(await state()).open&&!(await state()).pinned,'console click closes names');
 await send('Input.insertText',{text:'native input'});await sleep(50);
 assert(await evaluate('termXterm.buffer.active.getLine(1).translateToString().includes("native input")'),'console remains writable');
 await move(points.rail);await sleep(3200);await move(points.files);
 assert((await state()).pinned&&(await state()).open,'default sustained hover keeps names after leaving');
 const expanded=await state();assert(expanded.cols===baseline.cols&&expanded.consoleX===baseline.consoleX,'drawer preserves terminal grid');
 await click(points.console);
 await evaluate('termSetTabHoverPinSeconds(0.4)');
 assert(await evaluate('localStorage.getItem("labTermTabHoverPinSeconds")==="0.4"'),'configured delay persisted');
 await move(points.rail);await sleep(120);await move(points.files);assert(!(await state()).open,'crossing below configured delay closes');
 await move(points.rail);await sleep(450);await move(points.files);assert((await state()).pinned,'configured delay applied');
 await click(points.console);
 await send('Page.reload');await sleep(200);
 assert(await evaluate('termTabHoverPinSeconds===0.4'),'configured delay restored on reload');
 await move(points.rail);await sleep(450);await move(points.files);assert((await state()).pinned,'restored delay pins after hover');
 await evaluate('termSetSessionView("orientation","horizontal")');assert(!(await state()).open&&!(await state()).pinned,'horizontal layout resets drawer state');
 await evaluate('termSetSessionView("orientation","vertical");termSetTabHoverPinSeconds(0)');
 await move(points.console);await move(points.rail);await sleep(30);await move(points.files);assert((await state()).pinned,'zero delay keeps names immediately');
 await click(points.console);await click(points.rail);
 await evaluate('document.getElementById("termSessionsResizer").focus()');
 await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 assert(!(await state()).open,'Escape retains keyboard dismissal');
 assert(!(await state()).errors.length,'no browser exceptions');ws.close();console.log('PASS');
})().catch(error=>{console.error(error.stack);process.exit(1)});
'''
    profile = tmp_path/'profile'
    process = subprocess.Popen([chrome,'--headless=new','--no-first-run','--disable-background-timer-throttling',
                                '--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows',
                                '--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline, 'Chrome did not start'
            time.sleep(.05)
        result = subprocess.run(['node','-e',driver,str(profile),page.as_uri()],capture_output=True,text=True,timeout=30)
        assert result.returncode == 0, result.stdout+result.stderr
        assert 'PASS' in result.stdout
    finally:
        process.terminate();process.wait(timeout=10)
