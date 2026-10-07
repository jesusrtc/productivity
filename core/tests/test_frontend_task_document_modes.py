"""Task reading, explicit editing and idle locking use the native Markdown stack."""
from .test_frontend_project_cache import _check_project_html
from .test_frontend_objectives import STATIC


def test_task_view_mode_blocks_changes_and_idle_editing_preserves_drafts(tmp_path):
    setup = r'''
const assert=(ok,message)=>{if(!ok)throw Error(message)};
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const errors=[],actions=[],editors=[];
window.addEventListener('error',event=>errors.push(event.error?.stack||event.message));
window.addEventListener('unhandledrejection',event=>errors.push(String(event.reason)));
// Advance only the long edit-permission deadline. Native editor measurements,
// network work and autosave still use their normal timers.
const now=Date.now,nativeTimeout=window.setTimeout,nativeClear=window.clearTimeout;
let elapsed=0,nextTimer=0;const idleTimers=new Map();Date.now=()=>now()+elapsed;
window.setTimeout=(callback,delay,...args)=>{
 if(delay!==180000)return nativeTimeout(callback,delay,...args);
 const id='edit-idle-'+(++nextTimer);idleTimers.set(id,{callback,at:Date.now()+delay});return id;
};
window.clearTimeout=id=>{if(!idleTimers.delete(id))nativeClear(id)};
const advance=ms=>{elapsed+=ms;for(const [id,timer] of idleTimers)if(timer.at<=Date.now()){idleTimers.delete(id);timer.callback();}};
const task=(id,children=[])=>({id,title:id,children,status:'todo',done:false,assets:[],document_id:'details',tab_id:id});
const parent=task('parent',[task('child')]),second=task('second');
const sample='\n## Scope\n\nA [reference](https://example.com) with `inline code`.\n\n### Goals\n\n#### Notes\n\n##### More notes\n\n###### Detail\n\n> Quoted context\n\n| Name | Value |\n| --- | --- |\n| One | Two |\n\n```text\nCode sample\n```\n';
const documentResource={id:'details',kind:'document',title:'Details',path:'details.md',content:{revision:'doc',body:'Root body',tabs:[parent,...parent.children,second].map(t=>({id:t.id,title:t.title,body:'# '+t.title+'\n\n**Read** the details.\n\n- [ ] Keep this unchanged\n'+sample,parent:{id:'details'}}))}};
const objective={id:'one',name:'One',color:'#58a6ff',path:'/workspace/objectives/one',purpose:'',tasks:[parent,second],resources:[documentResource],worktrees:[],shared_assets:[],archived_assets:[],trashed_assets:[]};
const fixture={enabled:true,revision:'fixture',objectives:[objective],focused:['one'],terminal_links:{}};
let rejectSave=false;
window.fetch=async(url,options={})=>{
 if(options.method==='POST'){
  const action=JSON.parse(options.body).action;actions.push(action);
  if(rejectSave){rejectSave=false;return {ok:false,json:async()=>({detail:'Document changed elsewhere. Your draft is still here; Revert loads the saved version.'})};}
  if(action.type==='document'){
   if(action.tab_id)documentResource.content.tabs.find(t=>t.id===action.tab_id).body=action.body;
   else documentResource.content.body=action.body;
   documentResource.content.revision+='!';
  }else throw Error('Unexpected mutation '+action.type);
  fixture.revision+='!';
 }
 return {ok:true,json:async()=>structuredClone(fixture)};
};
const createEditor=LabMarkdownEditor.create;
LabMarkdownEditor.create=(node,options)=>{const editor=createEditor(node,options);editors.push(editor);return editor};
const editor=()=>editors.find(input=>input.view.dom.isConnected);
const click=selector=>{const node=document.querySelector(selector);assert(node,'Missing '+selector);node.click()};
const open=id=>click('.objective-sidebar-task [data-open-task="'+id+'"]');
const mode=()=>document.querySelector('.objective-document').dataset.documentMode;
const preview=()=>document.querySelector('.objective-document-preview');
const append=text=>{const view=editor().view;view.dispatch({changes:{from:view.state.doc.length,insert:text}})};
const saved=id=>documentResource.content.tabs.find(t=>t.id===id).body;
const style=node=>{assert(node,'Missing formatted element');const computed=getComputedStyle(node);return ['fontFamily','fontSize','fontWeight','lineHeight','color'].map(property=>computed[property]).join('|')};
LabObjectives.connect({context:()=>({workspace_id:'workspace',vault:'fixture',path:'/workspace'}),prepareCenter:()=>{}});
(async()=>{try{
 await LabObjectives.load();LabObjectives.selectObjective('one',{activateTerminal:false});open('parent');await tick();
 assert(mode()==='view'&&!editor()&&!document.querySelector('[contenteditable=true]'),'task defaults to a real read-only surface');
 assert(preview().querySelector('strong').textContent==='Read'&&preview().querySelector('input').disabled,'view renders Markdown with locked checkboxes');
 assert(document.querySelector('[data-task-document-mode=view]').getAttribute('aria-pressed')==='true','View toggle reflects default');
 for(const selector of ['.objective-task-mode-head [data-task-done]','[data-edit-objective-task]','[data-rename-objective-resource]']){
  assert(document.querySelector(selector).disabled,selector+' disabled');click(selector);
 }
 const completion=document.querySelector('.objective-task-mode-head [data-task-done]');completion.dispatchEvent(new Event('change',{bubbles:true}));
 assert(actions.length===0&&!document.querySelector('dialog'),'View cannot mutate task/document metadata');
 assert(document.querySelector('[data-save-objective-document]').hidden&&document.querySelector('[data-revert-objective-document]').hidden,'editing actions hidden in View');
 const readStyles=[...Array.from({length:6},(_,i)=>style(preview().querySelector('h'+(i+1)))),...['strong','a','code:not(pre code)','blockquote','td','pre code'].map(selector=>style(preview().querySelector(selector)))];
 const readColumn=preview().getBoundingClientRect();
 const readBody=preview().getBoundingClientRect();const readHeadingOffset=preview().querySelector('h2').getBoundingClientRect().top-readBody.top;
 const readCheckOffset=preview().querySelector('input').getBoundingClientRect().left-readBody.left;
 click('[data-task-document-mode=edit]');await tick();const firstEditor=editor();
 assert(mode()==='edit'&&firstEditor&&!document.querySelector('[data-rename-objective-resource]').disabled,'explicit Edit restores native editing');
 const editStyles=[...Array.from({length:6},(_,i)=>style(firstEditor.view.dom.querySelector('.lab-live-heading-'+(i+1)))),...['strong','a','.lab-live-code-inline','.lab-live-quote','.lab-live-table-row:not(.lab-live-table-header) .lab-live-table-cell','.lab-live-code-line'].map(selector=>style(firstEditor.view.dom.querySelector(selector)))];
 assert(JSON.stringify(readStyles)===JSON.stringify(editStyles),'View/Edit typography matches: '+JSON.stringify({readStyles,editStyles}));
 const editColumn=firstEditor.view.dom.getBoundingClientRect();assert(Math.abs(readColumn.width-editColumn.width)<1&&Math.abs(readColumn.left-editColumn.left)<1,'View/Edit document column matches');
 assert(Math.abs(readHeadingOffset-(firstEditor.view.dom.querySelector('.lab-live-heading-2').getBoundingClientRect().top-editColumn.top))<1,'View/Edit paragraph and list spacing matches');
 assert(Math.abs(readCheckOffset-(firstEditor.view.dom.querySelector('.lab-live-task-check').getBoundingClientRect().left-editColumn.left))<1,'View/Edit task checkbox indentation matches without an extra bullet');
 append('\n\nA preserved draft.');click('[data-task-document-mode=view]');await tick();await tick();
 assert(mode()==='view'&&!editor()&&preview().textContent.includes('A preserved draft.')&&saved('parent').includes('A preserved draft.'),'manual View saves and renders the draft');
 click('[data-task-document-mode=edit]');await tick();
 assert(editor()===firstEditor&&editors.length===1,'re-entering Edit retains editor state and undo');
 click('[data-objective-terminals-all]');assert(mode()==='edit'&&editor()===firstEditor&&document.querySelector('[data-task-document-mode=edit]'),'Show all terminals preserves edit ownership');
 click('[data-objective-terminals-all]');append('\n\nSaved on idle lock.');
 advance(120000);assert(mode()==='edit','two minutes alone does not lock');
 document.getElementById('content').dispatchEvent(new Event('scroll'));
 advance(120000);assert(mode()==='edit','scrolling the document resets inactivity');
 advance(60001);await tick();await tick();
 assert(mode()==='view'&&!editor()&&saved('parent').includes('Saved on idle lock.'),'three minutes of inactivity locks and saves');
 assert(!saved('child').includes('preserved draft')&&!saved('second').includes('idle lock'),'sibling bodies stay unchanged');
 click('[data-task-document-mode=edit]');append('\n\nSaved on navigation.');open('child');await tick();await tick();
 assert(mode()==='view'&&!editor()&&preview().querySelector('h1').textContent==='child','subtask navigation resets permission');
 assert(saved('parent').includes('Saved on navigation.'),'outgoing Edit draft saved');
 click('[data-task-document-mode=edit]');advance(120000);open('parent');await tick();click('[data-task-document-mode=edit]');
 advance(60001);assert(mode()==='edit','outgoing subtask timer cannot lock a newly opened task');
 click('[data-edit-objective-task]');const modal=document.querySelector('dialog');modal.querySelector('[name=title]').value='Keep this pending title';
 advance(180001);await tick();
 assert(mode()==='view'&&modal.querySelector('[type=submit]').disabled&&modal.querySelector('[name=title]').disabled,'idle lock also disables an open mutation form');
 assert(modal.querySelector('[name=title]').value==='Keep this pending title'&&!modal.querySelector('[data-cancel]').disabled,'pending form values and Cancel remain');
 click('[data-cancel]');
 click('[data-task-document-mode=edit]');append('\n\nConflict draft.');rejectSave=true;
 click('[data-task-document-mode=view]');await tick();await tick();await tick();
 assert(mode()==='view'&&preview().textContent.includes('Conflict draft.')&&document.querySelector('.objective-document-status.error'),'failed idle/manual saves retain the visible draft and error');
 assert(!saved('parent').includes('Conflict draft.'),'rejected save does not change the file');
 click('[data-task-document-mode=edit]');assert(editor()===firstEditor&&editor().value.includes('Conflict draft.'),'conflict draft remains editable after explicit unlock');
 click('[data-revert-objective-document]');await tick();await tick();
 assert(!editor().value.includes('Conflict draft.')&&!document.querySelector('.objective-document-status.error'),'Edit Revert safely restores saved body');
 click('[data-close-objective-task]');assert(LabObjectives.openOwnedFile('/workspace','details.md'),'Files opens the owned document');await tick();
 assert(editor()&&mode()==='edit'&&!document.querySelector('[data-task-document-mode]'),'ordinary Objective documents retain their existing editor');
 assert(errors.length===0,'Browser errors: '+errors.join('\n'));document.body.dataset.result='pass';
}catch(error){document.body.dataset.result='fail';document.body.append(String(error.stack||error));}})();
'''
    scripts = '\n'.join('<script>'+(STATIC/path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js', 'vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js', 'vendor/lab-markdown-editor/markdown-editor.min.js',
        'js/lib/workspace-objectives.js'])
    css = '\n'.join((STATIC/path).read_text() for path in ['css/lab-shell.css', 'css/workspace-objectives.css'])
    html = '<style>'+css+'</style><aside id="sidebar"><div data-project-sidebar="/workspace"><section data-objectives-sidebar></section></div></aside><main id="content"></main><section id="termSessionList"><div class="objective-terminal-group"><button data-objective-terminals-all="one">Show all</button></div></section>'+scripts+'<script>'+setup+'</script>'
    _check_project_html(tmp_path, html)
