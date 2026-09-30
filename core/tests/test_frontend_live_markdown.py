"""Native typing, idle autosave, conflicts, and recovery of one selected tab."""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import shutil
import subprocess
from threading import Thread
import time

import pytest

from .test_assistant_note_editing import note_data  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'core/src/core/static'


def test_live_markdown_autosaves_and_reverts_only_current_tab(client, note_data, tmp_path):
    from lab import assistant_records as records, assistant_documents as documents
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    root, note, child, sibling, _ = note_data
    original = '# Opening\n\nFirst paragraph with **bold**.\n\n## Second section\n\nOther paragraph.\n'
    records.update_body(root, str(note.relative_to(root)), original, expected=documents.read(note)[1])
    records.update_body(root, str(child.relative_to(root)), '# Child\n\nChild paragraph.', expected='')
    records.update_body(root, str(sibling.relative_to(root)), 'Untouched sibling', expected='')
    fixture = {'note':str(note.relative_to(root)), 'child':str(child.relative_to(root)), 'sibling':str(sibling.relative_to(root)), 'original':original}
    checks = r'''
window.assert=(ok,message)=>{if(!ok)throw new Error(message)};
window.until=async fn=>{for(let i=0;i<400;i++){if(fn())return;await new Promise(r=>setTimeout(r,25));}throw new Error('Timed out: '+fn)};
const makeEditor=LabMarkdownEditor.create;
window.editors=[];
LabMarkdownEditor.create=(parent,options)=>{const editor=makeEditor(parent,options);editors.push(editor);return editor};
window.editor=()=>editors.find(editor=>editor.view.dom.isConnected);
window.realFetch=window.fetch.bind(window);
window.writes=[];
window.fetch=async (url,options={})=>{
 if(url==='/api/assistant/content'&&options.method==='PUT')writes.push({at:Date.now(),...JSON.parse(options.body)});
 const response=await realFetch(url,options);
 if(window.holdSave&&url==='/api/assistant/content'&&options.method==='PUT')await new Promise(resolve=>window.releaseSave=resolve);
 return response;
};
window.read=path=>realFetch('/api/assistant/note?path='+encodeURIComponent(path)).then(r=>r.json());
(async()=>{
 AssistantView.init({section:'notes'});
 await AssistantView.refresh();
 await AssistantView.openDocument('note',FIX.note);
 assert(editor()&&document.querySelector('.cm-content[contenteditable="true"]'),'current tab is editable on open');
 assert(document.querySelector('.lab-live-markdown-block strong')?.textContent==='bold','inactive Markdown renders inline');
 assert(document.querySelector('.lab-live-markdown-block h1')?.textContent==='Opening','heading renders');
 assert(document.querySelectorAll('.cm-editor').length===1,'only current tab mounts an editor');
 document.getElementById('result').textContent='READY';
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    scripts = '\n'.join('<script>' + (STATIC / path).read_text() + '</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js', 'vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js', 'vendor/lab-markdown-editor/markdown-editor.min.js', 'js/views/assistant.js'])
    page = '<!doctype html><meta charset="utf-8"><style>'+ (STATIC/'css/lab-shell.css').read_text()+'</style><body class="assistant-active"><div id="repoTabs"></div><div id="content"></div><pre id="result">PENDING</pre>'+scripts+'<script>const FIX='+json.dumps(fixture)+';</script><script>'+checks+'</script>'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            if self.path.startswith('/api/'):
                response = client.get(self.path)
                data, code, content_type = response.content, response.status_code, 'application/json'
            else:
                data, code, content_type = page.encode(), 200, 'text/html'
            self.send_response(code); self.send_header('Content-Type', content_type); self.end_headers(); self.wfile.write(data)
        def do_POST(self):
            response = client.request(self.command, self.path, json=json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(response.status_code); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(response.content)
        do_PUT = do_POST
    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    profile = tmp_path / 'profile'
    process = subprocess.Popen([chrome, '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run', '--no-default-browser-check', '--user-data-dir='+str(profile), '--remote-debugging-port=0', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    driver = r'''
async function evaluate(expression) {
 const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
 if(result.exceptionDetails)throw new Error(result.exceptionDetails.exception?.description||'Browser check failed');
 return result.result?.value;
}
async function clickAt(point) {
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',...point});
 await send('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1});
 await send('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1});
}
async function typeInParagraph(text, label='First paragraph') {
 const point=await evaluate(`(() => {const block=[...document.querySelectorAll('.lab-live-markdown-block p')].find(node=>node.textContent.includes(${JSON.stringify(label)}));assert(block,'rendered paragraph available');const r=block.getBoundingClientRect();return {x:r.x+40,y:r.y+r.height/2}})()`);
 await clickAt(point);
 await evaluate(`until(()=>editor().view.hasFocus)`);
 await send('Input.insertText',{text});
}
await evaluate(`until(()=>document.getElementById('result').textContent!=='PENDING')`);
await evaluate(`assert(document.getElementById('result').textContent==='READY',document.getElementById('result').textContent)`);
await typeInParagraph('**live** ');
await evaluate(`assert(editor().value.includes('**live** '),'native typing changes the current Markdown source');window.lastInput=Date.now()`);
await send('Input.dispatchKeyEvent',{type:'keyDown',key:'z',code:'KeyZ',modifiers:4,windowsVirtualKeyCode:90});
await send('Input.dispatchKeyEvent',{type:'keyUp',key:'z',code:'KeyZ',windowsVirtualKeyCode:90});
await evaluate(`assert(editor().value===FIX.original,'native undo restores the exact Markdown')`);
await send('Input.insertText',{text:'**live** '});
await evaluate(`window.lastInput=Date.now();window.firstSave=editor().value`);
const title=await evaluate(`(() => {const r=document.getElementById('assistantModalTitle').getBoundingClientRect();return {x:r.x+20,y:r.y+r.height/2}})()`);
await clickAt(title);
await evaluate(`until(()=>[...document.querySelectorAll('.lab-live-markdown-block strong')].some(node=>node.textContent==='live'))`);
await evaluate(`new Promise(resolve=>setTimeout(resolve,9000))`);
await evaluate(`assert(writes.length===0,'autosave waits for the full idle interval')`);
await evaluate(`until(()=>document.getElementById('assistantNoteStatus').textContent.startsWith('Saved at'))`);
await evaluate(`(async()=>{
 assert(writes.length===1&&writes[0].at-lastInput>=9900,'autosave fires after ten idle seconds');
 assert((await read(FIX.note)).body===firstSave,'autosaved Markdown is on disk');
 assert((await read(FIX.sibling)).body==='Untouched sibling','autosave leaves sibling tabs alone');
 assert(document.querySelectorAll('.cm-editor').length===1,'saving keeps only the selected tab editable');
})()`);
await typeInParagraph('In flight ');
await evaluate(`window.holdSave=true;document.getElementById('assistantSaveNote').click();until(()=>window.releaseSave)`);
await send('Input.insertText',{text:'Newer typing '});
await evaluate(`window.latestBody=editor().value;window.holdSave=false;releaseSave();until(()=>document.getElementById('assistantNoteStatus').textContent.startsWith('Unsaved'))`);
await evaluate(`assert(editor().value===latestBody,'typing during a save remains editable and retained');document.getElementById('assistantSaveNote').click();until(()=>document.getElementById('assistantNoteStatus').textContent.startsWith('Saved at'))`);
await evaluate(`(async()=>{assert((await read(FIX.note)).body===latestBody,'later draft saves separately');await realFetch('/api/assistant/content',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:FIX.note,expected:latestBody,body:'External change'})})})()`);
await clickAt(title);
await typeInParagraph('Stale ');
await evaluate(`document.getElementById('assistantSaveNote').click();until(()=>document.getElementById('assistantNoteStatus').textContent.includes('changed elsewhere'))`);
await evaluate(`(async()=>{assert(editor().value.includes('Stale '),'conflict keeps the local draft');assert((await read(FIX.note)).body==='External change','conflict preserves the external version');document.getElementById('assistantRevertNote').click();await until(()=>document.querySelector('[data-discard-note]'));document.querySelector('[data-discard-note]').click();await until(()=>!document.getElementById('assistantNoteHistory'));assert(editor().value==='External change','discard reloads the latest version')})()`);
await evaluate(`document.getElementById('assistantRevertNote').click();until(()=>document.querySelector('[data-restore-note]'))`);
await evaluate(`(() => {const version=[...document.querySelectorAll('#assistantNoteHistory section')].find(row=>row.querySelector('pre').textContent===FIX.original.slice(0,240));assert(version,'original saved version exists');version.querySelector('button').click()})()`);
await evaluate(`until(()=>!document.getElementById('assistantNoteHistory'))`);
await evaluate(`assert(editor().value===FIX.original,'saved version restores exact current-tab content');document.querySelector('[data-rail-tab="'+FIX.child+'"]').click();until(()=>document.querySelector('[data-rail-tab="'+FIX.child+'"][aria-current="page"]'))`);
await typeInParagraph('Child edit ', 'Child paragraph');
await evaluate(`window.childBody=editor().value;document.querySelector('[data-rail-tab="'+FIX.note+'"]').click();until(()=>document.querySelector('[data-rail-tab="'+FIX.note+'"][aria-current="page"]'))`);
await evaluate(`(async()=>{assert(editor().value===FIX.original,'moving with UI selects a different independent editor');assert((await read(FIX.child)).body===childBody,'leaving a tab flushes its own edits');assert((await read(FIX.sibling)).body==='Untouched sibling','third tab remains untouched');assert(document.querySelectorAll('.cm-editor').length===1,'other tabs have no mounted editor')})()`);
await evaluate(`document.getElementById('result').textContent='RELOADING'`);
const reloaded=new Promise(resolve=>{
 const listener=event=>{if(JSON.parse(String(event.data)).method==='Page.loadEventFired'){ws.removeEventListener('message',listener);resolve()}};
 ws.addEventListener('message',listener);
});
await send('Page.reload');
await reloaded;
await evaluate(`until(()=>document.getElementById('result')?.textContent==='READY')`);
await evaluate(`document.getElementById('assistantRevertNote').click();until(()=>document.querySelector('[data-restore-note]'))`);
await evaluate(`assert(document.querySelectorAll('[data-restore-note]').length>=4,'saved history survives a real page reload')`);
await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
await evaluate(`until(()=>!document.getElementById('assistantNoteHistory'))`);
await evaluate(`assert(document.getElementById('assistantDocumentModal').classList.contains('active'),'Escape closes history and keeps the document open');document.getElementById('result').textContent='PASS'`);
'''
    path = tmp_path / 'live-editor.mjs'
    diagnostic = r'''
} catch(error) {
 const dom=await send('Runtime.evaluate',{expression:'document.documentElement.outerHTML',returnByValue:true});
 await writeFile(domPath,String(dom.result?.value||error));
 const screenshot=await send('Page.captureScreenshot',{format:'png'});
 await writeFile(screenshotPath,Buffer.from(screenshot.data,'base64'));ws.close();throw error;
}
'''
    path.write_text((ROOT/'scripts/chrome-dump-auth.mjs').read_text().replace(
        'const evaluated = await send', 'try {\n'+driver+diagnostic+'\nconst evaluated = await send'))
    try:
        deadline = time.monotonic() + 10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic() < deadline
            time.sleep(.05)
        result = subprocess.run(['node', str(path), str(profile), f'http://127.0.0.1:{server.server_port}/', str(tmp_path/'dom.html'), str(tmp_path/'live-markdown.png')], capture_output=True, text=True, timeout=60, env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        assert result.returncode == 0, result.stderr
        assert '<pre id="result">PASS</pre>' in (tmp_path/'dom.html').read_text()
    finally:
        process.terminate(); process.wait(timeout=10); server.shutdown(); server.server_close(); thread.join(timeout=5)
    assert documents.read(note)[1] == original
    assert 'Child edit ' in documents.read(child)[1]
    assert documents.read(sibling)[1] == 'Untouched sibling'
    assert documents.read(note)[0]['custom'] == {'keep': True}
    assert records.verify(root)['valid']
