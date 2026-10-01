"""Native editing keeps Markdown formatted and reveals only the active text span."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'core/src/core/static'


@pytest.mark.parametrize('viewport', [1440, 390])
def test_word_level_markdown_browser(tmp_path, viewport):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    body = '''# A working document

Edit **bold** then *italic* with `code` and [reference](https://example.org/path). Plus ~~crossed~~ and ***nested***.

- [ ] Check this item
- Second item

> A quote with **emphasis**.

## Section title

| Name | Value |
| ---- | ----- |
| Alpha | **Beta** |

```js
const answer = 42;
```

<details>
<summary>More context</summary>

A hidden **detail**.

</details>

Unsafe [label](javascript:alert(1)) remains text.
'''
    setup = r'''
window.assert=(ok,message)=>{if(!ok)throw Error(message)};
window.until=async fn=>{for(let i=0;i<300;i++){if(fn())return;await new Promise(r=>setTimeout(r,10))}throw Error('Timed out: '+fn)};
window.opened=[];window.LabExternalLinks={open:async url=>opened.push(url)};
window.changes=[];window.saves=[];
window.editor=LabMarkdownEditor.create(document.getElementById('editor'),{body:BASE,onChange:value=>changes.push(value),onSave:()=>saves.push(editor.value)});
window.visible=()=>editor.view.contentDOM.textContent;
window.cursor=()=>editor.view.state.selection.main.head;
window.reset=()=>{editor.value=BASE;document.getElementById('outside').focus()};
window.assertReading=()=>{
 assert(!visible().includes('**')&&!visible().includes('https://example.org/path')&&!visible().includes('```'),'reading hides Markdown syntax and link destinations');
 assert(document.querySelector('.cm-content strong')?.textContent==='bold','bold stays a formatted text span');
 assert(document.querySelector('.cm-content em')?.textContent==='italic','italic stays formatted');
 assert(document.querySelector('.lab-live-heading-1')?.textContent==='A working document','heading text is rendered without its prefix');
 assert(document.querySelector('.lab-live-table-cell strong')?.textContent==='Beta','tables render formatted editable cells');
 assert(!document.querySelector('a[href^="javascript:"]')&&!window.alerted,'unsafe Markdown links never become executable');
};
window.alert=()=>window.alerted=true;
assertReading();
document.getElementById('result').textContent='READY';
'''
    scripts = '\n'.join('<script>'+(STATIC/path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js', 'vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js', 'vendor/lab-markdown-editor/markdown-editor.min.js'])
    page = tmp_path/'word-editor.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>:root{--lab-document-font-size:18px;--bg-primary:#0d1117;--bg-secondary:#161b22;--bg-tertiary:#21262d;--text-primary:#e6edf3;--text-secondary:#8b949e;--text-dim:#6e7681;--accent:#58a6ff;--border:#30363d}body{margin:0;padding:28px;background:var(--bg-primary);color:var(--text-primary)}#outside{margin-bottom:24px}'+(STATIC/'css/lab-shell.css').read_text()+'</style><button id="outside">Outside document</button><div class="assistant-note-editor" id="editor"></div><pre id="result">PENDING</pre>'+scripts+'<script>const BASE='+json.dumps(body).replace('</','<\\/')+';</script><script>'+setup+'</script>')
    driver = r'''
async function evaluate(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||'Browser check failed');return result.result?.value;}
async function click(point){await send('Input.dispatchMouseEvent',{type:'mouseMoved',...point});await send('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1});}
async function key(key,code,modifiers=0){const windowsVirtualKeyCode=({Enter:13,Tab:9,Escape:27})[key]||key.toUpperCase().charCodeAt(0);await send('Input.dispatchKeyEvent',{type:'keyDown',key,code,modifiers,windowsVirtualKeyCode,...(key==='Enter'?{text:'\r'}:{})});await send('Input.dispatchKeyEvent',{type:'keyUp',key,code,windowsVirtualKeyCode});}
async function word(text,offset=2){
 const point=await evaluate(`(() => {const node=[...editor.view.contentDOM.querySelectorAll('.cm-line')].find(line=>line.textContent.includes(${JSON.stringify(text)}));assert(node,'editable line for '+${JSON.stringify(text)});node.scrollIntoView({block:'center'});const from=editor.value.indexOf(${JSON.stringify(text)}),position=from+${offset};const r=editor.view.coordsAtPos(position);assert(r,'caret coordinates for clicked word');return {x:r.left+1,y:(r.top+r.bottom)/2,position}})()`);
 await click({x:point.x,y:point.y});await evaluate(`until(()=>editor.view.hasFocus)`);
 await evaluate(`assert(cursor()===${point.position},'native click lands at the clicked character: '+cursor()+' versus '+${point.position})`);
}
await evaluate(`assert(document.getElementById('result').textContent==='READY','editor is mounted')`);
await word('bold');
await evaluate(`assert(visible().includes('**bold**')&&!visible().includes('*italic*')&&!visible().includes('https://example.org/path'),'only bold syntax appears while editing bold in the same paragraph');assert(document.querySelector('.cm-content em')&&document.querySelector('.cm-content code'),'neighboring italic and code remain formatted')`);
await send('Input.insertText',{text:'X'});
await evaluate(`assert(editor.value===BASE.replace('**bold**','**boXld**'),'native typing preserves exact Markdown and every other block')`);
await key('z','KeyZ',4);
await evaluate(`assert(editor.value===BASE,'native undo restores the exact source')`);
await key('i','KeyI',4);
await evaluate(`assert(editor.value===BASE.replace('**bold**','***bold***'),'italic shortcut nests inside bold without removing bold')`);
await key('i','KeyI',4);
await evaluate(`assert(editor.value===BASE,'italic toggle removes only italic from nested bold')`);
await word('italic');
await evaluate(`assert(visible().includes('*italic*')&&!visible().includes('**bold**')&&!visible().includes('https://example.org/path'),'moving to italic hides the previous word syntax')`);
await word('nested');
await evaluate(`assert([...document.querySelectorAll('.lab-live-syntax')].map(n=>n.textContent).join('')==='****','nested formatting reveals only the innermost emphasis');assert(document.querySelector('.cm-content em strong'),'nested formatting remains styled')`);
await word('Edit');
await evaluate(`assert(!document.querySelector('.lab-live-syntax'),'plain text exposes no unrelated Markdown')`);
await key('b','KeyB',4);
await evaluate(`assert(editor.value.includes('**Edit** **bold**'),'format shortcut writes Markdown around the current word');assert(document.querySelector('.lab-live-format-toolbar'),'selecting text exposes a compact formatting toolbar')`);
await evaluate(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
const boldButton=await evaluate(`(() => {const r=document.querySelector('.lab-live-format-toolbar button[aria-label="Bold"]').getBoundingClientRect();const toolbar=document.querySelector('.lab-live-format-toolbar').getBoundingClientRect();assert(toolbar.left>=0&&toolbar.right<=innerWidth,'selection toolbar fits viewport');return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);
await click(boldButton);
await evaluate(`assert(editor.value===BASE,'toolbar can remove formatting without changing surrounding source: '+JSON.stringify(editor.value))`);
await key('b','KeyB',4);
await evaluate(`document.querySelector('.lab-live-format-toolbar button[aria-label="Bold"]').focus()`);
await evaluate(`assert(document.activeElement.closest('.lab-live-format-toolbar'),'format controls retain keyboard focus and the editor selection')`);
await key('Enter','Enter');
await evaluate(`assert(editor.value===BASE,'keyboard activation can toggle formatting without losing the selection')`);
await word('reference');
await evaluate(`assert(visible().includes('[reference](https://example.org/path)')&&!visible().includes('**bold**'),'only the active link reveals its Markdown');assert(!opened.length,'ordinary link click edits without navigation')`);
await evaluate(`(async()=>{reset();await until(()=>!document.querySelector('.lab-live-syntax'));assertReading()})()`);
const checkbox=await evaluate(`(() => {const node=document.querySelector('.lab-live-task-check');node.scrollIntoView({block:'center'});const r=node.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);
await click(checkbox);
await evaluate(`assert(editor.value===BASE.replace('- [ ] Check','- [x] Check'),'native checkbox changes only its Markdown checkbox');assert(!visible().includes('https://example.org/path'),'checkbox focus does not reveal another word')`);
await evaluate(`reset()`);
await word('Second item','Second item'.length);
await key('Enter','Enter');await send('Input.insertText',{text:'Third item'});
await evaluate(`assert(editor.value.includes('- Second item\\n- Third item'),'Enter continues a rendered Markdown list')`);
await evaluate(`reset()`);
await word('Beta');await send('Input.insertText',{text:'X'});
await evaluate(`assert(editor.value===BASE.replace('**Beta**','**BeXta**'),'editing a table word keeps table structure and other cells intact');assert(!visible().includes('https://example.org/path'),'table editing never exposes another block syntax')`);
await evaluate(`reset()`);
await word('answer');
await evaluate(`assert(!visible().includes(String.fromCharCode(96).repeat(3)),'code editing keeps fences hidden');assert(getComputedStyle(document.querySelector('.lab-live-code-line:not(.lab-live-boundary)')).fontFamily.includes('monospace'),'code keeps its readable document styling')`);
await evaluate(`reset();document.querySelector('.lab-live-markdown-block summary').click()`);
const detailPoint=await evaluate(`(() => {const node=[...document.querySelectorAll('.lab-live-markdown-block strong')].find(node=>node.textContent==='detail');assert(node,'disclosure can be expanded');node.scrollIntoView({block:'center'});const r=node.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()`);
await click(detailPoint);
await evaluate(`assert(editor.view.hasFocus&&cursor()>=BASE.indexOf('**detail**')+2&&cursor()<=BASE.indexOf('**detail**')+8,'clicking disclosed rich text enters that word: '+cursor()+' focus='+editor.view.hasFocus);assert(!visible().includes('<details>')&&!visible().includes('https://example.org/path'),'editing disclosure content exposes no whole HTML or paragraph source')`);
await key('s','KeyS',4);
await evaluate(`(async()=>{assert(saves.length===1&&saves[0]===BASE,'Save submits the exact original Markdown after navigation');document.getElementById('outside').focus();await until(()=>!document.querySelector('.lab-live-syntax'));assertReading();document.getElementById('result').textContent='PASS'})()`);
'''
    profile = tmp_path/'profile'
    process = subprocess.Popen([chrome,'--headless','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check','--allow-file-access-from-files','--user-data-dir='+str(profile),'--remote-debugging-port=0','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    diagnostic = r'''
} catch(error) {
 const dom=await send('Runtime.evaluate',{expression:'document.documentElement.outerHTML',returnByValue:true});await writeFile(domPath,String(dom.result?.value||error));
 const screenshot=await send('Page.captureScreenshot',{format:'png'});await writeFile(screenshotPath,Buffer.from(screenshot.data,'base64'));ws.close();throw error;
}
'''
    path = tmp_path/'word-editor.mjs'
    path.write_text((ROOT/'scripts/chrome-dump-auth.mjs').read_text().replace('width: 1440,','width: '+str(viewport)+',').replace('const evaluated = await send','try {\n'+driver+diagnostic+'\nconst evaluated = await send'))
    try:
        deadline = time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline
            time.sleep(.05)
        result = subprocess.run(['node',str(path),str(profile),page.as_uri(),str(tmp_path/'dom.html'),str(tmp_path/'word-markdown.png')],capture_output=True,text=True,timeout=40,env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        assert result.returncode == 0, result.stderr
        assert '<pre id="result">PASS</pre>' in (tmp_path/'dom.html').read_text()
    finally:
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: process.kill();process.wait(timeout=5)
