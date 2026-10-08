"""Native task controls save schedules and verify the real Markdown before completion."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
from threading import Thread

from lab import assistant_tasks, assistant_records as records
from .test_frontend_project_cache import _check_project_html
from .test_objectives import objective_workspace, apply  # noqa: F401
from .test_assistant_document_tasks import owned_tasks, legacy_tasks  # noqa: F401
from .test_task_cycles import write_objective_body

STATIC = Path(__file__).resolve().parents[1] / 'src/core/static'


def test_native_schedules_checklists_and_completion(client,monorepo,objective_workspace,owned_tasks,tmp_path):
    folder, oid = objective_workspace
    data = apply(monorepo,oid,'task',title='Monthly review')
    task = data['objectives'][0]['tasks'][0]
    write_objective_body(monorepo,oid,task,'- [ ] Required review\n')
    root,note,*_ = owned_tasks
    tab = records.create_subtab(root,'Daily actions',parent={'type':'note','id':note.stem})
    tab_id = records.resolve(root,str(tab.relative_to(root)))[1]['id']
    records.update_body(root,str(tab.relative_to(root)),'- [ ] Required check\n',expected='')
    result = assistant_tasks.change(root,note.stem,{'title':'Daily check','tab_id':tab_id})
    fixture = {'workspace':str(folder),'objective':oid,'task':task['id'],'assistant':note.relative_to(root).as_posix(),'assistant_task':result['task_id'],'root':str(root),'tab':tab_id}
    checks = r'''
const assert=(ok,message)=>{if(!ok)throw Error(message)};
const until=async fn=>{for(let i=0;i<500;i++){if(await fn())return;await new Promise(r=>setTimeout(r,10));}throw Error('Timed out: '+fn)};
const click=selector=>{const node=document.querySelector(selector);assert(node,'Missing '+selector);node.click()};
const set=(selector,value)=>{const node=document.querySelector(selector);assert(node,'Missing '+selector);node.value=value;node.dispatchEvent(new Event('change',{bubbles:true}))};
const objective=async()=> (await (await fetch('/api/objectives?workspace_id=demo')).json()).objectives[0].tasks[0];
const assistant=async()=> (await (await fetch('/api/assistant/note?path='+encodeURIComponent(FIX.assistant))).json());
const errors=[],notices=[],editors=[];
window.addEventListener('error',event=>errors.push(event.message));
window.addEventListener('unhandledrejection',event=>errors.push(String(event.reason)));
window.explorerToast=message=>notices.push(message);
const createEditor=LabMarkdownEditor.create;LabMarkdownEditor.create=(...args)=>{const editor=createEditor(...args);editors.push(editor);return editor};
(async()=>{try{
  const ctx={workspace_id:'demo',path:FIX.workspace};
  LabObjectives.connect({context:()=>ctx,prepareCenter:()=>{}});
  await LabObjectives.load();LabObjectives.selectObjective(FIX.objective,{activateTerminal:false});
  click('[data-open-objective-tasks]');
  assert(document.querySelector('.objective-task-row').textContent.includes('0 completed · 1 pending'),'required progress is visible');
  click('[data-schedule-task="'+FIX.task+'"]');
  assert(document.querySelector('[data-cycle-fields]').hidden,'one-off task starts with repeat settings hidden');
  set('dialog [name=cycle_unit]','month');set('dialog [name=due]','2050-01-31');set('dialog [name=cycle_time]','09:00');set('dialog [name=cycle_timezone]','UTC');
  assert(document.querySelector('[name=cycle_lead]').value==='1'&&document.querySelector('[name=cycle_lead_unit]').value==='1440','default is one day');
  document.querySelector('dialog form').requestSubmit();await until(()=>!document.querySelector('dialog'));
  let task=await objective();assert(task.recurrence.unit==='month'&&task.recurrence.reactivate_before_minutes===1440,'Objective schedule persisted');
  click('.objective-task-row [data-task-done]');await until(()=>notices.some(message=>message.includes('pending action item')));
  await until(()=>!document.querySelector('.objective-task-row [data-task-done]').checked);
  assert(!(await objective()).done,'pending actions block completion');
  click('.objective-task-row [data-open-task]');await until(()=>document.querySelector('[data-task-document-mode=edit]'));
  click('[data-task-document-mode=edit]');await until(()=>editors.some(editor=>editor.view.dom.isConnected));
  const editor=editors.find(editor=>editor.view.dom.isConnected);
  editor.view.dispatch({changes:{from:0,to:editor.view.state.doc.length,insert:'- [x] Required review\n'}});
  assert(document.querySelector('[data-task-progress]').textContent.includes('1 completed · 0 pending'),'live checklist reflects edited Markdown');
  click('.objective-task-mode-head [data-task-done]');await until(async()=> (await objective()).done);
  task=await objective();assert(task.due==='2050-01-31'&&task.recurrence_next_due==='2050-02-28','completion queues a clamped monthly deadline');
  await until(()=>document.querySelector('[data-task-progress]').textContent.includes('reopens'));
  const detail=await assistant();
  const host=document.getElementById('assistantTasks');
  AssistantTasks.mount(host,{database:FIX.root,root:detail,tab:FIX.tab,navigate:()=>{},changed:async()=>{}});
  assert(host.textContent.includes('0 completed · 1 pending'),'Assistant action items are visible');
  click('#assistantTasks .assistant-tasks-task-menu summary');click('#assistantTasks [data-schedule-task="'+FIX.assistant_task+'"]');
  set('dialog [name=cycle_unit]','day');set('dialog [name=due]','2050-01-01');set('dialog [name=cycle_time]','17:00');set('dialog [name=cycle_timezone]','UTC');
  set('dialog [name=cycle_every]','3');set('dialog [name=cycle_lead]','1');set('dialog [name=cycle_lead_unit]','60');
  document.querySelector('dialog form').requestSubmit();await until(()=>!document.querySelector('dialog'));
  const saved=(await assistant()).document_tasks.tasks.find(task=>task.id===FIX.assistant_task);
  assert(saved.recurrence.unit==='day'&&saved.recurrence.every===3&&saved.recurrence.reactivate_before_minutes===60,'Assistant custom interval and one-hour window persisted');
  click('#assistantTasks [data-check="'+FIX.assistant_task+'"]');await until(()=>!AssistantTasks.busy()&&host.querySelector('[role=alert]')?.textContent.includes('pending action item'));
  assert(!host.querySelector('[data-check="'+FIX.assistant_task+'"]').checked,'Assistant completion cannot bypass action items');
  click('#assistantTasks .assistant-tasks-task-menu summary');click('#assistantTasks [data-schedule-task="'+FIX.assistant_task+'"]');
  set('dialog [name=cycle_unit]','');document.querySelector('dialog form').requestSubmit();await until(()=>!document.querySelector('dialog'));
  assert(!(await assistant()).document_tasks.tasks.find(task=>task.id===FIX.assistant_task).recurrence,'Once disables recurrence');
  assert(!errors.length,'Browser errors: '+errors.join('\n'));document.body.dataset.result='pass';
}catch(error){document.body.dataset.result='fail';document.body.append(error.stack||String(error));}})();
'''
    scripts = '\n'.join('<script>'+(STATIC/path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js','vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js','vendor/lab-markdown-editor/markdown-editor.min.js',
        'js/lib/task-schedule.js','js/lib/workspace-objectives.js','js/views/assistant-tasks.js'])
    css = '\n'.join((STATIC/path).read_text() for path in ['css/lab-shell.css','css/workspace-objectives.css','css/task-schedule.css','css/assistant-tasks.css'])
    page = '<!doctype html><meta charset="utf-8"><style>'+css+'</style><aside id="sidebar"><section data-objectives-sidebar></section></aside><main id="content"></main><section id="assistantTasks"></section>'+scripts+'<script>const FIX='+json.dumps(fixture)+';</script><script>'+checks+'</script>'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def do_GET(self):
            if self.path.startswith('/api/'):
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
