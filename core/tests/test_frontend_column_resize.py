"""Terminal panel widths belong to the workspace that was resized."""
import pytest

from .test_frontend_terminal_ui import _js_between, _run_node


def column_helpers():
    return _js_between('  function _termVisibilityKey()', '  async function termRefreshSessions(')


def test_terminal_widths_restore_per_workspace_and_cancel_cross_workspace_drags():
    result = _run_node(r'''
const stored={labTermPct:'36','labSidebarPct:workspace:alpha':'17','labSidebarPct:workspace:beta':'22'};
const styles={},classes=new Set(['workspace-active']),listeners={};
const classList={contains:name=>classes.has(name),add:name=>classes.add(name),remove:name=>classes.delete(name),
  toggle(name,on){if(on)classes.add(name);else classes.delete(name);}};
const root={style:{setProperty:(key,value)=>styles[key]=value,removeProperty:key=>delete styles[key]}};
const resizer={classList,events:{},addEventListener(type,callback){this.events[type]=callback;}};
const sidebarResizer={...resizer,events:{}};
const document={body:{classList},documentElement:root,getElementById:id=>id==='termResizer'?resizer:id==='sidebarResizer'?sidebarResizer:{},
  addEventListener(type,callback){(listeners[type]??=[]).push(callback);}};
window.innerWidth=1440;window.addEventListener=()=>{};
let currentWorkspace={name:'alpha',path:'/one/alpha',is_workspace:true},_workspaceDocPath=null;
const termXterm=null,termFitAddon=null,_resetSidebarLayout=()=>{},_primeSidebarLayout=()=>{};
const _TERM_VIS_KEY_PREFIX='labTermShown:',_TERM_PCT_KEY_PREFIX='labTermPct:';
const _SIDEBAR_VIS_KEY_PREFIX='labSidebarShown:',_SIDEBAR_PCT_KEY_PREFIX='labSidebarPct:';
const _termHomeViewActive=()=>classes.has('self-active')||classes.has('vault-active');
const _termSessionsKey=name=>'vault::'+name;
let denyWrites=false;
const localStorage={getItem:key=>stored[key]??null,setItem(key,value){if(denyWrites)throw Error('storage unavailable');stored[key]=value;}};
const getComputedStyle=()=>({getPropertyValue:key=>styles[key]??(key==='--term-width'?'40%':'10%')});
const emit=(type,event)=>listeners[type].forEach(callback=>callback(event));
const event=x=>({clientX:x,preventDefault(){}});
''' + column_helpers() + r'''
const snapshots={};
const width=()=>parseFloat(getComputedStyle(root).getPropertyValue('--term-width'));
const drag=pct=>{const start=width();resizer.events.mousedown(event(1000));emit('mousemove',event(1000+(start-pct)*14.4));emit('mouseup',event(0));};
const go=(name,path)=>{classes.clear();classes.add('workspace-active');currentWorkspace={name,path,is_workspace:true};_workspaceDocPath=null;_termApplyRememberedVisibility();};
snapshots.initial=width();
drag(45);snapshots.alpha=width();
const alphaKey=_termWidthKey();
go('beta','/one/beta');snapshots.betaInitial=width();drag(30);
const betaKey=_termWidthKey();
go('alpha','/one/alpha');snapshots.alphaRestored=width();snapshots.alphaFiles=styles['--sidebar-width'];
go('alpha','/two/alpha');snapshots.sameNameOtherVault=width();
go('alpha','/one/alpha');_workspaceDocPath='__proxy__/web';_termApplyRememberedVisibility();snapshots.proxy=width();
for(const view of ['self','assistant','vault','cerebro']){
  classes.clear();classes.add(view+'-active');_termApplyRememberedVisibility();drag(32);
  snapshots[view]=parseFloat(stored[_termWidthKey()]);
}
go('beta','/one/beta');snapshots.betaRestored=width();snapshots.betaFiles=styles['--sidebar-width'];
go('alpha','/one/alpha');resizer.events.mousedown(event(1000));
go('beta','/one/beta');emit('mousemove',event(700));emit('mouseup',event(0));
snapshots.afterInterruptedDrag=width();
snapshots.dragClassCleared=!classes.has('term-resizing');
denyWrites=true;drag(34);denyWrites=false;snapshots.deniedWrite=width();
delete stored.labTermPct;
go('untouched','/one/untouched');snapshots.noLegacy=width();snapshots.inlineCleared=!styles['--term-width'];
stored[_termWidthKey()]='150';_termApplyWidthForView();snapshots.invalidStored=width();
go('alpha','/one/alpha');delete styles['--term-width'];_termApplyRememberedVisibility();snapshots.reload=width();
console.log(JSON.stringify({snapshots,alphaSaved:stored[alphaKey],betaSaved:stored[betaKey],
  globalWritten:Object.hasOwn(stored,'labTermPct'),files:stored['labSidebarPct:workspace:alpha']}));
''')
    snapshots = result['snapshots']
    expected = {
        'initial': 36, 'alpha': 45, 'betaInitial': 36, 'alphaRestored': 45,
        'alphaFiles': '17%', 'sameNameOtherVault': 36, 'proxy': 45,
        'self': 32, 'assistant': 32, 'vault': 32, 'cerebro': 32,
        'betaRestored': 30, 'betaFiles': '22%', 'afterInterruptedDrag': 30,
        'dragClassCleared': True, 'deniedWrite': 34, 'noLegacy': 40,
        'inlineCleared': True, 'invalidStored': 40, 'reload': 45,
    }
    assert snapshots.keys() == expected.keys()
    for key, value in expected.items():
        assert snapshots[key] == (pytest.approx(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value)
    assert float(result['alphaSaved']) == pytest.approx(45)
    assert float(result['betaSaved']) == pytest.approx(30)
    assert result['globalWritten'] is False and result['files'] == '17'


def test_terminal_panel_widths_persist_with_native_drag_and_reload(tmp_path):
    import os
    from pathlib import Path
    import shutil
    import subprocess
    import time
    from .test_frontend_terminal_ui import ROOT, LAB_SHELL_CSS

    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    prelude = r'''
let currentWorkspace={name:'alpha',path:'/vault-one/alpha',is_workspace:true},_workspaceDocPath=null;
const termXterm=null,termFitAddon=null,_resetSidebarLayout=()=>{},_primeSidebarLayout=()=>{},termSendResize=()=>{};
const _TERM_VIS_KEY_PREFIX='labTermShown:',_TERM_PCT_KEY_PREFIX='labTermPct:';
const _SIDEBAR_VIS_KEY_PREFIX='labSidebarShown:',_SIDEBAR_PCT_KEY_PREFIX='labSidebarPct:';
const _termHomeViewActive=()=>document.body.classList.contains('self-active');
const _termSessionsKey=name=>'vault::'+name;
localStorage.setItem('labTermPct','36');
localStorage.setItem('labSidebarPct:workspace:alpha','17');
localStorage.setItem('labSidebarPct:workspace:beta','22');
function go(name){
  currentWorkspace={name,path:'/vault-one/'+name,is_workspace:true};_workspaceDocPath=null;
  document.body.className=(name==='assistant'?'assistant-active':'workspace-active')+' term-open';
  _termApplyRememberedVisibility();
  document.getElementById('scope').textContent=name;
}
'''
    html = ('<!doctype html><style>' + LAB_SHELL_CSS.read_text() + '</style>'
            '<body class="workspace-active term-open"><div style="position:fixed;top:10px;z-index:100">'
            '<button id="alpha" onclick="go(\'alpha\')">Alpha</button><button id="beta" onclick="go(\'beta\')">Beta</button>'
            '<button id="assistant" onclick="go(\'assistant\')">Assistant</button></div>'
            '<div class="layout"><aside class="sidebar" id="sidebar">Files</aside><div class="sidebar-resizer" id="sidebarResizer"></div>'
            '<main class="main" id="content"><h1 id="scope">alpha</h1><p>Each workspace keeps its own terminal width.</p></main></div>'
            '<section class="term-panel" id="termPanel"><div class="term-resizer" id="termResizer"></div><div class="term-header">Terminal</div></section>'
            '<script>' + prelude + column_helpers() + '_termApplyRememberedVisibility();</script>')
    page = tmp_path / 'columns.html'
    page.write_text(html)
    checks = r'''
async function evaluate(expression){
 const response=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
 if(response.exceptionDetails)throw Error(response.exceptionDetails.exception?.description||'Evaluation failed');
 return response.result.value;
}
const close=(actual,expected)=>Math.abs(actual-expected)<.1;
const width=()=>evaluate('document.getElementById("termPanel").getBoundingClientRect().width/innerWidth*100');
async function click(id){
 const point=await evaluate(`(()=>{const r=document.getElementById(${JSON.stringify(id)}).getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
 await send('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1});
 await send('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1});
}
async function drag(pct){
 const point=await evaluate(`(()=>{const r=document.getElementById('termResizer').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+100,delta:(parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--term-width'))-${pct})/100*innerWidth};})()`);
 await send('Input.dispatchMouseEvent',{type:'mousePressed',x:point.x,y:point.y,button:'left',clickCount:1});
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:point.x+point.delta,y:point.y,button:'left',buttons:1});
 await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:point.x+point.delta,y:point.y,button:'left',clickCount:1});
 if(!close(await width(),pct))throw Error('Native drag did not reach '+pct+'%');
}
if(!close(await width(),36))throw Error('Legacy width was not preserved');
await drag(45);
await click('beta');
if(!close(await width(),36))throw Error('New workspace borrowed Alpha width');
await drag(30);
await click('alpha');
if(!close(await width(),45))throw Error('Alpha width was not restored');
await click('assistant');
if(!close(await width(),36))throw Error('Assistant borrowed a workspace width');
await drag(42);
await click('beta');
if(!close(await width(),30))throw Error('Beta width was not restored');
await click('assistant');
if(!close(await width(),42))throw Error('Assistant width was not restored');
if(!await evaluate("localStorage.getItem('labTermPct')==='36' && localStorage.getItem('labSidebarPct:workspace:alpha')==='17' && localStorage.getItem('labSidebarPct:workspace:beta')==='22'"))throw Error('Terminal drag overwrote other preferences');
const oldOrigin=await evaluate('performance.timeOrigin');
await send('Page.reload');
for(let i=0;i<100;i++){
 try{if(await evaluate(`performance.timeOrigin!==${oldOrigin} && document.getElementById('scope')?.textContent==='alpha'`))break;}catch{}
 await new Promise(resolve=>setTimeout(resolve,25));
}
if(!close(await width(),45))throw Error('Reload did not restore Alpha width');
await click('beta');
if(!close(await width(),30))throw Error('Reload lost Beta width');
await evaluate("document.body.dataset.result='pass'");
'''
    driver = tmp_path / 'columns.mjs'
    driver.write_text((ROOT / 'scripts/chrome-dump-auth.mjs').read_text().replace(
        "const evaluated = await send('Runtime.evaluate', {", checks + "\nconst evaluated = await send('Runtime.evaluate', {"))
    profile = tmp_path / 'profile'
    browser = subprocess.Popen([chrome,'--headless=new','--no-first-run','--disable-background-networking',
                                '--user-data-dir='+str(profile),'--remote-debugging-port=0','about:blank'],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert browser.poll() is None and time.monotonic() < deadline
            time.sleep(.05)
        rendered = tmp_path / 'dom.html'
        subprocess.run(['node',str(driver),str(profile),page.as_uri(),str(rendered),str(tmp_path/'columns.png')],
                       check=True,timeout=25,env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        assert 'data-result="pass"' in rendered.read_text(), rendered.read_text()[-1000:]
    finally:
        browser.terminate()
        browser.wait(timeout=5)
