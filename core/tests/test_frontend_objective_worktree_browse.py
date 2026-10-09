"""Objective worktree browsing keeps task identity and scoped file ownership."""
from pathlib import Path

from .test_frontend_project_cache import _check_project_html
from .test_frontend_terminal_ui import _run_node, LAB_APP

OBJECTIVES = LAB_APP.parent / 'lib/workspace-objectives.js'


def test_task_terminals_default_off_preserve_existing_sessions_and_enable_deliberately():
    source = OBJECTIVES.read_text()
    helpers = source[source.index('  function terminalIdentity('):source.index('  function sidebarTarget(')]
    helpers += source[source.index('  function openTask(id,'):source.index('  function openTaskAssets(')]
    helpers += source[source.index('  function activateLinkedTerminal('):source.index('  function selectObjective(')]
    result = _run_node(r'''
const task=id=>({id,title:id,status:'in_progress',children:[],document_id:'doc-'+id,tab_id:id});
const o={id:'one',name:'One',tasks:[task('existing'),task('missing')],worktrees:[],resources:[]};
const registry={enabled:true,focused:['one'],objectives:[o],terminal_links:{main:{objective_id:'one',main:'objective'},existing:{objective_id:'one',task_id:'existing'}}};
const sessions=['main','existing'].map(name=>({name,session_id:name,logical_name:name}));
const view={terminalAll:{}},state=()=>view,context=()=>({workspace_id:'work',path:'/workspace'}),key=s=>s.workspace_id;
const data=()=>registry,active=()=>true,objective=()=>o,tasks=o=>o?.tasks||[],focusedTask=()=>o.tasks.find(t=>t.id===view.focus?.task);
const taskStatus=t=>t.status,taskDisplayName=t=>t.title,taskIcon=()=>'',customTaskIcon=()=>'',esc=String;
const opened=[],created=[],activated=[],resetWorktreeBrowse=()=>{},persistView=()=>{},openResource=(...args)=>opened.push(args);
const terminalLaunchContext=()=>({id:o.id,context:context(),task:focusedTask()}),selectObjective=()=>{};
const bridge={sessions:()=>sessions,refreshTerminals:()=>{},activateLinkedTerminal:ids=>activated.push(ids),createTaskTerminal:async(_,t)=>{created.push(t.id);return null;}};
''' + helpers + r'''
(async()=>{
 const before=JSON.stringify(sessions),defaults=terminalSessions(sessions);
 openTask('missing',{activateTerminal:true});await Promise.resolve();
 const createdByDefault=[...created];openTask('existing',{activateTerminal:true});
 registry.task_terminals=true;const enabled=terminalSessions(sessions);
 openTask('missing',{activateTerminal:true});await Promise.resolve();
 registry.task_terminals=false;const disabled=terminalSessions(sessions);
 console.log(JSON.stringify({defaults:defaults.map(t=>t.task_id||t.name),enabled:enabled.map(t=>t.task_id||t.name),disabled:disabled.map(t=>t.task_id||t.name),createdByDefault,created,activated,opened,unchanged:before===JSON.stringify(sessions)}));
})().catch(e=>{console.error(e);process.exit(1)});
''')
    assert result['defaults'] == result['disabled'] == ['workflow-terminal:work:main', 'main', 'existing']
    assert result['enabled'] == ['workflow-terminal:work:main', 'main', 'existing', 'missing']
    assert result['createdByDefault'] == [] and result['created'] == ['missing']
    assert result['activated'] == [['existing']]
    assert result['opened'] == [['doc-missing', 'missing'], ['doc-existing', 'existing'], ['doc-missing', 'missing']]
    assert result['unchanged']


def test_wip_filter_includes_inherited_children_and_keeps_all_sessions_recoverable():
    source = OBJECTIVES.read_text()
    helpers = source[source.index('  function terminalIdentity('):source.index('  function sidebarTarget(')]
    result = _run_node(r'''
const task=(id,status)=>({id,title:id,status,children:[]});
const o={id:'one',name:'One',tasks:[task('working','in_progress'),task('todo','todo'),task('done','done'),task('recommended','in_progress')],worktrees:[]};
const sessions=['global','working','extra','grandchild','todo','done','unassigned'].map(name=>({name,session_id:name,logical_name:name}));
const links={global:{objective_id:'one'},working:{objective_id:'one',task_id:'working'},todo:{objective_id:'one',task_id:'todo'},done:{objective_id:'one',task_id:'done'},extra:{objective_id:'one',view:'tasks'},grandchild:{objective_id:'one',view:'tasks'}};
const registry={enabled:true,task_terminals:true,focused:['one'],objectives:[o],terminal_links:links};
const data=()=>registry,active=()=>true,context=()=>({workspace_id:'work',path:'/workspace'}),tasks=o=>o?.tasks||[],taskDisplayName=t=>t.title;
const taskStatus=t=>t.status,taskIcon=()=>'',customTaskIcon=()=>'';
const view={terminalAll:{}},state=()=>view;
let selected=null;const focusedTask=()=>o.tasks.find(t=>t.id===selected),objective=()=>o;
const parents={extra:'working',grandchild:'extra'},bridge={parentTerminal:t=>sessions.find(s=>s.name===parents[t.name])};
''' + helpers + r'''
const original=JSON.stringify(sessions),filtered=terminalSessions(sessions),all=terminalSessions(sessions,{wipOnly:false});
view.terminalAll.one=true;const objectiveAll=terminalSessions(sessions);view.terminalAll.one=false;
selected='todo';const withTodo=terminalSessions(sessions);selected='done';const withDone=terminalSessions(sessions);selected=null;
links.working.task_id='done';const after=terminalSessions(sessions);
console.log(JSON.stringify({objectiveAll:objectiveAll.map(s=>s.task_id||s.name),withTodo:withTodo.map(s=>s.task_id||s.name),withDone:withDone.map(s=>s.task_id||s.name),filtered:filtered.map(s=>s.task_id||s.name),all:all.map(s=>s.task_id||s.name),after:after.map(s=>s.task_id||s.name),unchanged:original===JSON.stringify(sessions)}));
''')
    assert result['filtered'] == ['workflow-terminal:work:main', 'global', 'working', 'recommended', 'extra', 'grandchild']
    assert set(result['all']) == {'workflow-terminal:work:main','global','working','todo','done','recommended','extra','grandchild','unassigned'}
    assert result['objectiveAll'] == result['all']
    assert result['withTodo'] == ['workflow-terminal:work:main', 'global', 'working', 'todo', 'recommended', 'extra', 'grandchild']
    assert result['withDone'] == ['workflow-terminal:work:main', 'global', 'working', 'done', 'recommended', 'extra', 'grandchild']
    assert result['after'] == ['workflow-terminal:work:main', 'global', 'working', 'recommended']  # WIP primary is now recommended.
    assert result['unchanged']


def test_worktree_click_assignments_restore_task_and_union_recent_files_in_chrome(tmp_path):
    app = LAB_APP.read_text()
    recent = app[app.index('  function _sidebarObjectiveRecent('):app.index('  function _sidebarProjectRecent(')]
    setup = r'''
const assert=(ok,message)=>{if(!ok)throw Error(message)};
const tick=()=>new Promise(r=>setTimeout(r,0));
const task=(id,title,children=[])=>({id,title,children,status:'in_progress',done:false,assets:[],document_id:'details',tab_id:id});
const parent=task('parent','Original task',[task('child','Original subtask')]),second=task('second','Second task');
parent.assets=[{id:'root',folder:{root:'/workspace',path:'.'}},{id:'branch',folder:{root:'/trees/topic',path:'.'}}];
const o={id:'one',name:'One',path:'/workspace/objectives/one',color:'#58a6ff',purpose:'',tasks:[parent,second],resources:[{id:'details',kind:'document',title:'Details',path:'details.md',content:{revision:'doc',tabs:[parent,...parent.children,second].map(t=>({id:t.id,title:t.title,body:'Details of '+t.title,parent:{id:'details'}}))}}],worktrees:[{id:'topic',path:'/trees/topic',resolved_path:'/resolved/topic',label:'topic',color:'#bc8cff',repo:'/workspace',kind:'worktree'}],shared_assets:[],archived_assets:[],trashed_assets:[]};
const fixture={enabled:true,revision:'fixture',objectives:[o],focused:['one'],terminal_links:{}};
const actions=[],errors=[],requests=[];let fileRoot='/workspace';
window.addEventListener('error',event=>errors.push(event.error?.stack||event.message));
window.addEventListener('unhandledrejection',event=>errors.push(String(event.reason)));
window.fetch=async(url,options={})=>{
 if(options.method==='POST'){
  const action=JSON.parse(options.body).action;actions.push(action);
  if(action.type==='task-asset'){const t=[parent,...parent.children,second].find(t=>t.id===action.task_id);if(!t.assets.some(a=>a.folder?.root===action.folder.root))t.assets.push({id:'asset-'+t.id,folder:action.folder});}
  fixture.revision+='!';
 }
 return {ok:true,json:async()=>structuredClone(fixture)};
};
window.marked={};window.DOMPurify={};window.LabMarkdownEditor={create:(node,options)=>{node.textContent=options.body;return {value:options.body,destroy(){},focus(){}}}};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),escAttr=esc;
const _sidebarFileConfig={trackMode:'all',recentMinutes:60},showWorkspaceDotFiles=false,_workspaceDocPath=null;
const _sidebarCurrentSortMode=()=> 'recent',_sidebarRecentTypeAllowed=()=>true,_sidebarCompareFiles=(a,b)=>a.path.localeCompare(b.path),_sidebarCommitProjectView=()=>{};
const _sidebarRecentSectionHtml=(files,active,root)=>files.map(f=>`<a data-entry-root="${esc(root)}" data-filepath="${esc(f.path)}">${esc(f.path)}</a>`).join('');
const ProjectSidebar={read:(url,update,current,options)=>requests.push({url,update,current,options})};
const view=document.querySelector('[data-project-sidebar]');view._project={baseRoot:'/workspace'};
const host=view.querySelector('[data-project-recent]');
function refresh(mode='mtime'){const scopes=LabObjectives.recentScopes('/workspace');view.dataset.objectiveSidebarMode=LabObjectives.sidebarMode('/workspace');view.dataset.objectiveRecentScopes=scopes.length;_sidebarObjectiveRecent(view,host,scopes,mode,60,()=>true);}
LabObjectives.connect({context:()=>({workspace_id:'workspace',vault:'fixture',path:'/workspace'}),prepareCenter:()=>{},scopeRoot:()=>fileRoot,selectWorktree:row=>{fileRoot=row.path},refreshRecent:refresh});
const click=selector=>{const node=document.querySelector(selector);assert(node,'missing '+selector);node.click()};
const drop=(tree,id)=>{const transfer=new DataTransfer();document.querySelector('.objective-worktrees [data-select-worktree="'+tree+'"]').dispatchEvent(new DragEvent('dragstart',{bubbles:true,cancelable:true,dataTransfer:transfer}));document.querySelector('#content [data-task-id="'+id+'"]').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));document.dispatchEvent(new DragEvent('dragend',{bubbles:true}));};
const reply=(request,path)=>{if(request.current())request.update({entries:[{path,type:'file'}],total:1});};
(async()=>{try{
 await LabObjectives.load();LabObjectives.selectObjective('one',{activateTerminal:false});
 assert(document.querySelector('.objective-worktrees').hidden,'Worktrees starts folded');
 assert(document.querySelector('.objective-worktree-navigation').nextElementSibling.classList.contains('objective-sidebar-tasks'),'Worktrees above Tasks');
 assert(document.querySelectorAll('.objective-worktrees [data-select-worktree]').length===3,'Root, Objective and Objective worktree tracked');
 assert(!document.querySelector('.objective-worktrees h4'),'clean worktree buttons without assignment headings');
 click('.objective-sidebar-task [data-open-task="parent"]');await tick();
 assert(document.querySelector('.objective-sidebar-task-title').textContent==='Original task'&&!document.querySelector('.objective-sidebar-task.active .objective-task-worktree-name'),'multiple worktrees preserve the task name');
 assert(document.querySelector('#content').textContent.includes('Details of Original task'),'original task Markdown is opened: '+errors.join(' / '));
 const taskAssets=document.querySelector('[data-objective-bucket=task]'),taskWorktrees=document.querySelector('.objective-task-worktrees');
 assert(taskAssets.nextElementSibling===taskWorktrees&&taskWorktrees.getAttribute('aria-label')==='Worktrees for this task','task Worktrees immediately follows assets');
 assert(!taskAssets.querySelector('[data-objective-worktree]')&&taskAssets.querySelector('[data-objective-root=workspace-root]'),'assets retain the Root folder and omit worktrees');
 assert(taskWorktrees.querySelectorAll('[data-objective-worktree]').length===1&&taskWorktrees.querySelector('[data-select-worktree=topic]'),'only assigned worktrees in task section');
 const oldRequests=requests.slice();
 document.querySelector('.objective-worktree-navigation').dispatchEvent(new MouseEvent('mouseenter'));
 assert(document.querySelector('.objective-worktrees').hidden,'hover keeps Worktrees folded');
 document.querySelector('[data-fold-worktrees]').focus();
 assert(document.querySelector('.objective-worktrees').hidden,'focus keeps Worktrees folded');
 click('[data-fold-worktrees]');
 assert(!document.querySelector('.objective-worktrees').hidden,'explicit click reveals Worktrees');
 document.querySelector('.objective-worktree-navigation').dispatchEvent(new MouseEvent('mouseleave'));
 assert(!document.querySelector('.objective-worktrees').hidden,'leaving navigation keeps it open until an outside click');
 click('.objective-worktrees [data-select-worktree="topic"]');await tick();
 assert(LabObjectives.sidebarMode('/workspace')==='worktree'&&fileRoot==='/trees/topic','selected checkout owns file mode');
 assert(getComputedStyle(document.querySelector('.objective-sidebar-tasks')).display==='none'&&getComputedStyle(document.querySelector('[data-objective-bucket=task]')).display==='none','task assets replaced by files');
 assert(document.querySelectorAll('#content .objective-task-row').length===3,'all tasks and subtasks unfolded in middle');
 assert(getComputedStyle(document.querySelector('[data-project-directory]')).display!=='none','native Files visible in worktree mode');
 const rootRequest=oldRequests.find(r=>r.url.includes('path=%2Fworkspace&'));
 assert(rootRequest&&!rootRequest.current(),'previous task union callback invalidated');
 reply(rootRequest,'stale.md');assert(!host.textContent.includes('stale.md'),'late outgoing request cannot paint');
 drop('topic','second');await tick();await tick();
 drop('objective-root','child');await tick();await tick();
 assert(actions.length===2&&actions.every(a=>!a.choose_icon),'worktree drag assigns many tasks without changing icons');
 assert(document.querySelector('.objective-sidebar-task[data-task-id=second] .objective-task-worktree-name').textContent==='topic'&&document.querySelector('.objective-sidebar-task[data-task-id=second] .objective-task-worktree-name').style.getPropertyValue('--worktree-color')==='#bc8cff','one worktree replaces the task label with its own name and color');
 assert(second.assets.some(a=>a.folder.root==='/trees/topic')&&parent.children[0].assets.some(a=>a.folder.root===o.path),'task and subtask memberships persist');
 assert(parent.assets.length===2&&second.title==='Second task'&&parent.title==='Original task','assignment retains earlier owners and canonical titles');
 assert(LabObjectives.sidebarMode('/workspace')==='worktree','assignments keep browse mode open');
 document.querySelector('#content').click();
 assert(document.querySelector('.objective-worktrees').hidden&&document.querySelector('[data-fold-worktrees]').getAttribute('aria-expanded')==='false','clicking elsewhere folds the navigation');
 assert(LabObjectives.sidebarMode('/workspace')==='worktree'&&fileRoot==='/trees/topic','outside click retains the selected checkout and assignment view');
 click('[data-fold-worktrees]');
 click('[data-fold-worktrees]');await tick();
 assert(document.querySelector('.objective-worktrees').hidden&&LabObjectives.sidebarMode('/workspace')==='task','fold returns to task mode');
 assert(document.querySelector('.objective-sidebar-task.active').dataset.taskId==='parent'&&document.querySelector('#content').textContent.includes('Details of Original task'),'fold restores previous task and own document');
 assert(getComputedStyle(document.querySelector('.objective-sidebar-tasks')).display!=='none'&&getComputedStyle(document.querySelector('[data-objective-bucket=task]')).display!=='none','fold restores Tasks and task assets');
 assert(getComputedStyle(document.querySelector('[data-project-directory]')).display==='none','task mode shows recent files only');
 const roots=LabObjectives.recentScopes('/workspace');assert(JSON.stringify(roots.map(r=>r.path))===JSON.stringify(['/workspace','/trees/topic']),'only assigned roots in task union');
 for(const root of roots){const request=requests.filter(r=>r.url.includes('path='+encodeURIComponent(root.path)+'&')).at(-1);assert(request.options.maxAge===5000,'five second freshness');reply(request,root.id+'-updated.md');}
 assert(host.querySelectorAll('[data-recent-root]').length===2&&host.querySelector('[data-entry-root="/workspace"]')&&host.querySelector('[data-entry-root="/trees/topic"]'),'recent files keep each checkout owner');
 assert(!host.querySelector('[data-recent-root="'+o.path+'"]'),'unassigned Objective files excluded');
 const union=host.innerHTML;LabObjectives.paint();assert(host.innerHTML===union,'unchanged sidebar paint keeps recent rows');
 const first=requests.filter(r=>r.url.includes('path=%2Fworkspace&')).at(-1),page={entries:[{path:'first.md',type:'file'}],total:2,next_offset:1,cache:{updated:1}};
 first.update(page);host.querySelector('[data-more-recent="workspace-root"]').click();
 const more=requests.at(-1);assert(more.url.includes('&offset=1')&&more.current(),'root-specific pagination');more.update({entries:[{path:'second.md',type:'file'}],total:2,next_offset:null});
 const loaded=host.querySelector('[data-recent-root="/workspace"]');first.update({...page,cache:{updated:2}});assert(host.querySelector('[data-recent-root="/workspace"]')===loaded&&loaded.textContent.includes('second.md'),'unchanged fresh snapshot preserves loaded pages and DOM');
 refresh('local-main');
 const comparisons=roots.map(root=>requests.filter(r=>r.url.includes('repo='+encodeURIComponent(root.path)+'&mode=local-main')).at(-1));
 comparisons[0].update({entries:[],total:0,available:false,base_ref:'main'});
 reply(comparisons[1],'still-visible.md');
 assert(host.querySelectorAll('.objective-recent-status').length===1&&host.textContent.includes('Local main comparison unavailable')&&host.querySelector('[data-entry-root="/trees/topic"]'),'unavailable comparison stays compact and keeps successful checkout files visible');
 comparisons[1].update({entries:[],total:0,available:false,base_ref:'main'});
 assert(!host.querySelector('[data-recent-root]')&&host.querySelectorAll('.objective-recent-status').length===1&&host.textContent.includes('for 2 folders'),'many missing branches share one notice, without repeated empty worktree headings');
 assert(getComputedStyle(host.querySelector('.objective-recent-status')).fontSize==='12px'&&host.textContent.includes('Choose Uncommitted or a time filter'),'comparison notice has explicit compact typography and explains alternate filters');
 comparisons[0].update({entries:[],total:0,available:true});comparisons[1].update({entries:[],total:0,available:true});
 assert(host.querySelectorAll('.objective-recent-status').length===1&&host.textContent==='No matching recent files','empty results share one quiet message');
 click('.objective-sidebar-task [data-open-task="second"]');await tick();
 assert(document.querySelector('.objective-task-worktrees [data-select-worktree=topic]'),'switching tasks displays that task worktree');
 assert(!document.querySelector('[data-objective-bucket=task] [data-objective-worktree]'),'worktrees never return to task assets');
 click('.objective-task-worktrees [data-select-worktree=topic]');await tick();
 assert(document.querySelector('.objective-worktrees').hidden&&LabObjectives.sidebarMode('/workspace')==='worktree','task worktree opens its checkout without unfolding global navigation');
 click('.objective-sidebar-task [data-open-task="child"]');await tick();
 assert(!document.querySelector('.objective-task-worktrees [data-objective-worktree]')&&document.querySelector('.objective-task-worktrees').textContent.includes('No worktrees assigned'),'unassigned child has its own empty worktree section');
 assert(errors.length===0,'no browser errors: '+errors.join('\n'));document.body.dataset.result='pass';
}catch(error){document.body.dataset.result='fail';document.body.append(String(error.stack||error));}})();
'''
    css = (LAB_APP.parents[1] / 'css/workspace-objectives.css').read_text()
    html = '<style>'+css+'</style><div id="sidebar"><div data-project-sidebar="/workspace"><section data-objectives-sidebar></section><div class="sidebar-recent-selectors"></div><section data-project-recent></section><div class="sidebar-title">Files</div><section data-project-directory=".">files</section></div></div><main id="content"></main><script>'+OBJECTIVES.read_text()+'</script><script>'+recent+setup+'</script>'
    _check_project_html(tmp_path, html)
