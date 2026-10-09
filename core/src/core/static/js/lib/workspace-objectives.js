/* Workspace objectives own configuration and content; Assistant stays a reference. */
(() => {
  'use strict';
  const cache = new Map(), views = new Map(), pending = new Map(), queues = new Map(), overlays = new Map(), loadedAt = new Map();
  const resourceMime = 'application/x-lab-objective-resource', documentMime = 'application/x-lab-assistant-document';
  const objectiveMime = 'application/x-lab-workspace-objective', focusSlots = 5;
  const taskMoveMime = 'application/x-lab-objective-task';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const drafts = new Map(), linkDrafts = new Map();
  let actionTarget = null;
  const assetGroupHovers = new Map();
  let bridge, dialog = null, linkEditDialog = null, linkEditCleanup = null, hoverTimer, openView = null, activeDraft = null, activeLinkDraft = null, switchMenu = null, switchTimer;
  let taskCloseButton, taskCloseHost, taskCloseObserver, taskCloseResizeObserver, taskCloseFrame, taskModeHeader, taskModeSpacer;
  let taskStatusMenu, assetContextMenu;
  let refreshTimer;
  const taskEditIdleMs = 3 * 60 * 1000;
  const taskStatuses = {todo:{icon:'⬜',label:'Undo'},in_progress:{icon:'🚧',label:'In progress'},done:{icon:'✅',label:'Completed'},paused:{icon:'⏸',label:'Paused'},wont_do:{icon:'🚫',label:"Won’t do"}};
  const taskEmojiChoices = [['👷','Working'],['🌳','Tree'],['🔥','Fire'],['📓','Notebook'],['📝','Writing'],['‼️','Important'],['💡','Idea'],['🤖','Robot'],['📌','Pinned'],['✅','Done'],['❤️','Heart'],['⚠️','Warning'],['👀','Review'],['🏆','Achievement'],['🎯','Target'],['🚀','Launch'],['🛠️','Tools'],['🔬','Research'],['🐛','Bug'],['🧠','Thinking']];
  const key = scope => (scope?.vault || '') + '::' + scope?.workspace_id;
  const context = () => bridge?.context?.();
  const data = () => cache.get(key(context()));
  function state(scope = context()) {
    const id = key(scope);
    if (!views.has(id)) {
      let saved;try {saved = JSON.parse(localStorage.getItem('lab.objectives.view.v1:' + id));} catch {}
      views.set(id, {objective:saved?.objective || null, view:saved?.view || 'all', focus:saved?.focus || null, tree:saved?.tree || {}, pins:saved?.pins || {}, overview:saved?.overview || {}, terminalAll:saved?.terminalAll || {}, revealed:new Set(), selected:null});
    }
    return views.get(id);
  }
  function persistView() {const s=state();try{localStorage.setItem('lab.objectives.view.v1:'+key(context()),JSON.stringify({objective:s.objective,view:s.view,focus:s.focus,tree:s.tree,pins:s.pins,overview:s.overview,terminalAll:s.terminalAll}));}catch{}}
  function objective() {const d=data(),s=state();return d?.objectives.find(o=>o.id===s.objective)||d?.objectives.find(o=>d.focused.includes(o.id));}
  function active(path) {return context()?.path===path&&data()?.enabled===true;}
  function taskStatus(task) {
    if(['in_progress','paused','wont_do'].includes(task.status))return task.status;
    if(task.checklist?.pending)return task.children.length?'in_progress':'todo';
    if(task.children.length)return childrenStatus(task.children);
    return task.done?'done':'todo';
  }
  function childrenStatus(children) {
    if(children.every(c=>c.status==='wont_do'))return 'wont_do';
    if(children.every(c=>c.done||c.status==='wont_do'))return 'done';
    if(children.some(c=>c.done||c.status==='in_progress'))return 'in_progress';
    return children.every(c=>c.status==='paused')?'paused':'todo';
  }
  function complete(task) {return taskStatus(task)==='done';}
  function patchTaskStatus(o,id,status) {
    const task=tasks(o).find(t=>t.id===id);if(!task)return;
    const set=(t,s)=>Object.assign(t,{status:s,done:s==='done'});
    set(task,status);if(status!=='in_progress')tasks({tasks:task.children}).forEach(c=>set(c,status));
    taskAncestors(task,o).reverse().forEach(parent=>set(parent,childrenStatus(parent.children)));
  }
  function progress(o) {
    const dates=dueEntries(o).map(row=>row.at-Date.now());
    const done=o.tasks.filter(complete).length,status=!pendingTaskRows(o).length&&o.tasks.length?'complete':dates.some(d=>d<0)?'overdue':dates.some(d=>d<=2*86400000)?'risk':'track';
    return {done,total:o.tasks.length,status,label:{complete:'All complete',overdue:'Past due',risk:'At risk · due within 2 days',track:o.tasks.length?'On track':'No tasks yet'}[status]};
  }
  function badge(o) {const p=progress(o);return `<span class="objective-progress ${p.status}" title="${esc(p.label)}" aria-label="${p.done} of ${p.total} tasks complete · ${esc(p.label)}">${p.done}/${p.total}</span>`;}
  function scopeRows(o=objective()) {
    if(!o)return [];
    const root=context()?.path,folder=o.path||root+'/objectives/'+o.id;
    return [{id:'workspace-root',label:'Root',path:root,repo:root,kind:'folder',color:'#8b949e',fixed:true,membership:o.worktrees.find(t=>t.path===root)?.id},
      {id:'objective-root',label:'Objective',path:folder,repo:root,kind:'folder',color:'#8b949e',fixed:true,membership:o.worktrees.find(t=>t.path===folder)?.id},
      ...o.worktrees.filter(t=>t.path!==root&&t.path!==folder)];
  }
  function worktrees(path) {if(!active(path))return null;return scopeRows().map(t=>({...t,projectPath:t.repo}));}
  function terminalLaunchContext() {
    const o=objective(),scope=context();if(!active(scope?.path)||!o)return null;
    const path=o.path||scope.path+'/objectives/'+o.id;
    const task=focusedTask();
    return {id:o.id,name:o.name,path,context:{...scope},task_terminals:taskTerminalsEnabled(),task:task?{id:task.id,title:task.title}:null,
      worktrees:o.worktrees.filter(t=>t.path!==scope.path&&t.path!==path).map(t=>({...t}))};
  }
  function associateNewTerminal(terminal,association) {
    const {context:scope,...target}=association;
    return change({type:'terminal',session_id:terminalIdentity(terminal),...target},{scope});
  }
  function tree(o=objective()) {return o?(scopeRows(o).find(t=>t.id===state().tree[o.id])||scopeRows(o)[0]):null;}
  function taskWorktrees(task,o=objective()) {
    if(!task||!o)return [];
    return scopeRows(o).filter(row=>!isArchived({folder:{root:row.path,path:'.'}},o)&&(task.assets||[]).some(asset=>sameAsset(asset,{folder:{root:row.path,path:'.'}},o)));
  }
  function worktreeAssetScope(asset,o=objective()) {
    if(!asset.folder)return null;
    return scopeRows(o).find(row=>!row.fixed&&sameAsset(asset,{folder:{root:row.path,path:'.'}},o))||null;
  }
  function taskDisplayName(task,o=objective()) {const assigned=taskWorktrees(task,o);return assigned.length===1?assigned[0].label:task.title;}
  function taskNameHtml(task,o=objective()) {
    const assigned=taskWorktrees(task,o);
    return assigned.length===1?`<span class="objective-task-worktree-name" style="--worktree-color:${esc(assigned[0].color)}"><i aria-hidden="true"></i>${esc(assigned[0].label)}</span>`:esc(task.title);
  }
  function sidebarMode(path) {
    if(!active(path))return null;
    return state().worktreeBrowse?'worktree':focusedTask()?'task':'objective';
  }
  function recentScopes(path) {
    if(!active(path))return null;
    return state().worktreeBrowse?[tree()].filter(Boolean):taskWorktrees(focusedTask());
  }
  function foldWorktrees() {
    const s=state(),browse=s.worktreeBrowse;s.worktreesOpen=false;s.worktreeBrowse=null;
    if(browse?.focus&&tasks().some(t=>t.id===browse.focus.task)) {
      s.focus=browse.focus;s.view='objective';persistView();
      openTask(browse.focus.task);
    }else if(browse){renderTasks();}else paint();
  }
  function resetWorktreeBrowse() {state().worktreeBrowse=null;state().worktreesOpen=false;}
  function sidebarHtml(path) {return context()?.path===path?'<section data-objectives-sidebar aria-label="Workspace objectives"></section>':'';}
  async function load(scope=context(), fresh=false, {background=false}={}) {
    if(!scope?.workspace_id||scope.workspace_id.startsWith('__'))return;
    const id=key(scope);
    if(cache.has(id)&&!fresh){paint();if(Date.now()-(loadedAt.get(id)||0)<2000)return cache.get(id);}
    if(pending.has(id))return pending.get(id);
    const before=cache.get(id);
    const request=fetch('/api/objectives?'+new URLSearchParams({workspace_id:scope.workspace_id,...(scope.vault?{vault:scope.vault}:{})})).then(async r=>{
      const d=await r.json();if(!r.ok)throw new Error(d.detail||'Could not load objectives');const previous=cache.get(id);
      // A save started after this read owns the newer cache and UI.
      if(background&&(queues.has(id)||previous!==before))return previous;
      if(d.enabled&&!background)await Promise.all([bridge.readyContent?.(),scope.path&&bridge.warmWorktrees?.([{path:scope.path},...d.objectives.filter(o=>d.focused.includes(o.id)).flatMap(o=>[{path:o.path||scope.path+'/objectives/'+o.id},...o.worktrees])],scope)]);
      for(const overlay of overlays.get(id)||[])overlay.apply(d);
      const changed=JSON.stringify(previous)!==JSON.stringify(d);cache.set(id,d);loadedAt.set(id,Date.now());
      if(key(context())===id)bridge.syncTaskHierarchy?.(d);
      if(key(context())===id){if(changed||!background)paint();if(changed){bridge.refreshSidebar?.();bridge.refreshTerminals?.();if(openView?.type==='all')paintLibrary();else if(openView?.type==='overview')renderOverview();else if(openView?.type==='tasks')renderTasks();}if(!previous)bridge.openDefault?.();}return d;
    }).catch(e=>{if(!background&&key(context())===id)notify(e.message,true);}).finally(()=>pending.delete(id));pending.set(id,request);return request;
  }
  function refreshCurrent() {
    const scope=context(),id=key(scope);
    if(document.hidden||!scope?.workspace_id||!data()?.enabled||pending.has(id)||queues.has(id))return;
    return load({...scope},true,{background:true});
  }
  function startRefreshing() {
    if(refreshTimer)return;
    refreshTimer=setInterval(()=>void refreshCurrent(),5000);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)void refreshCurrent();});
    window.addEventListener('focus',()=>void refreshCurrent());
  }
  function notify(text,error=false) {window.explorerToast?.(text,error);}
  function change(action,{optimistic,scope:destination,expected}={}) {
    const scope={...(destination||context())},id=key(scope);
    const overlay=optimistic?{apply:optimistic}:null;
    if(overlay){overlays.set(id,[...(overlays.get(id)||[]),overlay]);overlay.apply(cache.get(id));paint();if(openView?.type==='tasks')renderTasks();else if(openView?.type==='overview')renderOverview();}
    const previous=queues.get(id)||Promise.resolve();
    const next=previous.catch(()=>{}).then(async()=>{
      const resolvedAction=typeof action==='function'?action(cache.get(id)):action;
      const r=await fetch('/api/objectives',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace_id:scope.workspace_id,vault:scope.vault,expected:expected??cache.get(id)?.revision,action:resolvedAction})});
      const d=await r.json();if(!r.ok)throw new Error(d.detail||'Could not save objective');if(d.enabled)await bridge.readyContent?.();overlays.set(id,(overlays.get(id)||[]).filter(item=>item!==overlay));cache.set(id,d);loadedAt.set(id,Date.now());
      if(key(context())===id)bridge.syncTaskHierarchy?.(d);
      for(const item of overlays.get(id)||[])item.apply(d);
      if(key(context())===id){paint();bridge.refreshTerminals?.();if(openView?.type==='tasks')renderTasks();else if(openView?.type==='overview')renderOverview();else if(openView?.type==='all')paintLibrary();}return d;
    }).catch(async e=>{overlays.set(id,(overlays.get(id)||[]).filter(item=>item!==overlay));notify(e.message,true);await load(scope,true);throw e;});queues.set(id,next);
    const cleanup=()=>{if(queues.get(id)===next)queues.delete(id);};next.then(cleanup,cleanup);return next;
  }
  function collapse() {clearTimeout(hoverTimer);state().revealed.clear();for(const hover of assetGroupHovers.values())clearTimeout(hover.timer);assetGroupHovers.clear();}
  function tabsFor(resource) {
    const root=resource.document_id||resource.id,rows=resource.content?.tabs||[],children=new Map();rows.forEach(t=>{const parent=t.parent?.id||root;if(!children.has(parent))children.set(parent,[]);children.get(parent).push(t);});
    const result=[],seen=new Set();function visit(id,depth){for(const t of children.get(id)||[]){if(seen.has(t.id))continue;seen.add(t.id);result.push({...t,depth});visit(t.id,depth+1);}}visit(root,0);rows.filter(t=>!seen.has(t.id)).forEach(t=>result.push({...t,depth:0}));return result;
  }
  function taskTree(rows,parent=null,depth=0) {return (rows||[]).flatMap(task=>[{task,parent,depth},...taskTree(task.children,task,depth+1)]);}
  function tasks(o=objective()) {return taskTree(o?.tasks).map(row=>row.task);}
  function taskParent(task,o=objective()) {return tasks(o).find(t=>t.children.some(c=>c.id===task.id))||null;}
  function taskAncestors(task,o=objective()) {const result=[];let parent=taskParent(task,o);while(parent){result.unshift(parent);parent=taskParent(parent,o);}return result;}
  function waiting(task) {return !!task.recurrence_state?.waiting;}
  function pendingTaskRows(o=objective()) {return taskTree(o?.tasks).filter(({task})=>!waiting(task)&&!taskAncestors(task,o).some(parent=>waiting(parent)||taskStatus(parent)==='wont_do')&&!['done','wont_do'].includes(taskStatus(task)));}
  function pendingActions(task) {return (task.action_items||[]).filter(item=>!item.done);}
  function taskDeadline(task,o=objective()) {
    const owner=task.due?task:taskAncestors(task,o).reverse().find(parent=>parent.due);
    return owner?.recurrence_state?.due_at||owner?.due||null;
  }
  function dueTime(due) {return due?new Date(due.length===10?due+'T23:59:59.999':due).getTime():NaN;}
  function dueClass(due) {const delta=dueTime(due)-Date.now();return delta<0?'overdue':delta<=2*86400000?'risk':'';}
  function dueBadge(due,inherited=false) {
    if(!due)return '<span class="objective-action-due undated">No due date</span>';
    const at=dueTime(due),status=dueClass(due),label=due.length<=16?due.replace('T',' '):new Date(at).toLocaleString();
    return `<time class="objective-action-due ${status}" datetime="${esc(due)}" title="${esc((inherited?'Inherits task deadline · ':'')+new Date(at).toLocaleString())}">${status==='overdue'?'Past due · ':status==='risk'?'Due soon · ':''}${esc(label)}</time>`;
  }
  function dueEntries(o=objective()) {
    return pendingTaskRows(o).flatMap(({task})=>[{task,due:taskDeadline(task,o)},...pendingActions(task).map(item=>({task,item,due:item.due||taskDeadline(task,o)}))])
      .map(row=>({...row,at:dueTime(row.due)})).filter(row=>Number.isFinite(row.at)).sort((a,b)=>a.at-b.at);
  }
  function actionLink(task,item) {return `data-open-action="${esc(task.id)}" data-action-line="${item.line}" href="${esc(taskHref(task,item))}"`;}
  function actionRow(task,item,depth=0) {
    const due=item.due||taskDeadline(task),label=item.label||item.title||'Untitled action item';
    return `<div class="objective-action-row ${dueClass(due)}" style="--objective-task-depth:${depth+1}"><span aria-hidden="true">☐</span><a ${actionLink(task,item)} title="${esc(label+' · '+task.title+(due?' · '+due.replace('T',' '):''))}">${esc(label)}</a>${dueBadge(due,!item.due)}</div>`;
  }
  function taskWithActions(task,parent=null,depth=0) {return taskRow(task,parent,depth)+(!complete(task)&&taskStatus(task)!=='wont_do'?pendingActions(task).map(item=>actionRow(task,item,depth)).join(''):'');}
  function dueDashboard(o) {
    const rows=dueEntries(o).filter(row=>row.at<=Date.now()+2*86400000);
    if(!rows.length)return '';
    return `<section class="objective-due-dashboard" aria-label="Overdue and due soon"><h3>Overdue & due within 2 days</h3>${rows.map(({task,item,due})=>`<div class="objective-due-row"><a ${item?actionLink(task,item):`data-open-task="${esc(task.id)}" href="${esc(taskHref(task))}"`}>${esc(item?(item.label||item.title):task.title)}<small>${esc(item?task.title:taskParent(task,o)?.title||'Task')}</small></a>${dueBadge(due,item&&!item.due)}</div>`).join('')}</section>`;
  }
  function taskFocus() {const f=state().focus,o=objective();return state().view==='objective'&&f?.objective===o?.id&&tasks(o).some(t=>t.id===f.task)?f:null;}
  function focusedTask() {return tasks().find(t=>t.id===taskFocus()?.task);}
  function taskAssets(task) {return [{id:'details',resource_id:task.document_id,tab_id:task.tab_id,required:true},...(task.assets||[])];}
  function contextAssets(task,o=objective()) {
    return [...(o.shared_assets||[]),...taskAncestors(task,o).flatMap(taskAssets),...taskAssets(task)].filter(a=>!isArchived(a,o));
  }

  function contextReferenceRows(rows,o=objective()) {
    return rows.filter(a=>!isArchived(a,o)).map(asset=>{
      const info=assetInfo(asset,o),r=info?.resource,path=r?.path||'',scope=asset.folder&&scopeRows(o).find(t=>[t.path,t.resolved_path].includes(asset.folder.root));
      const type=asset.required?'Task specification':asset.folder?(scope?.kind==='worktree'?'Worktree':'Folder'):
        r?.kind==='link'?(asset.sub_link_id?'Sublink':'Link'):r?.kind==='assistant'?(asset.tab_id?'Assistant document tab':'Assistant document'):
        asset.tab_id?'Document tab':r?.kind==='notebook'||/\.ipynb$/i.test(path)?'Notebook':r?.kind==='document'||/\.md$/i.test(path)?'Document':/\.sql$/i.test(path)?'SQL file':'File';
      return {title:info?.title||'',type,reference:info?.reference};
    });
  }
  function taskContext(task,o=objective()) {
    const assets=rows=>contextReferenceRows(rows,o);
    return {version:1,objective:{title:o.name,purpose:o.purpose||'',assets:assets(o.shared_assets||[])},parents:taskAncestors(task,o).map(parent=>({title:parent.title,assets:assets(taskAssets(parent))})),task:{title:task.title,assets:assets(taskAssets(task))}};
  }
  function objectiveContext(o) {
    const children=o.resources.filter(r=>!isArchived({resource_id:r.id},o)).flatMap(r=>
      r.kind==='link'?subLinksFor(r).map(t=>({resource_id:r.id,sub_link_id:t.id})):tabsFor(r).map(t=>({resource_id:r.id,tab_id:t.id})));
    return {version:1,kind:'objective',objective:{title:o.name,purpose:o.purpose||'',assets:[
      {title:o.name,type:'Objective manifest',reference:o.manifest_path||context().path+'/.lab/objectives.json#objective='+encodeURIComponent(o.id)},
      {title:o.name,type:'Objective folder',reference:o.path},...contextReferenceRows(o.shared_assets||[],o)]},
      tasks:tasks(o).map(task=>({title:task.title,parent:taskParent(task,o)?.title||'',assets:contextReferenceRows(taskAssets(task),o)})),
      unassigned_assets:contextReferenceRows(unassignedAssets(o),o),
      assets:contextReferenceRows([...assetCatalog(o),...o.resources.map(r=>({resource_id:r.id})),...children],o)};
  }
  function assetTarget(asset) {const {id,required,...target}=asset;return target;}
  function assetRoot(root,o=objective()) {return scopeRows(o).find(t=>[t.path,t.resolved_path].includes(root))?.resolved_path||root;}
  function sameAsset(a,b,o=objective()) {const folder=target=>target.folder?JSON.stringify({root:assetRoot(target.folder.root,o),path:target.folder.path.replace(/\/+$/,'')||'.'}):null;return a.resource_id===b.resource_id&&(a.tab_id||null)===(b.tab_id||null)&&(a.sub_link_id||null)===(b.sub_link_id||null)&&folder(a)===folder(b)&&JSON.stringify(a.reference||null)===JSON.stringify(b.reference||null);}
  function isShared(asset,o=objective()) {return (o?.shared_assets||[]).some(a=>sameAsset(a,asset));}
  function requiredAsset(asset,o=objective()) {return tasks(o).some(t=>t.document_id===asset.resource_id&&(!asset.tab_id||t.tab_id===asset.tab_id));}
  function coversAsset(a,asset,o=objective()) {return sameAsset(a,asset,o)||!!(a.resource_id&&a.resource_id===asset.resource_id&&!a.tab_id&&!a.sub_link_id);}
  function isTrashed(asset,o=objective()) {return (o?.trashed_assets||[]).some(a=>coversAsset(a,asset,o));}
  function isArchived(asset,o=objective()) {return isTrashed(asset,o)||(o?.archived_assets||[]).some(a=>coversAsset(a,asset,o));}
  function assetControls(asset) {
    const info=assetInfo(asset);if(!info)return '';
    const target=esc(JSON.stringify(assetTarget(asset))),shared=isShared(asset);
    return `<span class="objective-asset-tools"><button type="button" class="objective-star" data-objective-star="${target}" aria-pressed="${shared}" aria-label="${shared?'Unstar':'Star'} ${esc(info.title)}" title="${shared?'Unstar · keep task associations':'Star · share across all tasks'}">${shared?'★':'☆'}</button>${requiredAsset(asset)?'':`<button type="button" class="objective-asset-menu" data-classify-asset="${target}" aria-label="Classify ${esc(info.title)}">⋯</button>`}</span>`;
  }
  function visibleAsset(asset,o=objective()) {
    const r=o.resources.find(r=>r.id===asset.resource_id),t=tree(o);return !r?.worktree||[t?.id,t?.membership].includes(r.worktree);
  }
  function assetCatalog(o) {
    const rows=[...scopeRows(o).filter(t=>!t.fixed).map(t=>({folder:{root:t.path,path:'.'}})),...o.resources.filter(r=>!r.task_document).map(r=>({resource_id:r.id})),...(o.asset_shelf||[]),...(o.shared_assets||[]),...(o.archived_assets||[]),...tasks(o).flatMap(t=>t.assets||[]),...(o.asset_groups||[]).flatMap(g=>g.assets)];
    return rows.filter((row,i)=>!isTrashed(row,o)&&rows.findIndex(a=>sameAsset(a,row))===i);
  }
  function unassignedAssets(o,visible=false) {
    const assigned=tasks(o).flatMap(taskAssets);
    return assetCatalog(o).filter(a=>!isShared(a,o)&&!isArchived(a,o)&&!assigned.some(b=>sameAsset(a,b))&&(!visible||visibleAsset(a,o)));
  }
  function sidebarTaskRow(task,parent=null,depth=parent?1:0) {
    const status=taskStatus(task),done=status==='done',selected=focusedTask()?.id===task.id;
    const worktrees=taskWorktrees(task),iconColor=task.terminal_color||(worktrees.length===1?worktrees[0].color:null);
    const compactIcon=`<span class="objective-sidebar-task-compact-icon" aria-hidden="true"${iconColor?` style="color:${esc(iconColor)}"`:''}>${taskIcon(task)}</span>`;
    return `<div class="objective-sidebar-task${parent?' child':''}${selected?' active':''}" style="--objective-task-depth:${depth}" data-task-id="${esc(task.id)}"><button type="button" class="objective-sidebar-task-status objective-task-status-icon" data-task-status="${status}" data-task-icon="${esc(task.id)}" aria-label="Choose icon for ${esc(task.title)} · ${taskStatuses[status].label}" title="${taskStatuses[status].label} · Click to choose an icon · Secondary-click to change status">${taskStatuses[status].icon}</button>${compactIcon}<a class="objective-sidebar-task-title${done?' done':''}" data-open-task="${esc(task.id)}" href="${esc(taskHref(task))}" draggable="true" title="${esc(task.title)}">${taskNameHtml(task)}</a>${task.recurrence?'<span class="objective-task-recurring" aria-label="Recurring task" title="Recurring task">🔄</span>':''}<span class="objective-sidebar-task-count" title="${taskAssets(task).length} assets">${taskAssets(task).length}</span><button type="button" data-task-icon="${esc(task.id)}" aria-label="Icon for ${esc(task.title)}" title="Choose a task icon · Or drop an asset here" draggable="true">${customTaskIcon(task)}</button></div>`;
  }
  function bucketHtml(id,label,assets,add=false) {
    return `<section class="objective-bucket" data-objective-bucket="${id}" aria-label="${label}"><div class="sidebar-title objective-title">${id==='unassigned'?`<button type="button" class="objective-bucket-label" data-show-unassigned>${label}</button>`:`<span${id==='objective'?` data-drag-objective="${esc(objective().id)}" draggable="true" title="Drag ${esc(objective().name)} into a terminal to pass its whole context"`:''}>${label}</span>`}${add?'<button type="button" data-add-resource="document" aria-label="Add objective asset">+</button>':''}</div><div class="objective-resources">${assetListHtml(assets,'sidebar:'+id+(id==='task'?':'+(focusedTask()?.id||''):''))||`<p class="objective-bucket-empty">${{unassigned:'All assets are assigned.',objective:'Star an asset to share it across tasks.',task:'Select a task to see its assets.',archive:'Drop assets here to set them aside.'}[id]}</p>`}</div></section>`;
  }
  function assetGroupFor(asset,o=objective()) {return (o.asset_groups||[]).find(g=>g.assets.some(a=>sameAsset(a,asset,o)));}
  function assetListEntries(assets,o=objective()) {
    const entries=[],seen=new Set();
    for(const asset of assets){
      if(!assetInfo(asset,o))continue;
      const group=assetGroupFor(asset,o);
      if(group){if(!seen.has(group.id)){seen.add(group.id);entries.push({group,assets:group.assets.map(a=>assets.find(b=>sameAsset(a,b,o))).filter(a=>a&&assetInfo(a,o))});}}
      else entries.push({asset});
    }
    const rank=entry=>{const i=(o.asset_order||[]).findIndex(item=>entry.group?item.group_id===entry.group.id:!item.group_id&&sameAsset(item,entry.asset,o));return i<0?Infinity:i;};
    return entries.sort((a,b)=>Number(!!b.asset?.required)-Number(!!a.asset?.required)||rank(a)-rank(b));
  }
  function assetLayoutRow(html,item) {return html.replace(/^(<[^>]+)(>)/,`$1 data-asset-layout-item="${esc(JSON.stringify(item))}"$2`);}
  function flatAssetRow(asset) {
    const scope=worktreeAssetScope(asset);
    return scope?scopeRow(scope,asset):`<div class="objective-asset-line" data-objective-asset="${esc(JSON.stringify(assetTarget(asset)))}">${taskAssetRow(asset)}${assetControls(asset)}</div>`;
  }
  function assetListHtml(assets,view,render=assetRow,childRender=flatAssetRow) {
    return assetListEntries(assets).map(entry=>{
      if(entry.asset)return assetLayoutRow(render(entry.asset),assetTarget(entry.asset));
      const {group,assets:children}=entry,groupKey=key(context())+'::'+objective().id+'::'+view+'::'+group.id;
      const open=!!assetGroupHovers.get(groupKey)?.open;
      return `<div class="objective-asset-group" data-asset-group="${esc(group.id)}" data-asset-group-key="${esc(groupKey)}" data-asset-layout-item="${esc(JSON.stringify({group_id:group.id}))}"><div class="objective-asset-group-header" data-asset-group-header="${esc(group.id)}"><button type="button" class="sidebar-scope-link objective-resource" data-asset-group-toggle="${esc(group.id)}" aria-expanded="${open}" title="${esc(group.title)} · Hover for one second to show assets"><span class="objective-asset-group-caret" aria-hidden="true">${open?'▾':'▸'}</span><span>${esc(group.title)}</span><small>${children.length}</small></button><span class="objective-asset-tools"><button type="button" class="objective-asset-menu" data-asset-group-menu="${esc(group.id)}" aria-label="Actions for ${esc(group.title)}">⋯</button></span></div><div class="objective-asset-group-children" role="group" aria-label="Assets in ${esc(group.title)}" ${open?'':'hidden'}>${children.map(a=>assetLayoutRow(childRender(a),assetTarget(a))).join('')}</div></div>`;
    }).join('');
  }
  function setAssetGroupOpen(node,open) {
    node.querySelector(':scope > .objective-asset-group-children').hidden=!open;
    node.querySelector('[data-asset-group-toggle]').setAttribute('aria-expanded',String(open));
    node.querySelector('.objective-asset-group-caret').textContent=open?'▾':'▸';
  }
  function closeAssetGroup(node,hold=false) {
    const id=node.dataset.assetGroupKey,hover=assetGroupHovers.get(id);
    if(hover)clearTimeout(hover.timer);
    if(hold&&node.matches(':hover'))assetGroupHovers.set(id,{open:false,blocked:true,timer:null});
    else assetGroupHovers.delete(id);
    setAssetGroupOpen(node,false);
  }
  function openAssetGroup(node,immediate=false) {
    const id=node.dataset.assetGroupKey;
    let hover=assetGroupHovers.get(id);
    if(!hover){hover={enteredAt:performance.now(),open:false,timer:null};assetGroupHovers.set(id,hover);}
    clearTimeout(hover.timer);
    if(hover.blocked&&!immediate)return;
    hover.blocked=false;
    if(immediate||hover.open){hover.open=true;setAssetGroupOpen(node,true);return;}
    hover.timer=setTimeout(()=>{
      const current=document.querySelector(`[data-asset-group-key="${CSS.escape(id)}"]`);
      if(assetGroupHovers.get(id)!==hover)return;
      if(current?.matches(':hover')){hover.open=true;setAssetGroupOpen(current,true);}
      else assetGroupHovers.delete(id);
    },Math.max(0,1000-(performance.now()-hover.enteredAt)));
  }
  document.addEventListener('pointerover',event=>{const node=event.target.closest?.('[data-asset-group]');if(node&&!node.contains(event.relatedTarget))openAssetGroup(node);});
  document.addEventListener('pointerout',event=>{const node=event.target.closest?.('[data-asset-group]');if(node&&!node.contains(event.relatedTarget))closeAssetGroup(node);});
  document.addEventListener('focusin',event=>{const node=event.target.closest?.('[data-asset-group]');if(node)openAssetGroup(node,true);});
  document.addEventListener('focusout',event=>{const node=event.target.closest?.('[data-asset-group]');if(node&&!node.contains(event.relatedTarget)&&!node.matches(':hover'))closeAssetGroup(node);});
  document.addEventListener('pointerdown',event=>{for(const [id,hover] of assetGroupHovers){const node=document.querySelector(`[data-asset-group-key="${CSS.escape(id)}"]`);if(!node||!node.contains(event.target)){clearTimeout(hover.timer);assetGroupHovers.delete(id);if(node)setAssetGroupOpen(node,false);}}});
  document.addEventListener('keydown',event=>{
    const toggle=event.target.closest?.('[data-asset-group-toggle]');if(!toggle)return;
    const node=toggle.closest('[data-asset-group]');
    if(event.key==='ArrowRight'){event.preventDefault();openAssetGroup(node,true);node.querySelector('.objective-asset-group-children button')?.focus();}
    if(event.key==='ArrowLeft'||event.key==='Escape'){event.preventDefault();closeAssetGroup(node,true);}
  });
  function groupAsset(asset) {
    const scope={...context()},o=objective(),current=assetGroupFor(asset,o);
    const node=form('Group asset',`<p>${esc(assetInfo(asset)?.title||'Asset')}</p><label>Group<select name="group"><option value="">Create a new group</option>${(o.asset_groups||[]).map(g=>`<option value="${esc(g.id)}">${esc(g.title)}</option>`).join('')}</select></label><div data-new-group>${input('Group name','title')}</div>`,async values=>{
      const id=values.get('group');await change({type:id?'asset-group-member':'asset-group-create',objective_id:o.id,...assetTarget(asset),...(id?{group_id:id}:{title:values.get('title')})},{scope});
    });
    const select=node.querySelector('[name=group]'),field=node.querySelector('[name=title]');
    if(current)select.value=current.id;
    const sync=()=>{node.querySelector('[data-new-group]').hidden=!!select.value;field.required=!select.value;};
    select.onchange=sync;field.maxLength=120;sync();
  }
  function renameAssetGroup(id) {
    const scope={...context()},o=objective(),group=o.asset_groups.find(g=>g.id===id);if(!group)return;
    form('Rename group',input('Group name','title',group.title),values=>change({type:'asset-group-rename',objective_id:o.id,group_id:id,title:values.get('title')},{scope}));
  }
  function assetOrderButtons(item,node) {
    const entry=node.closest('[data-asset-layout-item]');if(!entry)return '';
    const target=JSON.parse(entry.dataset.assetLayoutItem);
    if(item.group_id?target.group_id!==item.group_id:target.group_id||!sameAsset(target,item))return '';
    const siblings=[...entry.parentElement.children].filter(n=>n.hasAttribute('data-asset-layout-item'));
    const at=siblings.indexOf(entry);
    return [['up',at-1,'before'],['down',at+1,'after']].map(([label,index,position])=>{
      const relative=siblings[index]&&JSON.parse(siblings[index].dataset.assetLayoutItem);
      if(relative&&!relative.group_id&&requiredAsset(relative))return '';
      return `<button type="button" role="menuitem" data-asset-order="${esc(JSON.stringify({item,relative,position}))}" ${relative?'':'disabled'}>Move ${label}</button>`;
    }).join('');
  }
  function assetRow(asset) {
    const info=assetInfo(asset);if(!info)return '';
    const scope=asset.folder?.path==='.'&&scopeRows().find(t=>[t.path,t.resolved_path].includes(asset.folder.root));
    if(scope)return scopeRow(scope,asset);
    if(info.resource&&!asset.tab_id&&!asset.sub_link_id)return resourceRow(objective(),info.resource);
    return `<div class="objective-asset-line" data-objective-asset="${esc(JSON.stringify(assetTarget(asset)))}">${taskAssetRow(asset)}${assetControls(asset)}</div>`;
  }
  function scopeRow(item,asset=null) {
    const selected=item.id===tree()?.id;
    return `<div class="sidebar-scope-chip${selected?' active':''}" style="--sidebar-workspace-color:${esc(item.color)}" ${item.fixed?'data-objective-root':'data-objective-worktree'}="${esc(item.id)}" ${asset?`data-objective-asset="${esc(JSON.stringify(assetTarget(asset)))}"`:''}><span class="objective-worktree-icon" aria-hidden="true">${item.kind==='folder'?'⌂':'⑂'}</span><button type="button" class="sidebar-file-scope-button" data-select-worktree="${esc(item.id)}" draggable="true" aria-pressed="${selected}" title="${esc(item.path)}"><span>${esc(item.label)}</span></button><span class="sidebar-scope-tag">${esc(item.kind==='folder'?'Folder':'Worktree')}</span>${bridge.scopeActions?.(item)||''}${asset?assetControls(asset):''}</div>`;
  }
  function worktreeNavigationHtml(o) {
    const scopes=scopeRows(o),entries=tasks(o),groups=new Map(),archived=[];
    const taskName=t=>[...taskAncestors(t,o),t].map(t=>t.title).join(' / ');
    for(const scope of scopes.filter(s=>!s.fixed)){
      const asset={folder:{root:scope.path,path:'.'}};
      if(isArchived(asset,o)){archived.push(scopeRow(scope,asset));continue;}
      const assigned=entries.filter(t=>(t.assets||[]).some(a=>sameAsset(a,asset)));
      const shared=isShared(asset,o),id=assigned.length?'tasks:'+assigned.map(t=>t.id).join(','):shared?'shared':'unassigned';
      if(!groups.has(id))groups.set(id,{label:assigned.length?assigned.map(taskName).join(' + '):shared?'Objective · pinned':'Unassigned',rank:assigned.length?2+entries.indexOf(assigned[0]):shared?1:0,rows:[]});
      groups.get(id).rows.push(scopeRow(scope,asset));
    }
    return scopes.filter(s=>s.fixed).map(s=>scopeRow(s)).join('')+
      [...groups.entries()].sort((a,b)=>a[1].rank-b[1].rank).map(([id,g])=>`<section class="objective-worktree-group" data-worktree-group="${esc(id)}" aria-label="${esc(g.label)} worktrees">${g.rows.join('')}</section>`).join('')+
      (archived.length?`<details class="objective-worktree-archive" ${state().worktreeArchiveOpen?'open':''}><summary>Archive · ${archived.length} ${archived.length===1?'worktree':'worktrees'}</summary><div class="objective-worktree-group" data-objective-bucket="archive">${archived.join('')}</div></details>`:'');
  }
  function resourceIcon(r,subLink) {
    return r?.kind==='link'?(window.LabScopeLinks?.icon({kind:'external',url:linkTarget(r,subLink)?.url})||'<span aria-hidden="true">↗</span>'):
      (r?.kind!=='assistant'&&bridge.fileIcon?.(r?.path||r?.title))||`<span aria-hidden="true">${r?.kind==='notebook'?'▦':'▤'}</span>`;
  }
  function assetInfo(asset,o=objective()) {
    if(asset.reference){const r=asset.reference;return {title:r.title,icon:resourceIcon(r),reference:resourceReference(r)};}
    if(asset.folder){const scope=scopeRows(o).find(t=>[t.path,t.resolved_path].includes(asset.folder.root));return {title:asset.folder.path==='.'?scope?.label||asset.folder.root.split('/').pop():asset.folder.path,icon:`<span aria-hidden="true">${scope?.kind==='worktree'?'⑂':'⌂'}</span>`,reference:asset.folder.root.replace(/\/$/,'')+(asset.folder.path==='.'?'':'/'+asset.folder.path)};}
    const r=o?.resources.find(r=>r.id===asset.resource_id);if(!r)return null;
    const child=asset.sub_link_id?linkTarget(r,asset.sub_link_id):asset.tab_id?tabsFor(r).find(t=>t.id===asset.tab_id):null;
    if((asset.tab_id||asset.sub_link_id)&&!child&&r.kind!=='assistant')return null;
    return {resource:r,title:child?r.title+' · '+child.title:r.title,icon:resourceIcon(r,asset.sub_link_id),reference:resourceReference(r,asset.tab_id,asset.sub_link_id)};
  }
  function customTaskIcon(task,o=objective()) {
    if(task.icon?.emoji)return `<span aria-hidden="true">${esc(task.icon.emoji)}</span>`;
    if(task.icon?.service)return window.LabScopeLinks?.icon({kind:'external',type:task.icon.service})||`<span class="scope-link-icon" data-link-service="${esc(task.icon.service)}" aria-hidden="true"></span>`;
    const asset=task.icon?.asset||taskAssets(task).find(a=>a.id===task.icon_asset_id);
    return (asset&&assetInfo(asset,o)?.icon)||'';
  }
  function taskIcon(task,o=objective()) {const status=taskStatus(task);return customTaskIcon(task,o)||`<span class="objective-task-default-icon objective-task-status-icon" data-task-status="${status}" aria-hidden="true">${taskStatuses[status].icon}</span>`;}
  function markTaskAssets(host) {
    const sidebar=document.getElementById('sidebar');if(!sidebar)return;
    sidebar.querySelectorAll('[data-native-asset-tools]').forEach(n=>n.remove());
  }
  function nativeAssetTarget(node) {
    const root=node.dataset.entryRoot||bridge.scopeRoot?.()||context()?.path,path=node.dataset.entryPath||node.dataset.filepath;
    if(!root||!path)return null;
    if(node.dataset.entryKind==='folder')return {folder:{root,path}};
    const full=path.startsWith('/')?path:assetRoot(root).replace(/\/$/,'')+'/'+path;
    const r=objective()?.resources.find(r=>resourceReference(r)?.split('#')[0]===full);
    const scope=scopeRows().find(t=>[t.path,t.resolved_path].includes(root));
    return r?{resource_id:r.id}:{reference:{kind:'file',title:path.split('/').pop(),file_root:root,path,worktree:scope&&!scope.fixed?scope.id:null}};
  }
  function positionTaskClose() {
    if(!taskCloseHost?.isConnected||!taskCloseButton?.isConnected)return;
    const box=taskCloseHost.getBoundingClientRect(),tabs=document.querySelector('.repo-tabs')?.getBoundingClientRect();
    const size=taskCloseButton.getBoundingClientRect().width||36;
    taskCloseButton.style.top=Math.max(box.top,tabs?.bottom||0)+16+'px';
    taskCloseButton.style.left=Math.max(box.left+8,box.right-size-16)+'px';
    if(taskModeHeader){taskModeHeader.style.top=Math.max(box.top,tabs?.bottom||0)+8+'px';taskModeHeader.style.left=box.left+12+'px';taskModeHeader.style.width=Math.max(0,box.width-24)+'px';const height=Math.max(64,taskModeHeader.getBoundingClientRect().height+16);taskModeSpacer.style.height=height+'px';taskCloseHost.style.setProperty('--objective-task-header-height',height+'px');}
  }
  function scheduleTaskClosePosition() {
    if(taskCloseHost&&!taskCloseFrame)taskCloseFrame=requestAnimationFrame(()=>{taskCloseFrame=null;positionTaskClose();});
  }
  function paintTaskClose() {
    const content=document.getElementById('content'),task=context()&&active(context().path)&&focusedTask();
    if(!task||!content){
      taskCloseObserver?.disconnect();taskCloseObserver=null;taskCloseResizeObserver?.disconnect();
      if(taskCloseFrame)cancelAnimationFrame(taskCloseFrame);taskCloseFrame=null;taskCloseButton?.remove();
      taskModeHeader?.remove();taskModeSpacer?.remove();
      taskCloseHost?.classList.remove('objective-task-center');taskCloseHost=null;return;
    }
    if(!taskCloseObserver){
      // Native file/notebook views replace the center independently. Watch only
      // its immediate children and host, never editor/cell output mutations.
      taskCloseObserver=new MutationObserver(paintTaskClose);
      taskCloseObserver.observe(content,{childList:true});
      if(content.parentElement)taskCloseObserver.observe(content.parentElement,{childList:true});
    }
    const host=document.querySelector('.main.assistant-inline-host')||content;
    if(taskCloseHost!==host){
      taskCloseHost?.classList.remove('objective-task-center');taskCloseHost=host;
      taskCloseResizeObserver?.disconnect();taskCloseResizeObserver ||= new ResizeObserver(scheduleTaskClosePosition);taskCloseResizeObserver.observe(host);
    }
    host.classList.add('objective-task-center');
    const draft=taskDocumentDraft(),editable=!draft||draftEditable(draft);
    taskModeHeader ||= document.createElement('div');taskModeHeader.className='objective-task-mode-head';taskModeHeader.dataset.taskModeHead='';
    taskModeHeader.dataset.taskId=task.id;
    taskModeHeader.innerHTML=`<div class="objective-task-mode-title"><button type="button" data-task-icon="${esc(task.id)}" data-task-id="${esc(task.id)}" data-open-task="${esc(task.id)}" aria-label="Open ${esc(task.title)}" title="Drop an asset here to use its icon" draggable="${editable}">${taskIcon(task)}</button><a href="${esc(taskHref(task))}" data-open-task="${esc(task.id)}">${taskNameHtml(task)}</a><label><input type="checkbox" data-task-done="${esc(task.id)}" aria-label="Complete ${esc(task.title)}" ${complete(task)?'checked':''}${editable?'':' disabled'}> Completed</label><span data-task-progress>${window.LabTaskSchedule?.badges(task)||''}</span></div><div class="objective-task-mode-actions"><span>${esc(objective().name)}</span>${draft?`<div class="objective-task-modes objective-document-modes" role="group" aria-label="Document mode">${['view','edit'].map(mode=>`<button type="button" data-task-document-mode="${mode}" aria-pressed="${(mode==='edit')===editable}" title="${mode==='edit'?'Enable editing · returns to View after 3 minutes of inactivity':'Read only'}">${mode==='edit'?'Edit':'View'}</button>`).join('')}</div>`:''}<button type="button" data-edit-objective-task="${esc(task.id)}"${editable?'':' disabled'}>Edit task</button><button type="button" class="objective-task-delete" data-delete-objective-task="${esc(task.id)}">Delete task…</button></div>`;
    taskModeSpacer ||= document.createElement('div');taskModeSpacer.className='objective-task-mode-spacer';taskModeSpacer.setAttribute('aria-hidden','true');
    if(taskModeSpacer.parentElement!==host)host.prepend(taskModeSpacer);
    if(taskModeHeader.parentElement!==host)host.append(taskModeHeader);
    if(!taskCloseButton){
      taskCloseButton=document.createElement('button');taskCloseButton.type='button';
      taskCloseButton.className='objective-task-close';taskCloseButton.dataset.closeObjectiveTask='';
      taskCloseButton.setAttribute('aria-label','Close task mode');taskCloseButton.title='Close task mode';
      taskCloseButton.innerHTML='<span aria-hidden="true">×</span>';
    }
    if(taskCloseButton.parentElement!==host)host.append(taskCloseButton);
    positionTaskClose();
  }
  function taskAssetRow(asset) {
    const info=assetInfo(asset);if(!info)return '';
    const selected=state().selected,r=info.resource,active=r?selected?.resource===r.id&&(selected.tab||null)===(asset.tab_id||null)&&(selected.subLink||null)===(asset.sub_link_id||null):false;
    return `<button type="button" class="sidebar-scope-link objective-resource${r?.kind==='link'?' objective-link':''}${active?' active':''}" data-task-asset="${esc(asset.id||'')}" data-objective-asset="${esc(JSON.stringify(assetTarget(asset)))}" ${r?`data-objective-resource="${esc(r.id)}" ${asset.tab_id?`data-objective-tab="${esc(asset.tab_id)}"`:''} ${asset.sub_link_id?`data-objective-sublink="${esc(asset.sub_link_id)}"`:''}`:''} draggable="true" title="${esc(info.title)}">${info.icon}<span>${esc(info.title)}</span></button>`;
  }
  function subLinksFor(resource,depth=0) {return (resource?.sublinks||[]).flatMap(row=>[{...row,depth},...subLinksFor(row,depth+1)]);}
  function linkTarget(resource,subLink) {return subLink?subLinksFor(resource).find(row=>row.id===subLink):resource;}
  function resourceReference(resource,tabId,subLink) {
    if(!resource||resource.error)return null;
    if(resource.kind==='link')return linkTarget(resource,subLink)?.url;
    const root=resource.kind==='assistant'?resource.assistant_root:resource.kind==='file'?resource.file_root:context()?.path;
    if(!root?.startsWith('/')||!resource.path)return null;
    const path=resource.path.startsWith('/')?resource.path:root.replace(/\/+$/,'')+'/'+resource.path;
    const tab=tabId||resource.tab_id;
    return path+(tab&&!path.includes('#tab=')?'#tab='+encodeURIComponent(tab):'');
  }
  function dragReference(transfer,reference) {
    const references=Array.isArray(reference)?reference:[reference];
    if(!transfer||!references.length||references.some(r=>typeof r!=='string'||!r||/[\x00-\x1f\x7f]/.test(r)))return false;
    transfer.setData('application/x-lab-reference',JSON.stringify(references));
    transfer.setData('text/plain',references.join('\n'));
    if(references.every(r=>r.startsWith('/')&&!r.includes('#')))transfer.setData('application/x-lab-file-path',JSON.stringify(references));
    else if(references.every(r=>/^https?:\/\//i.test(r)))transfer.setData('text/uri-list',references.join('\n'));
    transfer.effectAllowed='copyLink';return true;
  }
  function resourceRow(o,r) {
    const selected=state().selected?.resource===r.id&&!state().selected?.tab&&!state().selected?.subLink;
    const icon=resourceIcon(r);
    const controls=assetControls({resource_id:r.id});
    const rows=(r.kind==='link'?subLinksFor(r):tabsFor(r)).filter(row=>!isTrashed({resource_id:r.id,...(r.kind==='link'?{sub_link_id:row.id}:{tab_id:row.id})},o)),reveal=state().revealed.has(r.id),pins=state().pins[r.id]||[];
    if(r.kind==='link')return `<div class="objective-resource-group" data-resource-group="${esc(r.id)}"><div class="objective-resource-head"><button type="button" class="sidebar-scope-link objective-resource objective-link${selected?' active':''}" data-objective-resource="${esc(r.id)}" draggable="true" title="${esc(r.title)}">${icon}<span>${esc(r.title)}</span></button>${controls}${rows.length?'<span class="objective-sublinks-marker" aria-hidden="true">'+(reveal?'▾':'▸')+'</span>':''}</div>${reveal&&rows.length?`<div class="objective-subtabs objective-sublinks" role="tree" aria-label="${esc(r.title)} sublinks">${rows.map(row=>`<div class="objective-subtab-row" style="--objective-tab-depth:${row.depth}" role="treeitem" aria-level="${row.depth+1}"><button type="button" class="objective-subtab${state().selected?.resource===r.id&&state().selected?.subLink===row.id?' active':''}" data-objective-resource="${esc(r.id)}" data-objective-sublink="${esc(row.id)}" draggable="true" title="${esc(row.title)}">${window.LabScopeLinks?.icon({kind:'external',url:row.url})||'↗'}<span>${esc(row.title)}</span></button>${assetControls({resource_id:r.id,sub_link_id:row.id})}</div>`).join('')}</div>`:''}</div>`;
    return `<div class="objective-resource-group" data-resource-group="${esc(r.id)}"><div class="objective-resource-head"><button type="button" class="sidebar-scope-link objective-resource${selected?' active':''}" data-objective-resource="${esc(r.id)}" draggable="true" title="${esc(r.title)}">${icon}<span>${esc(r.title)}</span></button>${controls}${rows.length?`<button type="button" class="objective-tree-toggle" data-reveal-resource="${esc(r.id)}" aria-label="Show subtabs for ${esc(r.title)}" aria-expanded="${reveal}">${reveal?'▾':'▸'}</button>`:''}</div>
      ${rows.length?`<div class="objective-subtabs" role="tree" aria-label="${esc(r.title)} subtabs">${rows.filter(t=>reveal||pins.includes(t.id)).map(t=>`<div class="objective-subtab-row" style="--objective-tab-depth:${t.depth}" role="treeitem" aria-level="${t.depth+1}"><button type="button" class="objective-subtab${state().selected?.resource===r.id&&state().selected.tab===t.id?' active':''}" data-objective-resource="${esc(r.id)}" data-objective-tab="${esc(t.id)}" draggable="true" title="${esc(t.title)}"><span aria-hidden="true">▤</span><span>${esc(t.title)}</span></button>${assetControls({resource_id:r.id,tab_id:t.id})}<button type="button" class="objective-pin" data-pin-resource="${esc(r.id)}" data-pin-tab="${esc(t.id)}" aria-label="Pin ${esc(t.title)}" aria-pressed="${pins.includes(t.id)}">${pins.includes(t.id)?'◆':'◇'}</button></div>`).join('')}</div>`:''}</div>`;
  }
  function paint() {
    paintTaskClose();
    bridge.refreshTabs?.();
    if(switchMenu)paintSwitchMenu();
    refreshLinkDetails();
    const scope=context(),host=document.querySelector('[data-objectives-sidebar]');if(!host||!scope)return;
    const d=data();if(!d)return;
    if(!d.enabled){host.innerHTML='<button type="button" class="sidebar-objective-add" data-new-objective>+ Objective</button>';return;}
    const o=objective();if(!o)return;state().objective=o.id;
    bridge.refreshAgentContext?.();
    host.dataset.worktreeBrowse=String(!!state().worktreeBrowse);
    const task=focusedTask(),sidebarRows=pendingTaskRows(o);
    const reservedTaskRows=Math.max(1,sidebarRows.length);
    const unassigned=unassignedAssets(o,true);
    const selectedAssets=task?taskAssets(task).filter(a=>!isArchived(a,o)):[];
    const selectedWorktrees=selectedAssets.filter(a=>worktreeAssetScope(a,o));
    const overview=!task&&!state().selected&&openView?.type==='overview'&&openView.scope===key(scope)&&openView.objective===o.id;
    host.innerHTML=`<div class="objective-sidebar-heading" style="--objective-color:${esc(o.color)}"><button type="button" data-select-objective="${esc(o.id)}" data-drag-objective="${esc(o.id)}" draggable="true" aria-pressed="${!task&&state().view==='objective'}" title="${esc(o.name)} · Drag into a terminal for the full context"><span class="objective-library-dot" aria-hidden="true"></span><span>${esc(o.name)}</span></button><button type="button" data-objective-settings aria-label="Objective settings">⚙</button></div>`+
      `<section class="objective-worktree-navigation" aria-label="Worktrees"><div class="sidebar-title objective-title"><button type="button" class="objective-bucket-label" data-fold-worktrees aria-expanded="${!!state().worktreesOpen}">${state().worktreesOpen?'▾':'▸'} Worktrees <small>${scopeRows(o).length}</small></button><button type="button" data-associate-worktree aria-label="Associate worktree">+</button></div><div class="objective-worktrees" ${state().worktreesOpen?'':'hidden'}>${worktreeNavigationHtml(o)}</div></section>`+
      ((o.shared_assets||[]).length?bucketHtml('objective','Objective · pinned',o.shared_assets.filter(a=>!isArchived(a,o))):'')+
      `<section class="objective-bucket objective-sidebar-tasks" data-objective-bucket="tasks"><div class="sidebar-title objective-title objective-tasks-drop" data-objective-tasks-drop title="Drop a task or its terminal here to make it a top-level task"><button type="button" class="objective-bucket-label" data-open-objective-tasks draggable="true">Tasks</button>${badge(o)}<button type="button" data-new-objective-task aria-label="New objective task">+</button></div><div class="objective-sidebar-task-list" style="--objective-task-rows:${reservedTaskRows}">${sidebarRows.map(({task,parent,depth})=>sidebarTaskRow(task,parent,depth)).join('')||'<p class="objective-bucket-empty">No pending tasks.</p>'}</div></section>`+
      bucketHtml('task','Task assets',selectedAssets.filter(a=>!worktreeAssetScope(a,o)))+
      (task?`<section class="objective-bucket objective-task-worktrees" data-task-id="${esc(task.id)}" aria-label="Worktrees for this task"><div class="sidebar-title objective-title">Worktrees</div><div class="objective-resources">${assetListHtml(selectedWorktrees,'sidebar:worktrees:'+task.id)||'<p class="objective-bucket-empty">No worktrees assigned to this task.</p>'}</div></section>`:'')+
      (overview?bucketHtml('unassigned','Unassigned',unassigned,true)+`<details class="objective-archive" ${state().archiveOpen?'open':''}><summary>Archive · ${(o.archived_assets||[]).length}</summary>${bucketHtml('archive','Archived assets',o.archived_assets||[])}</details>`:'');
    host.closest('[data-project-sidebar]')?.setAttribute('data-objective-sidebar-mode',sidebarMode(scope.path));
    bridge.refreshRecent?.();
    const archive=host.querySelector('.objective-archive');if(archive)archive.ontoggle=()=>{state().archiveOpen=archive.open;};
    const archivedWorktrees=host.querySelector('.objective-worktree-archive');if(archivedWorktrees)archivedWorktrees.ontoggle=()=>{state().worktreeArchiveOpen=archivedWorktrees.open;};
    host.querySelectorAll('[data-resource-group]').forEach(row=>{row.onmouseenter=()=>{clearTimeout(hoverTimer);const id=row.dataset.resourceGroup;if(state().revealed.has(id))return;const resource=o.resources.find(r=>r.id===id);hoverTimer=setTimeout(()=>{if(row.isConnected&&key(context())===key(scope)){state().revealed.add(id);paint();}},resource?.kind==='link'?1000:1500);};row.onmouseleave=()=>clearTimeout(hoverTimer);});
    markTaskAssets(host);
  }
  function activateLinkedTerminal(matches) {
    const sessions=Object.entries(data().terminal_links||{}).filter(([,link])=>matches(link)).map(([session])=>session);
    Promise.resolve(bridge.activateLinkedTerminal?.(sessions)).catch(error=>notify(error.message,true));
  }
  function selectObjective(id,{activateTerminal=true}={}) {
    closeTaskStatusMenu();
    closeAssetContextMenu();
    closeLinkEdit();
    const o=data()?.objectives.find(o=>o.id===id);if(!o)return;closeSwitchMenu();collapse();resetWorktreeBrowse();state().focus=null;state().objective=id;state().view='objective';state().selected=null;persistView();paint();renderOverview();bridge.refreshTerminals?.();
    const t=tree(o)||{path:context().path,kind:'folder'};if(bridge.scopeRoot?.()!==t.path)bridge.selectWorktree?.(t);
    if(activateTerminal)activateLinkedTerminal(link=>link.objective_id===id&&!link.task_id&&!link.resource_id&&!link.file&&!link.folder&&!link.view);
  }
  function tabsHtml(path,working=true) {
    if(context()?.path!==path)return '';
    const s=state(),all=working&&s.view==='all',o=objective(),selected=!!(working&&!all&&o),task=working&&focusedTask();
    return `<button type="button" class="repo-tab vault-context-tab objective-tab${all?' active':''}" data-all-objectives aria-pressed="${all}">Objectives</button>`+
      (o?`<button type="button" class="repo-tab vault-context-tab objective-tab${selected?' active':''}" style="--vault-color:${esc(o.color)}" data-current-objective data-select-objective="${esc(o.id)}" draggable="true" aria-pressed="${selected}" aria-haspopup="menu" aria-expanded="${!!switchMenu}" aria-controls="objective-switch-menu" title="${esc(o.name+(task?' / '+task.title:''))} · Drag the whole Objective into a terminal">${task?`<span class="objective-task-tab-icon">${taskIcon(task)}</span>`:'<span class="vault-mark" aria-hidden="true"></span>'}<span class="objective-tab-name">${task?taskNameHtml(task):esc(o.name)}</span><span class="objective-switch-arrow" data-toggle-objective-switch aria-hidden="true">▾</span></button>`:'');
  }
  function closeSwitchMenu() {
    clearTimeout(switchTimer);switchMenu?.remove();switchMenu=null;
    document.querySelector('[data-current-objective]')?.setAttribute('aria-expanded','false');
  }
  function paintSwitchMenu() {
    const anchor=document.querySelector('[data-current-objective]'),d=data();if(!anchor||!d||!switchMenu){closeSwitchMenu();return;}
    const focusedIndex=[...switchMenu.querySelectorAll('button')].indexOf(document.activeElement);
    switchMenu.innerHTML=Array.from({length:focusSlots},(_,slot)=>{
      const o=d.objectives.find(o=>o.id===d.focused[slot]),selected=o?.id===objective()?.id;
      return `<button type="button" role="menuitemradio" aria-checked="${selected}" ${o?`data-select-objective="${esc(o.id)}" data-drag-objective="${esc(o.id)}" draggable="true" title="Drag this Objective into a terminal to pass its whole context"`:`data-choose-objective-slot="${slot}"`} style="--vault-color:${esc(o?.color||d.slot_palettes?.[slot]?.[0]||'#8b949e')}"><span class="objective-switch-number">${slot+1}</span><span class="vault-mark" aria-hidden="true"></span><span class="objective-tab-name">${esc(o?.name||'Choose an objective…')}</span></button>`;
    }).join('');
    anchor.setAttribute('aria-expanded','true');const box=anchor.getBoundingClientRect();
    switchMenu.style.left=Math.max(8,Math.min(box.left,window.innerWidth-switchMenu.offsetWidth-8))+'px';
    const bottom=Math.max(box.bottom,anchor.closest('.repo-tabs')?.getBoundingClientRect().bottom||box.bottom);
    switchMenu.style.top=Math.min(bottom,window.innerHeight-switchMenu.offsetHeight-8)+'px';
    if(focusedIndex>=0)switchMenu.querySelectorAll('button')[focusedIndex]?.focus({preventScroll:true});
  }
  function showSwitchMenu() {
    clearTimeout(switchTimer);if(switchMenu)return;
    if(!document.querySelector('[data-current-objective]'))return;
    switchMenu=document.createElement('div');switchMenu.id='objective-switch-menu';switchMenu.className='objective-switch-menu';switchMenu.setAttribute('role','menu');switchMenu.setAttribute('aria-label','Focused objectives');
    document.body.append(switchMenu);paintSwitchMenu();
  }
  function focusSlotsHtml() {
    const d=data();return Array.from({length:focusSlots},(_,slot)=>{
      const o=d.objectives.find(o=>o.id===d.focused[slot]);
      return `<button type="button" class="objective-focus-slot${o?'':' objective-slot-empty'}" data-objective-slot="${slot}" ${o?`data-select-objective="${esc(o.id)}" data-drag-objective="${esc(o.id)}" draggable="true"`:''} style="--vault-color:${esc(d.slot_palettes?.[slot]?.[0]||o?.color||'#8b949e')}" title="${o?esc(o.name):'Drop an objective here or click to choose'}"><span class="objective-focus-slot-label">Slot ${slot+1}<span class="vault-mark" aria-hidden="true"></span></span><span class="objective-tab-name">${esc(o?.name||'Drop an objective')}</span></button>`;
    }).join('');
  }
  function showAll() {
    closeTaskStatusMenu();
    closeLinkEdit();
    if(!data()){const scope=key(context());void load().then(result=>{if(result&&key(context())===scope)showAll();});return;}
    closeSwitchMenu();resetWorktreeBrowse();state().view='all';state().focus=null;state().selected=null;collapse();persistView();
    const host=showCenter('all');
    host.innerHTML=`<section class="objective-working objective-library"><header><h2>All objectives</h2><button type="button" data-new-objective>+ Objective</button></header><section class="objective-focus" aria-label="Focus slots"><h3>Focus slots</h3><div class="objective-focus-slots"></div><p class="objective-purpose">Drop into a slot to insert. Following objectives move down; the fifth returns to the list.</p></section><div class="objective-library-filters"><label>Search<input type="search" data-objective-search placeholder="Name or outcome" value="${esc(state().query||'')}"></label><label>Focus<select data-objective-filter><option value="all">All objectives</option><option value="focused">In focus</option><option value="parked">Parked</option></select></label><label>Tasks<select data-objective-status-filter><option value="all">Any status</option><option value="track">On track</option><option value="risk">At risk</option><option value="overdue">Past due</option><option value="complete">Complete</option></select></label></div><div class="objective-library-list"></div></section>`;
    host.querySelector('[data-objective-filter]').value=state().filter||'all';host.querySelector('[data-objective-status-filter]').value=state().statusFilter||'all';
    paintLibrary();paint();
  }
  function paintLibrary() {
    const host=document.querySelector('.objective-library-list');if(!host||openView?.scope!==key(context()))return;
    const d=data(),s=state(),query=(s.query||'').trim().toLocaleLowerCase();
    document.querySelector('.objective-focus-slots').innerHTML=focusSlotsHtml();
    const rows=d.objectives.filter(o=>(!query||(o.name+' '+o.purpose).toLocaleLowerCase().includes(query))&&(!s.filter||s.filter==='all'||d.focused.includes(o.id)===(s.filter==='focused'))&&(!s.statusFilter||s.statusFilter==='all'||progress(o).status===s.statusFilter));
    host.innerHTML=rows.map(o=>`<div class="objective-library-row" data-drag-objective="${esc(o.id)}" draggable="true" style="--objective-color:${esc(o.color)}"><span class="objective-library-dot" aria-hidden="true"></span><button type="button" data-library-objective="${esc(o.id)}"><strong>${esc(o.name)}</strong><span>${esc(o.purpose)}</span></button>${badge(o)}<span class="objective-library-focus">${d.focused.includes(o.id)?'Slot '+(d.focused.indexOf(o.id)+1):'Parked'}</span><button type="button" data-place-objective="${esc(o.id)}" aria-label="Choose focus slot for ${esc(o.name)}">Focus…</button></div>`).join('')||'<p>No objectives match. Create one or change the filters.</p>';
  }
  function showCenter(type) {releaseDraft();bridge.prepareCenter?.(type);openView={type,scope:key(context()),objective:objective()?.id};return document.getElementById('content');}
  function taskHref(task,item=null) {const url=new URL(location.pathname,location.origin);url.searchParams.set('workspace',context().path);url.searchParams.set('objective',objective().id);url.searchParams.set('objective_task',task.id);if(item){url.searchParams.set('objective_action_line',item.line);url.searchParams.set('objective_action_source',item.source);}return url.pathname+url.search;}
  function taskRow(task,parent=null,depth=parent?1:0) {
    const done=parent?task.done:complete(task);return `<div class="objective-task-row${parent?' child':''}" style="--objective-task-depth:${depth}" data-task-id="${esc(task.id)}"><input type="checkbox" aria-label="Complete ${esc(task.title)}" data-task-done="${esc(task.id)}" ${done?'checked':''}><a class="objective-task-title${done?' done':''}" href="${esc(taskHref(task))}" data-open-task="${esc(task.id)}" draggable="true">${taskNameHtml(task)}${window.LabTaskSchedule?.badges(task)||''}</a><button type="button" data-task-assets="${esc(task.id)}" aria-label="Assets and icon for ${esc(task.title)}" title="${taskAssets(task).length} assets · drag an asset onto the sidebar task icon to change it">${taskIcon(task)}</button><span class="objective-task-schedule"><input type="date" aria-label="Due date for ${esc(task.title)}" data-task-due="${esc(task.id)}" value="${esc(task.due||'')}" title="${parent&&!task.due?'Inherits '+(parent.due||'parent deadline'):'Due date'}"><button type="button" data-schedule-task="${esc(task.id)}" aria-label="Schedule for ${esc(task.title)}" title="Repeat and reactivation window">↻</button></span><button type="button" data-add-subtask="${esc(task.id)}" aria-label="Add subtask to ${esc(task.title)}">+</button><button type="button" class="objective-task-delete" data-delete-objective-task="${esc(task.id)}" aria-label="Delete ${esc(task.title)}">Delete</button></div>`;
  }
  function renderTasks() {
    const o=objective();if(!o)return;state().focus=null;state().view='objective';persistView();const host=showCenter('tasks'),p=progress(o);state().selected=null;
    const rows=state().showFinished?taskTree(o.tasks).filter(({task})=>!waiting(task)&&!taskAncestors(task,o).some(waiting)):pendingTaskRows(o);
    host.innerHTML=`<section class="objective-working"><header><h2 data-open-objective-tasks title="Drop a task here to make it a top-level task">Tasks</h2><button type="button" data-new-objective-task>+ Task</button></header><p class="objective-purpose">${esc(o.name)} · ${esc(o.purpose)}</p>${state().worktreeBrowse?`<p class="objective-worktree-assignment-help">Drag ${esc(tree()?.label)} from Worktrees onto any task below. Repeat to assign it to multiple tasks. Fold Worktrees to return to task assets.</p>`:''}<div class="objective-task-progress">${badge(o)}<span>${esc(p.label)}</span></div>${dueDashboard(o)}<div class="objective-task-display-options"><label><input type="checkbox" data-show-finished-tasks ${state().showFinished?'checked':''}> Show completed / discarded</label><p>Add a deadline to an action item: <code>- [ ] [YYYY-MM-DD HH:mm] Action item</code> · local time</p></div><div class="objective-task-list">${rows.map(({task,parent,depth})=>taskWithActions(task,parent,depth)).join('')||'<p>No pending tasks.</p>'}</div></section>`;
    host.querySelector('[data-show-finished-tasks]').onchange=event=>{state().showFinished=event.target.checked;renderTasks();};
    paint();
  }

  function overviewAssets(label,assets) {
    return `<section class="objective-overview-assets" aria-label="${esc(label)}"><h3>${esc(label)}</h3><div class="objective-resources">${assetListHtml(assets,'overview:'+label)||'<p class="objective-bucket-empty">No assets.</p>'}</div></section>`;
  }
  function overviewState() {const s=state();return s.overview[objective().id] ||= {mode:'assets',query:''};}
  function assignmentLabel(destination) {
    const owner=data().objectives.find(o=>o.id===destination.objective_id)||objective();
    if(destination.bucket==='task')return (owner.id!==objective().id?owner.name+' / ':'')+(tasks(owner).find(t=>t.id===destination.task_id)?.title||'Unavailable task');
    return 'Objective: '+owner.name;
  }
  function reviewAssetRow(asset,archived=false,flat=false) {
    const source=flat?flatAssetRow(asset):assetRow(asset);
    const target=esc(JSON.stringify(assetTarget(asset))),suggestions=(objective().assignment_suggestions||[]).filter(s=>sameAsset(s.asset,asset));
    const pending=suggestions.filter(s=>s.status==='pending'),rejected=suggestions.some(s=>s.status==='rejected');
    if(requiredAsset(asset))return `<div class="objective-review-asset">${source}<span class="objective-assignment-status">Required task details</span></div>`;
    return `<div class="objective-review-asset"><div class="objective-review-source">${source}<span class="objective-assignment-status">${archived?'Archived':pending.length?'Suggestion available':rejected?'Suggestion rejected':'No suggestion'}</span></div>${archived?`<div class="objective-review-actions"><button type="button" data-restore-objective-asset="${target}">Restore to Unassigned</button><button type="button" data-trash-objective-asset="${target}">Trash</button></div>`:`${pending.map(s=>`<div class="objective-assignment-suggestion"><div><strong>Suggested → ${esc(assignmentLabel(s.destination))}</strong><p>${esc(s.reason)}</p></div><div class="objective-review-actions"><button type="button" data-accept-assignment="${esc(s.id)}">Accept</button><button type="button" data-reject-assignment="${esc(s.id)}">Reject</button></div></div>`).join('')}<div class="objective-review-actions"><button type="button" data-classify-asset="${target}">${pending.length?'Choose another…':'Assign…'}</button><button type="button" data-archive-objective-asset="${target}">Archive</button><button type="button" data-trash-objective-asset="${target}">Trash</button></div>`}</div>`;
  }
  function overviewReviewSection(label,assets,archived=false) {
    return `<section class="objective-overview-assets" aria-label="${esc(label)}"><h3>${esc(label)} <span class="objective-result-count">${assets.length}</span></h3><div class="objective-review-list">${assetListHtml(assets,'review:'+label,a=>reviewAssetRow(a,archived),a=>reviewAssetRow(a,archived,true))||'<p class="objective-bucket-empty">No assets.</p>'}</div></section>`;
  }
  function paintOverviewResults() {
    const host=document.querySelector('[data-objective-overview-results]');if(!host||openView?.scope!==key(context()))return;
    const o=objective(),s=overviewState(),query=s.query.trim().toLocaleLowerCase(),includes=text=>!query||String(text||'').toLocaleLowerCase().includes(query);
    const matchAsset=a=>{const info=assetInfo(a,o);return info&&includes(info.title+' '+info.reference);};
    const matchTask=t=>includes(t.title+' '+(t.due||''))||pendingActions(t).some(item=>includes(item.label+' '+(item.due||'')))||taskAssets(t).filter(a=>!isArchived(a,o)).some(matchAsset);
    const sharedMatch=!!query&&(o.shared_assets||[]).filter(a=>!isArchived(a,o)).some(matchAsset);
    const entries=pendingTaskRows(o).map(row=>row.task).filter(t=>matchTask(t)||sharedMatch);
    if(s.mode==='archive'){
      host.innerHTML=overviewReviewSection('Archived assets',(o.archived_assets||[]).filter(a=>!isTrashed(a,o)&&matchAsset(a)),true);return;
    }
    const unassigned=unassignedAssets(o).filter(matchAsset);
    let html=s.mode!=='tasks'?overviewReviewSection('Unassigned assets',unassigned):'';
    if(s.mode!=='unassigned'){
      const empty=t=>!(t.assets||[]).some(a=>!isArchived(a,o));
      const renderTask=t=>{const parent=taskParent(t,o);return `<section class="objective-overview-task" data-overview-task="${esc(t.id)}">${parent?`<p class="objective-task-parent">Subtask of ${esc(parent.title)}</p>`:''}${taskWithActions(t,parent,taskAncestors(t,o).length)}${s.mode==='assets'?overviewAssets('Task: '+t.title,taskAssets(t).filter(a=>!isArchived(a,o))):''}</section>`;};
      html+=`<section class="objective-overview-tasks"><header><h3>Tasks</h3><button type="button" data-new-objective-task>+ Task</button></header><div class="objective-task-progress">${badge(o)}<span>${esc(progress(o).label)}</span></div>${[true,false].map(without=>{const rows=entries.filter(t=>empty(t)===without);return rows.length?`<h3 class="objective-task-group-label">${without?'Tasks without attached assets':'Tasks with assets'} · ${rows.length}</h3><div class="objective-task-list">${rows.map(renderTask).join('')}</div>`:'';}).join('')||'<p class="objective-bucket-empty">No matching tasks.</p>'}</section>`;
      if(s.mode==='assets'){
        html+=overviewReviewSection('Global assets · shared across tasks',(o.shared_assets||[]).filter(a=>!isArchived(a,o)&&(matchAsset(a)||query&&entries.length)));
        const catalog=assetCatalog(o).filter(a=>!isArchived(a,o)&&matchAsset(a)).concat(o.resources.filter(r=>r.task_document&&!isArchived({resource_id:r.id},o)&&matchAsset({resource_id:r.id})).map(r=>({resource_id:r.id})));
        html+=`<details class="objective-overview-catalog"><summary>All Objective assets · ${catalog.length}</summary>${overviewAssets('All Objective assets',catalog)}</details>`;
      }
    }
    host.innerHTML=html;
  }
  function renderOverview() {
    const o=objective();if(!o)return;state().focus=null;state().view='objective';state().selected=null;persistView();
    const host=showCenter('overview');
    const s=overviewState();
    host.innerHTML=`<section class="objective-working objective-overview"><header><h2>${esc(o.name)}</h2><button type="button" data-objective-settings>Objective settings</button></header><p class="objective-purpose">${esc(o.purpose)}</p><div class="objective-overview-toolbar"><label>Search tasks and assets<input type="search" data-objective-overview-search placeholder="Task, asset name or path…" value="${esc(s.query)}"></label><label>View<select data-objective-overview-mode><option value="assets">Tasks with assets</option><option value="tasks">Tasks only</option><option value="unassigned">Unassigned assets</option><option value="archive">Archive · ${(o.archived_assets||[]).length}</option></select></label></div><div data-objective-overview-results aria-live="polite"></div></section>`;
    host.querySelector('[data-objective-overview-mode]').value=s.mode;paintOverviewResults();paint();
  }
  function selectScope(row) {
    if(!row)return;collapse();const s=state();
    s.worktreeBrowse ||= {focus:s.focus?{...s.focus}:null};s.tree[objective().id]=row.id;
    s.focus=null;s.selected=null;s.view='objective';persistView();
    renderTasks();
    Promise.resolve(bridge.selectWorktree?.(row)).catch(error=>notify(error.message,true));
  }
  function openTask(id,{activateTerminal=false,actionItem=null}={}) {
    const o=objective(),task=tasks(o).find(t=>t.id===id);if(!task)return;
    actionTarget=actionItem?{scope:key(context()),task:id,item:actionItem}:null;
    resetWorktreeBrowse();
    state().focus={objective:o.id,task:id};
    state().view='objective';persistView();openResource(task.document_id,task.tab_id);
    bridge.refreshTerminals?.();
    if(activateTerminal&&taskTerminalVisible(task,o)){
      if(taskTerminalsEnabled())void openTaskTerminal(id,o.id,{openTaskView:false}).catch(error=>notify(error.message,true));
      else if(Object.values(data().terminal_links||{}).some(link=>link.objective_id===o.id&&link.task_id===id))activateLinkedTerminal(link=>link.objective_id===o.id&&link.task_id===id);
    }
  }
  function openTaskAssets(id) {
    const task=tasks().find(t=>t.id===id);if(!task)return;
    form('Task assets',`<p class="objective-purpose">${esc(task.title)} · Drop documents, notebooks, links or folders here or onto its task row. Drag an asset onto the icon at the right of its sidebar row to set its terminal icon.</p><div class="objective-task-asset-list" data-task-id="${esc(id)}">${taskAssets(task).map(a=>{const info=assetInfo(a);return info?`<div class="objective-task-asset-choice"><span class="objective-task-asset-icon" aria-hidden="true">${info.icon}</span><button type="button" data-open-task-asset="${esc(a.id)}" data-asset-task="${esc(id)}">${esc(info.title)}</button>${a.required?'<span class="objective-purpose">Details</span>':`<button type="button" data-remove-task-asset="${esc(a.id)}" data-asset-task="${esc(id)}" aria-label="Detach ${esc(info.title)}">×</button>`}</div>`:'';}).join('')}</div>`,async()=>{});
    dialog.querySelector('[type=submit]').textContent='Done';
  }
  function openTaskIconPicker(id) {
    const o=objective(),task=tasks(o).find(t=>t.id===id);if(!task)return;
    const scope={...context()},seen=new Set(),choices=[];
    for(const asset of [...taskAssets(task),...assetCatalog(o)]){
      const info=assetInfo(asset,o);if(!info||seen.has(info.icon))continue;
      seen.add(info.icon);
      choices.push({icon:{asset:assetTarget(asset)},html:info.icon,label:info.title});
    }
    for(const service of window.LAB_LINK_SERVICES||[]){
      const icon={service:service.id},html=customTaskIcon({icon},o);if(seen.has(html))continue;
      seen.add(html);choices.push({icon,html,label:service.name});
    }
    const legacy=taskAssets(task).find(a=>a.id===task.icon_asset_id);
    let selected=task.icon||(legacy?{asset:assetTarget(legacy)}:null),color=task.terminal_color||null;
    const current=customTaskIcon(task,o),button=choice=>`<button type="button" data-pick-task-icon="${esc(JSON.stringify(choice.icon))}" title="${esc(choice.label)}" aria-label="${esc(choice.label)}" aria-pressed="${current===choice.html}">${choice.html}</button>`;
    const node=form('Task icon and terminal color',`<p class="objective-purpose">${esc(task.title)}</p><div class="objective-task-icon-preview"><span data-task-icon-preview></span><span data-task-color-preview>${esc(taskDisplayName(task,o))}</span></div><section aria-label="Asset icons"><h3>Asset icons</h3><div class="objective-task-icon-grid">${choices.map(button).join('')||'<p class="objective-purpose">No asset icons available.</p>'}</div></section><section aria-label="Suggested emojis"><h3>Suggested emojis</h3><div class="objective-task-icon-grid">${taskEmojiChoices.map(([emoji,label])=>button({icon:{emoji},html:`<span aria-hidden="true">${emoji}</span>`,label:emoji+' · '+label})).join('')}</div></section><label>Custom emoji<input name="emoji" value="${esc(task.icon?.emoji||'')}" maxlength="32" placeholder="Paste an emoji, such as 💡"></label><div class="objective-task-icon-options"><button type="button" data-task-text-color>Terminal text color…</button><button type="button" data-task-default-color>Default color</button><button type="button" data-pick-task-icon="null">Default icon</button></div>`,()=>change({type:'task-update',objective_id:o.id,task_id:id,icon:selected,terminal_color:color},{scope}));
    node.classList.add('objective-task-icon-picker');
    const preview=()=>{
      node.querySelector('[data-task-icon-preview]').innerHTML=customTaskIcon({icon:selected,assets:[]},o)||'💻';
      node.querySelector('[data-task-color-preview]').style.color=color||'';
    };
    node.addEventListener('click',event=>{
      const choice=event.target.closest('[data-pick-task-icon]');
      if(choice){selected=JSON.parse(choice.dataset.pickTaskIcon);node.querySelector('[name=emoji]').value=selected?.emoji||'';node.querySelectorAll('[data-pick-task-icon]').forEach(n=>n.setAttribute('aria-pressed',String(n===choice)));preview();}
    });
    node.querySelector('[name=emoji]').oninput=event=>{selected=event.target.value?{emoji:event.target.value}:null;node.querySelectorAll('[data-pick-task-icon]').forEach(n=>n.setAttribute('aria-pressed','false'));preview();};
    node.querySelector('[data-task-text-color]').onclick=event=>window.LabSidebarScopes?.colors(event.currentTarget,bridge.scopeColorPalette?.()||[],chosen=>{color=chosen;preview();});
    node.querySelector('[data-task-default-color]').onclick=()=>{color=null;preview();};
    preview();
  }
  function classifyAsset(target,preset=null) {
    const info=assetInfo(target);if(!info)return;
    const scope={...context()},owner=objective(),assigned=tasks(owner).find(t=>(t.assets||[]).some(a=>sameAsset(a,target))),pending=(owner.assignment_suggestions||[]).find(s=>s.status==='pending'&&sameAsset(s.asset,target));
    const node=form('Assign '+info.title,`<label>Bucket<select name="bucket"><option value="task">Task</option><option value="objective">Objective · shared across tasks</option><option value="unassigned">Unassigned</option><option value="archive">Archive</option><option value="trash">Trash</option></select></label><label>Objective<select name="objective">${data().objectives.map(o=>`<option value="${esc(o.id)}">${esc(o.name)}</option>`).join('')}</select></label><label>Task<select name="task"></select></label><p data-trash-confirm hidden>Remove this asset from the Objective and detach its task assignments? Source files and running terminals are preserved.</p>`,async values=>{
      const bucket=values.get('bucket');
      await change({type:bucket==='trash'?'asset-trash':['task','objective'].includes(bucket)?'asset-assign':'asset-bucket',objective_id:owner.id,...target,...(bucket==='trash'?{confirmed:true}:['task','objective'].includes(bucket)?{destination:{bucket,objective_id:values.get('objective'),...(bucket==='task'?{task_id:values.get('task')}:{})}}:{bucket})},{scope});
    });
    node.querySelector('[name=bucket]').value=preset||(isArchived(target)?'archive':isShared(target)?'objective':assigned?'task':pending?.destination.bucket|| (tasks(owner).length?'task':'objective'));
    node.querySelector('[name=objective]').value=pending?.destination.objective_id||owner.id;
    const syncTasks=()=>{const entries=tasks(data().objectives.find(o=>o.id===node.querySelector('[name=objective]').value));node.querySelector('[name=task]').innerHTML=entries.map(t=>`<option value="${esc(t.id)}">${esc(t.title)}</option>`).join('');};
    const sync=()=>{const bucket=node.querySelector('[name=bucket]').value;node.querySelector('[name=objective]').parentElement.hidden=!['task','objective'].includes(bucket);node.querySelector('[name=task]').parentElement.hidden=bucket!=='task';node.querySelector('[data-trash-confirm]').hidden=bucket!=='trash';node.querySelector('[type=submit]').textContent=bucket==='trash'?'Trash asset':'Move';};
    node.querySelector('[name=objective]').onchange=syncTasks;node.querySelector('[name=bucket]').onchange=sync;syncTasks();
    if(assigned||pending?.destination.task_id)node.querySelector('[name=task]').value=pending?.destination.task_id||assigned.id;sync();
  }
  function trashAsset(target) {
    const info=assetInfo(target);if(!info)return;const scope={...context()},owner=objective().id;
    const node=form('Trash '+info.title+'?',`<p>Remove this asset from the Objective and detach its task assignments? Source files and running terminals are preserved.</p>`,()=>change({type:'asset-trash',objective_id:owner,...target,confirmed:true},{scope}));
    node.querySelector('[type=submit]').textContent='Trash asset';
  }
  function openAsset(asset,event=null) {
    if(asset.folder){const scope=asset.folder.path==='.'&&scopeRows().find(t=>[t.path,t.resolved_path].includes(asset.folder.root));if(scope)selectScope(scope);else bridge.openFolder?.(asset.folder);return;}
    const info=assetInfo(asset);if(info?.resource?.kind==='link'){openLinkUrl(info.reference,event);return;}
    openResource(asset.resource_id,asset.tab_id||null,asset.sub_link_id||null);
  }
  function openResource(resourceId,tabId=null,subLink=null) {
    const o=objective(),r=o?.resources.find(r=>r.id===resourceId);if(!r)return;
    closeLinkEdit();
    if(r.kind==='link'&&subLink&&!linkTarget(r,subLink))subLink=null;
    state().view='objective';persistView();
    releaseDraft();
    const wasRevealed=state().revealed.has(resourceId);collapse();state().selected={resource:resourceId,tab:tabId,subLink};if(r.content?.tabs?.length||r.kind==='link'&&wasRevealed)state().revealed.add(resourceId);paint();
    openView={type:r.kind,scope:key(context()),objective:o.id,resource:r.id,tab:tabId};
    if(r.kind==='assistant'){bridge.openAssistant?.({...r,tab_id:tabId||r.tab_id});return;}
    if(r.kind==='link'){if(linkTarget(r,subLink))renderLinkDetails(o,r,subLink);return;}
    if(r.kind==='notebook'){bridge.openNotebook?.(r);return;}
    if(r.kind==='file'){bridge.openFile?.({root:r.file_root,path:r.path});return;}
    const tab=r.content?.tabs?.find(t=>t.id===tabId),body=tab?.body??r.content?.body??'',host=showCenter('document');openView.resource=r.id;openView.tab=tabId;
    host.innerHTML=`<section class="objective-working objective-document"><header><h2>${esc(tab?.title||r.title)}</h2><button type="button" data-rename-objective-resource="${esc(r.id)}">Rename</button></header><div class="objective-document-context"><button type="button" data-open-objective-tasks>← Tasks</button><span>${esc(o.name)}${tab?' / '+esc(r.title):''}</span></div><article class="workspace-doc-body markdown-body"></article><div class="objective-document-actions"><button type="button" data-save-objective-document>Save</button><button type="button" data-revert-objective-document>Revert</button>${!tabId?`<button type="button" data-add-objective-subtab="${esc(r.id)}">+ Subtab</button>`:''}<span class="objective-document-status" role="status" aria-live="polite"></span></div></section>`;
    mountDraft(o,r,tabId,body,host.querySelector('article'));
  }
  const linkFields=r=>({title:r.title,url:r.url,tldr:r.tldr||'',metadata:r.metadata||{}});
  const linkSnapshot=r=>JSON.stringify(linkFields(r));
  const propertyText=value=>typeof value==='string'?value:JSON.stringify(value);
  const linkUi=d=>JSON.stringify([d.title,d.url,d.tldr,d.properties]);
  const dirtyLink=d=>linkUi(d)!==d.baseUi;
  function resetLinkDraft(d,r) {
    Object.assign(d,linkFields(r));d.properties=Object.entries(r.metadata||{}).map(([name,value])=>({name,value:propertyText(value),original:value}));
    d.base=linkSnapshot(r);d.baseUi=linkUi(d);d.error='';
  }
  function linkDraftValues(d) {
    const title=d.title.trim(),url=d.url.trim();if(!title)throw new Error('Give this link a title.');
    if(!validLinkUrl(url))throw new Error('Use a full http or https URL.');
    const entries=[],names=new Set();
    for(const item of d.properties){
      const name=item.name.trim();if(!name&&!item.value)continue;
      if(!name)throw new Error('Give each metadata property a name.');
      if(names.has(name))throw new Error('Metadata property names must be unique.');
      names.add(name);entries.push([name,item.value===propertyText(item.original)?item.original:item.value]);
    }
    return {title,url,tldr:d.tldr,metadata:Object.fromEntries(entries)};
  }
  function validLinkUrl(value) {
    try{const url=new URL(value);return /^https?:\/\//i.test(value)&&['http:','https:'].includes(url.protocol)&&!!url.hostname&&!/[\x00-\x1f\x7f]/.test(value);}catch{return false;}
  }
  function openLinkUrl(url,event=null) {
    if(!validLinkUrl(url)){notify('Use a full http or https URL.',true);return;}
    const browserTab=event&&(event.metaKey||event.ctrlKey||event.shiftKey||event.button===1);
    void window.LabExternalLinks?.open(url,{clientOnly:true,popup:!browserTab});
  }
  function linkPropertiesHtml(d) {
    return d.properties.map((p,i)=>`<div class="objective-link-property" data-link-property="${i}"><input aria-label="Property ${i+1} name" data-link-property-name maxlength="80" placeholder="Property" value="${esc(p.name)}"><textarea aria-label="Property ${i+1} value" data-link-property-value rows="1" placeholder="Value">${esc(p.value)}</textarea><button type="button" data-remove-link-property="${i}" aria-label="Remove property ${i+1}">×</button></div>`).join('')||'<p class="objective-purpose">No properties yet.</p>';
  }
  function updateLinkHeader(d) {
    if(activeLinkDraft!==d||!d.node?.isConnected)return;
    d.node.querySelector('[data-link-details-title]').textContent=d.title||'Link details';
    d.node.querySelector('[data-link-details-icon]').innerHTML=window.LabScopeLinks?.icon({kind:'external',url:d.url})||'↗';
    d.node.querySelector('[data-link-details-service]').textContent=window.LabScopeLinks?.serviceFor({kind:'external',url:d.url})?.name||'External link';
    d.node.querySelector('[data-open-objective-link]').disabled=!validLinkUrl(d.url.trim());
    d.node.querySelector('[data-save-objective-link]').disabled=!dirtyLink(d)||d.saving;
    d.node.querySelector('[data-revert-objective-link]').disabled=!!d.saving;
    const status=d.node.querySelector('[data-link-details-status]');status.textContent=d.error||(d.saving?'Saving…':dirtyLink(d)?'Unsaved changes':d.saved?'Saved':'');status.classList.toggle('error',!!d.error);
  }
  function linkChildrenHtml(d,r) {
    return (r.sublinks||[]).map(row=>`<div class="objective-link-child"><button type="button" data-objective-resource="${esc(d.resource)}" data-objective-sublink="${esc(row.id)}">${window.LabScopeLinks?.icon({kind:'external',url:row.url})||'↗'}<span>${esc(row.title)}</span></button><button type="button" data-remove-objective-sublink="${esc(row.id)}" aria-label="Remove ${esc(row.title)}">×</button></div>`).join('')||'<p class="objective-purpose">No sublinks yet.</p>';
  }
  function mountLinkDetails(d,o,r,host) {
    const resource=o.resources.find(row=>row.id===d.resource),worktree=o.worktrees.find(t=>t.id===resource.worktree);
    host.innerHTML=`<section class="objective-working objective-link-details"><header><div class="objective-link-heading"><span data-link-details-icon></span><h2 data-link-details-title></h2></div><button type="button" data-open-objective-link>Open ↗</button></header><p class="objective-purpose">${esc(o.name)}</p><form class="objective-link-editor"><label>Title<input data-objective-link-field="title" required maxlength="512" value="${esc(d.title)}"></label><label>URL<input data-objective-link-field="url" type="url" required maxlength="4096" value="${esc(d.url)}"></label><label>TL;DR<textarea data-objective-link-field="tldr" rows="4" maxlength="8192" placeholder="What this link contains and why it matters">${esc(d.tldr)}</textarea></label><section aria-label="Link metadata"><h3>Metadata</h3><dl class="objective-link-context"><dt>Service</dt><dd data-link-details-service></dd><dt>Scope</dt><dd>${esc(worktree?.label||'Shared across this objective')}</dd></dl><div data-link-properties>${linkPropertiesHtml(d)}</div><button type="button" data-add-link-property>+ Property</button></section><div class="objective-document-actions"><button type="submit" data-save-objective-link>Save</button><button type="button" data-revert-objective-link>Revert</button><span class="objective-document-status" data-link-details-status role="status" aria-live="polite"></span></div></form></section>`;
    d.node=host.querySelector('.objective-link-details');
    const children=document.createElement('section');children.className='objective-link-children';children.innerHTML=`<h3>Sublinks</h3><div data-link-children>${linkChildrenHtml(d,r)}</div><button type="button" data-add-objective-sublink>+ Sublink</button>`;
    d.node.querySelector('form').insertBefore(children,d.node.querySelector('.objective-document-actions'));
    if(d.subLink){const back=document.createElement('button');back.type='button';back.dataset.openParentLink=d.resource;back.textContent='← '+resource.title;d.node.querySelector('.objective-purpose').append(document.createTextNode(' · '),back);}
    activeLinkDraft=d;updateLinkHeader(d);
    d.node.querySelector('form').onsubmit=event=>{event.preventDefault();void saveLinkDetails(d);};
  }
  function linkDraftFor(o,r,subLink=null) {
    const scope={...context()},id=JSON.stringify([key(scope),o.id,r.id,subLink]),target=linkTarget(r,subLink);let d=linkDrafts.get(id);
    if(!d){d={scope,objective:o.id,resource:r.id,subLink};resetLinkDraft(d,target);linkDrafts.set(id,d);}
    else if(!dirtyLink(d)&&!d.saving&&d.base!==linkSnapshot(target))resetLinkDraft(d,target);
    for(const [id,entry] of linkDrafts){if(linkDrafts.size<=32)break;if(entry!==d&&!entry.saving&&!dirtyLink(entry))linkDrafts.delete(id);}
    return d;
  }
  function renderLinkDetails(o,r,subLink=null) {
    const host=showCenter('link');openView.resource=r.id;openView.subLink=subLink;
    mountLinkDetails(linkDraftFor(o,r,subLink),o,linkTarget(r,subLink),host);
  }
  function closeLinkEdit() {
    const modal=linkEditDialog,cleanup=linkEditCleanup;if(!modal)return;
    modal.close();cleanup();
  }
  function openLinkEdit(resourceId,subLink=null) {
    const o=objective(),r=o?.resources.find(r=>r.id===resourceId),target=linkTarget(r,subLink);if(r?.kind!=='link'||!target)return;
    closeLinkEdit();
    const previous=activeLinkDraft,previousNode=previous?.node,d=linkDraftFor(o,r,subLink),modal=document.createElement('dialog');
    modal.className='objective-dialog objective-link-edit-dialog';modal.setAttribute('aria-label','Edit link');
    modal.innerHTML='<header class="objective-link-edit-header"><h2>Edit link</h2><button type="button" data-close-link-edit aria-label="Close link editor">×</button></header><div data-link-edit-body></div>';
    let closed=false;
    const cleanup=()=>{
      if(closed)return;closed=true;closeAssetContextMenu();modal.remove();
      if(linkEditDialog!==modal)return;linkEditDialog=null;linkEditCleanup=null;activeLinkDraft=null;
      if(!previousNode?.isConnected||key(previous.scope)!==key(context()))return;
      const owner=data()?.objectives.find(o=>o.id===previous.objective),saved=owner?.resources.find(r=>r.id===previous.resource),row=linkTarget(saved,previous.subLink);
      if(row)mountLinkDetails(linkDraftFor(owner,saved,previous.subLink),owner,row,previousNode.parentElement);
    };
    linkEditDialog=modal;linkEditCleanup=cleanup;modal.addEventListener('close',cleanup,{once:true});
    document.body.append(modal);mountLinkDetails(d,o,target,modal.querySelector('[data-link-edit-body]'));modal.showModal();
    const field=modal.querySelector('[data-objective-link-field="url"]');field.focus();field.select();
  }
  function refreshLinkDetails() {
    for(const node of dialog?.querySelectorAll('[data-open-task-asset]')||[]){
      const task=tasks().find(t=>t.id===node.dataset.assetTask),asset=task&&taskAssets(task).find(a=>a.id===node.dataset.openTaskAsset),info=asset&&assetInfo(asset);if(!info)continue;
      node.textContent=info.title;node.previousElementSibling.innerHTML=info.icon;node.nextElementSibling?.setAttribute('aria-label','Detach '+info.title);
    }
    const d=activeLinkDraft;if(!d?.node?.isConnected||key(d.scope)!==key(context()))return;
    const o=data()?.objectives.find(o=>o.id===d.objective),r=linkTarget(o?.resources.find(r=>r.id===d.resource),d.subLink);if(!r)return;
    if(!dirtyLink(d)&&!d.saving&&d.base!==linkSnapshot(r)){resetLinkDraft(d,r);mountLinkDetails(d,o,r,d.node.parentElement);}
    updateLinkHeader(d);
    d.node.querySelector('[data-link-children]').innerHTML=linkChildrenHtml(d,r);
  }
  function saveLinkDetails(d) {
    if(!d||d.saving||!dirtyLink(d))return d?.pending;
    let fields;try{fields=linkDraftValues(d);}catch(error){d.error=error.message;updateLinkHeader(d);return;}
    const ui=linkUi(d),base=d.base;d.saving=true;d.error='';updateLinkHeader(d);
    d.pending=change(value=>{
      const r=linkTarget(value.objectives.find(o=>o.id===d.objective)?.resources.find(r=>r.id===d.resource),d.subLink);
      if(!r||linkSnapshot(r)!==base)throw new Error('Link changed elsewhere. Your draft is still here; Revert loads the saved version.');
      return {type:'link-update',objective_id:d.objective,resource_id:d.resource,sub_link_id:d.subLink,...fields};
    },{scope:d.scope}).then(value=>{
      const r=linkTarget(value.objectives.find(o=>o.id===d.objective).resources.find(r=>r.id===d.resource),d.subLink);
      if(linkUi(d)===ui)resetLinkDraft(d,r);else{d.base=linkSnapshot(r);d.baseUi=ui;}
      d.saved=Date.now();
    }).catch(error=>{d.error=error.message;}).finally(()=>{d.saving=false;updateLinkHeader(d);});
    return d.pending;
  }
  async function revertLinkDetails(d) {
    if(!d||d.saving)return;await load(d.scope,true);
    const o=cache.get(key(d.scope))?.objectives.find(o=>o.id===d.objective),r=linkTarget(o?.resources.find(r=>r.id===d.resource),d.subLink);if(!r)return;
    resetLinkDraft(d,r);if(activeLinkDraft===d&&d.node?.isConnected)mountLinkDetails(d,o,r,d.node.parentElement);
  }
  const dirtyDraft=draft=>draft.body!==draft.base;
  function actionLine(draft) {
    const item=draft.actionTarget;if(!item)return -1;
    const lines=draft.body.split(/\r?\n/),line=item.line-1;
    if(lines[line]===item.source)return line;
    // Retained unsaved drafts can have inserted lines. Never highlight a
    // different action merely because its old line number still exists.
    const matches=lines.flatMap((text,index)=>text===item.source?[index]:[]);
    return matches.length===1?matches[0]:-1;
  }
  function highlightedBody(draft) {
    const line=actionLine(draft);if(line<0)return draft.body;
    const lines=draft.body.split(/\r?\n/);
    lines[line]=lines[line].replace(/^(\s*(?:[-*+]|\d+[.)])\s+\[[ xX]\]\s*)(.*)$/,'$1<span class="objective-action-target"></span>$2');
    return lines.join('\n');
  }
  function revealAction(draft) {
    const line=actionLine(draft);if(line<0)return;
    if(draftEditable(draft)){
      const view=draft.input?.view;if(!view)return;
      const row=view.state.doc.line(line+1);
      view.dispatch({selection:{anchor:row.from,head:row.to},scrollIntoView:true});view.focus();
    }else{
      const target=draft.preview.querySelector('.objective-action-target');if(!target)return;
      let parent=target.parentElement;
      while(parent&&parent!==draft.preview){if(parent.tagName==='DETAILS')parent.open=true;parent=parent.parentElement;}
      const row=target.closest('li')||target;row.classList.add('objective-action-highlight');row.tabIndex=-1;
      requestAnimationFrame(()=>{if(activeDraft===draft&&row.isConnected){row.scrollIntoView({block:'center'});row.focus({preventScroll:true});}});
    }
  }
  const draftEditable=draft=>!draft.taskMode||draft.editMode;
  function taskDocumentDraft() {return activeDraft?.taskMode&&activeDraft.node.isConnected&&activeDraft.objective===objective()?.id&&taskFocus()?activeDraft:null;}
  function touchDraftEditing(draft) {
    if(activeDraft!==draft||!draft.taskMode||!draft.editMode)return;
    draft.activity=Date.now();clearTimeout(draft.editTimer);
    draft.editTimer=setTimeout(()=>{
      if(activeDraft!==draft||!draft.editMode)return;
      const remaining=draft.activity+taskEditIdleMs-Date.now();
      if(remaining>0){draft.editTimer=setTimeout(()=>setDraftEditMode(draft,false),remaining);return;}
      setDraftEditMode(draft,false);
    },taskEditIdleMs);
  }
  function setDraftEditMode(draft,edit) {
    if(activeDraft!==draft||!draft.taskMode||!draft.node.isConnected)return;
    draft.editMode=edit;clearTimeout(draft.editTimer);
    if(edit)touchDraftEditing(draft);
    else void(async()=>{if(draft.saving)await draft.pending;await saveDraft(draft);})();
    if(draft.editDialog?.isConnected){
      draft.editDialog.querySelectorAll('input,textarea,select,[type=submit]').forEach(node=>node.disabled=!edit);
      draft.editDialog.querySelector('[role=status]').textContent=edit?'':'View mode · close this dialog and enable Edit to continue.';
    }
    renderDraftSurface(draft);paintTaskClose();
  }
  function draftEditDialog(draft,node) {if(draft?.taskMode){draft.editDialog=node;node._editDraft=draft;node.dataset.documentEditDialog='';}return node;}
  function requireDraftEditing(draft) {if(draft&&(activeDraft!==draft||!draft.node.isConnected||!draftEditable(draft)))throw new Error('Enable Edit mode to make changes.');}
  function draftResource(draft,value=cache.get(key(draft.scope))) {return value?.objectives.find(o=>o.id===draft.objective)?.resources.find(r=>r.id===draft.resource);}
  function draftBody(resource,tab) {return tab?resource?.content?.tabs.find(t=>t.id===tab)?.body:resource?.content?.body;}
  function draftControls(draft) {
    if(activeDraft!==draft||!draft.node.isConnected)return;
    const host=draft.node.closest('.objective-document'),status=host.querySelector('.objective-document-status');
    const editable=draftEditable(draft);
    host.dataset.documentMode=editable?'edit':'view';
    const progress=host.closest('#content')?.querySelector('[data-task-progress]'),task=focusedTask();
    if(progress&&task)progress.innerHTML=window.LabTaskSchedule?.badges(task,draft.body)||'';
    host.querySelector('[data-save-objective-document]').hidden=!editable;
    host.querySelector('[data-save-objective-document]').disabled=!editable||!dirtyDraft(draft)||draft.saving;
    host.querySelector('[data-revert-objective-document]').hidden=!editable;
    host.querySelector('[data-revert-objective-document]').disabled=!editable||draft.saving;
    host.querySelectorAll('[data-rename-objective-resource],[data-add-objective-subtab]').forEach(node=>node.disabled=!editable);
    status.textContent=draft.error||draft.loadingError||(draft.saving?'Saving…':dirtyDraft(draft)?'Unsaved · saves after 10s idle':!editable?'View mode · Cmd/Ctrl-click Markdown to edit':draft.saved?'Saved at '+new Date(draft.saved).toLocaleTimeString():'Click to edit · / for commands');
    status.classList.toggle('error',!!(draft.error||draft.loadingError));
  }
  function scheduleDraft(draft) {
    clearTimeout(draft.timer);
    if(activeDraft!==draft||!dirtyDraft(draft)||draft.error)return;
    draft.timer=setTimeout(()=>void saveDraft(draft),Math.max(0,(draft.edited||Date.now())+10000-Date.now()));
  }
  function saveDraft(draft,manual=false) {
    if(!draft)return Promise.resolve();
    if(draft.saving)return draft.pending;
    if(!dirtyDraft(draft)||draft.error&&!manual)return Promise.resolve();
    const body=draft.body,base=draft.base;
    clearTimeout(draft.timer);draft.saving=true;draft.error='';draftControls(draft);
    draft.pending=change(value=>{
      const resource=draftResource(draft,value);
      if(draftBody(resource,draft.tab)!==base)throw new Error('Document changed elsewhere. Your draft is still here; Revert loads the saved version.');
      return {type:'document',objective_id:draft.objective,resource_id:draft.resource,tab_id:draft.tab,
        document_revision:resource.content.revision,body};
    },{scope:draft.scope}).then(()=>{draft.base=body;draft.saved=Date.now();}).catch(error=>{draft.error=error.message;}).finally(()=>{
      draft.saving=false;draftControls(draft);scheduleDraft(draft);
    });
    return draft.pending;
  }
  function releaseDraft() {
    if(!linkEditDialog)activeLinkDraft=null;
    const draft=activeDraft;if(!draft)return;
    activeDraft=null;clearTimeout(draft.timer);clearTimeout(draft.editTimer);draft.editMode=false;
    // Navigation paints immediately. Capture the outgoing body and retain a
    // newer draft even when its preceding save has not finished yet.
    void (async()=>{if(draft.saving)await draft.pending;await saveDraft(draft);})();
  }
  function mountDraft(o,r,tab,body,host) {
    const scope={...context()},id=JSON.stringify([key(scope),o.id,r.id,tab]);
    let draft=drafts.get(id);
    if(!draft){
      const node=document.createElement('div');node.className='assistant-note-editor objective-note-editor';
      draft={scope,objective:o.id,resource:r.id,tab,base:body,body,node};drafts.set(id,draft);
    }else if(!dirtyDraft(draft)&&!draft.saving&&draft.base!==body){
      draft.base=draft.body=body;draft.syncing=true;if(draft.input)draft.input.value=body;draft.syncing=false;
    }
    draft.taskMode=!!taskFocus();draft.editMode=!draft.taskMode;
    draft.actionTarget=actionTarget?.scope===key(scope)&&actionTarget.task===taskFocus()?.task?actionTarget.item:null;
    activeDraft=draft;host.replaceChildren(draft.node);renderDraftSurface(draft);paintTaskClose();
    draftControls(draft);scheduleDraft(draft);
    for(const [entry,value] of drafts){
      if(drafts.size<=32)break;
      if(value!==activeDraft&&!value.saving&&!dirtyDraft(value)){value.input?.destroy();drafts.delete(entry);}
    }
  }
  function renderDraftSurface(draft) {
    if(activeDraft!==draft||!draft.node.isConnected)return;
    if(!window.marked||!window.DOMPurify||draftEditable(draft)&&!window.LabMarkdownEditor){
      // Resources can open while the lazy editor/parser scripts are still in
      // flight. Rendering the preview also needs Marked and DOMPurify.
      draft.node.textContent='Loading document…';
      draft.loading ||= Promise.resolve().then(()=>bridge.readyContent?.()).then(()=>{
        if(activeDraft!==draft||!draft.node.isConnected)return;
        if(!window.marked||!window.DOMPurify)throw new Error('Could not load Markdown rendering');
        if(draftEditable(draft)&&!window.LabMarkdownEditor)return window.ensureLiveMarkdownEditor();
      }).then(()=>{draft.loading=null;if(activeDraft===draft&&draft.node.isConnected)renderDraftSurface(draft);})
        .catch(error=>{draft.loading=null;draft.loadingError=error.message;if(activeDraft===draft)draft.node.textContent=draft.body;draftControls(draft);});
      draftControls(draft);return;
    }
    draft.loadingError='';
    if(!draftEditable(draft)){
      draft.preview ||= document.createElement('div');draft.preview.className='assistant-markdown objective-document-preview';
      draft.preview.innerHTML=window.LabMarkdown?.render(highlightedBody(draft))??esc(draft.body);
      draft.preview.querySelectorAll('[contenteditable]').forEach(node=>node.removeAttribute('contenteditable'));
      draft.preview.querySelectorAll('input,textarea,select').forEach(node=>node.disabled=true);
      draft.node.replaceChildren(draft.preview);
    }else{
      draft.editorNode ||= document.createElement('div');draft.editorNode.className='assistant-note-editor';draft.node.replaceChildren(draft.editorNode);
      if(!draft.input)draft.input=window.LabMarkdownEditor.create(draft.editorNode,{body:draft.body,
        onChange:text=>{if(draft.syncing||!draftEditable(draft))return;draft.body=text;draft.edited=Date.now();touchDraftEditing(draft);draftControls(draft);scheduleDraft(draft);},
        onSave:()=>draftEditable(draft)&&saveDraft(draft,true)});
      else draft.input.view?.requestMeasure();
    }
    revealAction(draft);
    draftControls(draft);
  }
  async function revertDraft(draft) {
    if(!draft||!draftEditable(draft)||draft.saving)return;
    clearTimeout(draft.timer);await load(draft.scope,true);
    const body=draftBody(draftResource(draft),draft.tab);if(typeof body!=='string')return;
    draft.base=draft.body=body;draft.error='';draft.syncing=true;if(draft.input)draft.input.value=body;draft.syncing=false;renderDraftSurface(draft);
  }
  function form(title,fields,submit,{submitLabel='Save',destructive=false}={}) {
    dialog?.remove();const node=document.createElement('dialog');node.className='objective-dialog';node.innerHTML=`<form><header><h2>${esc(title)}</h2></header>${fields}<footer><button type="button" data-cancel>Cancel</button><button type="submit"${destructive?' class="objective-task-delete"':''}>${esc(submitLabel)}</button></footer><p role="status"></p></form>`;document.body.append(node);dialog=node;window.LabTaskSchedule?.bind(node);node.showModal();node.querySelector('[data-cancel]').onclick=()=>{node.close();node.remove();if(dialog===node)dialog=null;};node.querySelector('form').onsubmit=async e=>{e.preventDefault();const button=node.querySelector('[type=submit]');button.disabled=true;try{await submit(new FormData(e.target));if(node.isConnected){node.close();node.remove();}if(dialog===node)dialog=null;}catch(error){node.querySelector('[role=status]').textContent=error.message;button.disabled=!!node._editDraft&&!draftEditable(node._editDraft);}};return node;
  }
  const input=(label,name,value='',type='text',required=true)=>`<label>${esc(label)}<input name="${name}" type="${type}" value="${esc(value)}" ${required?'required':''}></label>`;
  function newObjective(slot=null) {const d=data();if(!d){const scope=key(context());void load().then(result=>{if(result&&key(context())===scope)newObjective(slot);});return;}form('New objective',input('Name','name')+input('Outcome','purpose','','text',false)+(d.objectives.length?'':'<label><span><input name="import_existing" type="checkbox" checked> Bring current workspace worktrees, files and links</span></label>')+(slot===null&&d.focused.filter(Boolean).length===focusSlots?`<label>Insert at<select name="slot">${d.focused.map((id,i)=>`<option value="${i}">Slot ${i+1} · ${esc(d.objectives.find(o=>o.id===id).name)}</option>`).join('')}</select></label>`:''),async values=>{const result=await change({type:'create',name:values.get('name'),purpose:values.get('purpose'),slot:values.has('slot')?Number(values.get('slot')):slot,import_existing:values.has('import_existing')});selectObjective(result.objectives.at(-1).id);bridge.refreshSidebar?.();});}
  function focusDialog(objectiveId=null,slot=null) {
    const d=data();form('Insert an objective into focus',`<label>Objective<select name="objective">${d.objectives.map(o=>`<option value="${esc(o.id)}">${esc(o.name)}</option>`).join('')}</select></label><label>Insert at<select name="slot">${Array.from({length:focusSlots},(_,i)=>`<option value="${i}">Slot ${i+1} · ${esc(d.objectives.find(o=>o.id===d.focused[i])?.name||'Empty')}</option>`).join('')}</select></label>`,async values=>{
      await placeObjective(values.get('objective'),Number(values.get('slot')));
    });
    if(objectiveId)dialog.querySelector('[name=objective]').value=objectiveId;
    dialog.querySelector('[name=slot]').value=String(slot??Array.from({length:focusSlots},(_,i)=>i).find(i=>!d.focused[i])??0);
  }
  async function placeObjective(id,slot) {
    const scope=key(context());await change({type:'focus',objective_id:id,slot});
    if(scope!==key(context()))return;
    if(openView?.type==='all'){
      if(!data().focused.includes(state().objective)){state().objective=id;persistView();paint();bridge.refreshTerminals?.();}
    }else selectObjective(id);
  }
  function addResource(kind='document') {
    if(kind==='link'){form('Add link',input('Title','title')+input('URL','url','','url')+'<label>TL;DR<textarea name="tldr" rows="3" maxlength="8192"></textarea></label>',async values=>{const o=objective(),result=await change({type:'resource',objective_id:o.id,kind:'link',title:values.get('title'),url:values.get('url'),tldr:values.get('tldr')});openResource(result.objectives.find(row=>row.id===o.id).resources.at(-1).id);});return;}
    form('Add objective resource',`<label>Type<select name="kind"><option value="document">Markdown document</option><option value="notebook">Notebook</option><option value="link">Link</option><option value="file">Existing workspace file</option></select></label>`+input('Name','title')+input('URL (links only)','url','','text',false)+input('Workspace-relative path (existing files only)','path','','text',false),async values=>{const result=await change({type:'resource',objective_id:objective().id,kind:values.get('kind'),title:values.get('title'),url:values.get('url'),path:values.get('path')});openResource(result.objectives.find(o=>o.id===objective().id).resources.at(-1).id);});dialog.querySelector('[name=kind]').value=kind;}
  function addTask(parentId=null) {const o=objective();form(parentId?'New subtask':'New task',input('Task','title')+(window.LabTaskSchedule?.fields()||input('Due date','due','','date',false)),async values=>{await change({type:'task',objective_id:o.id,parent_id:parentId,title:values.get('title'),...(window.LabTaskSchedule?.read(values)||{due:values.get('due')})});renderTasks();});}
  async function deleteTask(taskId) {
    const o=objective(),scope={...context()};
    const action={objective_id:o.id,task_id:taskId,terminal_parents:bridge.taskDeletionHierarchy?.()||{}};
    try{
      // Drain editor saves before reviewing files that may contain siblings.
      for(const draft of drafts.values())if(key(draft.scope)===key(scope)&&draft.objective===o.id){
        clearTimeout(draft.timer);await saveDraft(draft,true);
        if(draft.error||dirtyDraft(draft))throw new Error(draft.error||'Save the task Markdown before deleting it.');
      }
      const response=await fetch('/api/objectives/task-delete-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace_id:scope.workspace_id,vault:scope.vault,action})});
      const review=await response.json();if(!response.ok)throw new Error(review.detail||'Could not review task deletion');
      if(key(context())!==key(scope))return;
      const summary=`<p>Permanently delete <strong>${esc(review.title)}</strong> and its whole task branch?</p><ul>${review.tasks.map(t=>`<li>${esc(t.title)}</li>`).join('')}</ul><p>${review.terminal_ids.length} terminals will close. ${review.asset_count} exclusive assets or document tabs will be deleted.</p>${review.files.length?`<p>Owned files to delete:</p><ul>${review.files.map(path=>`<li>${esc(path)}</li>`).join('')}</ul>`:''}<p>Shared assets, external source files, and worktree folders stay intact. Task associations are removed. This cannot be undone.</p>`;
      form('Delete task · 1 of 2',summary,()=>{
        const confirm=form('Delete task · 2 of 2',`<p>Type <strong>${esc(review.title)}</strong> exactly to confirm permanent deletion.</p><label>Task name<input name="confirm_title" autocomplete="off" spellcheck="false" required></label>`,async values=>{
          if(values.get('confirm_title')!==review.title)throw new Error('Type the exact task name.');
          const result=await change({...action,type:'task-delete',confirmed:true,confirm_title:values.get('confirm_title'),review_token:review.review_token},{scope,expected:review.revision});
          const owner=result.objectives.find(item=>item.id===o.id);
          for(const [id,draft] of drafts)if(key(draft.scope)===key(scope)&&draft.objective===o.id){
            const resource=owner.resources.find(r=>r.id===draft.resource);
            if(!resource||draft.tab&&!resource.content?.tabs.some(t=>t.id===draft.tab)){
              clearTimeout(draft.timer);clearTimeout(draft.editTimer);draft.input?.destroy();drafts.delete(id);if(activeDraft===draft)activeDraft=null;
            }
          }
          for(const [id,draft] of linkDrafts)if(key(draft.scope)===key(scope)&&draft.objective===o.id&&!owner.resources.some(r=>r.id===draft.resource)){
            clearTimeout(draft.timer);linkDrafts.delete(id);if(activeLinkDraft===draft)activeLinkDraft=null;
          }
          if(key(context())===key(scope)){
            if(review.tasks.some(t=>t.id===state().focus?.task))state().focus=null;
            await bridge.taskDeleted?.(review.terminal_ids);renderTasks();bridge.refreshSidebar?.();notify('Task branch deleted.');
          }
        },{submitLabel:'Delete permanently',destructive:true});
        const typed=confirm.querySelector('[name=confirm_title]'),button=confirm.querySelector('[type=submit]');button.disabled=true;
        typed.addEventListener('input',()=>{button.disabled=typed.value!==review.title;});typed.focus();
      },{submitLabel:'Continue'});
    }catch(error){notify(error.message,true);}
  }
  function moveTaskDrop(source,targetId) {
    const o=objective(),scope={...context()},task=tasks(o).find(t=>t.id===source.task_id),target=tasks(o).find(t=>t.id===targetId);
    if(source.scope!==key(scope)||source.objective_id!==o.id||!task)throw new Error('Move a task within this Objective.');
    if(target&&tasks({tasks:[task]}).some(t=>t.id===target.id))throw new Error('A task cannot be moved into itself or its descendants.');
    const move=async(parent,before=null)=>{
      const result=await change({type:'task-move',objective_id:o.id,task_id:task.id,parent_id:parent,before_id:before},{scope});
      if(key(context())!==key(scope))return;
      if(focusedTask()&&openView?.type==='document')paint();else renderTasks();
      bridge.refreshTerminals?.();notify('Task and its terminals moved.');return result;
    };
    if(!target){void move(null).catch(()=>{});return;}
    form('Move '+task.title,`<p>Move this task with its subtasks and terminals.</p><label>Placement<select name="placement"><option value="child">Make subtask of ${esc(target.title)}</option><option value="before">Move above ${esc(target.title)}</option><option value="after">Move below ${esc(target.title)}</option><option value="root">Make top-level task</option></select></label>`,values=>{
      const placement=values.get('placement'),parent=taskParent(target,o);
      if(placement==='child')return move(target.id);
      if(placement==='root')return move(null);
      const siblings=(parent?parent.children:o.tasks).filter(t=>t.id!==task.id),next=siblings[siblings.indexOf(target)+1];
      return move(parent?.id||null,placement==='before'?target.id:next?.id||null);
    });
  }
  async function moveForTerminalDrop(source,destination,{relation,placeBefore}={}) {
    if(!active(context()?.path))return false;
    const binding=terminalTask(source);if(!binding||binding.inherited)return false;
    const target=destination?terminalTask(destination):null;
    if(destination&&!target)return false;
    if(target&&target.objective.id!==binding.objective.id)throw new Error('Move a task within its Objective.');
    const o=binding.objective,task=binding.task,scope={...context()};
    let parent=null,before=null;
    if(target){
      parent=relation==='child'||target.inherited?target.task:taskParent(target.task,o);
      if(relation!=='child'&&!target.inherited){
        const siblings=(parent?parent.children:o.tasks).filter(t=>t.id!==task.id);
        before=placeBefore?target.task.id:siblings[siblings.indexOf(target.task)+1]?.id||null;
      }
    }
    await change({type:'task-move',objective_id:o.id,task_id:task.id,parent_id:parent?.id||null,before_id:before},{scope});
    if(key(context())===key(scope))bridge.refreshTerminals?.();return true;
  }
  function associate(row) {return change({type:'worktree',objective_id:objective().id,path:row.path,label:row.label||row.name||row.path.split('/').pop(),repo:row.projectPath||row.path,branch:row.branch,kind:row.kind||'worktree'}).then(d=>{const o=d.objectives.find(o=>o.id===objective().id);state().tree[o.id]=o.worktrees.at(-1).id;persistView();return o.worktrees.at(-1);});}
  function terminalIdentity(t) {return t.session_id||t.name;}
  function terminalLink(t) {return t.objective_placeholder?{objective_id:t.objective_id,task_id:t.task_id,main:t.main}:data()?.terminal_links[terminalIdentity(t)];}
  function taskTerminalsEnabled() {return data()?.task_terminals===true;}
  function taskTerminalVisible(task,o,wipOnly=bridge?.terminalWipOnly?.()??true) {
    return taskStatus(task)==='in_progress'||!wipOnly||o.id===objective()?.id&&state().terminalAll?.[o.id]===true;
  }
  function terminalMain(t) {
    if(!t||!active(context()?.path))return null;
    const link=terminalLink(t);if(!link)return null;
    if(link.main==='workflow'){
      if(!t.objective_placeholder&&Object.entries(data().terminal_links||{}).find(([,other])=>other.main==='workflow')?.[0]!==terminalIdentity(t))return null;
      return {kind:'workflow',label:'Main · '+(bridge?.workflowName?.()||context().path.split('/').pop()),icon:'🏠'};
    }
    const o=data()?.objectives.find(o=>o.id===link.objective_id);if(!o)return null;
    if(link.task_id||link.resource_id||link.file||link.folder||link.view)return null;
    if(t.objective_placeholder&&link.main!=='objective')return null;
    if(!t.objective_placeholder){
      const candidates=Object.entries(data().terminal_links||{}).filter(([,other])=>other.objective_id===o.id
        &&!other.task_id&&!other.resource_id&&!other.file&&!other.folder&&!other.view);
      const primary=candidates.find(([,other])=>other.main==='objective')||candidates[0];
      if(primary?.[0]!==terminalIdentity(t))return null;
    }
    return {kind:'objective',objective_id:o.id,label:'Main · '+o.name,icon:'🎯'};
  }
  function terminalTask(t) {
    const seen=new Set();let source=t;
    while(source&&!seen.has(terminalIdentity(source))){
      seen.add(terminalIdentity(source));if(terminalMain(source))return null;
      const link=terminalLink(source),o=data()?.objectives.find(o=>o.id===link?.objective_id),task=tasks(o).find(task=>task.id===link?.task_id);
      if(task)return {objective:o,task,inherited:source!==t};
      source=bridge?.parentTerminal?.(source);
    }
    return null;
  }
  function taskForTerminal(t) {const binding=terminalTask(t);return binding?{title:taskDisplayName(binding.task,binding.objective),icon:taskIcon(binding.task,binding.objective),assetIcon:customTaskIcon(binding.task,binding.objective),color:binding.task.terminal_color||null,inherited:binding.inherited,status:taskStatus(binding.task)}:null;}
  function terminalTaskNameHtml(t) {const binding=terminalTask(t);return binding?taskNameHtml(binding.task,binding.objective):null;}
  function terminalWorktreeColor(t) {const binding=terminalTask(t),assigned=binding?taskWorktrees(binding.task,binding.objective):[];return assigned.length===1?assigned[0].color:null;}
  function terminalColor(t) {return terminalWorktreeColor(t);}
  function terminalObjective(t) {const d=data();if(!d?.enabled)return null;const link=terminalLink(t);if(link?.main==='workflow'||link?.view==='workflow')return null;return d.objectives.find(o=>o.id===link?.objective_id)||d.objectives.find(o=>o.worktrees.some(w=>t.linked_scope?.root&&[w.path,w.resolved_path].includes(t.linked_scope.root)||t.cwd&&[w.path,w.resolved_path].includes(t.cwd)))||d.objectives[0];}
  function terminalSessions(sessions,{wipOnly=true}={}) {
    if(!active(context()?.path))return sessions;
    const result=[],seen=new Set();
    const workflow=sessions.find(t=>terminalMain(t)?.kind==='workflow');
    if(workflow){result.push(workflow);seen.add(workflow);}else{
      const logical='workflow-terminal:'+context().workspace_id+':main';
      result.push({name:logical,logical_name:logical,objective_placeholder:true,main:'workflow',label:terminalMain({objective_placeholder:true,main:'workflow'}).label,cwd:context().path});
    }
    const ids=new Set([...data().focused,objective()?.id]);
    for(const t of sessions)if(!wipOnly)ids.add(terminalObjective(t)?.id);
    for(const id of ids){
      const o=data().objectives.find(o=>o.id===id);if(!o)continue;
      const owned=sessions.filter(t=>terminalObjective(t)?.id===id);
      const add=(task=null)=>{
        const matches=owned.filter(t=>{const link=terminalLink(t);return task?link?.task_id===task.id:terminalMain(t)?.kind==='objective';});
        if(matches.length){matches.forEach(t=>{result.push(t);seen.add(t);});return;}
        if(task&&!taskTerminalsEnabled())return;
        const logical='objective-terminal:'+id+':'+(task?.id||'global');
        result.push({name:logical,logical_name:logical,objective_placeholder:true,objective_id:id,task_id:task?.id||null,...(task?{}:{main:'objective'}),
          label:task?taskDisplayName(task,o):'Main · '+o.name,cwd:o.path||context().path+'/objectives/'+id});
      };
      add();tasks(o).forEach(task=>add(task));owned.filter(t=>!seen.has(t)).forEach(t=>{result.push(t);seen.add(t);});
    }
    const all=[...result,...sessions.filter(t=>!seen.has(t))];
    const selectedObjective=objective()?.id;
    const showObjective=state().terminalAll?.[selectedObjective]===true;
    return all.filter(t=>{
      const main=terminalMain(t);
      if(main)return main.kind==='workflow'||main.objective_id===selectedObjective;
      if(!wipOnly||showObjective&&terminalObjective(t)?.id===selectedObjective)return true;
      const binding=terminalTask(t);
      if(binding)return taskTerminalVisible(binding.task,binding.objective,wipOnly);
      const link=terminalLink(t);
      if(link?.view==='workflow'||link?.view==='objective')return true;
      return terminalParentMain(t,selectedObjective);
    });
  }
  function terminalParents(sessions,explicit={}) {
    const parents={...explicit};
    const fixed=new Set(sessions.filter(t=>terminalMain(t)).map(t=>t.logical_name));
    for(const child of Object.keys(parents))if(fixed.has(child))delete parents[child];
    const find=(o,task)=>sessions.find(t=>terminalObjective(t)?.id===o.id&&terminalLink(t)?.task_id===task.id);
    for(const o of data()?.objectives||[])for(const parent of tasks(o)){
      const terminal=find(o,parent);if(!terminal)continue;
      for(const child of parent.children){const sub=find(o,child);if(!sub||parents[sub.logical_name])continue;
        let ancestor=terminal.logical_name;const seen=new Set();while(parents[ancestor]&&!seen.has(ancestor)){seen.add(ancestor);ancestor=parents[ancestor];}
        if(ancestor!==sub.logical_name)parents[sub.logical_name]=terminal.logical_name;
      }
    }
    return parents;
  }
  function terminalParentMain(t,selectedObjective) {
    const seen=new Set();
    while(t&&!seen.has(terminalIdentity(t))){
      seen.add(terminalIdentity(t));t=bridge?.parentTerminal?.(t);
      const main=terminalMain(t);if(main)return main.kind==='workflow'||main.objective_id===selectedObjective;
    }
    return false;
  }
  function terminalExpanded(t) {
    const link=terminalLink(t),o=terminalObjective(t),task=tasks(o).find(task=>task.id===link?.task_id);if(!task)return undefined;
    const selected=focusedTask(),contains=rows=>rows.some(child=>child.id===selected?.id||contains(child.children));
    return o?.id===objective()?.id&&(selected?.id===task.id||contains(task.children));
  }
  const openingTerminals=new Map();
  async function openMainTerminal(kind,objectiveId) {
    if(kind==='objective')return openTaskTerminal(null,objectiveId);
    if(kind!=='workflow'||!active(context()?.path))return;
    const existing=(bridge.sessions?.()||[]).find(t=>terminalMain(t)?.kind==='workflow');
    if(existing)return bridge.activateLinkedTerminal?.([terminalIdentity(existing)]);
    const scope={...context()},selectedObjective=objective()?.id,selectedTask=focusedTask()?.id,openingKey=JSON.stringify([scope,'workflow']);
    if(openingTerminals.has(openingKey))return openingTerminals.get(openingKey);
    const pending=Promise.resolve(bridge.createWorkflowTerminal?.({context:scope})).then(async terminal=>{
      if(terminal&&key(context())===key(scope)&&objective()?.id===selectedObjective&&focusedTask()?.id===selectedTask)
        await bridge.activateLinkedTerminal?.([terminalIdentity(terminal)]);
      return terminal;
    }).finally(()=>openingTerminals.delete(openingKey));openingTerminals.set(openingKey,pending);return pending;
  }
  async function openTaskTerminal(id,objectiveId=objective()?.id,{openTaskView=true}={}) {
    const o=data()?.objectives.find(o=>o.id===objectiveId),task=id?tasks(o).find(task=>task.id===id):null;if(!o||id&&!task)return;
    if(objective()?.id!==o.id)selectObjective(o.id,{activateTerminal:false});
    if(task){if(openTaskView)openTask(task.id);}else selectObjective(o.id,{activateTerminal:false});
    if(task&&!taskTerminalVisible(task,o))return;
    const existing=(bridge.sessions?.()||[]).find(t=>{const link=terminalLink(t);return link?.objective_id===o.id&&(task?link.task_id===task.id:terminalMain(t)?.kind==='objective');});
    if(existing)return bridge.activateLinkedTerminal?.([terminalIdentity(existing)]);
    const launch=terminalLaunchContext(),scope={...context()},openingKey=JSON.stringify([scope,o.id,id]);
    if(openingTerminals.has(openingKey))return openingTerminals.get(openingKey);
    const pending=Promise.resolve(bridge.createTaskTerminal?.(launch,task)).then(async terminal=>{
      const current=objective(),currentTask=tasks(current).find(t=>t.id===id);
      if(terminal&&key(context())===key(scope)&&current?.id===o.id&&(task?focusedTask()?.id===id&&currentTask&&taskTerminalVisible(currentTask,current):!focusedTask()))
        await bridge.activateLinkedTerminal?.([terminalIdentity(terminal)]);
      return terminal;
    }).finally(()=>openingTerminals.delete(openingKey));openingTerminals.set(openingKey,pending);return pending;
  }
  function terminalHtml(sessions,pill,newButton,{arrange=rows=>rows,showAll=false}={}) {
    if(!active(context()?.path))return null;
    const d=data(),current=objective()?.id,rows=sessions.filter(t=>{const main=terminalMain(t);return main?.kind!=='objective'||main.objective_id===current;}).map((t,index)=>({t,index,objective:terminalObjective(t)?.id}));
    let position=0;
    const workflowRows=rows.filter(row=>!row.objective).sort((a,b)=>Number(!!terminalMain(b.t))-Number(!!terminalMain(a.t))).map(row=>row.t);
    const workflow=arrange(workflowRows).map(t=>pill(t,position++)).join('');
    const ids=new Set([...d.focused,current,...rows.filter(row=>showAll||terminalMain(row.t)?.kind==='objective').map(row=>row.objective)]);
    return workflow+[...ids].map(id=>{
      const o=d.objectives.find(o=>o.id===id);if(!o)return '';
      const order=new Map(tasks(o).map((task,index)=>[task.id,index+1]));
      const rank=row=>{
        const link=terminalLink(row.t);
        if(order.has(link?.task_id))return order.get(link.task_id);
        return link&&!link.task_id&&!link.resource_id&&!link.file&&!link.folder?0:Infinity;
      };
      const main=rows.find(row=>row.objective===id&&terminalMain(row.t));
      const mainHtml=main?pill(main.t,position++):'';
      const ranked=rows.filter(row=>row.objective===id&&!terminalMain(row.t)).sort((a,b)=>rank(a)-rank(b)||a.index-b.index);
      const bySession=new Map(ranked.map(row=>[row.t,row]));
      const ordered=arrange(ranked.map(row=>row.t)).map(session=>bySession.get(session)),groups=[];
      // Task hierarchy takes precedence over checkout grouping. Keep spacing
      // only between consecutive runs of sessions from the same folder.
      for(const row of ordered){
        const root=row.t.linked_scope?.root||row.t.cwd||context().path;
        const worktree=o.worktrees.find(w=>w.path===root||w.resolved_path===root);
        const path=worktree?.path||root;
        if(groups.at(-1)?.path!==path)groups.push({path,worktree,items:[]});
        groups.at(-1).items.push(row);
      }
      const terminals=groups.map(({path,worktree,items})=>{
        const contents=items.map(row=>pill(row.t,position++)).join('');
        return contents?`<div class="objective-terminal-worktree" role="group" aria-label="${esc(worktree?.label||(path===context().path?'Objective folder':path.split('/').filter(Boolean).slice(-2).join('/')))}">${contents}</div>`:'';
      }).join('');
      const expanded=showAll||id===current;
      const all=showAll||state().terminalAll?.[id]===true;
      const filterLabel=showAll?'All terminals are shown. Use the terminal menu to restore In progress task terminals.':all?'Show In progress task terminals in this Objective':'Show all terminals in this Objective';
      const filter=id===current?`<button type="button" class="objective-terminal-filter" data-objective-terminals-all="${esc(id)}" aria-pressed="${all}" aria-label="${filterLabel}" title="${filterLabel}"${showAll?' disabled':''}><span aria-hidden="true">☰</span><span class="objective-terminal-filter-label">${showAll?'All shown':all?'Show WIP':'Show all'}</span></button>`:'';
      return `<section class="objective-terminal-group" data-objective-active="${id===current}" style="--objective-color:${esc(o.color)}"><div class="objective-terminal-header"><button type="button" class="objective-terminal-heading" data-select-objective="${esc(id)}" aria-expanded="${expanded}" title="${esc(o.name)}"><span aria-hidden="true">${expanded?'▾':'▸'}</span> ${esc(o.name)}</button>${filter}</div>${mainHtml}<div class="objective-terminal-rows"${expanded?'':' hidden'}>${terminals}</div></section>`;
    }).join('')+newButton;
  }
  function openForTerminal(t) {
    if(terminalMain(t)?.kind==='workflow')return true;
    const binding=terminalTask(t);
    if(binding?.inherited){state().objective=binding.objective.id;openTask(binding.task.id);paint();return true;}
    const link=terminalLink(t),o=terminalObjective(t);if(!o||!link)return false;
    state().objective=o.id;state().view='objective';
    const resource=o.resources.find(r=>r.id===link.resource_id),root=link.folder?.root||link.file?.root||t.linked_scope?.root;
    const w=scopeRows(o).find(w=>w.id===resource?.worktree||[w.path,w.resolved_path].includes(root));
    if(link.folder?.path==='.'&&w&&!link.task_id){selectScope(w);return true;}
    let selected;if(w){state().tree[o.id]=w.id;if(bridge.scopeRoot?.()!==w.path)selected=bridge.selectWorktree?.(w);}persistView();
    if(link.task_id){openTask(link.task_id);}
    else if(link.view==='tasks'||link.folder){
      state().selected=null;renderTasks();
      if(link.folder){const view=openView,scope=key(context());Promise.resolve(selected).then(()=>{if(openView===view&&key(context())===scope)bridge.openFolder?.(link.folder);});}
    }else if(link.resource_id)openResource(link.resource_id,link.tab_id,link.sub_link_id);else if(link.file)bridge.openFile?.(link.file);else renderOverview();
    paint();return true;
  }
  function sidebarTarget(node,o=objective()) {
    if(node.closest?.('[data-objectives-sidebar] [data-select-objective]'))return {};
    const task=node.closest?.('[data-open-task],[data-task-id]');if(task)return {task_id:task.dataset.openTask||task.dataset.taskId};
    const asset=node.closest?.('[data-objective-asset]');if(asset)return JSON.parse(asset.dataset.objectiveAsset);
    const resource=node.closest?.('[data-objective-resource]');if(resource)return {resource_id:resource.dataset.objectiveResource,tab_id:resource.dataset.objectiveTab||null,sub_link_id:resource.dataset.objectiveSublink||null};
    if(node.closest?.('[data-objective-tasks-drop],[data-objectives-sidebar] [data-open-objective-tasks]'))return {view:'tasks'};
    const row=node.closest?.('[data-objective-root],[data-objective-worktree]'),tree=scopeRows(o).find(t=>t.id===(row?.dataset.objectiveRoot||row?.dataset.objectiveWorktree));
    if(tree)return {folder:{root:tree.path,path:'.'}};
    const file=node.closest?.('[data-open-file][data-filepath],[data-entry-kind][data-entry-path]'),target=file&&nativeAssetTarget(file);
    return target?.reference?{file:{root:target.reference.file_root,path:target.reference.path}}:target;
  }
  function linkTerminal(t,target,o=objective()) {
    if(!t)throw new Error('Choose a terminal in this workspace');
    if(terminalMain(t))throw new Error('Main terminals have a fixed workflow or Objective context');
    return change({type:'terminal',objective_id:o.id,session_id:terminalIdentity(t),source:t.document_source,...target}).then(()=>notify('Terminal linked.'));
  }
  function fileDropTarget(transfer) {
    const raw=transfer.getData('application/x-lab-file-context');
    if(raw){const file=JSON.parse(raw);if(!['file','folder'].includes(file.kind)||!file.root?.startsWith('/')||typeof file.path!=='string')throw new Error('Choose a file or folder in this objective');return {[file.kind]:{root:file.root,path:file.path}};}
    const path=JSON.parse(transfer.getData('application/x-lab-file-path'))[0];
    const root=scopeRows().map(t=>t.path).filter(root=>typeof path==='string'&&(path===root||path.startsWith(root.replace(/\/+$/,'')+'/'))).sort((a,b)=>b.length-a.length)[0];
    if(!root)throw new Error('Choose a file in this objective');return {file:{root,path}};
  }
  function closeTaskStatusMenu() {taskStatusMenu?.remove();taskStatusMenu=null;}
  function showTaskStatusMenu(event,row) {
    const o=objective(),task=tasks(o).find(t=>t.id===row.dataset.taskId);if(!task)return;
    event.preventDefault();event.stopImmediatePropagation();closeTaskStatusMenu();
    const scope={...context()},oid=o.id,anchor=row.querySelector('[data-open-task]'),status=taskStatus(task);
    const menu=document.createElement('div');taskStatusMenu=menu;menu.className='objective-task-status-menu';menu.setAttribute('role','menu');menu.setAttribute('aria-label','Status for '+task.title);
    menu.innerHTML=`<div class="objective-task-status-menu-title">${esc(task.title)}</div>`+['done','todo','in_progress','paused','wont_do'].map(s=>`<button type="button" role="menuitemradio" aria-checked="${status===s}" data-set-task-status="${s}"><span class="objective-task-status-icon" data-task-status="${s}" aria-hidden="true">${taskStatuses[s].icon}</span><span>Set to ${taskStatuses[s].label.toLowerCase()}</span></button>`).join('')+`<button type="button" role="menuitem" class="objective-task-delete" data-delete-task>Delete task…</button>`;
    menu.addEventListener('click',e=>{if(e.target.closest('[data-delete-task]')){closeTaskStatusMenu();void deleteTask(task.id);return;}const button=e.target.closest('[data-set-task-status]');if(!button)return;const next=button.dataset.setTaskStatus;closeTaskStatusMenu();void change({type:'task-update',objective_id:oid,task_id:task.id,status:next},{scope,optimistic:d=>{const owner=d?.objectives.find(o=>o.id===oid);if(owner)patchTaskStatus(owner,task.id,next);}}).catch(()=>{});});
    menu.addEventListener('keydown',e=>{
      const rows=[...menu.querySelectorAll('button')],at=rows.indexOf(document.activeElement);
      if(e.key==='Escape'){e.preventDefault();closeTaskStatusMenu();anchor?.focus({preventScroll:true});}
      else if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();rows[e.key==='Home'?0:e.key==='End'?rows.length-1:e.key==='ArrowDown'?(at+1)%rows.length:(at+rows.length-1)%rows.length]?.focus();}
      else if(e.key==='Tab')closeTaskStatusMenu();
    });
    document.body.append(menu);const box=row.getBoundingClientRect(),size=menu.getBoundingClientRect();
    menu.style.left=Math.max(8,Math.min(event.clientX||box.left,innerWidth-size.width-8))+'px';menu.style.top=Math.max(8,Math.min(event.clientY||box.bottom,innerHeight-size.height-8))+'px';
    menu.querySelector('[aria-checked=true]')?.focus({preventScroll:true});
  }
  function closeAssetContextMenu() {assetContextMenu?.remove();assetContextMenu=null;}
  function openAssetContextMenu(event,node,html) {
    event.preventDefault();event.stopImmediatePropagation();closeTaskStatusMenu();closeAssetContextMenu();
    assetContextMenu=document.createElement('div');assetContextMenu.className='objective-asset-context-menu';assetContextMenu.setAttribute('role','menu');assetContextMenu.setAttribute('aria-label','Asset actions');
    assetContextMenu.innerHTML=html;(node.closest('dialog[open]')||document.body).append(assetContextMenu);const box=node.getBoundingClientRect();
    assetContextMenu.style.left=Math.max(8,Math.min(event.clientX||box.left,window.innerWidth-assetContextMenu.offsetWidth-8))+'px';
    assetContextMenu.style.top=Math.max(8,Math.min(event.clientY||box.bottom,window.innerHeight-assetContextMenu.offsetHeight-8))+'px';assetContextMenu.querySelector('button:not(:disabled)')?.focus();return true;
  }
  function linkDetailsMenu(asset) {
    return assetInfo(asset)?.resource?.kind==='link'?`<button type="button" role="menuitem" data-edit-link-details="${esc(JSON.stringify(assetTarget(asset)))}">Edit</button>`:'';
  }
  function showAssetContextMenu(event) {
    if(!active(context()?.path)||!event.target.closest?.('[data-objectives-sidebar],.objective-working,.objective-dialog'))return false;
    const header=event.target.closest('[data-asset-group-header]');
    if(header){const id=header.dataset.assetGroupHeader;return openAssetContextMenu(event,header,`<button type="button" role="menuitem" data-rename-asset-group="${esc(id)}">Rename group…</button>${assetOrderButtons({group_id:id},header)}<button type="button" role="menuitem" data-ungroup-assets="${esc(id)}">Ungroup assets</button>`);}
    const node=event.target.closest('[data-objective-asset],[data-objective-resource],[data-classify-asset],[data-objective-star],[data-open-task-asset]');if(!node)return false;
    const target=node.dataset.classifyAsset||node.dataset.objectiveStar||node.dataset.objectiveAsset;
    const task=node.dataset.openTaskAsset&&tasks().find(t=>t.id===node.dataset.assetTask);
    const asset=node.dataset.openTaskAsset?task&&taskAssets(task).find(a=>a.id===node.dataset.openTaskAsset):target?JSON.parse(target):{resource_id:node.dataset.objectiveResource,...(node.dataset.objectiveTab?{tab_id:node.dataset.objectiveTab}:{}),...(node.dataset.objectiveSublink?{sub_link_id:node.dataset.objectiveSublink}:{})};
    if(!asset)return false;
    if(!assetInfo(asset))return false;
    if(node.dataset.openTaskAsset)return linkDetailsMenu(asset)?openAssetContextMenu(event,node,linkDetailsMenu(asset)):false;
    const json=esc(JSON.stringify(assetTarget(asset))),required=requiredAsset(asset),group=assetGroupFor(asset);
    return openAssetContextMenu(event,node,linkDetailsMenu(asset)+`<button type="button" role="menuitem" data-objective-star="${json}">${isShared(asset)?'Unpin':'Pin above tasks'}</button>${required?'<span class="objective-bucket-empty">Required task details</span>':`<button type="button" role="menuitem" data-group-asset="${json}">Group asset…</button>${group?`<button type="button" role="menuitem" data-remove-asset-group="${json}">Remove from group</button>`:''}${assetOrderButtons(assetTarget(asset),node)}<button type="button" role="menuitem" data-menu-asset="${json}" data-menu-assignment="task">Move to task…</button><button type="button" role="menuitem" data-menu-asset="${json}" data-menu-assignment="objective">Move to Objective…</button><button type="button" role="menuitem" data-menu-asset="${json}" data-menu-bucket="unassigned">Move to Unassigned</button><button type="button" role="menuitem" data-menu-asset="${json}" data-menu-bucket="archive">Archive</button><button type="button" role="menuitem" data-trash-objective-asset="${json}">Trash…</button>`}`);
  }
  document.addEventListener('contextmenu',event=>{if(showAssetContextMenu(event))return;const row=event.target.closest?.('[data-objectives-sidebar] .objective-sidebar-task,.objective-task-row,.objective-task-mode-head');if(row&&active(context()?.path))showTaskStatusMenu(event,row);},true);
  document.addEventListener('keydown',event=>{if(assetContextMenu&&event.target.closest?.('.objective-asset-context-menu')){const rows=[...assetContextMenu.querySelectorAll('button:not(:disabled)')];if(event.key==='Escape'){closeAssetContextMenu();event.preventDefault();}else if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();const i=rows.indexOf(document.activeElement);rows[event.key==='Home'?0:event.key==='End'?rows.length-1:(i+(event.key==='ArrowDown'?1:rows.length-1))%rows.length]?.focus();}return;}if(event.key==='ContextMenu'||event.shiftKey&&event.key==='F10')showAssetContextMenu(event);},true);
  document.addEventListener('pointerdown',event=>{if(!event.target.closest?.('.objective-asset-context-menu'))closeAssetContextMenu();});
  document.addEventListener('scroll',event=>{if(!event.target.closest?.('.objective-asset-context-menu'))closeAssetContextMenu();},true);
  window.addEventListener('resize',closeAssetContextMenu);
  document.addEventListener('keydown',event=>{if(event.key!=='ContextMenu'&&!(event.shiftKey&&event.key==='F10'))return;const row=event.target.closest?.('[data-objectives-sidebar] .objective-sidebar-task,.objective-task-row,.objective-task-mode-head');if(row&&active(context()?.path))showTaskStatusMenu(event,row);},true);
  document.addEventListener('pointerdown',event=>{if(!event.target.closest?.('.objective-task-status-menu'))closeTaskStatusMenu();});
  document.addEventListener('scroll',event=>{if(!event.target.closest?.('.objective-task-status-menu'))closeTaskStatusMenu();},true);
  window.addEventListener('resize',closeTaskStatusMenu);
  function handleClick(e) {
    if(e.target.closest?.('[data-close-objective-task]')){const id=focusedTask()?.id;renderTasks();document.querySelector(`[data-open-task="${id}"]`)?.focus({preventScroll:true});return;}
    const host=e.target.closest?.('[data-objectives-sidebar],.objective-working,.objective-task-mode-head,.objective-dialog,.objective-terminal-group,[data-objective-notebook-controls],.repo-tabs,.objective-switch-menu,.objective-asset-context-menu');
    if(!host)return;
    const node=e.target.closest('button,input,a');if(!node)return;
    if(node.disabled)return;
    if(node.closest('.objective-asset-context-menu'))closeAssetContextMenu();
    if(node.hasAttribute('data-close-link-edit')){closeLinkEdit();return;}
    if(node.hasAttribute('data-edit-link-details')){const asset=JSON.parse(node.dataset.editLinkDetails);openLinkEdit(asset.resource_id,asset.sub_link_id||null);return;}
    if(node.hasAttribute('data-asset-group-toggle')){openAssetGroup(node.closest('[data-asset-group]'),true);return;}
    if(node.hasAttribute('data-asset-group-menu')){showAssetContextMenu(e);return;}
    if(node.hasAttribute('data-group-asset')){groupAsset(JSON.parse(node.dataset.groupAsset));return;}
    if(node.hasAttribute('data-remove-asset-group')){void change({type:'asset-group-member',objective_id:objective().id,...JSON.parse(node.dataset.removeAssetGroup),group_id:null}).catch(()=>{});return;}
    if(node.hasAttribute('data-rename-asset-group')){renameAssetGroup(node.dataset.renameAssetGroup);return;}
    if(node.hasAttribute('data-ungroup-assets')){void change({type:'asset-group-ungroup',objective_id:objective().id,group_id:node.dataset.ungroupAssets}).catch(()=>{});return;}
    if(node.hasAttribute('data-asset-order')){void change({type:'asset-order',objective_id:objective().id,...JSON.parse(node.dataset.assetOrder)}).catch(()=>{});return;}
    if(node.dataset.menuAssignment){classifyAsset(JSON.parse(node.dataset.menuAsset),node.dataset.menuAssignment);return;}
    if(node.dataset.menuBucket){void change({type:'asset-bucket',objective_id:objective().id,...JSON.parse(node.dataset.menuAsset),bucket:node.dataset.menuBucket}).catch(()=>{});return;}
    if(node.hasAttribute('data-objective-star')){const target=JSON.parse(node.dataset.objectiveStar);void change({type:'asset-star',objective_id:objective().id,...target,starred:!isShared(target)}).catch(()=>{});return;}
    if(node.hasAttribute('data-classify-asset')){if(node.classList.contains('objective-asset-menu'))showAssetContextMenu(e);else classifyAsset(JSON.parse(node.dataset.classifyAsset));return;}
    if(node.dataset.acceptAssignment||node.dataset.rejectAssignment){const accept=!!node.dataset.acceptAssignment;void change({type:accept?'accept-assignment':'reject-assignment',objective_id:objective().id,suggestion_id:node.dataset.acceptAssignment||node.dataset.rejectAssignment}).catch(()=>{});return;}
    if(node.hasAttribute('data-trash-objective-asset')){trashAsset(JSON.parse(node.dataset.trashObjectiveAsset));return;}
    if(node.hasAttribute('data-archive-objective-asset')||node.hasAttribute('data-restore-objective-asset')){void change({type:'asset-bucket',objective_id:objective().id,...JSON.parse(node.dataset.archiveObjectiveAsset||node.dataset.restoreObjectiveAsset),bucket:node.hasAttribute('data-archive-objective-asset')?'archive':'unassigned'}).catch(()=>{});return;}
    if(node.hasAttribute('data-show-unassigned')){collapse();Object.assign(overviewState(),{mode:'unassigned',query:''});persistView();renderOverview();return;}
    if(node.hasAttribute('data-task-document-mode')){const draft=taskDocumentDraft();if(draft)setDraftEditMode(draft,node.dataset.taskDocumentMode==='edit');return;}
    if(node.dataset.taskIcon){if(node.closest('.objective-task-mode-head')){const draft=taskDocumentDraft();if(draft&&!draftEditable(draft))return;}e.preventDefault();openTaskIconPicker(node.dataset.taskIcon);return;}
    if(node.dataset.deleteObjectiveTask){void deleteTask(node.dataset.deleteObjectiveTask);return;}
    if(node.dataset.editObjectiveTask){const draft=taskDocumentDraft();if(draft&&!draftEditable(draft))return;const task=tasks().find(t=>t.id===node.dataset.editObjectiveTask);draftEditDialog(draft,form('Edit task',input('Task','title',task.title)+(window.LabTaskSchedule?.fields(task)||input('Due date','due',task.due||'','date',false)),async values=>{requireDraftEditing(draft);await change({type:'task-update',objective_id:objective().id,task_id:task.id,title:values.get('title'),...(window.LabTaskSchedule?.read(values)||{due:values.get('due')})});}));return;}
    if(node.dataset.openAction){if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;e.preventDefault();const task=tasks().find(task=>task.id===node.dataset.openAction),item=task?.action_items?.find(item=>item.line===Number(node.dataset.actionLine));if(item)openTask(task.id,{activateTerminal:true,actionItem:item});return;}
    if(node.dataset.openTask){if(node.tagName==='A'&&(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey))return;e.preventDefault();openTask(node.dataset.openTask,{activateTerminal:true});return;}
    if(node.dataset.scheduleTask){const o=objective(),scope={...context()},task=tasks(o).find(t=>t.id===node.dataset.scheduleTask);window.LabTaskSchedule?.edit(task,values=>change({type:'task-update',objective_id:o.id,task_id:task.id,...values},{scope}));return;}
    if(node.dataset.taskAssets){openTaskAssets(node.dataset.taskAssets);return;}
    if(node.dataset.removeTaskAsset){const id=node.dataset.assetTask;void change({type:'task-remove-asset',objective_id:objective().id,task_id:id,asset_id:node.dataset.removeTaskAsset}).then(()=>openTaskAssets(id)).catch(()=>{});return;}
    if(node.dataset.openTaskAsset){const task=tasks().find(t=>t.id===node.dataset.assetTask),asset=task&&taskAssets(task).find(a=>a.id===node.dataset.openTaskAsset);if(asset){const info=assetInfo(asset);if(info?.resource?.kind==='link'){openLinkUrl(info.reference,e);return;}dialog?.remove();dialog=null;openTask(task.id);openAsset(asset,e);}return;}
    if(node.hasAttribute('data-objective-asset')&&!node.dataset.objectiveResource){openAsset(JSON.parse(node.dataset.objectiveAsset),e);return;}
    if(e.target.closest('[data-toggle-objective-switch]')){switchMenu?closeSwitchMenu():showSwitchMenu();return;}
    if(node.hasAttribute('data-choose-objective-slot')){closeSwitchMenu();showAll();data()?.objectives.length?focusDialog(null,Number(node.dataset.chooseObjectiveSlot)):newObjective(Number(node.dataset.chooseObjectiveSlot));return;}
    if(node.dataset.objectiveTerminalsAll){
      const id=node.dataset.objectiveTerminalsAll;if(id!==objective()?.id)return;
      const focused=document.activeElement===node,s=state();s.terminalAll||={};s.terminalAll[id]=!s.terminalAll[id];persistView();bridge.refreshTerminals?.();
      if(focused)document.querySelector(`[data-objective-terminals-all="${CSS.escape(id)}"]`)?.focus({preventScroll:true});return;
    }
    if(node.dataset.selectObjective){const fromMenu=!!node.closest('.objective-switch-menu');selectObjective(node.dataset.selectObjective);if(fromMenu)document.querySelector('[data-current-objective]')?.focus({preventScroll:true});return;}
    if(node.hasAttribute('data-all-objectives')){showAll();return;}
    if(node.hasAttribute('data-objective-slot')){data()?.objectives.length?focusDialog(null,Number(node.dataset.objectiveSlot)):newObjective(Number(node.dataset.objectiveSlot));return;}
    if(node.dataset.libraryObjective){data().focused.includes(node.dataset.libraryObjective)?selectObjective(node.dataset.libraryObjective):focusDialog(node.dataset.libraryObjective);return;}
    if(node.dataset.placeObjective){focusDialog(node.dataset.placeObjective);return;}
    if(node.hasAttribute('data-new-objective')){newObjective();return;}
    if(node.hasAttribute('data-focus-objective')){focusDialog();return;}
    if(node.hasAttribute('data-fold-worktrees')){if(state().worktreesOpen)foldWorktrees();else{state().worktreesOpen=true;paint();}document.querySelector('[data-fold-worktrees]')?.focus({preventScroll:true});return;}
    if(node.hasAttribute('data-open-objective-tasks')){collapse();renderTasks();return;}
    if(node.dataset.objectiveResource){const r=objective()?.resources.find(r=>r.id===node.dataset.objectiveResource),sub=node.dataset.objectiveSublink||null;e.preventDefault();if(r?.kind==='link')openLinkUrl(linkTarget(r,sub)?.url,e);else openResource(node.dataset.objectiveResource,node.dataset.objectiveTab||null,sub);return;}
    if(node.dataset.openParentLink){if(node.closest('.objective-link-edit-dialog'))openLinkEdit(node.dataset.openParentLink);else openResource(node.dataset.openParentLink);return;}
    if(node.hasAttribute('data-add-objective-sublink')){const d=activeLinkDraft;form('Add sublink',input('Title','title')+input('URL','url','','url'),values=>change({type:'link-sublink',objective_id:d.objective,resource_id:d.resource,parent_id:d.subLink,title:values.get('title'),url:values.get('url')},{scope:d.scope}));return;}
    if(node.dataset.removeObjectiveSublink){const d=activeLinkDraft;void change({type:'link-remove-sublink',objective_id:d.objective,resource_id:d.resource,sub_link_id:node.dataset.removeObjectiveSublink},{scope:d.scope}).catch(()=>{});return;}
    if(node.hasAttribute('data-open-objective-link')){openLinkUrl(activeLinkDraft.url.trim(),e);return;}
    if(node.hasAttribute('data-revert-objective-link')){void revertLinkDetails(activeLinkDraft);return;}
    if(node.hasAttribute('data-add-link-property')){const d=activeLinkDraft;d.properties.push({name:'',value:''});d.node.querySelector('[data-link-properties]').innerHTML=linkPropertiesHtml(d);updateLinkHeader(d);d.node.querySelector('.objective-link-property:last-child input').focus();return;}
    if(node.hasAttribute('data-remove-link-property')){const d=activeLinkDraft;d.properties.splice(Number(node.dataset.removeLinkProperty),1);d.node.querySelector('[data-link-properties]').innerHTML=linkPropertiesHtml(d);updateLinkHeader(d);return;}
    if(node.dataset.revealResource){const id=node.dataset.revealResource;if(state().revealed.has(id))state().revealed.delete(id);else state().revealed.add(id);paint();return;}
    if(node.dataset.pinResource){const id=node.dataset.pinResource,tab=node.dataset.pinTab,pins=state().pins[id]||[];state().pins[id]=pins.includes(tab)?pins.filter(t=>t!==tab):[...pins,tab];persistView();paint();return;}
    if(node.dataset.selectWorktree){selectScope(scopeRows().find(t=>t.id===node.dataset.selectWorktree));return;}
    if(node.hasAttribute('data-associate-worktree')){collapse();bridge.addWorktree?.(node);return;}
    if(node.dataset.addResource){addResource(node.dataset.addResource);return;}
    if(node.hasAttribute('data-new-objective-task')){addTask();return;}
    if(node.dataset.addSubtask){addTask(node.dataset.addSubtask);return;}
    if(node.dataset.taskDocument){openTask(node.dataset.taskDocument,{activateTerminal:true});return;}
    if(node.hasAttribute('data-objective-settings')){const o=objective();form('Objective settings',input('Name','name',o.name)+input('Outcome','purpose',o.purpose,'text',false),v=>change({type:'settings',objective_id:o.id,name:v.get('name'),purpose:v.get('purpose')}));return;}
    if(node.dataset.renameObjectiveResource){const draft=activeDraft;if(draft&&!draftEditable(draft))return;const r=objective().resources.find(r=>r.id===node.dataset.renameObjectiveResource),tab=r.kind==='document'&&openView?.resource===r.id?openView.tab:null;draftEditDialog(draft,form(tab?'Rename subtab':'Rename resource',input('Name','title',r.content?.tabs?.find(t=>t.id===tab)?.title||r.title),async v=>{requireDraftEditing(draft);await change({type:'rename',objective_id:objective().id,resource_id:r.id,tab_id:tab,title:v.get('title')});openResource(r.id,tab);}));return;}
    if(node.dataset.addObjectiveSubtab){const draft=activeDraft;if(draft&&!draftEditable(draft))return;draftEditDialog(draft,form('New document subtab',input('Name','title'),async v=>{requireDraftEditing(draft);await change({type:'subtab',objective_id:objective().id,resource_id:node.dataset.addObjectiveSubtab,title:v.get('title'),body:''});openResource(node.dataset.addObjectiveSubtab);}));return;}
    if(node.hasAttribute('data-save-objective-document')&&activeDraft&&draftEditable(activeDraft))void saveDraft(activeDraft,true);
    if(node.hasAttribute('data-revert-objective-document'))void revertDraft(activeDraft);
  }
  document.addEventListener('click',event=>{
    if(event.button!==0||!event.metaKey&&!event.ctrlKey)return;
    const draft=taskDocumentDraft();if(!draft?.node.contains(event.target))return;
    event.preventDefault();event.stopImmediatePropagation();setDraftEditMode(draft,!draft.editMode);
  },true);
  document.addEventListener('click',handleClick);
  function dismissWorktreeNavigation(event) {
    if(!active(context()?.path)||!state().worktreesOpen||event.target.closest?.('.objective-worktree-navigation'))return;
    state().worktreesOpen=false;
    // Keep the clicked row mounted and retain the checkout's browsing context.
    const navigation=document.querySelector('.objective-worktree-navigation'),toggle=navigation?.querySelector('[data-fold-worktrees]');
    if(navigation)navigation.querySelector('.objective-worktrees').hidden=true;
    if(toggle){toggle.setAttribute('aria-expanded','false');toggle.innerHTML=`▸ Worktrees <small>${scopeRows().length}</small>`;}
  }
  document.addEventListener('click',dismissWorktreeNavigation,true);
  for(const type of ['pointerdown','keydown','input','scroll'])document.addEventListener(type,event=>{
    const draft=taskDocumentDraft();
    if(draft&&(event.target.closest?.('.objective-document,.objective-task-mode-head,[data-document-edit-dialog]')
      ||type==='scroll'&&event.target.contains?.(draft.node)))touchDraftEditing(draft);
  },true);
  document.addEventListener('mouseover',event=>{
    const target=event.target.closest?.('[data-current-objective],.objective-switch-menu');
    if(target){clearTimeout(switchTimer);if(target.hasAttribute('data-current-objective'))showSwitchMenu();}
  });
  document.addEventListener('mouseout',event=>{
    if(event.target.closest?.('[data-current-objective],.objective-switch-menu')&&!event.relatedTarget?.closest?.('[data-current-objective],.objective-switch-menu')){clearTimeout(switchTimer);switchTimer=setTimeout(closeSwitchMenu,180);}
  });
  document.addEventListener('pointerdown',event=>{if(!event.target.closest?.('[data-current-objective],.objective-switch-menu'))closeSwitchMenu();});
  document.addEventListener('keydown',event=>{
    const anchor=event.target.closest?.('[data-current-objective]'),menu=event.target.closest?.('.objective-switch-menu');
    if(event.key==='Escape'&&switchMenu){closeSwitchMenu();document.querySelector('[data-current-objective]')?.focus();event.preventDefault();return;}
    if(!anchor&&!menu)return;
    if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){
      event.preventDefault();showSwitchMenu();const rows=[...switchMenu.querySelectorAll('button')],current=rows.indexOf(document.activeElement);
      rows[event.key==='Home'?0:event.key==='End'?rows.length-1:event.key==='ArrowDown'?(current+1)%rows.length:current<0?rows.length-1:(current+rows.length-1)%rows.length]?.focus();
    }else if(anchor&&event.key==='Escape')closeSwitchMenu();
  });
  window.addEventListener('resize',()=>{closeSwitchMenu();scheduleTaskClosePosition();});
  window.addEventListener('scroll',scheduleTaskClosePosition,true);
  document.addEventListener('scroll',event=>{if(switchMenu&&event.target.matches?.('.repo-tabs'))closeSwitchMenu();},true);
  document.addEventListener('click',event=>{
    if(active(context()?.path)&&event.target.closest?.('#sidebar,.repo-tabs,#termSessionList')
      &&!event.target.closest('[data-objectives-sidebar],.objective-tab,[data-objective-terminals-all]')){
      releaseDraft();collapse();state().selected=null;if(event.target.closest('[data-open-file],#termSessionList .sess')){state().view='objective';persistView();}paint();
    }
  },true);
  document.addEventListener('input',event=>{
    const node=event.target,d=activeLinkDraft;
    if(node.hasAttribute('data-objective-overview-search')){overviewState().query=node.value;persistView();paintOverviewResults();return;}
    if(d&&node.closest('.objective-link-details')===d.node){
      if(node.hasAttribute('data-objective-link-field'))d[node.dataset.objectiveLinkField]=node.value;
      else if(node.closest('[data-link-property]')){const item=d.properties[Number(node.closest('[data-link-property]').dataset.linkProperty)];item[node.hasAttribute('data-link-property-name')?'name':'value']=node.value;}
      d.error='';updateLinkHeader(d);return;
    }
    if(!node.matches('[data-objective-search],[data-objective-filter],[data-objective-status-filter]'))return;
    state()[node.hasAttribute('data-objective-search')?'query':node.hasAttribute('data-objective-filter')?'filter':'statusFilter']=node.value;paintLibrary();
  });
  document.addEventListener('change',async e=>{const node=e.target;if(node.disabled)return;if(node.hasAttribute('data-objective-overview-mode')){overviewState().mode=node.value;persistView();paintOverviewResults();return;}if(!node.matches('[data-task-done],[data-task-due]'))return;const o=objective(),id=node.dataset.taskDone||node.dataset.taskDue,patch=node.dataset.taskDone?{done:node.checked}:{due:node.value};const scope={...context()},draft=taskDocumentDraft();if(patch.done&&draft&&draftEditable(draft)){await saveDraft(draft,true);if(draft.error||dirtyDraft(draft)){node.checked=false;notify(draft.error||'Save the task’s Markdown before completing it',true);return;}}change({type:'task-update',objective_id:o.id,task_id:id,...patch},{scope,optimistic:d=>{const owner=d.objectives.find(item=>item.id===o.id);if('done'in patch)patchTaskStatus(owner,id,patch.done?'done':'todo');else Object.assign(tasks(owner).find(t=>t.id===id),patch);}}).catch(()=>{});});
  document.addEventListener('dragstart',e=>{
    const project=e.target.closest?.('[data-drag-objective],.objective-tab[data-select-objective]');
    if(project){
      const id=project.dataset.dragObjective||project.dataset.selectObjective;e.dataTransfer.setData(objectiveMime,JSON.stringify({scope:key(context()),objective_id:id}));e.dataTransfer.effectAllowed='all';
      try{
      const o=data()?.objectives.find(o=>o.id===id),payload=objectiveContext(o);
      if(!dragReference(e.dataTransfer,window.LabTaskContext.references(payload)))throw new Error('Unavailable reference');
      e.dataTransfer.setData(window.LabTaskContext.mime,JSON.stringify(payload));e.dataTransfer.setData('text/plain',window.LabTaskContext.format(payload));e.dataTransfer.effectAllowed='all';
    }catch{notify('Some Objective references are unavailable. Check its assets before passing it to the agent.',true);}return;}
    const o=objective(),taskNode=e.target.closest?.('[data-open-task]'),task=taskNode&&tasks(o).find(t=>t.id===taskNode.dataset.openTask);
    if(task){e.dataTransfer.setData(taskMoveMime,JSON.stringify({scope:key(context()),objective_id:o.id,task_id:task.id}));try{const payload=taskContext(task,o),prompt=window.LabTaskContext.format(payload);if(!dragReference(e.dataTransfer,window.LabTaskContext.references(payload)))throw new Error('Unavailable reference');e.dataTransfer.setData(window.LabTaskContext.mime,JSON.stringify(payload));e.dataTransfer.setData('text/plain',prompt);e.dataTransfer.setData(resourceMime,JSON.stringify({scope:key(context()),objective_id:o.id,task_id:task.id}));e.dataTransfer.effectAllowed='all';}catch{e.dataTransfer.effectAllowed='move';}return;}
    const assetNode=e.target.closest?.('[data-objective-asset]');if(assetNode&&!assetNode.dataset.objectiveResource){const asset=JSON.parse(assetNode.dataset.objectiveAsset);if(dragReference(e.dataTransfer,assetInfo(asset)?.reference))e.dataTransfer.setData(resourceMime,JSON.stringify({scope:key(context()),objective_id:o.id,...assetTarget(asset)}));else e.preventDefault();return;}
    const row=e.target.closest?.('[data-objective-resource]');
    if(row&&o){const resource=o.resources.find(r=>r.id===row.dataset.objectiveResource);if(!dragReference(e.dataTransfer,resourceReference(resource,row.dataset.objectiveTab,row.dataset.objectiveSublink))) {e.preventDefault();return;}e.dataTransfer.setData(resourceMime,JSON.stringify({scope:key(context()),objective_id:o.id,resource_id:row.dataset.objectiveResource,tab_id:row.dataset.objectiveTab||null,sub_link_id:row.dataset.objectiveSublink||null}));return;}
    const folder=e.target.closest?.('[data-select-worktree]');if(folder){const tree=scopeRows(o).find(t=>t.id===folder.dataset.selectWorktree);if(dragReference(e.dataTransfer,tree?.path))e.dataTransfer.setData(resourceMime,JSON.stringify({scope:key(context()),objective_id:o.id,folder:{root:tree.path,path:'.'}}));return;}
    if(o&&e.target.closest?.('[data-objectives-sidebar] [data-open-objective-tasks]')){
      const documents=[...new Set(o.tasks.map(t=>t.document_id))].map(id=>o.resources.find(r=>r.id===id)),resource=documents[0];
      // Empty lists still have an actual source: the objective's task registry.
      const manifest=o.manifest_path||context().path+'/.lab/objectives.json#objective='+encodeURIComponent(o.id);
      const reference=documents.length===1?resourceReference(resource):manifest+(manifest.includes('#')?'&':'#')+'view=tasks';
      if(dragReference(e.dataTransfer,reference))e.dataTransfer.setData(resourceMime,JSON.stringify({scope:key(context()),objective_id:o.id,view:'tasks'}));
    }
  });
  document.addEventListener('dragover',e=>{const slot=e.target.closest?.('[data-objective-slot]');if(slot&&e.dataTransfer.types.includes(objectiveMime)){e.preventDefault();e.dataTransfer.dropEffect='move';slot.classList.add('objective-drop-target');}},true);
  document.addEventListener('dragleave',e=>e.target.closest?.('[data-objective-slot]')?.classList.remove('objective-drop-target'));
  document.addEventListener('dragend',()=>document.querySelectorAll('.objective-drop-target').forEach(n=>n.classList.remove('objective-drop-target')));
  const linkDropSelector='[data-asset-group-header],[data-task-id],[data-task-icon],[data-objective-asset],[data-objective-resource],[data-objective-root],[data-objective-worktree],[data-objective-bucket],.objective-archive,[data-objectives-sidebar] [data-select-objective],[data-objective-tasks-drop],[data-objectives-sidebar] [data-open-objective-tasks],#sidebar [data-entry-kind],[data-open-file][data-filepath],#termSessionList .sess';
  const taskMoveTarget='.objective-sidebar-task,.objective-task-row,[data-open-objective-tasks]';
  document.addEventListener('dragover',event=>{
    if(!active(context()?.path)||!event.dataTransfer.types.includes(taskMoveMime))return;
    const target=event.target.closest?.('[data-objective-tasks-drop]')||event.target.closest?.(taskMoveTarget);if(!target)return;
    event.preventDefault();event.stopImmediatePropagation();event.dataTransfer.dropEffect='move';target.classList.add('objective-drop-target');
  },true);
  document.addEventListener('drop',event=>{
    if(!active(context()?.path))return;const raw=event.dataTransfer.getData(taskMoveMime),target=event.target.closest?.('[data-objective-tasks-drop]')||event.target.closest?.(taskMoveTarget);if(!raw||!target)return;
    event.preventDefault();event.stopImmediatePropagation();target.classList.remove('objective-drop-target');
    try{moveTaskDrop(JSON.parse(raw),target.dataset.taskId);}catch(error){notify(error.message,true);}
  },true);
  document.addEventListener('dragover',e=>{if(!active(context()?.path))return;const draft=taskDocumentDraft();if(e.target.closest?.('.objective-task-mode-head')&&draft&&!draftEditable(draft)){e.preventDefault();e.stopImmediatePropagation();e.dataTransfer.dropEffect='none';return;}const target=e.target.closest?.(linkDropSelector);if(e.dataTransfer.types.includes('application/x-lab-terminal')&&e.target.closest('#content,.assistant-inline-host')&&!e.target.closest('#sidebar')){e.preventDefault();e.stopImmediatePropagation();e.dataTransfer.dropEffect='none';return;}if(target&&[resourceMime,documentMime,'application/x-lab-file-path','application/x-lab-terminal',...(target.classList.contains('sess')?[objectiveMime]:[]),...(target.closest('[data-task-id],[data-objective-bucket]')?['text/uri-list','application/x-lab-reference']:[])].some(m=>e.dataTransfer.types.includes(m))){e.preventDefault();e.dataTransfer.dropEffect='link';const row=target.closest('[data-objective-tasks-drop]')||target;if(row.hasAttribute('data-task-id')||row.hasAttribute('data-objective-tasks-drop')||row.hasAttribute('data-asset-group-header'))row.classList.add('objective-drop-target');}},true);
  document.addEventListener('dragleave',e=>{const row=e.target.closest?.('[data-asset-group-header],[data-task-id],[data-objective-tasks-drop]');if(row&&!row.contains(e.relatedTarget))row.classList.remove('objective-drop-target');});
  document.addEventListener('drop',e=>{
    const draft=taskDocumentDraft();if(e.target.closest?.('.objective-task-mode-head')&&draft&&!draftEditable(draft)){e.preventDefault();e.stopImmediatePropagation();return;}
    if(active(context()?.path)&&e.target.closest?.('#termSessionList [data-terminal-main]')){e.preventDefault();e.stopImmediatePropagation();notify('Main terminals have a fixed workflow or Objective context',true);return;}
    const project=e.dataTransfer.getData(objectiveMime),slot=e.target.closest?.('[data-objective-slot]');
    if(project&&slot){e.preventDefault();e.stopImmediatePropagation();slot.classList.remove('objective-drop-target');try{const item=JSON.parse(project);if(item.scope!==key(context()))throw new Error('Choose an objective in this workspace');void placeObjective(item.objective_id,Number(slot.dataset.objectiveSlot)).catch(()=>{});}catch(error){notify(error.message,true);}return;}
    if(project&&active(context()?.path)&&e.target.closest?.('#termSessionList .sess')){
      e.preventDefault();e.stopImmediatePropagation();try{const item=JSON.parse(project);if(item.scope!==key(context()))throw new Error('Choose an Objective in this workspace');const o=data().objectives.find(o=>o.id===item.objective_id);if(!o)throw new Error('Objective not found');void linkTerminal(bridge.session?.(e.target.closest('#termSessionList .sess').dataset.name),{},o).catch(()=>{});}catch(error){notify(error.message,true);}return;
    }
    if(project||!active(context()?.path))return;const target=e.target.closest?.(linkDropSelector);if(!target)return;
    const raw=e.dataTransfer.getData(resourceMime),assistant=e.dataTransfer.getData(documentMime),file=e.dataTransfer.getData('application/x-lab-file-path'),terminal=e.dataTransfer.getData('application/x-lab-terminal'),external=target.closest('[data-task-id],[data-objective-bucket]')&&(e.dataTransfer.getData('text/uri-list')||e.dataTransfer.getData('application/x-lab-reference'));if(!raw&&!assistant&&!file&&!terminal&&!external)return;
    if(terminal&&target.classList.contains('sess')&&!raw&&!assistant&&!file)return;
    e.preventDefault();e.stopImmediatePropagation();
    target.closest('[data-objective-tasks-drop]')?.classList.remove('objective-drop-target');
    const groupHeader=target.closest('[data-asset-group-header]');
    if(groupHeader){
      groupHeader.classList.remove('objective-drop-target');
      try{
        if(!raw||terminal)throw new Error('Drop an existing Objective asset onto the group');
        const {scope,...item}=JSON.parse(raw);
        if(scope!==key(context())||item.objective_id!==objective().id||(!item.resource_id&&!item.folder)||item.task_id||item.view)throw new Error('Choose an asset in this Objective');
        void change({type:'asset-group-member',...item,group_id:groupHeader.dataset.assetGroupHeader}).catch(()=>{});
      }catch(error){notify(error.message,true);}
      return;
    }
    if(terminal&&!target.closest('#sidebar')&&!target.classList.contains('sess'))return;
    if(terminal&&target.closest('[data-objective-tasks-drop]')){
      const session=bridge.session?.(terminal);
      void moveForTerminalDrop(session,null).then(moved=>moved||linkTerminal(session,{view:'tasks'})).catch(error=>notify(error.message,true));return;
    }
    // A worktree remains a scope drop target even when its row lives in a bucket.
    const worktree=target.closest('[data-objective-worktree]');
    if(worktree&&!terminal&&(raw||assistant)){try{
      if(raw){const {scope,...item}=JSON.parse(raw);if(scope!==key(context())||item.objective_id!==objective().id)throw new Error('Choose an asset in this objective');if(item.resource_id){void change({type:'scope',...item,worktree:worktree.dataset.objectiveWorktree}).catch(()=>{});return;}}
      else {const ref=JSON.parse(assistant);void change({type:'resource',objective_id:objective().id,kind:'assistant',title:ref.title||'Assistant document',document_id:ref.document_id,assistant_root:ref.assistant_root,worktree:worktree.dataset.objectiveWorktree}).catch(()=>{});return;}
    }catch(error){notify(error.message,true);return;}}
    const bucket=target.closest('[data-objective-bucket]'),bucketId=bucket?.dataset.objectiveBucket;
    const taskNode=target.closest('[data-task-id]');
    if(taskNode||!terminal&&(bucket||target.closest('.objective-archive'))){taskNode?.classList.remove('objective-drop-target');const id=taskNode?.dataset.taskId||focusedTask()?.id;try{
      if(terminal){void linkTerminal(bridge.session?.(terminal),{task_id:id,rename_to_task:true}).catch(()=>{});return;}
      let item;if(raw){const {scope,...source}=JSON.parse(raw);if(scope!==key(context())||source.objective_id!==objective().id)throw new Error('Choose an asset in this objective');if(source.task_id||source.view)throw new Error('Drop a document, notebook, link or folder onto a task');item=source;}
      else if(assistant){const ref=JSON.parse(assistant);item={reference:{...ref,kind:'assistant',title:ref.title||'Assistant document'}};}
      else if(file){const source=fileDropTarget(e.dataTransfer),scope=scopeRows().find(t=>[t.path,t.resolved_path].includes(source.file?.root));item=source.folder?source:{reference:{kind:'file',title:source.file.path.split('/').pop(),file_root:source.file.root,path:source.file.path,worktree:scope&&!scope.fixed?scope.id:null}};}
      else if(external){let urls;try{urls=JSON.parse(external);}catch{urls=external.split(/\r?\n/).filter(line=>line&&!line.startsWith('#'));}if(!Array.isArray(urls)||urls.length!==1||!validLinkUrl(urls[0]))throw new Error('Drop one full http or https link');item={reference:{kind:'link',title:new URL(urls[0]).hostname,url:urls[0]}};}
      if(item){
        const destination=taskNode?'task':target.closest('.objective-archive')?'archive':bucketId;
        if(destination==='tasks'||destination==='task'&&!id)throw new Error('Drop the asset onto a task');
        if(destination==='task'&&item.folder?.path==='.'&&state().worktreeBrowse&&!state().worktreeBrowse.focus)state().worktreeBrowse.focus={objective:objective().id,task:id,mode:'focus'};
        void change({...item,type:destination==='task'?'task-asset':'asset-bucket',objective_id:objective().id,...(destination==='task'?{task_id:id,choose_icon:!!target.closest('[data-task-icon]')}:{bucket:destination})}).then(()=>{if(dialog?.open&&dialog.querySelector('[data-task-id]')?.dataset.taskId===id)openTaskAssets(id);notify(destination==='task'?'Asset attached to task.':'Asset moved.');}).catch(()=>{});
      }
    }catch(error){notify(error.message,true);}return;}
    try{if(raw){const {scope,...item}=JSON.parse(raw);if(scope!==key(context())||item.objective_id!==objective().id)throw new Error('Choose a resource in this objective');if(target.classList.contains('sess'))linkTerminal(bridge.session?.(target.dataset.name),item).catch(()=>{});else if(item.resource_id&&!target.hasAttribute('data-open-objective-tasks'))change({type:'scope',...item,worktree:target.dataset.objectiveWorktree||null}).catch(()=>{});}
      else if(assistant){const ref=JSON.parse(assistant),o=objective();change({type:'resource',objective_id:o.id,kind:'assistant',title:ref.title||'Assistant document',document_id:ref.document_id,assistant_root:ref.assistant_root,worktree:target.dataset.objectiveWorktree||null}).then(d=>{if(target.classList.contains('sess'))return change({type:'terminal',objective_id:o.id,session_id:terminalIdentity(bridge.session(target.dataset.name)),source:bridge.session(target.dataset.name).document_source,resource_id:d.objectives.find(item=>item.id===o.id).resources.at(-1).id});}).catch(()=>{});}
      else if(file&&target.classList.contains('sess'))linkTerminal(bridge.session?.(target.dataset.name),fileDropTarget(e.dataTransfer)).catch(()=>{});
      else if(terminal){const item=sidebarTarget(target);if(item)linkTerminal(bridge.session?.(terminal),item).catch(()=>{});}
    }catch(error){notify(error.message,true);}
  },true);
  window.LabObjectives={connect(adapter){bridge=adapter;startRefreshing();},load,active,sidebarHtml,paint,worktrees,tree,associate,terminalHtml,taskForTerminal,openForTerminal,collapse,progress,complete,change,selectObjective,openTask,renderTasks,tabsHtml,showAll,terminalLaunchContext,associateNewTerminal,
    instructionRoot(path){return active(path)?scopeRows().find(row=>row.id==='objective-root')?.path:null;},
    terminalSessions,terminalParents,terminalExpanded,terminalMain,openMainTerminal,openTaskTerminal,terminalTaskNameHtml,terminalWorktreeColor,terminalColor,sidebarMode,recentScopes,moveForTerminalDrop,
    syncTerminalHierarchy(){if(active(context()?.path))bridge.syncTaskHierarchy?.(data());},
    terminalTaskContext(t){const binding=terminalTask(t);return binding?taskContext(binding.task,binding.objective):null;},
    childTerminalAssociation(t){const o=terminalObjective(t);return !active(context()?.path)?null:o?{context:{...context()},objective_id:o.id,view:'tasks'}:{context:{...context()},view:'workflow'};},
    findTaskTerminal(sessions,target){return sessions.find(t=>{if(target.main==='workflow')return terminalMain(t)?.kind==='workflow';const link=terminalLink(t);return link?.objective_id===target.objective_id&&(target.task_id?link.task_id===target.task_id:terminalMain(t)?.kind==='objective');});},
    sameTerminalObjective(a,b){return terminalObjective(a)?.id===terminalObjective(b)?.id;},
    openCurrent(){const params=new URLSearchParams(location.search),o=data()?.objectives.find(o=>o.id===params.get('objective'));if(o&&tasks(o).some(t=>t.id===params.get('objective_task'))){state().objective=o.id;const task=tasks(o).find(task=>task.id===params.get('objective_task')),line=Number(params.get('objective_action_line')),source=params.get('objective_action_source');const item=source?{line,source}:task.action_items?.find(item=>item.line===line);openTask(task.id,{actionItem:item});return;}const f=taskFocus();if(f){openTask(f.task);return;}state().view==='objective'&&objective()?selectObjective(objective().id,{activateTerminal:false}):showAll();},
    openOwnedFile(root,path){
      if(!active(context()?.path))return false;
      const scope=context(),full=root.replace(/\/$/,'')+'/'+path;
      const resource=objective()?.resources.find(r=>r.kind==='document'&&scope.path+'/'+r.path===full);
      if(!resource)return false;openResource(resource.id);return true;
    },
    async addAssistant(scope,reference){const d=await load(scope);if(!d?.enabled)return false;const o=d.objectives.find(o=>o.id===state(scope).objective)||d.objectives.find(o=>d.focused.includes(o.id));if(!o)return false;if(!o.resources.some(r=>r.kind==='assistant'&&r.document_id===reference.document_id&&r.assistant_root===reference.assistant_root))await change({type:'resource',objective_id:o.id,kind:'assistant',title:reference.title||'Assistant document',...reference},{scope});return true;},
    worktreeColor(path){return active(context()?.path)?scopeRows().find(t=>t.fixed&&t.path===path)?.color||data()?.objectives.flatMap(o=>o.worktrees).find(t=>t.path===path||t.resolved_path===path)?.color:null;},
    notebookControls(root,path){const r=objective()?.resources.find(r=>r.kind==='notebook'&&r.path===path&&context()?.path===root);return r?`<span data-objective-notebook-controls><button type="button" data-rename-objective-resource="${esc(r.id)}">Rename</button></span>`:'';},
    ownsCenter(path){return context()?.path===path&&openView?.scope===key(context())&&!!(document.querySelector('#content .objective-working')||state().selected);},
    leave(){closeTaskStatusMenu();closeSwitchMenu();closeLinkEdit();releaseDraft();if(context()){collapse();resetWorktreeBrowse();state().focus=null;state().selected=null;persistView();}paintTaskClose();document.querySelectorAll('[data-native-asset-tools]').forEach(n=>n.remove());document.getElementById('sidebar')?.removeAttribute('data-objective-task-mode');document.querySelectorAll('.objective-task-asset-highlight').forEach(n=>n.classList.remove('objective-task-asset-highlight'));openView=null;dialog?.remove();dialog=null;clearTimeout(hoverTimer);}};
  document.addEventListener('keydown',event=>{if(activeLinkDraft?.node?.contains(event.target)&&(event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='s'){event.preventDefault();void saveLinkDetails(activeLinkDraft);}});
  window.addEventListener('beforeunload',event=>{if([...drafts.values()].some(dirtyDraft)||[...linkDrafts.values()].some(dirtyLink)){event.preventDefault();event.returnValue='';}});
})();
