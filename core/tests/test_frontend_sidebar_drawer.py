"""The first column stays compact while its live rows expand over the work area."""
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'core/src/core/static'


def test_sidebar_drawer_native_pointer_keyboard_resize_and_view_changes(tmp_path):
    chrome = os.environ.get('CHROME_BIN') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    app = (STATIC / 'js/lab-app.js').read_text()
    def between(start, end):
        at = app.index(start)
        return app[at:app.index(end, at)]
    helpers = between('  function _termVisibilityKey()', '  async function termRefreshSessions(')
    helpers += between('  function _termNormalizeTabHoverPinSeconds(', '  function _termNormalizeRecentMinutes(')
    helpers += between('  function _sidebarRecentSelectorsHtml()', '  async function sidebarSelectRecentMode(')
    helpers += between('  function _sidebarFilesTitle(', '  function _explorerContextFromRow(')
    helpers += between('  function _sidebarRecentSectionHtml(', '  function _sidebarConfigFolderCardHtml(')
    helpers += between('  function _agentContextSource(', '  // ─── Keep Alive and Lid Awake')
    helpers += between("  document.addEventListener('dragstart', event => {", '  function _termReflowSelection(')
    bridge = between('  window.LabSidebarDrawer?.connect({', '  _termApplyRecentSettings();')
    setup = r'''
window.errors=[];addEventListener('error',e=>errors.push(e.message));
const _TERM_VIS_KEY_PREFIX='labTermShown:',_TERM_PCT_KEY_PREFIX='labTermPct:';
const _SIDEBAR_VIS_KEY_PREFIX='labSidebarShown:',_SIDEBAR_PCT_KEY_PREFIX='labSidebarPct:';
const _TERM_TAB_HOVER_PIN_KEY='labTermTabHoverPinSeconds';
let termTabHoverPinSeconds=Number(localStorage.getItem(_TERM_TAB_HOVER_PIN_KEY)??3),_termSessionDrawer=null;
let currentWorkspace={name:'alpha',path:'/alpha',is_workspace:true},_workspaceDocPath=null;
const _termHomeViewActive=()=>false,_termSessionsKey=name=>name;
const _sidebarRecentSelectorValue=()=>'local-main',esc=v=>String(v),escAttr=esc;
const _canCreateExecutableNotebook=()=>false,_sidebarSortSelectHtml=()=>'',_sidebarScanStates=new Map(),_sidebarScanLabel=()=>'';
const _sidebarRecentTreeModel=files=>({folders:[],files}),symlinkClass=()=>'',symlinkTitle=()=>'',symlinkMarker=()=>'';
const fileIconHtml=()=>'<span class="ft-icon ft-md"></span>',_sidebarGitHistoryButtonHtml=()=>'';
const _explorerContextFromRow=()=>null;
let _workspaceDocEditing=false,_docModalEscHandler=null,_docModalFilesGeneration=0;
const closeDocModal=()=>document.getElementById('docViewModal').classList.remove('active');
let _termDragState=null,workspaceTabsDragId=null,termCurrentSession='context-target',termCurrentWorkspaceId='alpha';
const termWS={readyState:WebSocket.OPEN},nativePastes=[],explorerToast=message=>errors.push(message);
const guide='Lab framework context\nUse lab for tasks and notebooks.';
window.fetch=async()=>({ok:true,json:async()=>({content:guide})});
let resets=0,primes=0;
const _resetSidebarLayout=()=>resets++,_primeSidebarLayout=()=>primes++,termSendResize=()=>{};
const termXterm=new Terminal({fontSize:14}),termFitAddon=new FitAddon.FitAddon();
termXterm.loadAddon(termFitAddon);termXterm.open(document.getElementById('termBody'));
let selected=0;document.getElementById('selectedFile').addEventListener('click',()=>{selected++;termXterm.focus()});
function view(name){currentWorkspace={name,path:'/'+name,is_workspace:true};_termApplyRememberedVisibility();}
localStorage.setItem('labSidebarPct:workspace:alpha','24');
localStorage.setItem('labSidebarPct:workspace:beta','19');
localStorage.setItem('labSidebarShown:workspace:alpha','0');
'''
    rows = ''.join('<div class="sidebar-file" tabindex="0" title="File '+str(i)+'"><span class="ft-icon ft-md"></span><span class="sidebar-fname">File '+str(i)+'.md</span></div>' for i in range(45))
    css = ''.join((STATIC / p).read_text() for p in ['css/lab-shell.css', 'css/workspace-objectives.css', 'vendor/xterm@5.3.0/xterm.min.css'])
    vendors = ''.join('<script>'+(STATIC / p).read_text()+'</script>' for p in ['vendor/xterm@5.3.0/xterm.min.js', 'vendor/xterm-addon-fit@0.8.0/xterm-addon-fit.min.js'])
    template = (ROOT / 'core/src/core/templates/index.html').read_text()
    toggle = template[template.index('<div class="sidebar-toggle"'):template.index('\n', template.index('<div class="sidebar-toggle"'))]
    html = '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+css+'</style><body class="workspace-active has-repo-tabs term-open">'
    html += '<div class="topbar"><button id="beta" onclick="view(\'beta\')">Beta</button></div><div class="layout"><aside class="sidebar" id="sidebar">'
    html += '<div id="recentFilters"></div><div id="recentSection"></div><div id="filesTitle"></div><section data-sidebar-files-list><div id="selectedFile" class="sidebar-file" tabindex="0" title="Selected file"><span class="ft-icon ft-md"></span><span class="sidebar-fname">Selected file.md</span><button class="sidebar-actions">History</button></div>'+rows+'</section>'
    html += '<div class="objective-sidebar-task-list"><div class="objective-sidebar-task active"><button class="objective-sidebar-task-status">🚧</button><span class="objective-sidebar-task-compact-icon" aria-hidden="true">🚧</span><a class="objective-sidebar-task-title" href="#task">Selected task</a><button>◈</button></div></div>'
    html += '<div class="sidebar-scope-chip" data-scope-kind="folder" style="--sidebar-workspace-color:#58a6ff"><button id="folderScope" class="sidebar-file-scope-button"><span>Root</span></button><span class="sidebar-scope-tag">Folder</span></div><div class="sidebar-scope-chip" data-scope-kind="worktree" style="--sidebar-workspace-color:#a371f7"><button id="worktreeScope" class="sidebar-file-scope-button"><span>Worktree</span></button></div><div id="assetHeading" class="sidebar-title objective-title"><span>Assets</span><button>+</button></div>'
    html += '</aside><div class="sidebar-resizer" id="sidebarResizer"></div><main class="main" id="content"><textarea id="editor" style="width:600px;height:60px">Draft stays intact</textarea><iframe id="proxy" style="width:600px;height:200px" srcdoc="<button>Embedded app</button>"></iframe></main></div>'
    html += '<section class="term-panel" id="termPanel"><div id="termResizer" class="term-resizer"></div><div class="term-header">Terminal</div><div class="term-stage"><div class="term-console"><div class="term-status">Attached</div><div id="termBody" class="term-body"></div></div></div></section>'+toggle
    html += '<div class="doc-modal-overlay" id="docViewModal"><div class="doc-modal-box"><div class="doc-modal-header"><span id="docModalTitle"></span></div><div class="doc-modal-layout"><nav id="docModalFiles" hidden></nav><div class="doc-modal-body" id="docModalBody"></div></div></div></div>'
    html += vendors+'<script>'+setup+'</script><script>'+(STATIC / 'js/lib/sidebar-drawer.js').read_text()+'</script><script>'+helpers+bridge+"document.getElementById('recentFilters').innerHTML=_sidebarRecentSelectorsHtml();document.getElementById('recentSection').innerHTML=_sidebarRecentSectionHtml([{path:'recent-one.md'},{path:'recent-two.md'}],null,'/alpha',{resolved:true});document.getElementById('filesTitle').innerHTML=_sidebarFilesTitle('/alpha');document.querySelector('#filesTitle .sidebar-title').id='filesHeading';document.getElementById('sidebar').insertAdjacentHTML('beforeend',_agentContextRowHtml());document.getElementById('termBody').ondragover=event=>event.preventDefault();document.getElementById('termBody').ondrop=_termHandleDrop;_termApplyRememberedVisibility();termFitAddon.fit();</script>"
    page = tmp_path / 'sidebar.html'
    page.write_text(html)
    driver = r'''
const fs=require('node:fs');
(async()=>{
 const assert=(ok,message)=>{if(!ok)throw Error(message)},sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const [port]=fs.readFileSync(process.argv[1]+'/DevToolsActivePort','utf8').split('\n');
 const target=await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'}).then(r=>r.json());
 const ws=new WebSocket(target.webSocketDebuggerUrl),pending=new Map();let sequence=0,dragData;
 ws.onmessage=event=>{const m=JSON.parse(event.data);if(m.method==='Input.dragIntercepted')dragData=m.params.data;if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
 await new Promise(r=>ws.addEventListener('open',r,{once:true}));
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||'Browser assertion');return r.result.value;}
 const move=p=>send('Input.dispatchMouseEvent',{type:'mouseMoved',...p});
 async function click(p){await move(p);await send('Input.dispatchMouseEvent',{type:'mousePressed',...p,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...p,button:'left',clickCount:1});}
 const point=id=>evaluate(`(()=>{const r=document.getElementById('${id}').getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+Math.min(15,r.height/2)}})()`);
 const state=()=>evaluate(`(()=>{const sb=document.getElementById('sidebar'),main=document.getElementById('content');return{open:document.body.classList.contains('sidebar-drawer-open'),pinned:document.body.classList.contains('sidebar-drawer-pinned'),enabled:document.body.classList.contains('sidebar-drawer-enabled'),width:sb.getBoundingClientRect().width,mainX:main.getBoundingClientRect().x,cols:termXterm.cols,selected,errors}})()`);
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:process.argv[2]});await send('Page.bringToFront');
 for(let i=0;i<200;i++){if(await evaluate('!!window.LabSidebarDrawer&&document.querySelector(".xterm-screen")'))break;await sleep(20)}
 const baseline=await state();assert(baseline.enabled&&!baseline.open&&baseline.width===62&&baseline.mainX===62,'compact rail supersedes legacy hidden preference');
 assert(await evaluate("getComputedStyle(document.querySelector('.sidebar-recent-selectors')).display==='none'"),'time and Git filter menus hidden in compact mode');
 assert(await evaluate("document.querySelector('#filesHeading span').getClientRects().length===0&&document.querySelector('#assetHeading span').getClientRects().length===0&&getComputedStyle(document.getElementById('assetHeading')).borderTopWidth==='1px'"),'headings become dividers without extra header icons');
 assert(await evaluate("document.querySelectorAll('#sidebar .sidebar-section-shortcut').length===2&&[...document.querySelectorAll('#sidebar .sidebar-section-shortcut')].every(button=>button.getClientRects().length>0)&&![...document.querySelectorAll('[data-sidebar-files-list] .sidebar-file,[data-sidebar-recent-list] .sidebar-file')].some(row=>row.getClientRects().length)&&getComputedStyle(document.querySelector('[data-sidebar-section-shortcut=files]'),'::before').maskImage!==getComputedStyle(document.querySelector('[data-sidebar-section-shortcut=recent]'),'::before').maskImage"),'one distinct Files and Recently updated icon replaces every file in both lists');
 assert(await evaluate("getComputedStyle(document.getElementById('folderScope'),'::before').maskImage!==getComputedStyle(document.getElementById('worktreeScope'),'::before').maskImage"),'main folder and worktree navigation have distinct icons');
 assert(await evaluate("getComputedStyle(document.querySelector('.objective-sidebar-task-title')).fontSize==='0px'&&getComputedStyle(document.querySelector('.objective-sidebar-task > button')).display==='none'&&document.querySelector('.objective-sidebar-task-compact-icon').getBoundingClientRect().width===20&&document.querySelector('.objective-sidebar-task-compact-icon').textContent==='🚧'"),'task navigation retains its emoji when status and customization buttons are folded');
 fs.writeFileSync(process.argv[1]+'/compact.png',Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
 assert(await evaluate('termTabHoverPinSeconds===3'),'shared default is three seconds');
 const rail={x:25,y:135},outside={x:600,y:250};
 await move(rail);assert((await state()).open&&(await state()).width>300,'hover reveals saved full width');
 assert(await evaluate("getComputedStyle(document.querySelector('.sidebar-recent-selectors')).display!=='none'&&document.querySelector('#filesHeading span').getClientRects().length>0"),'expansion restores the complete menus and labels');
 assert(await evaluate("![...document.querySelectorAll('#sidebar .sidebar-section-shortcut')].some(button=>button.getClientRects().length)&&[...document.querySelectorAll('#sidebar .sidebar-file')].every(row=>row.getClientRects().length>0)"),'expanded Files and Recently updated preserve every row');
 fs.writeFileSync(process.argv[1]+'/expanded.png',Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
 await sleep(120);await move(outside);assert(!(await state()).open,'short crossing collapses');
 await sleep(3100);assert(!(await state()).open,'leave cancels pending hover timer');
 await move(rail);await sleep(3100);await move(outside);assert((await state()).pinned,'long hover keeps sidebar open');
 assert((await state()).mainX===baseline.mainX&&(await state()).cols===baseline.cols,'expansion preserves editor position and terminal columns');
 await click(await point('editor'));assert(!(await state()).open,'main editor click returns to compact');
 await move(rail);const file=await point('selectedFile');file.x=(await state()).width-40;
 assert(await evaluate(`document.elementFromPoint(${file.x},${file.y}).closest('#sidebar')!==null`),'expanded row owns overlap hit testing');
 await click(file);await move(outside);assert((await state()).pinned&&(await state()).selected===1,'selection remains open even after terminal focus');
 await evaluate("document.getElementById('sidebar').scrollTop=200");
 const edge=await evaluate("(()=>{const r=document.getElementById('sidebar').getBoundingClientRect();return{x:r.right-8,y:r.y+100}})()");
 await move(edge);assert((await state()).open,'right edge and scrollbar stay inside drawer');
 await click(await point('termBody'));assert(!(await state()).open,'console click collapses sidebar');
 await evaluate("document.getElementById('sidebar').scrollTop=0;termSetTabHoverPinSeconds(.15)");
 await move(rail);await sleep(180);await move(outside);assert((await state()).pinned,'configured hover delay applies');
 await click(await point('proxy'));await sleep(80);assert(!(await state()).open,'embedded app click collapses sidebar');
 await evaluate("document.querySelector('[data-sidebar-section-shortcut=files]').focus()");assert((await state()).open,'keyboard focus on Files reveals its rows');
 await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 assert(!(await state()).open,'Escape dismisses sidebar');
 await move(rail);await click(await point('selectedFile'));await move(outside);
 const resize=await point('sidebarResizer'),oldWidth=(await state()).width;
 await send('Input.dispatchMouseEvent',{type:'mousePressed',...resize,button:'left',clickCount:1});
 await move({x:resize.x+50,y:resize.y});await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:resize.x+50,y:resize.y,button:'left',clickCount:1});
 assert(Math.abs((await state()).width-oldWidth-50)<2,'resizer preserves full overlay width');
 await click(await point('beta'));assert(!(await state()).open,'top navigation resets deliberate open');
 await move(rail);assert(Math.abs((await state()).width-1440*.19)<2,'each workspace retains its full width');
 await click(await point('editor'));await evaluate("view('alpha')");await move(rail);
 assert(Math.abs((await state()).width-oldWidth-50)<2,'original workspace width restored');
 assert(await evaluate("document.getElementById('editor').value==='Draft stays intact'"),'draft retained');
 // Native dragging must retain its source until Chrome captures the payload.
 // A synthetic DragEvent cannot detect cancellation from hiding the modal.
 await evaluate("termXterm.paste=text=>nativePastes.push(text);termXterm.write('\\x1b[?2004h')");await sleep(30);
 await send('Input.setInterceptDrags',{enabled:true});
 async function dragContext(selector){
  dragData=null;
  const source=await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});el.scrollIntoView({block:'center'});const r=el.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);
  await move(source);await send('Input.dispatchMouseEvent',{type:'mousePressed',...source,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:source.x+35,y:source.y,button:'left',buttons:1});
  for(let i=0;i<20&&!dragData;i++)await sleep(25);
  assert(dragData,'native context drag starts: '+selector);
  assert(dragData.dragOperationsMask===1&&dragData.items.some(item=>item.mimeType==='application/x-lab-agent-context'&&item.data==='overview'),'native context payload is a copy of the full-guide action');
  await sleep(20);const destination=await point('termBody');
  for(const type of ['dragEnter','dragOver','drop'])await send('Input.dispatchDragEvent',{type,...destination,data:dragData});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',...destination,button:'left',clickCount:1});
 }
 await dragContext('#sidebar [data-lab-agent-context]');
 assert(await evaluate('nativePastes.length===1&&nativePastes[0]===guide'),'native sidebar drop pastes full context without Enter');
 await evaluate('openAgentContext()');await dragContext('#docModalBody [data-lab-agent-context]');
 assert(await evaluate("nativePastes.length===2&&nativePastes[1]===guide&&getComputedStyle(document.getElementById('docViewModal')).display==='none'"),'native reader drop hides modal and pastes full context without Enter');
 await send('Input.setInterceptDrags',{enabled:false});
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:900,deviceScaleFactor:1,mobile:true});await sleep(100);
 assert(!(await state()).enabled,'mobile retains original sidebar mode');
 await evaluate('sidebarToggleCollapse()');assert(await evaluate("!document.body.classList.contains('sidebar-collapsed')"),'mobile toggle still works');
 assert(!(await state()).errors.length,'no browser exceptions');
 ws.close();console.log('PASS sidebar drawer');
})().catch(error=>{console.error(error.stack);process.exit(1)});
'''
    profile = tmp_path / 'profile'
    process = subprocess.Popen([chrome, '--headless=new', '--no-first-run', '--disable-background-timer-throttling',
                                '--disable-renderer-backgrounding', '--remote-debugging-port=0', '--user-data-dir='+str(profile), 'about:blank'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic()+10
        while not (profile / 'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic() < deadline, 'Chrome did not start'
            time.sleep(.05)
        result = subprocess.run(['node', '-e', driver, str(profile), page.as_uri()], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout+result.stderr
        assert 'PASS sidebar drawer' in result.stdout
    finally:
        process.terminate()
        process.wait(timeout=10)
