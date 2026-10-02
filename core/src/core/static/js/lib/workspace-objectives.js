/* Workspace objectives own configuration and content; Assistant stays a reference. */
(() => {
  'use strict';
  const cache = new Map(), views = new Map(), pending = new Map(), queues = new Map(), overlays = new Map(), loadedAt = new Map();
  const resourceMime = 'application/x-lab-objective-resource', documentMime = 'application/x-lab-assistant-document';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let bridge, dialog = null, hoverTimer, openView = null;
  const key = scope => (scope?.vault || '') + '::' + scope?.workspace_id;
  const context = () => bridge?.context?.();
  const data = () => cache.get(key(context()));
  function state(scope = context()) {
    const id = key(scope);
    if (!views.has(id)) {
      let saved;try {saved = JSON.parse(localStorage.getItem('lab.objectives.view.v1:' + id));} catch {}
      views.set(id, {objective:saved?.objective || null, tree:saved?.tree || {}, pins:saved?.pins || {}, revealed:new Set(), selected:null});
    }
    return views.get(id);
  }
  function persistView() {const s=state();try{localStorage.setItem('lab.objectives.view.v1:'+key(context()),JSON.stringify({objective:s.objective,tree:s.tree,pins:s.pins}));}catch{}}
  function objective() {const d=data(),s=state();return d?.objectives.find(o=>o.id===s.objective)||d?.objectives.find(o=>d.focused.includes(o.id));}
  function active(path) {return context()?.path===path&&data()?.enabled===true;}
  function complete(task) {return task.children.length?task.children.every(c=>c.done):task.done;}
  function progress(o) {
    const today=new Date(),day=Date.UTC(today.getFullYear(),today.getMonth(),today.getDate());
    const dates=o.tasks.flatMap(t=>complete(t)?[]:[t.due,...t.children.filter(c=>!c.done).map(c=>c.due||t.due)]).filter(Boolean).map(d=>(Date.parse(d+'T00:00:00Z')-day)/86400000);
    const done=o.tasks.filter(complete).length,status=o.tasks.length&&done===o.tasks.length?'complete':dates.some(d=>d<0)?'overdue':dates.some(d=>d<=2)?'risk':'track';
    return {done,total:o.tasks.length,status,label:{complete:'All complete',overdue:'Past due',risk:'At risk · due within 2 days',track:o.tasks.length?'On track':'No tasks yet'}[status]};
  }
  function badge(o) {const p=progress(o);return `<span class="objective-progress ${p.status}" title="${esc(p.label)}" aria-label="${p.done} of ${p.total} tasks complete · ${esc(p.label)}">${p.done}/${p.total}</span>`;}
  function worktrees(path) {if(!active(path))return null;return (objective()?.worktrees||[]).map(t=>({...t,projectPath:t.repo}));}
  function tree(o=objective()) {return o?.worktrees.find(t=>t.id===state().tree[o.id])||o?.worktrees[0];}
  function sidebarHtml(path) {return context()?.path===path?'<section data-objectives-sidebar aria-label="Workspace objectives"></section>':'';}
  async function load(scope=context(), fresh=false) {
    if(!scope?.workspace_id||scope.workspace_id.startsWith('__'))return;
    const id=key(scope);
    if(cache.has(id)&&!fresh){paint();if(Date.now()-(loadedAt.get(id)||0)<2000)return cache.get(id);}
    if(pending.has(id))return pending.get(id);
    const request=fetch('/api/objectives?'+new URLSearchParams({workspace_id:scope.workspace_id,...(scope.vault?{vault:scope.vault}:{})})).then(async r=>{
      const d=await r.json();if(!r.ok)throw new Error(d.detail||'Could not load objectives');if(d.enabled)await Promise.all([bridge.readyContent?.(),scope.path&&bridge.warmWorktrees?.(d.objectives.filter(o=>d.focused.includes(o.id)).flatMap(o=>o.worktrees),scope)]);const previous=cache.get(id);cache.set(id,d);loadedAt.set(id,Date.now());
      for(const overlay of overlays.get(id)||[])overlay.apply(d);
      if(key(context())===id){paint();if(previous?.revision!==d.revision){bridge.refreshSidebar?.();bridge.refreshTerminals?.();}}return d;
    }).catch(e=>{if(key(context())===id)notify(e.message,true);}).finally(()=>pending.delete(id));pending.set(id,request);return request;
  }
  function notify(text,error=false) {window.explorerToast?.(text,error);}
  function change(action,{optimistic,scope:destination}={}) {
    const scope={...(destination||context())},id=key(scope);
    const overlay=optimistic?{apply:optimistic}:null;
    if(overlay){overlays.set(id,[...(overlays.get(id)||[]),overlay]);overlay.apply(cache.get(id));paint();if(openView?.type==='tasks')renderTasks();}
    const previous=queues.get(id)||Promise.resolve();
    const next=previous.catch(()=>{}).then(async()=>{
      const r=await fetch('/api/objectives',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace_id:scope.workspace_id,vault:scope.vault,expected:cache.get(id)?.revision,action})});
      const d=await r.json();if(!r.ok)throw new Error(d.detail||'Could not save objective');if(d.enabled)await bridge.readyContent?.();overlays.set(id,(overlays.get(id)||[]).filter(item=>item!==overlay));cache.set(id,d);loadedAt.set(id,Date.now());
      for(const item of overlays.get(id)||[])item.apply(d);
      if(key(context())===id){paint();bridge.refreshTerminals?.();if(openView?.type==='tasks')renderTasks();}return d;
    }).catch(async e=>{overlays.set(id,(overlays.get(id)||[]).filter(item=>item!==overlay));notify(e.message,true);await load(scope,true);throw e;});queues.set(id,next);return next;
  }
  function collapse() {clearTimeout(hoverTimer);state().revealed.clear();}
  function tabsFor(resource) {
    const root=resource.document_id||resource.id,rows=resource.content?.tabs||[],children=new Map();rows.forEach(t=>{const parent=t.parent?.id||root;if(!children.has(parent))children.set(parent,[]);children.get(parent).push(t);});
    const result=[],seen=new Set();function visit(id,depth){for(const t of children.get(id)||[]){if(seen.has(t.id))continue;seen.add(t.id);result.push({...t,depth});visit(t.id,depth+1);}}visit(root,0);rows.filter(t=>!seen.has(t.id)).forEach(t=>result.push({...t,depth:0}));return result;
  }
  function resourceRow(o,r) {
    const selected=state().selected?.resource===r.id&&!state().selected?.tab,icon=r.kind==='notebook'?'▦':r.kind==='link'?'↗':'▤';
    const rows=tabsFor(r),reveal=state().revealed.has(r.id),pins=state().pins[r.id]||[];
    return `<div class="objective-resource-group" data-resource-group="${esc(r.id)}"><div class="objective-resource-head"><button type="button" class="sidebar-scope-link objective-resource${selected?' active':''}" data-objective-resource="${esc(r.id)}" draggable="true" title="${esc(r.title)}"><span aria-hidden="true">${icon}</span><span>${esc(r.title)}</span></button>${rows.length?`<button type="button" class="objective-tree-toggle" data-reveal-resource="${esc(r.id)}" aria-label="Show subtabs for ${esc(r.title)}" aria-expanded="${reveal}">${reveal?'▾':'▸'}</button>`:''}</div>
      ${rows.length?`<div class="objective-subtabs" role="tree" aria-label="${esc(r.title)} subtabs">${rows.filter(t=>reveal||pins.includes(t.id)).map(t=>`<div class="objective-subtab-row" style="--objective-tab-depth:${t.depth}" role="treeitem" aria-level="${t.depth+1}"><button type="button" class="objective-subtab${state().selected?.resource===r.id&&state().selected.tab===t.id?' active':''}" data-objective-resource="${esc(r.id)}" data-objective-tab="${esc(t.id)}" draggable="true" title="${esc(t.title)}"><span aria-hidden="true">▤</span><span>${esc(t.title)}</span></button><button type="button" class="objective-pin" data-pin-resource="${esc(r.id)}" data-pin-tab="${esc(t.id)}" aria-label="Pin ${esc(t.title)}" aria-pressed="${pins.includes(t.id)}">${pins.includes(t.id)?'◆':'◇'}</button></div>`).join('')}</div>`:''}</div>`;
  }
  function paint() {
    const scope=context(),host=document.querySelector('[data-objectives-sidebar]');if(!host||!scope)return;
    const d=data();if(!d)return;
    if(!d.enabled){host.innerHTML='<button type="button" class="sidebar-objective-add" data-new-objective>+ Objective</button>';return;}
    const o=objective();if(!o)return;state().objective=o.id;
    const t=tree(o),general=o.resources.filter(r=>!r.worktree),scoped=o.resources.filter(r=>r.worktree&&r.worktree===t?.id);
    host.innerHTML=`<div class="sidebar-title objective-title">OBJECTIVES <button type="button" data-focus-objective aria-label="Choose objective">+</button></div><div class="objective-selectors">${d.focused.map(id=>d.objectives.find(o=>o.id===id)).filter(Boolean).map(item=>`<button type="button" class="objective-selector${item.id===o.id?' active':''}" style="--objective-color:${esc(item.color)}" data-select-objective="${esc(item.id)}" aria-pressed="${item.id===o.id}"><span aria-hidden="true">◎</span><span>${esc(item.name)}</span>${badge(item)}</button>`).join('')}</div>
      <div class="sidebar-title objective-title">${esc(o.name)}<button type="button" data-objective-settings aria-label="Objective settings">⚙</button></div>
      <section data-objective-shared><div class="sidebar-title objective-title">Documents & notebooks<button type="button" data-add-resource="document" aria-label="Add objective document">+</button></div><div class="objective-resources">${general.filter(r=>r.kind!=='link').map(r=>resourceRow(o,r)).join('')}</div><div class="sidebar-title objective-title">Links<button type="button" data-add-resource="link" aria-label="Add objective link">+</button></div><div class="objective-resources">${general.filter(r=>r.kind==='link').map(r=>resourceRow(o,r)).join('')}</div>
      <button type="button" class="sidebar-scope-link objective-tasks" data-open-objective-tasks><span aria-hidden="true">☑</span><span>Tasks</span>${badge(o)}</button></section>
      <div class="sidebar-title objective-title">Worktrees<button type="button" data-associate-worktree aria-label="Associate worktree">+</button></div><div class="objective-worktrees">${o.worktrees.map(item=>`<div class="sidebar-scope-chip${item.id===t?.id?' active':''}" style="--sidebar-workspace-color:${esc(item.color)}" data-objective-worktree="${esc(item.id)}"><span class="objective-worktree-icon" aria-hidden="true">⑂</span><button type="button" class="sidebar-file-scope-button" data-select-worktree="${esc(item.id)}" aria-pressed="${item.id===t?.id}" title="${esc(item.path)}"><span>${esc(item.label)}</span></button><span class="sidebar-scope-tag">${esc(item.kind==='folder'?'Folder':'Worktree')}</span></div>`).join('')}</div>
      ${scoped.length?`<div class="sidebar-title">For this worktree</div><div class="objective-resources">${scoped.map(r=>resourceRow(o,r)).join('')}</div>`:''}`;
    host.querySelectorAll('[data-resource-group]').forEach(row=>{row.onmouseenter=()=>{clearTimeout(hoverTimer);const id=row.dataset.resourceGroup;hoverTimer=setTimeout(()=>{if(row.isConnected&&key(context())===key(scope)){state().revealed.add(id);paint();}},1500);};row.onmouseleave=()=>clearTimeout(hoverTimer);});
  }
  function selectObjective(id) {
    const o=data()?.objectives.find(o=>o.id===id);if(!o)return;collapse();state().objective=id;state().selected=null;persistView();paint();renderTasks();bridge.refreshTerminals?.();
    const t=tree(o)||{path:context().path,kind:'folder'};if(bridge.scopeRoot?.()!==t.path)bridge.selectWorktree?.(t);
  }
  function showCenter(type) {bridge.prepareCenter?.();openView={type,scope:key(context()),objective:objective().id};return document.getElementById('content');}
  function taskRow(task,parent=null) {
    const done=parent?task.done:complete(task);return `<div class="objective-task-row${parent?' child':''}" data-task-id="${esc(task.id)}"><input type="checkbox" aria-label="Complete ${esc(task.title)}" data-task-done="${esc(task.id)}" ${done?'checked':''}><span class="objective-task-title${done?' done':''}">${esc(task.title)}</span><button type="button" data-task-document="${esc(task.id)}" aria-label="Open details for ${esc(task.title)}">▤</button><input type="date" aria-label="Due date for ${esc(task.title)}" data-task-due="${esc(task.id)}" value="${esc(task.due||'')}" title="${parent&&!task.due?'Inherits '+(parent.due||'parent deadline'):'Due date'}"><button type="button" data-add-subtask="${esc(task.id)}" ${parent?'hidden':''} aria-label="Add subtask to ${esc(task.title)}">+</button></div>`;
  }
  function renderTasks() {
    const o=objective();if(!o)return;const host=showCenter('tasks'),p=progress(o);state().selected=null;
    host.innerHTML=`<section class="objective-working"><header><h2>Tasks</h2><button type="button" data-new-objective-task>+ Task</button></header><p class="objective-purpose">${esc(o.name)} · ${esc(o.purpose)}</p><div class="objective-task-progress">${badge(o)}<span>${esc(p.label)}</span></div><div class="objective-task-list">${o.tasks.map(t=>taskRow(t)+t.children.map(c=>taskRow(c,t)).join('')).join('')||'<p>No tasks yet. Add a task and its details document will be created with it.</p>'}</div></section>`;
    paint();
  }
  function openResource(resourceId,tabId=null) {
    const o=objective(),r=o?.resources.find(r=>r.id===resourceId);if(!r)return;
    collapse();state().selected={resource:resourceId,tab:tabId};if(r.content?.tabs?.length)state().revealed.add(resourceId);paint();
    openView={type:r.kind,scope:key(context()),objective:o.id,resource:r.id,tab:tabId};
    if(r.kind==='assistant'){bridge.openAssistant?.({...r,tab_id:tabId||r.tab_id});return;}
    if(r.kind==='link'){bridge.openLink?.(r);return;}
    if(r.kind==='notebook'){bridge.openNotebook?.(r);return;}
    if(r.kind==='file'){bridge.openFile?.({root:r.file_root,path:r.path});return;}
    const tab=r.content?.tabs?.find(t=>t.id===tabId),body=tab?.body??r.content?.body??'',host=showCenter('document');openView.resource=r.id;openView.tab=tabId;
    host.innerHTML=`<section class="objective-working objective-document"><header><h2>${esc(tab?.title||r.title)}</h2><button type="button" data-rename-objective-resource="${esc(r.id)}">Rename</button></header><div class="objective-document-context"><button type="button" data-open-objective-tasks>← Tasks</button><span>${esc(o.name)}${tab?' / '+esc(r.title):''}</span></div><article class="workspace-doc-body markdown-body">${window.LabMarkdown.render(body)}</article><div class="objective-document-actions"><button type="button" data-edit-objective-document>Edit</button>${!tabId?`<button type="button" data-add-objective-subtab="${esc(r.id)}">+ Subtab</button>`:''}</div></section>`;
  }
  function form(title,fields,submit) {
    dialog?.remove();const node=document.createElement('dialog');node.className='objective-dialog';node.innerHTML=`<form><header><h2>${esc(title)}</h2></header>${fields}<footer><button type="button" data-cancel>Cancel</button><button type="submit">Save</button></footer><p role="status"></p></form>`;document.body.append(node);dialog=node;node.showModal();node.querySelector('[data-cancel]').onclick=()=>{node.close();node.remove();};node.querySelector('form').onsubmit=async e=>{e.preventDefault();const button=node.querySelector('[type=submit]');button.disabled=true;try{await submit(new FormData(e.target));node.close();node.remove();}catch(error){node.querySelector('[role=status]').textContent=error.message;button.disabled=false;}};return node;
  }
  const input=(label,name,value='',type='text',required=true)=>`<label>${esc(label)}<input name="${name}" type="${type}" value="${esc(value)}" ${required?'required':''}></label>`;
  function newObjective() {const d=data();form('New objective',input('Name','name')+input('Outcome','purpose','','text',false)+(d.objectives.length?'':'<label><span><input name="import_existing" type="checkbox" checked> Bring current workspace worktrees, files and links</span></label>')+(d.focused.length===3?`<label>Replace focus slot<select name="replace">${d.focused.map(id=>`<option value="${esc(id)}">${esc(d.objectives.find(o=>o.id===id).name)}</option>`).join('')}</select></label>`:''),async values=>{const result=await change({type:'create',name:values.get('name'),purpose:values.get('purpose'),replace:values.get('replace'),import_existing:values.has('import_existing')});selectObjective(result.objectives.at(-1).id);bridge.refreshSidebar?.();});}
  function focusDialog() {const d=data();form('Bring an objective into focus',`<label>Objective<select name="objective"><option value="new">Create a new objective</option>${d.objectives.filter(o=>!d.focused.includes(o.id)).map(o=>`<option value="${esc(o.id)}">${esc(o.name)}</option>`).join('')}</select></label>`+(d.focused.length===3?`<label>Replace focus slot<select name="replace">${d.focused.map(id=>`<option value="${esc(id)}">${esc(d.objectives.find(o=>o.id===id).name)}</option>`).join('')}</select></label>`:''),async values=>{if(values.get('objective')==='new'){setTimeout(newObjective,0);return;}await change({type:'focus',objective_id:values.get('objective'),replace:values.get('replace')});selectObjective(values.get('objective'));});}
  function addResource(kind='document') {form('Add objective resource',`<label>Type<select name="kind"><option value="document">Markdown document</option><option value="notebook">Notebook</option><option value="link">Link</option><option value="file">Existing workspace file</option></select></label>`+input('Name','title')+input('URL (links only)','url','','text',false)+input('Workspace-relative path (existing files only)','path','','text',false),async values=>{const result=await change({type:'resource',objective_id:objective().id,kind:values.get('kind'),title:values.get('title'),url:values.get('url'),path:values.get('path')});openResource(result.objectives.find(o=>o.id===objective().id).resources.at(-1).id);});dialog.querySelector('[name=kind]').value=kind;}
  function addTask(parentId=null) {const o=objective();form(parentId?'New subtask':'New task',input('Task','title')+input('Due date','due','','date',false),async values=>{await change({type:'task',objective_id:o.id,parent_id:parentId,title:values.get('title'),due:values.get('due')});renderTasks();});}
  function associate(row) {return change({type:'worktree',objective_id:objective().id,path:row.path,label:row.label||row.name||row.path.split('/').pop(),repo:row.projectPath||row.path,branch:row.branch,kind:row.kind||'worktree'}).then(d=>{const o=d.objectives.find(o=>o.id===objective().id);state().tree[o.id]=o.worktrees.at(-1).id;persistView();return o.worktrees.at(-1);});}
  function terminalIdentity(t) {return t.session_id||t.name;}
  function terminalObjective(t) {const d=data();if(!d?.enabled)return null;const link=d.terminal_links[terminalIdentity(t)];return d.objectives.find(o=>o.id===link?.objective_id)||d.objectives.find(o=>o.worktrees.some(w=>[w.path,w.resolved_path].includes(t.linked_scope?.root)||[w.path,w.resolved_path].includes(t.cwd)))||d.objectives[0];}
  function terminalHtml(sessions,pill,newButton) {
    if(!active(context()?.path))return null;const d=data();return d.focused.map(id=>{const o=d.objectives.find(o=>o.id===id);if(!o)return '';const rows=sessions.map((t,index)=>({t,index})).filter(row=>terminalObjective(row.t)?.id===id),groups=new Map();for(const row of rows){const path=row.t.linked_scope?.root||row.t.cwd||context().path;if(!groups.has(path))groups.set(path,[]);groups.get(path).push(row);}return `<section class="objective-terminal-group" style="--objective-color:${esc(o.color)}"><button type="button" class="objective-terminal-heading" data-select-objective="${esc(id)}">${esc(o.name)}</button>${[...groups].map(([path,items])=>{const t=o.worktrees.find(w=>w.path===path||w.resolved_path===path);return `<div class="objective-terminal-worktree" style="--objective-color:${esc(t?.color||o.color)}"><span>${esc(t?.label||(path===context().path?'Objective folder':path.split('/').filter(Boolean).slice(-2).join('/')))}</span><div>${items.map(row=>pill(row.t,row.index)).join('')}</div></div>`;}).join('')}</section>`;}).join('')+newButton;
  }
  function openForTerminal(t) {const link=data()?.terminal_links[terminalIdentity(t)],o=terminalObjective(t);if(!o||!link)return false;state().objective=o.id;const resource=o.resources.find(r=>r.id===link.resource_id),w=o.worktrees.find(w=>w.id===resource?.worktree||[w.path,w.resolved_path].includes(link.file?.root||t.linked_scope?.root));if(w){state().tree[o.id]=w.id;if(bridge.scopeRoot?.()!==w.path)bridge.selectWorktree?.(w);}persistView();if(link.resource_id)openResource(link.resource_id,link.tab_id);else if(link.file)bridge.openFile?.(link.file);paint();return true;}
  function handleClick(e) {
    const host=e.target.closest?.('[data-objectives-sidebar],.objective-working,.objective-dialog,.objective-terminal-group,[data-objective-notebook-controls]');
    if(!host){if(active(context()?.path)&&e.target.closest?.('#sidebar,.repo-tabs,#termSessionList')){collapse();state().selected=null;paint();}return;}
    const node=e.target.closest('button,input');if(!node)return;
    if(node.dataset.selectObjective){selectObjective(node.dataset.selectObjective);return;}
    if(node.hasAttribute('data-new-objective')){newObjective();return;}
    if(node.hasAttribute('data-focus-objective')){focusDialog();return;}
    if(node.hasAttribute('data-open-objective-tasks')){collapse();renderTasks();return;}
    if(node.dataset.objectiveResource){openResource(node.dataset.objectiveResource,node.dataset.objectiveTab||null);return;}
    if(node.dataset.revealResource){const id=node.dataset.revealResource;if(state().revealed.has(id))state().revealed.delete(id);else state().revealed.add(id);paint();return;}
    if(node.dataset.pinResource){const id=node.dataset.pinResource,tab=node.dataset.pinTab,pins=state().pins[id]||[];state().pins[id]=pins.includes(tab)?pins.filter(t=>t!==tab):[...pins,tab];persistView();paint();return;}
    if(node.dataset.selectWorktree){const o=objective(),t=o.worktrees.find(t=>t.id===node.dataset.selectWorktree);collapse();state().tree[o.id]=t.id;persistView();paint();bridge.selectWorktree?.(t);return;}
    if(node.hasAttribute('data-associate-worktree')){collapse();bridge.addWorktree?.(node);return;}
    if(node.dataset.addResource){addResource(node.dataset.addResource);return;}
    if(node.hasAttribute('data-new-objective-task')){addTask();return;}
    if(node.dataset.addSubtask){addTask(node.dataset.addSubtask);return;}
    if(node.dataset.taskDocument){const t=objective().tasks.flatMap(t=>[t,...t.children]).find(t=>t.id===node.dataset.taskDocument);openResource(t.document_id,t.tab_id);return;}
    if(node.hasAttribute('data-objective-settings')){const o=objective();form('Objective settings',input('Name','name',o.name)+input('Outcome','purpose',o.purpose,'text',false),v=>change({type:'settings',objective_id:o.id,name:v.get('name'),purpose:v.get('purpose')}));return;}
    if(node.dataset.renameObjectiveResource){const r=objective().resources.find(r=>r.id===node.dataset.renameObjectiveResource),tab=r.kind==='document'&&openView?.resource===r.id?openView.tab:null;form(tab?'Rename subtab':'Rename resource',input('Name','title',r.content?.tabs?.find(t=>t.id===tab)?.title||r.title),async v=>{await change({type:'rename',objective_id:objective().id,resource_id:r.id,tab_id:tab,title:v.get('title')});openResource(r.id,tab);});return;}
    if(node.dataset.addObjectiveSubtab){form('New document subtab',input('Name','title'),async v=>{await change({type:'subtab',objective_id:objective().id,resource_id:node.dataset.addObjectiveSubtab,title:v.get('title'),body:''});openResource(node.dataset.addObjectiveSubtab);});return;}
    if(node.hasAttribute('data-edit-objective-document')){
      const o=objective(),r=o.resources.find(r=>r.id===openView.resource),tab=r.content.tabs.find(t=>t.id===openView.tab),article=host.querySelector('article'),body=tab?.body??r.content.body;
      article.innerHTML='<textarea class="objective-document-editor" aria-label="Document content"></textarea><button type="button" data-save-objective-document>Save</button>';article.querySelector('textarea').value=body;return;
    }
    if(node.hasAttribute('data-save-objective-document')){const r=objective().resources.find(r=>r.id===openView.resource),tab=openView.tab,text=host.querySelector('textarea').value;node.disabled=true;change({type:'document',objective_id:objective().id,resource_id:r.id,tab_id:tab,document_revision:r.content.revision,body:text}).then(()=>openResource(r.id,tab)).catch(()=>node.disabled=false);}
  }
  document.addEventListener('click',handleClick);
  document.addEventListener('change',e=>{const node=e.target;if(!node.matches('[data-task-done],[data-task-due]'))return;const o=objective(),id=node.dataset.taskDone||node.dataset.taskDue,patch=node.dataset.taskDone?{done:node.checked}:{due:node.value};change({type:'task-update',objective_id:o.id,task_id:id,...patch},{optimistic:d=>{const t=d.objectives.find(item=>item.id===o.id).tasks.flatMap(t=>[t,...t.children]).find(t=>t.id===id);Object.assign(t,patch);if('done'in patch)t.children.forEach(c=>c.done=patch.done);}}).catch(()=>{});});
  document.addEventListener('dragstart',e=>{const row=e.target.closest?.('[data-objective-resource]');if(row)e.dataTransfer.setData(resourceMime,JSON.stringify({objective_id:objective().id,resource_id:row.dataset.objectiveResource,tab_id:row.dataset.objectiveTab||null}));});
  document.addEventListener('dragover',e=>{if(!active(context()?.path))return;const target=e.target.closest?.('[data-objective-resource],[data-objective-worktree],[data-objective-shared],#termSessionList .sess');if(target&&[resourceMime,documentMime,'application/x-lab-file-path','application/x-lab-terminal'].some(m=>e.dataTransfer.types.includes(m))){e.preventDefault();e.dataTransfer.dropEffect='link';}},true);
  document.addEventListener('drop',e=>{
    if(!active(context()?.path))return;const target=e.target.closest?.('[data-objective-resource],[data-objective-worktree],[data-objective-shared],#termSessionList .sess');if(!target)return;
    const raw=e.dataTransfer.getData(resourceMime),assistant=e.dataTransfer.getData(documentMime),file=e.dataTransfer.getData('application/x-lab-file-path'),terminal=e.dataTransfer.getData('application/x-lab-terminal');if(!raw&&!assistant&&!file&&!terminal)return;e.preventDefault();e.stopImmediatePropagation();
    try{if(raw){const item=JSON.parse(raw);if(item.objective_id!==objective().id)throw new Error('Choose a resource in this objective');if(target.classList.contains('sess')){const t=bridge.session?.(target.dataset.name);change({type:'terminal',objective_id:item.objective_id,session_id:terminalIdentity(t),source:t.document_source,resource_id:item.resource_id,tab_id:item.tab_id}).catch(()=>{});}else change({type:'scope',...item,worktree:target.dataset.objectiveWorktree||null}).catch(()=>{});}
      else if(assistant){const ref=JSON.parse(assistant),o=objective();change({type:'resource',objective_id:o.id,kind:'assistant',title:ref.title||'Assistant document',document_id:ref.document_id,assistant_root:ref.assistant_root,worktree:target.dataset.objectiveWorktree||null}).then(d=>{if(target.classList.contains('sess'))return change({type:'terminal',objective_id:o.id,session_id:terminalIdentity(bridge.session(target.dataset.name)),source:bridge.session(target.dataset.name).document_source,resource_id:d.objectives.find(item=>item.id===o.id).resources.at(-1).id});}).catch(()=>{});}
      else if(file&&target.classList.contains('sess')){const paths=JSON.parse(file),t=bridge.session?.(target.dataset.name);change({type:'terminal',objective_id:objective().id,session_id:terminalIdentity(t),source:t.document_source,file:{root:bridge.scopeRoot?.(),path:paths[0]}}).catch(()=>{});}
      else if(terminal&&target.dataset.objectiveResource){const t=bridge.session?.(terminal);if(!t)throw new Error('Choose a terminal in this workspace');change({type:'terminal',objective_id:objective().id,session_id:terminalIdentity(t),source:t.document_source,resource_id:target.dataset.objectiveResource,tab_id:target.dataset.objectiveTab||null}).catch(()=>{});}
    }catch(error){notify(error.message,true);}
  },true);
  window.LabObjectives={connect(adapter){bridge=adapter;},load,active,sidebarHtml,paint,worktrees,tree,associate,terminalHtml,openForTerminal,collapse,progress,complete,change,selectObjective,renderTasks,
    async addAssistant(scope,reference){const d=await load(scope);if(!d?.enabled)return false;const o=d.objectives.find(o=>o.id===state(scope).objective)||d.objectives.find(o=>d.focused.includes(o.id));if(!o)return false;if(!o.resources.some(r=>r.kind==='assistant'&&r.document_id===reference.document_id&&r.assistant_root===reference.assistant_root))await change({type:'resource',objective_id:o.id,kind:'assistant',title:reference.title||'Assistant document',...reference},{scope});return true;},
    worktreeColor(path){return active(context()?.path)?data()?.objectives.flatMap(o=>o.worktrees).find(t=>t.path===path||t.resolved_path===path)?.color:null;},
    notebookControls(root,path){const r=objective()?.resources.find(r=>r.kind==='notebook'&&r.path===path&&context()?.path===root);return r?`<span data-objective-notebook-controls><button type="button" data-rename-objective-resource="${esc(r.id)}">Rename</button></span>`:'';},
    ownsCenter(path){return context()?.path===path&&openView?.scope===key(context())&&!!(document.querySelector('#content .objective-working')||state().selected);},
    leave(){if(context()){collapse();state().selected=null;}openView=null;dialog?.remove();dialog=null;clearTimeout(hoverTimer);}};
})();
