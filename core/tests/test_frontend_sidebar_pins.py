"""Single-node Pin controls preserve old geometry and native actions."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import pytest

from .test_frontend_terminal_ui import ROOT, _js_between


def test_sidebar_pin_controls_in_chrome(tmp_path):
    chrome = (os.environ.get('CHROME_BIN') or shutil.which('chromium')
              or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node required')
    source = (ROOT / 'core/src/core/static/js/lab-app.js').read_text()
    helpers = _js_between('  function esc(s)', '  function symlinkClass(')
    helpers += _js_between('  function _sidebarPinButtonHtml(', '  function openSidebarFileHistory(')
    helpers += _js_between('  function _sidebarHandleFileAction(', '  async function openWorkspaceDoc(')
    helpers += _js_between('  function _sidebarPlaceGitBadge(', '  function _sidebarGitStatusIndex(')
    setup = r'''
const calls=[];
const togglePin=name=>calls.push({kind:'pin',name});
const openWorkspaceDocFromFileClick=(path,{root})=>calls.push({kind:'file',path,root});
const openWorkspaceDocModal=(path,{root})=>calls.push({kind:'modal',path,root});
const openSidebarFileHistory=(path,root)=>calls.push({kind:'history',path,root});
const name=`pin/name ' " & <tag> résumé.md`,path='different/document.md';
const markup=pinned=>`<a class="sidebar-file" data-open-file data-filepath="${path}" data-entry-root="/workspace"><span class="sidebar-fname">A long file name for clipping and pin alignment.md</span>${_sidebarPinButtonHtml(name,pinned)}</a>`;
window.prepare=(pinned,badge)=>{
 for(const id of ['reference','sidebar']){
  const el=document.getElementById(id);el.innerHTML=markup(pinned);
  if(id==='reference'){
   const button=el.querySelector('button'),wrapper=document.createElement('span');
   wrapper.className='sidebar-actions';button.replaceWith(wrapper);wrapper.appendChild(button);
   button.className='';button.removeAttribute('type');button.removeAttribute('data-pin-name');
  }
  if(badge){const status=document.createElement('span');status.className='git-badge';status.textContent='M';_sidebarPlaceGitBadge(el.firstChild,status);}
 }
};
prepare(false,false);
'''
    css = (ROOT / 'core/src/core/static/css/lab-shell.css').read_text()
    page = tmp_path / 'pins.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>' + css + '''
*{box-sizing:border-box}body{margin:0;background:#0d1117;--text-secondary:#aab;--text-primary:#eee;--tree-hover:#242a32;--bg-secondary:#202630}
aside{position:absolute;top:50px;width:340px}#reference{left:16px}#sidebar{left:400px}
</style><body><aside id="reference"></aside><aside id="sidebar"></aside><script>'''
                    + helpers + setup + '</script>')
    checks = r'''
const evaluate=async expression=>{
 const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
 if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);
 return r.result.value;
};
const frame=()=>evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
const comparisons=[];
for(const light of [false,true])for(const zoom of [1,1.25])for(const width of [220,340])for(const pinned of [false,true])for(const badge of [false,true]){
 await evaluate(`document.body.classList.toggle('light-mode',${light});document.body.style.zoom=${zoom};for(const el of document.querySelectorAll('aside'))el.style.width='${width}px';prepare(${pinned},${badge});`);
 for(const hover of ['none','row','button']){
  const samples=[];
  for(const id of ['reference','sidebar']){
   await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:0,y:0});await frame();
   if(hover!=='none'){
    const point=await evaluate(`(()=>{const r=document.querySelector('#${id} .sidebar-file').getBoundingClientRect();return {x:r.x+30,y:r.y+r.height/2}})()`);
    await send('Input.dispatchMouseEvent',{type:'mouseMoved',...point});await frame();
   }
   if(hover==='button'){
    const point=await evaluate(`(()=>{const r=document.querySelector('#${id} button').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);
    await send('Input.dispatchMouseEvent',{type:'mouseMoved',...point});await frame();
   }
   samples.push(await evaluate(`(()=>{
    const row=document.querySelector('#${id} .sidebar-file'),button=row.querySelector('button'),label=row.querySelector('.sidebar-fname');
    const r=row.getBoundingClientRect(),b=button.getBoundingClientRect(),l=label.getBoundingClientRect(),style=getComputedStyle(button);
    if(row.matches(':hover')!==${hover!=='none'} || button.matches(':hover')!==${hover==='button'})throw Error('Native hover state mismatch');
    const range=document.createRange();range.selectNodeContents(button);const text=range.getBoundingClientRect();
    return {rowHeight:r.height,labelLeft:l.left-r.left,labelWidth:l.width,visible:button.getClientRects().length>0,
      width:b.width,height:b.height,right:b.width?r.right-b.right:0,top:b.height?b.top-r.top:0,textTop:text.height?text.top-b.top:0,
      color:style.color,background:style.backgroundColor,title:button.title,text:button.textContent,
      badgeBefore:!row.querySelector('.git-badge')||!!(row.querySelector('.git-badge').compareDocumentPosition(button)&Node.DOCUMENT_POSITION_FOLLOWING)};
   })()`));
  }
  for(const key of Object.keys(samples[0])){
   const a=samples[0][key],b=samples[1][key];
   if(typeof a==='number'?Math.abs(a-b)>.1:a!==b)throw Error('Pin geometry/theme mismatch '+JSON.stringify({key,samples,light,zoom,width,pinned,badge,hover}));
  }
  comparisons.push({light,zoom,width,pinned,badge,hover,samples});
 }
}
await evaluate("document.body.classList.remove('light-mode');document.body.style.zoom=1;prepare(false,true)");
const point=await evaluate(`(()=>{const r=document.querySelector('#sidebar .sidebar-file').getBoundingClientRect();return {x:r.x+30,y:r.y+r.height/2}})()`);
await send('Input.dispatchMouseEvent',{type:'mouseMoved',...point});await frame();
const buttonPoint=await evaluate(`(()=>{const r=document.querySelector('#sidebar button').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);
await send('Input.dispatchMouseEvent',{type:'mousePressed',...buttonPoint,button:'left',clickCount:1});
await send('Input.dispatchMouseEvent',{type:'mouseReleased',...buttonPoint,button:'left',clickCount:1});
await evaluate(`if(calls.length!==1 || calls[0].kind!=='pin' || calls[0].name!==name)throw Error('Native pin click changed target or opened a file');document.querySelector('#sidebar button').focus()`);
await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r',unmodifiedText:'\r'});
await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
await evaluate(`
 if(calls.length!==2 || calls[1].name!==name)throw Error('Keyboard pin action failed');
 const sidebar=document.getElementById('sidebar'),template=document.createElement('template');template.innerHTML=markup(true);
 sidebar.replaceChildren(template.content.cloneNode(true));sidebar.querySelector('button').click();
 if(calls.length!==3 || calls[2].name!==name || sidebar.querySelector('button').title!=='Unpin')throw Error('Fresh clone lost pin action');
 sidebar.querySelector('.sidebar-fname').click();
 if(calls.at(-1).kind!=='file'||calls.at(-1).path!==path||calls.at(-1).root!=='/workspace')throw Error('File click changed');
 sidebar.querySelector('button').dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));
 if(calls.at(-1).kind!=='modal')throw Error('Existing row double-click behavior changed');
 if(template.content.querySelector('button').hasAttribute('onclick'))throw Error('Inline pin handler remains');
`);
await writeFile(screenshotPath.replace('.png','.json'),JSON.stringify({comparisons,calls:await evaluate('calls')},null,2));
'''
    driver = (ROOT / 'scripts/chrome-dump-auth.mjs').read_text()
    runner = tmp_path / 'pins.mjs'
    runner.write_text(driver.replace('const evaluated = await send(', checks + '\nconst evaluated = await send(', 1))
    profile = tmp_path / 'chrome'
    process = subprocess.Popen([
        chrome, '--headless', '--no-sandbox', '--no-first-run', '--disable-background-networking',
        '--user-data-dir=' + str(profile), '--remote-debugging-port=0', 'about:blank',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic() < deadline, 'Chrome did not start'
            time.sleep(.05)
        result = subprocess.run([
            node, str(runner), str(profile), page.as_uri(), str(tmp_path / 'rendered.html'), str(tmp_path / 'pins.png'),
        ], env={**os.environ, 'LAB_UI_AUTH_COOKIE': ''}, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        report = json.loads((tmp_path / 'pins.json').read_text())
        assert len(report['comparisons']) == 96
        assert [call['kind'] for call in report['calls']] == ['pin', 'pin', 'pin', 'file', 'modal']
        assert '_sidebarPinButtonHtml(f.name, isPinned)' in source
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
