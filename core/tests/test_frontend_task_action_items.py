"""Native dashboard navigation opens and reveals the authoritative Markdown item."""
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
from threading import Thread

from lab import objectives, task_cycles
from .test_frontend_project_cache import _check_project_html
from .test_objectives import objective_workspace, apply  # noqa: F401
from .test_task_cycles import write_objective_body, config

STATIC = Path(__file__).resolve().parents[1] / 'src/core/static'


def test_pending_hierarchy_deadlines_source_highlights_and_cycle_reactivation(client, monorepo, objective_workspace, tmp_path):
    folder, oid = objective_workspace
    parent = apply(monorepo, oid, 'task', title='Review report')['objectives'][0]['tasks'][0]
    child = apply(monorepo, oid, 'task', title='Child evidence', parent_id=parent['id'])['objectives'][0]['tasks'][0]['children'][0]
    apply(monorepo, oid, 'task', title='Grandchild check', parent_id=child['id'])
    source = '- [ ] [2050-01-03 09:00] Review **evidence**'
    body = '# Review\n\n- [ ] [2050-01-01 09:00] Overdue action\n'+source+'\n- [ ] Undated action\n\n<details>\n<summary>Folded actions</summary>\n\n'+source+'\n\n</details>\n'
    write_objective_body(monorepo, oid, parent, body)
    write_objective_body(monorepo, oid, child, '- [ ] Child action\n')
    for title, status in [('Finished task','done'), ('Discarded task','wont_do')]:
        task = apply(monorepo, oid, 'task', title=title)['objectives'][0]['tasks'][-1]
        if status == 'wont_do':
            write_objective_body(monorepo, oid, task, '- [ ] Discarded action\n')
        apply(monorepo, oid, 'task-update', task_id=task['id'], status=status)
    repeated = apply(monorepo, oid, 'task', title='Waiting repeat', due='2050-01-01', recurrence=config())['objectives'][0]['tasks'][-1]
    repeated_child = apply(monorepo, oid, 'task', title='Repeated child', parent_id=repeated['id'])['objectives'][0]['tasks'][-1]['children'][0]
    write_objective_body(monorepo, oid, repeated, '- [x] Repeated action\n')
    write_objective_body(monorepo, oid, repeated_child, '- [x] Repeated child action\n')
    data = apply(monorepo, oid, 'task-update', task_id=repeated['id'], done=True)['objectives'][0]
    repeated = data['tasks'][-1]
    wake = task_cycles.activation_at(repeated)
    fixture = {'workspace':str(folder), 'objective':oid, 'task':parent['id'], 'source':source,
               'line':data['tasks'][0]['action_items'][-1]['line'], 'repeat':repeated['id'], 'body':body}
    checks = r'''
const assert=(ok,message)=>{if(!ok)throw Error(message)};
const until=async fn=>{for(let i=0;i<500;i++){if(await fn())return;await new Promise(r=>setTimeout(r,10));}throw Error('Timed out: '+fn)};
const click=selector=>{const node=document.querySelector(selector);assert(node,'Missing '+selector);node.click()};
const errors=[],editors=[];window.addEventListener('error',e=>errors.push(e.message));window.addEventListener('unhandledrejection',e=>errors.push(String(e.reason)));
const createEditor=LabMarkdownEditor.create;LabMarkdownEditor.create=(...args)=>{const editor=createEditor(...args);editors.push(editor);return editor};
Date.now=()=>new Date(2050,0,2,12).getTime();
(async()=>{try{
  const ctx={workspace_id:'demo',path:FIX.workspace};LabObjectives.connect({context:()=>ctx,prepareCenter:()=>{}});
  await LabObjectives.load();LabObjectives.selectObjective(FIX.objective,{activateTerminal:false});LabObjectives.renderTasks();
  const sidebar=()=>document.querySelector('.objective-sidebar-task-list');
  assert(sidebar().textContent.includes('Child evidence')&&sidebar().textContent.includes('Grandchild check'),'all levels are visible without WIP or focus');
  assert(!sidebar().querySelector('[data-open-action]')&&!sidebar().textContent.includes('Undated action')&&!sidebar().textContent.includes('Child action'),'Markdown action items stay out of the task sidebar');
  assert(document.querySelector('.objective-task-list').textContent.includes('Undated action')&&document.querySelector('.objective-task-list').textContent.includes('Child action'),'pending actions remain in the main dashboard');
  assert(sidebar().getBoundingClientRect().height<=sidebar().querySelectorAll('.objective-sidebar-task').length*32+1,'sidebar does not reserve blank space for document actions');
  assert(!sidebar().textContent.includes('Finished task')&&!sidebar().textContent.includes('Discarded task')&&!sidebar().textContent.includes('Waiting repeat'),'finished, discarded and waiting tasks hidden');
  assert(!document.querySelector('.objective-task-list').textContent.includes('Discarded task'),'dashboard defaults to pending');
  assert(document.querySelectorAll('.objective-due-dashboard .objective-due-row').length===3,'dated actions including duplicate occurrence are due soon');
  assert(document.querySelector('.objective-due-row').textContent.includes('Overdue action'),'nearest deadline first');
  assert(document.querySelector('.objective-action-due.overdue').textContent.includes('Past due'),'overdue clock shown');
  assert([...document.querySelectorAll('.objective-action-row')].some(row=>row.textContent.includes('No due date')),'undated work retained');
  click('[data-show-finished-tasks]');
  assert(document.querySelector('.objective-task-list').textContent.includes('Finished task')&&document.querySelector('.objective-task-list').textContent.includes('Discarded task'),'history can be reviewed');
  assert(!document.querySelector('.objective-task-list').textContent.includes('Waiting repeat'),'waiting repeat hidden even in history');
  assert(!document.querySelector('.objective-task-list').textContent.includes('Discarded action'),'discarded actions excluded');
  const discarded=[...document.querySelectorAll('.objective-task-row')].find(row=>row.textContent.includes('Discarded task'));
  discarded.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true}));
  assert(document.querySelector('.objective-task-status-menu'),'history retains task status controls');
  click('[data-set-task-status=todo]');await until(()=>sidebar().textContent.includes('Discarded task'));
  const restored=[...document.querySelectorAll('.objective-task-row')].find(row=>row.textContent.includes('Discarded task'));
  restored.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true}));click('[data-set-task-status=wont_do]');
  await until(()=>!sidebar().textContent.includes('Discarded task'));
  click('[data-show-finished-tasks]');
  const selector='.objective-action-row [data-open-action="'+FIX.task+'"][data-action-line="'+FIX.line+'"]';
  const href=document.querySelector(selector).getAttribute('href');
  assert(href.includes('objective_action_line='+FIX.line)&&href.includes('objective_action_source='),'deep link keeps exact source');
  click(selector);await until(()=>document.querySelector('.objective-action-highlight'));
  let target=document.querySelector('.objective-action-highlight');
  assert(target.closest('details')?.open,'closed source section revealed');
  assert(target.querySelector('strong')?.textContent==='evidence','highlight retains Markdown formatting');
  assert(document.querySelectorAll('.objective-action-highlight').length===1,'only requested duplicate highlighted');
  click('[data-task-document-mode=edit]');await until(()=>editors.some(editor=>editor.view.dom.isConnected));
  const editor=editors.find(editor=>editor.view.dom.isConnected);
  assert(editor.view.state.doc.lineAt(editor.view.state.selection.main.from).text===FIX.source,'edit mode selects exact source line');
  assert(editor.value===FIX.body&&!editor.value.includes('objective-action-target'),'navigation does not change Markdown');
  click('[data-task-document-mode=view]');await until(()=>document.querySelector('.objective-action-highlight'));
  LabObjectives.renderTasks();
  // Cmd-click/new-tab hydration must reveal the same source occurrence.
  history.replaceState(null,'',href);LabObjectives.openCurrent();await until(()=>document.querySelector('.objective-action-highlight'));
  assert(document.querySelector('.objective-action-highlight').closest('details').open,'URL hydration reveals exact item');
  LabObjectives.renderTasks();
  await fetch('/test/before-wake');await LabObjectives.load(ctx,true);
  assert(!sidebar().textContent.includes('Waiting repeat'),'still hidden before exact show-again boundary');
  await fetch('/test/reactivate');await LabObjectives.load(ctx,true);LabObjectives.renderTasks();
  assert(sidebar().textContent.includes('Waiting repeat')&&sidebar().textContent.includes('Repeated child'),'whole repeated branch returns');
  assert(!sidebar().textContent.includes('Repeated action')&&!sidebar().textContent.includes('Repeated child action'),'refreshed sidebar still omits document actions');
  assert(document.querySelector('.objective-task-list').textContent.includes('Repeated action')&&document.querySelector('.objective-task-list').textContent.includes('Repeated child action'),'repeated action items return in the dashboard');
  const repeatedRow=document.querySelector('.objective-task-row[data-task-id="'+FIX.repeat+'"]');
  assert(repeatedRow&&!repeatedRow.querySelector('[data-task-done]').checked,'reactivated task is unchecked');
  document.getElementById('sidebar').classList.add('sidebar');document.body.classList.add('sidebar-drawer-enabled');
  await new Promise(requestAnimationFrame);
  assert(!sidebar().querySelector('.objective-sidebar-action,[data-open-action]'),'compact sidebar has task navigation only');
  document.body.classList.add('sidebar-drawer-open');
  assert(!sidebar().querySelector('.objective-sidebar-action,[data-open-action]'),'expanded drawer also omits document actions');
  document.body.classList.remove('sidebar-drawer-enabled','sidebar-drawer-open');document.getElementById('sidebar').classList.remove('sidebar');
  assert(!errors.length,'Browser errors: '+errors.join('\n'));document.body.dataset.result='pass';
}catch(error){document.body.dataset.result='fail';document.body.append(error.stack||String(error));}})();
'''
    scripts = '\n'.join('<script>'+(STATIC/path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js','vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js','vendor/lab-markdown-editor/markdown-editor.min.js',
        'js/lib/task-schedule.js','js/lib/workspace-objectives.js'])
    css = '\n'.join((STATIC/path).read_text() for path in ['css/lab-shell.css','css/workspace-objectives.css','css/task-schedule.css'])
    page = '<!doctype html><meta charset="utf-8"><style>'+css+'</style><aside id="sidebar"><section data-objectives-sidebar></section></aside><main id="content"></main>'+scripts+'<script>const FIX='+json.dumps(fixture)+';</script><script>'+checks+'</script>'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path.startswith('/test/'):
                objectives.refresh_recurring(monorepo, 'demo', now=wake if self.path == '/test/reactivate' else wake-timedelta(microseconds=1))
                data, code, kind = b'{}', 200, 'application/json'
            elif self.path.startswith('/api/'):
                response = client.get(self.path)
                data, code, kind = response.content, response.status_code, response.headers['content-type']
            else:
                data, code, kind = page.encode(), 200, 'text/html'
            self.send_response(code); self.send_header('Content-Type',kind); self.end_headers(); self.wfile.write(data)

        def do_POST(self):
            response = client.post(self.path,json=json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(response.status_code); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(response.content)

    server = HTTPServer(('127.0.0.1',0),Handler)
    thread = Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        _check_project_html(tmp_path,'<script>location.replace('+json.dumps(f'http://127.0.0.1:{server.server_port}/')+')</script>')
    finally:
        server.shutdown(); server.server_close(); thread.join()
