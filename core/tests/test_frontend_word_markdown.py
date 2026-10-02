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
window.editorErrors=[];
window.addEventListener('error',event=>editorErrors.push(event.error?.stack||event.message));
window.addEventListener('unhandledrejection',event=>editorErrors.push(String(event.reason)));
const realConsoleError=console.error;
console.error=(...args)=>{editorErrors.push(args.map(String).join(' '));realConsoleError(...args)};
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
        'vendor/marked@12.0.1/marked.min.js', 'vendor/dompurify@3.4.15/purify.min.js', 'vendor/highlightjs@11.9.0/highlight.min.js',
        'js/lib/markdown-content.js', 'vendor/lab-markdown-editor/markdown-editor.min.js'])
    page = tmp_path/'word-editor.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>:root{--lab-document-font-size:18px;--bg-primary:#0d1117;--bg-secondary:#161b22;--bg-tertiary:#21262d;--text-primary:#e6edf3;--text-secondary:#8b949e;--text-dim:#6e7681;--accent:#58a6ff;--border:#30363d}body{margin:0;padding:28px;background:var(--bg-primary);color:var(--text-primary)}#outside{margin-bottom:24px}'+(STATIC/'css/lab-shell.css').read_text()+'</style><button id="outside">Outside document</button><div class="assistant-note-editor" id="editor"></div><pre id="result">PENDING</pre>'+scripts+'<script>const BASE='+json.dumps(body).replace('</','<\\/')+';</script><script>'+setup+'</script>')
    driver = r'''
async function evaluate(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||'Browser check failed');return result.result?.value;}
async function click(point){await send('Input.dispatchMouseEvent',{type:'mouseMoved',...point});await send('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1});}
async function key(key,code,modifiers=0){const windowsVirtualKeyCode=({Enter:13,Tab:9,Escape:27,ArrowDown:40,ArrowUp:38,Backspace:8,Delete:46,Home:36,End:35})[key]||key.toUpperCase().charCodeAt(0);await send('Input.dispatchKeyEvent',{type:'keyDown',key,code,modifiers,windowsVirtualKeyCode,...(key==='Enter'?{text:'\r'}:{})});await send('Input.dispatchKeyEvent',{type:'keyUp',key,code,windowsVirtualKeyCode});}
async function selectSource(source,from=0,to=source.length){await evaluate(`editor.value=${JSON.stringify(source)};editor.view.dispatch({selection:{anchor:${from},head:${to}},scrollIntoView:true});editor.focus();until(()=>editor.view.hasFocus)`);}
async function toolbar(label){await evaluate(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);const point=await evaluate(`(() => {const node=document.querySelector('.lab-live-format-toolbar button[aria-label="'+${JSON.stringify(label)}+'"]');assert(node,'format button');const r=node.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);await click(point);}
async function snapshot(name){const screenshot=await send('Page.captureScreenshot',{format:'png'});await writeFile(screenshotPath.replace('.png','-'+name+'.png'),Buffer.from(screenshot.data,'base64'));}
// Native type-to-select works in headless macOS; its platform popup ignores CDP arrow keys.
async function languageKey(letter){await evaluate(`document.querySelector('.lab-live-code-toolbar select').focus()`);await send('Input.dispatchKeyEvent',{type:'keyDown',key:letter,code:'Key'+letter.toUpperCase(),text:letter,windowsVirtualKeyCode:letter.toUpperCase().charCodeAt(0)});await send('Input.dispatchKeyEvent',{type:'keyUp',key:letter,code:'Key'+letter.toUpperCase(),windowsVirtualKeyCode:letter.toUpperCase().charCodeAt(0)});}
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
await evaluate(`(async()=>{assert(saves.length===1&&saves[0]===BASE,'Save submits the exact original Markdown after navigation');document.getElementById('outside').focus();await until(()=>!document.querySelector('.lab-live-syntax'));assertReading()})()`);
for(const [source,formatted,plain,label,shortcut] of [
 ['plain **bold** words **again**','**plain bold words again**','plain bold words again','Bold','b'],
 ['__alpha__ plain __beta__','**alpha plain beta**','alpha plain beta','Bold','b'],
 ['plain **bold *italic*** [label](https://example.org)','**plain bold *italic* [label](https://example.org)**','plain bold *italic* [label](https://example.org)','Bold','b'],
 ['*alpha* plain *beta*','*alpha plain beta*','alpha plain beta','Italic','i'],
 ['~~alpha~~ plain ~~beta~~','~~alpha plain beta~~','alpha plain beta','Strikethrough',null],
 ['`alpha` plain `beta`','`alpha plain beta`','alpha plain beta','Inline code','e'],
 ['plain `**literal**` **bold**','**plain `**literal**` bold**','plain `**literal**` bold','Bold','b'],
 ['# Header\n\n**One** and **two**\n\nLast','# **Header**\n\n**One and two**\n\n**Last**','# Header\n\nOne and two\n\nLast','Bold','b'],
]){
 await selectSource(source);if(shortcut)await key(shortcut,'Key'+shortcut.toUpperCase(),4);else await toolbar(label);
 await evaluate(`assert(editor.value===${JSON.stringify(formatted)},'mixed selection becomes one format per block: '+JSON.stringify(editor.value));assert(document.querySelector('.lab-live-format-toolbar button[aria-label="'+${JSON.stringify(label)}+'"]').getAttribute('aria-pressed')==='true','fully formatted selection has an active button')`);
 await toolbar(label);await evaluate(`assert(editor.value===${JSON.stringify(plain)},'second click removes that format: '+JSON.stringify(editor.value))`);
 await key('z','KeyZ',4);await evaluate(`assert(editor.value===${JSON.stringify(formatted)},'each formatting command is one undo step')`);
}
await selectSource('**alpha** **beta**');await toolbar('Bold');
await evaluate(`assert(editor.value==='alpha beta','separate fully bold runs toggle off together')`);
await selectSource('**alpha beta gamma**',8,12);await toolbar('Bold');
await evaluate(`assert(editor.value==='**alpha** beta **gamma**','partial unbold preserves text and formatting outside the selection');assert(editor.view.state.sliceDoc(editor.view.state.selection.main.from,editor.view.state.selection.main.to)==='beta','selection stays on its text')`);
await selectSource('__alphabeta__',7,11);await toolbar('Bold');
await evaluate(`assert(editor.value==='**alpha**beta'&&document.querySelector('.cm-content strong').textContent==='alpha','partial underscore formatting stays valid at word boundaries')`);
await selectSource('**alpha beta** plain **gamma delta**',8,28);await toolbar('Bold');
await evaluate(`assert(editor.value==='**alpha** **beta plain gamma** **delta**','mixed partial runs keep both outside fragments bold: '+editor.value)`);
await selectSource('');await key('b','KeyB',4);await send('Input.insertText',{text:'New'});
await evaluate(`assert(editor.value==='**New**','empty selection places caret inside new delimiters')`);
await selectSource('A **bold** selection');await toolbar('Bold');
for(const theme of ['dark','light']){
 await evaluate(`document.body.classList.toggle('light-mode',${theme==='light'});new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
 await evaluate(`(() => {const toolbar=document.querySelector('.lab-live-format-toolbar'),tip=toolbar.closest('.cm-tooltip'),button=toolbar.querySelector('button');const style=getComputedStyle(tip),expected=getComputedStyle(document.body).getPropertyValue('--bg-secondary');const probe=document.createElement('span');probe.style.backgroundColor=expected;document.body.append(probe);assert(style.backgroundColor===getComputedStyle(probe).backgroundColor,'tooltip uses the current Lab theme instead of editor defaults');probe.remove();const luminance=color=>{const rgb=color.match(/[\\d.]+/g).slice(0,3).map(Number).map(value=>{value/=255;return value<=.04045?value/12.92:((value+.055)/1.055)**2.4});return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]};for(const control of toolbar.querySelectorAll('button')){const fg=luminance(getComputedStyle(control).color),bg=luminance(control.getAttribute('aria-pressed')==='true'?getComputedStyle(control).backgroundColor:style.backgroundColor);assert((Math.max(fg,bg)+.05)/(Math.min(fg,bg)+.05)>=4.5,'toolbar labels have readable contrast');assert(getComputedStyle(control).fontSize==='14px','toolbar typography does not grow with document headings')}const r=tip.getBoundingClientRect();assert(r.left>=0&&r.right<=innerWidth,'themed toolbar fits viewport')})()`);
 await snapshot('toolbar-'+theme);
}
await evaluate(`document.body.classList.remove('light-mode')`);
await selectSource('');await send('Input.insertText',{text:'/'});
await evaluate(`until(()=>document.querySelector('.lab-live-slash-menu'))`);
await evaluate(`(() => {const menu=document.querySelector('.lab-live-slash-menu');assert(menu.querySelectorAll('button').length===11,'slash exposes the block actions including foldable HTML');const r=menu.getBoundingClientRect();assert(r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight,'slash menu fits viewport')})()`);
await snapshot('slash');await key('ArrowUp','ArrowUp');
await evaluate(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
await evaluate(`(() => {const menu=document.querySelector('.lab-live-slash-menu'),selected=menu.querySelector('.is-selected'),r=selected.getBoundingClientRect(),bounds=menu.getBoundingClientRect();assert(selected.textContent.includes('Divider')&&r.top>=bounds.top&&r.bottom<=bounds.bottom,'keyboard navigation scrolls the final action into view')})()`);
await key('ArrowDown','ArrowDown');await send('Input.insertText',{text:'fold'});
await evaluate(`assert(document.querySelectorAll('.lab-live-slash-menu button').length===1,'typing filters slash actions')`);
await key('Enter','Enter');
const folded='<details>\n<summary>Toggle title</summary>\n\nContent\n\n</details>';
await evaluate(`assert(editor.value===${JSON.stringify(folded)},'fold action inserts native details with Markdown spacing');assert(editor.view.state.sliceDoc(editor.view.state.selection.main.from,editor.view.state.selection.main.to)==='Toggle title','fold title is selected for editing')`);
await key('z','KeyZ',4);await evaluate(`assert(editor.value==='/fold','fold insertion is one undo step')`);
await key('Enter','Enter');await send('Input.insertText',{text:'Context'});
await evaluate(`document.getElementById('outside').focus();until(()=>document.querySelector('.lab-live-markdown-block details'))`);
await evaluate(`assert(document.querySelector('.lab-live-markdown-block summary').textContent==='Context','inserted fold renders an editable title');assert(!document.querySelector('.lab-live-markdown-block details').open,'new fold starts closed');document.querySelector('.lab-live-markdown-block summary').click();assert(document.querySelector('.lab-live-markdown-block details').open,'inserted fold opens with its normal toggle')`);
await selectSource('');await send('Input.insertText',{text:'/'});await key('ArrowDown','ArrowDown');await key('ArrowUp','ArrowUp');await key('ArrowDown','ArrowDown');await key('Enter','Enter');
await evaluate(`assert(editor.value==='# Heading','arrow keys and Enter insert the selected action')`);
await selectSource('');await send('Input.insertText',{text:'/table'});
await evaluate(`until(()=>document.querySelector('.lab-live-slash-menu button'))`);
await evaluate(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
const tablePoint=await evaluate(`(() => {const r=document.querySelector('.lab-live-slash-menu button').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);await click(tablePoint);
await evaluate(`assert(editor.value.startsWith('| Column 1 | Column 2 |'),'native click inserts a slash action')`);
await selectSource('');await send('Input.insertText',{text:'/quote'});await evaluate(`document.querySelector('.lab-live-slash-menu button').focus()`);await key('Enter','Enter');
await evaluate(`assert(editor.value==='> Quote','slash actions retain the selection while their buttons have keyboard focus')`);
await selectSource('');await send('Input.insertText',{text:'/toggle'});await key('Escape','Escape');
await evaluate(`assert(editor.value==='/toggle'&&!document.querySelector('.lab-live-slash-menu'),'Escape closes the menu without modifying source')`);
for(const source of ['https://example.org/path','A / fraction','```\n/\n```','`/`']){const at=source==='```\n/\n```'?5:source==='`/`'?2:source.length;await selectSource(source,at,at);await evaluate(`assert(!document.querySelector('.lab-live-slash-menu'),'ordinary slashes and code do not open commands')`);}
await selectSource('');await send('Input.insertText',{text:'/unknown'});await key('Enter','Enter');
await evaluate(`assert(editor.value==='/unknown\\n','unknown commands keep normal Enter behavior')`);
await selectSource('');for(let i=0;i<3;i++)await send('Input.insertText',{text:'`'});
await evaluate(`assert(editor.value==='\u0060\u0060\u0060\\n\\n\u0060\u0060\u0060\\n\\n','typing the third backtick completes a Markdown container');assert(cursor()===4,'new block starts with caret in its body');assert(document.querySelector('.lab-live-code-toolbar select').value===''&&!visible().includes('\u0060\u0060\u0060'),'new block defaults to None and hides fence syntax')`);
await send('Input.insertText',{text:'SELECT * from mytable;'});
await evaluate(`assert(!document.querySelector('.lab-live-code-token'),'None keeps code plain')`);await languageKey('s');
await evaluate(`assert(editor.value.startsWith('\u0060\u0060\u0060sql\\nSELECT * from mytable;'),'native language dropdown changes only the fence info: '+JSON.stringify(editor.value));assert([...document.querySelectorAll('.lab-live-code-token.hljs-keyword')].some(node=>node.textContent==='SELECT'),'SQL is highlighted while editable');assert(getComputedStyle(document.querySelector('.lab-live-code-token.hljs-keyword')).color!==getComputedStyle(editor.view.contentDOM).color,'SQL keyword has a visible syntax color');assert(document.querySelector('.lab-live-code-framed').getAttribute('spellcheck')==='false','code disables prose spelling marks')`);
await snapshot('code-sql');
await languageKey('p');
await evaluate(`const start=editor.value.indexOf('SELECT'),end=start+'SELECT * from mytable;'.length;editor.view.dispatch({selection:{anchor:start,head:end}});editor.focus()`);
await send('Input.insertText',{text:'def greet(name):\n    return "Hello " + name'});
await evaluate(`assert(editor.value.startsWith('\u0060\u0060\u0060python\\n'),'Python dropdown preserves standard Markdown');assert(document.querySelector('.lab-live-code-token.hljs-keyword').textContent==='def'&&document.querySelector('.lab-live-code-token.hljs-string').textContent.includes('Hello'),'Python keywords and strings highlight without changing code')`);
await snapshot('code-python');
await evaluate(`document.body.classList.add('light-mode')`);await snapshot('code-python-light');await evaluate(`document.body.classList.remove('light-mode')`);await languageKey('n');
await evaluate(`assert(editor.value.startsWith('\u0060\u0060\u0060\\n')&&!document.querySelector('.lab-live-code-token'),'None removes language metadata and syntax colors');editor.view.dispatch({selection:{anchor:4}});editor.focus()`);
const protectedSource=await evaluate(`editor.value`);await key('Backspace','Backspace');
await evaluate(`assert(editor.value===${JSON.stringify(protectedSource)}&&cursor()===4,'Backspace at the code start cannot remove its opening fence')`);
await evaluate(`editor.view.dispatch({selection:{anchor:editor.value.lastIndexOf('\\n\u0060\u0060\u0060')}})`);await key('Delete','Delete');
await evaluate(`assert(editor.value===${JSON.stringify(protectedSource)},'Delete at the code end cannot remove its closing fence')`);
await evaluate(`editor.view.dispatch({selection:{anchor:0,head:editor.value.length}})`);await key('Backspace','Backspace');
await evaluate(`assert(editor.value==='\u0060\u0060\u0060\\n\\n\u0060\u0060\u0060'&&document.querySelector('.lab-live-code-toolbar'),'deleting a selected code block clears its content but preserves the container')`);
await send('Input.insertText',{text:'```'});
await evaluate(`assert(editor.value==='\u0060\u0060\u0060\u0060\\n\u0060\u0060\u0060\\n\u0060\u0060\u0060\u0060'&&document.querySelectorAll('.lab-live-code-toolbar').length===1,'literal backticks in code extend the outer fences instead of closing the block')`);
await key('z','KeyZ',4);await evaluate(`assert(editor.value==='\u0060\u0060\u0060\\n\\n\u0060\u0060\u0060','literal fence growth and typing undo together');const data=new DataTransfer();data.setData('text/plain','\u0060\u0060\u0060');editor.view.contentDOM.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));assert(editor.value==='\u0060\u0060\u0060\u0060\\n\u0060\u0060\u0060\\n\u0060\u0060\u0060\u0060','clipboard paste also extends the code fences')`);
await evaluate(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
const deleteCode=await evaluate(`(() => {const r=document.querySelector('.lab-live-code-delete').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);await click(deleteCode);
await evaluate(`assert(editor.value===''&&!document.querySelector('.lab-live-code-toolbar'),'Delete button removes the complete block')`);await key('z','KeyZ',4);
await evaluate(`assert(document.querySelector('.lab-live-code-toolbar')&&editor.value.startsWith('\u0060\u0060\u0060\u0060'),'Undo restores a deleted code block with its controls')`);
await selectSource('```sql\nSELECT 1;\n```',7,7);await key('ArrowDown','ArrowDown');await send('Input.insertText',{text:'Outside'});
await evaluate(`assert(editor.value==='\u0060\u0060\u0060sql\\nSELECT 1;\\n\u0060\u0060\u0060\\n\\nOutside','Down from the last code line exits into a normal paragraph');assert(!LabMarkdown.cloneVisible(editor.view.dom).textContent.includes('Language'),'code UI controls never leak into copying')`);
await key('s','KeyS',4);await evaluate(`assert(saves.at(-1)===editor.value,'code controls continue saving plain Markdown')`);
await selectSource('```\n```',4,4);await send('Input.insertText',{text:'first'});
await evaluate(`assert(editor.value==='\u0060\u0060\u0060\\nfirst\\n\u0060\u0060\u0060'&&cursor()===9,'typing in an imported empty block keeps its closing fence on a separate line: '+JSON.stringify({source:editor.value,cursor:cursor()}))`);
await selectSource('```\n```',4,4);await evaluate(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
const emptyCode=await evaluate(`(() => {const r=document.querySelector('.lab-live-empty-code-body').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);await click(emptyCode);await send('Input.insertText',{text:'clicked'});
await evaluate(`assert(editor.value==='\u0060\u0060\u0060\\nclicked\\n\u0060\u0060\u0060','imported empty blocks expose a clickable editable body')`);

const tableSource='| Purpose | Entry | Evidence or prerequisites |\n| --- | --- |\n| Shared EI browser test | [Nile Forgot](https://example.org/very/long/evidence) | Long evidence text that wraps cleanly inside its column |\n\nAfter table.';
await selectSource(tableSource,0,0);
await evaluate(`(() => {const rows=[...document.querySelectorAll('.lab-live-table-row')];assert(rows.length===2&&rows.every(row=>row.querySelectorAll('.lab-live-table-cell').length===3),'mismatched delimiter counts still render all three columns');assert(!visible().includes('| Purpose')&&!visible().includes('---'),'table editing hides structural delimiters');assert(editor.value===${JSON.stringify(tableSource)},'table rendering preserves exact stored Markdown');const header=[...rows[0].querySelectorAll('.lab-live-table-cell')],cells=[...rows[1].querySelectorAll('.lab-live-table-cell')];for(let i=0;i<3;i++){const a=header[i].getBoundingClientRect(),b=cells[i].getBoundingClientRect();assert(Math.abs(a.left-b.left)<1&&Math.abs(a.width-b.width)<1,'table columns align across header and body');assert(Math.abs(a.top-header[0].getBoundingClientRect().top)<1&&Math.abs(b.top-cells[0].getBoundingClientRect().top)<1,'cells share the same visual row');assert(Math.abs(b.height-cells[0].getBoundingClientRect().height)<1,'cell borders span the full wrapped row');assert(b.right<=innerWidth,'long table content stays inside viewport')}const host=document.createElement('div');host.innerHTML=LabMarkdown.render(editor.value);assert(host.querySelectorAll('th').length===3&&host.querySelectorAll('td').length===3&&host.textContent.includes('After table.'),'rendered tables use the same tolerance and retain following content')})()`);
await snapshot('table');await evaluate(`document.body.classList.add('light-mode')`);await snapshot('table-light');await evaluate(`document.body.classList.remove('light-mode')`);
await word('Shared');await send('Input.insertText',{text:'X'});
await evaluate(`assert(editor.value===${JSON.stringify(tableSource.replace('Shared','ShXared'))},'editing a rendered table cell changes only that word')`);
const emptyTable='| A | B |\n| :--- | ---: |\n| | right |';await selectSource(emptyTable,0,0);
await evaluate(`assert(document.querySelectorAll('.lab-live-table-cell').length===4,'empty cells keep their column');assert(getComputedStyle(document.querySelectorAll('.lab-live-table-row')[1].querySelectorAll('.lab-live-table-cell')[1]).textAlign==='right','Markdown column alignment is retained')`);
await evaluate(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
const emptyCell=await evaluate(`(() => {const r=document.querySelectorAll('.lab-live-table-row')[1].querySelector('.lab-live-table-cell').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);await click(emptyCell);await send('Input.insertText',{text:'Left'});
await evaluate(`assert(editor.value.endsWith('| Left| right |'),'clicking an empty cell edits its own Markdown position: '+editor.value)`);
await evaluate(`reset();editor.view.dispatch({selection:{anchor:0,head:0}});until(()=>!document.querySelector('.lab-live-syntax'))`);
await evaluate(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
await evaluate(`assertReading();assert(!editorErrors.length,'native editing must not raise update/measurement errors: '+editorErrors.join('\\n'));document.getElementById('result').textContent='PASS'`);
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
