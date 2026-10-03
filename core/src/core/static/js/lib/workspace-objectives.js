/* Workspace objectives own configuration and content; Assistant stays a reference. */
(() => {
  'use strict';
  const cache = new Map(), views = new Map(), pending = new Map(), queues = new Map(), overlays = new Map(), loadedAt = new Map();
  const resourceMime = 'application/x-lab-objective-resource', documentMime = 'application/x-lab-assistant-document';
  const objectiveMime = 'application/x-lab-workspace-objective', focusSlots = 5;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const drafts = new Map(), linkDrafts = new Map();
  let bridge, dialog = null, hoverTimer, openView = null, activeDraft = null, activeLinkDraft = null, switchMenu = null, switchTimer;
  const key = scope => (scope?.vault || '') + '::' + scope?.workspace_id;
  const context = () => bridge?.context?.();
  const data = () => cache.get(key(context()));
  function state(scope = context()) {
    const id = key(scope);
    if (!views.has(id)) {
      let saved;try {saved = JSON.parse(localStorage.getItem('lab.objectives.view.v1:' + id));} catch {}
      views.set(id, {objective:saved?.objective || null, view:saved?.view || 'all', focus:saved?.focus || null, tree:saved?.tree || {}, pins:saved?.pins || {}, revealed:new Set(), selected:null});
    }
    return views.get(id);
  }
  function persistView() {const s=state();try{localStorage.setItem('lab.objectives.view.v1:'+key(context()),JSON.stringify({objective:s.objective,view:s.view,focus:s.focus,tree:s.tree,pins:s.pins}));}catch{}}
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
  function scopeRows(o=objective()) {
    if(!o)return [];
    const root=context()?.path,folder=o.path||root+'/objectives/'+o.id;
    return [{id:'workspace-root',label:'Root',path:root,repo:root,kind:'folder',color:'#8b949e',fixed:true,membership:o.worktrees.find(t=>t.path===root)?.id},
      {id:'objective-root',label:'Objective',path:folder,repo:root,kind:'folder',color:'#8b949e',fixed:true,membership:o.worktrees.find(t=>t.path===folder)?.id},
      ...o.worktrees.filter(t=>t.path!==root&&t.path!==folder)];
  }
  function worktrees(path) {if(!active(path))return null;return scopeRows().map(t=>({...t,projectPath:t.repo}));}
  function tree(o=objective()) {return o?(scopeRows(o).find(t=>t.id===state().tree[o.id])||scopeRows(o)[0]):null;}
  function sidebarHtml(path) {return context()?.path===path?'<section data-objectives-sidebar aria-label="Workspace objectives"></section>':'';}
  async function load(scope=context(), fresh=false) {
    if(!scope?.workspace_id||scope.workspace_id.startsWith('__'))return;
    const id=key(scope);
    if(cache.has(id)&&!fresh){paint();if(Date.now()-(loadedAt.get(id)||0)<2000)return cache.get(id);}
    if(pending.has(id))return pending.get(id);
    const request=fetch('/api/objectives?'+new URLSearchParams({workspace_id:scope.workspace_id,...(scope.vault?{vault:scope.vault}:{})})).then(async r=>{
      const d=await r.json();if(!r.ok)throw new Error(d.detail||'Could not load objectives');if(d.enabled)await Promise.all([bridge.readyContent?.(),scope.path&&bridge.warmWorktrees?.([{path:scope.path},...d.objectives.filter(o=>d.focused.includes(o.id)).flatMap(o=>[{path:o.path||scope.path+'/objectives/'+o.id},...o.worktrees])],scope)]);const previous=cache.get(id);cache.set(id,d);loadedAt.set(id,Date.now());
      for(const overlay of overlays.get(id)||[])overlay.apply(d);
      if(key(context())===id){paint();if(previous?.revision!==d.revision){bridge.refreshSidebar?.();bridge.refreshTerminals?.();if(openView?.type==='all')paintLibrary();}if(!previous)bridge.openDefault?.();}return d;
    }).catch(e=>{if(key(context())===id)notify(e.message,true);}).finally(()=>pending.delete(id));pending.set(id,request);return request;
  }
  function notify(text,error=false) {window.explorerToast?.(text,error);}
  function change(action,{optimistic,scope:destination}={}) {
    const scope={...(destination||context())},id=key(scope);
    const overlay=optimistic?{apply:optimistic}:null;
    if(overlay){overlays.set(id,[...(overlays.get(id)||[]),overlay]);overlay.apply(cache.get(id));paint();if(openView?.type==='tasks')renderTasks();}
    const previous=queues.get(id)||Promise.resolve();
    const next=previous.catch(()=>{}).then(async()=>{
      const resolvedAction=typeof action==='function'?action(cache.get(id)):action;
      const r=await fetch('/api/objectives',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace_id:scope.workspace_id,vault:scope.vault,expected:cache.get(id)?.revision,action:resolvedAction})});
      const d=await r.json();if(!r.ok)throw new Error(d.detail||'Could not save objective');if(d.enabled)await bridge.readyContent?.();overlays.set(id,(overlays.get(id)||[]).filter(item=>item!==overlay));cache.set(id,d);loadedAt.set(id,Date.now());
      for(const item of overlays.get(id)||[])item.apply(d);
      if(key(context())===id){paint();bridge.refreshTerminals?.();if(openView?.type==='tasks')renderTasks();else if(openView?.type==='all')paintLibrary();}return d;
    }).catch(async e=>{overlays.set(id,(overlays.get(id)||[]).filter(item=>item!==overlay));notify(e.message,true);await load(scope,true);throw e;});queues.set(id,next);return next;
  }
  function collapse() {clearTimeout(hoverTimer);state().revealed.clear();}
  function tabsFor(resource) {
    const root=resource.document_id||resource.id,rows=resource.content?.tabs||[],children=new Map();rows.forEach(t=>{const parent=t.parent?.id||root;if(!children.has(parent))children.set(parent,[]);children.get(parent).push(t);});
    const result=[],seen=new Set();function visit(id,depth){for(const t of children.get(id)||[]){if(seen.has(t.id))continue;seen.add(t.id);result.push({...t,depth});visit(t.id,depth+1);}}visit(root,0);rows.filter(t=>!seen.has(t.id)).forEach(t=>result.push({...t,depth:0}));return result;
  }
  function tasks(o=objective()) {return o?.tasks.flatMap(t=>[t,...t.children])||[];}
  function taskFocus() {const f=state().focus,o=objective();return state().view==='objective'&&f?.objective===o?.id&&tasks(o).some(t=>t.id===f.task)?f:null;}
  function focusedTask() {return tasks().find(t=>t.id===taskFocus()?.task);}
  function taskAssets(task) {return [{id:'details',resource_id:task.document_id,tab_id:task.tab_id,required:true},...(task.assets||[])];}
  function taskReferences(task) {const refs=taskAssets(task).map(a=>assetInfo(a)?.reference);return refs.every(Boolean)?[...new Set(refs)]:null;}
  function assetTarget(asset) {const {id,required,...target}=asset;return target;}
  function sameAsset(a,b) {return a.resource_id===b.resource_id&&(a.tab_id||null)===(b.tab_id||null)&&(a.sub_link_id||null)===(b.sub_link_id||null)&&JSON.stringify(a.folder||null)===JSON.stringify(b.folder||null);}
  function resourceIcon(r,subLink) {
    return r?.kind==='link'?(window.LabScopeLinks?.icon({kind:'external',url:linkTarget(r,subLink)?.url})||'<span aria-hidden="true">↗</span>'):
      (r?.kind!=='assistant'&&bridge.fileIcon?.(r?.path||r?.title))||`<span aria-hidden="true">${r?.kind==='notebook'?'▦':'▤'}</span>`;
  }
  function assetInfo(asset,o=objective()) {
    if(asset.folder){const scope=scopeRows(o).find(t=>[t.path,t.resolved_path].includes(asset.folder.root));return {title:asset.folder.path==='.'?scope?.label||asset.folder.root.split('/').pop():asset.folder.path,icon:`<span aria-hidden="true">${scope?.kind==='worktree'?'⑂':'⌂'}</span>`,reference:asset.folder.root.replace(/\/$/,'')+(asset.folder.path==='.'?'':'/'+asset.folder.path)};}
    const r=o?.resources.find(r=>r.id===asset.resource_id);if(!r)return null;
    const child=asset.sub_link_id?linkTarget(r,asset.sub_link_id):asset.tab_id?tabsFor(r).find(t=>t.id===asset.tab_id):null;
    if((asset.tab_id||asset.sub_link_id)&&!child&&r.kind!=='assistant')return null;
    return {resource:r,title:child?r.title+' · '+child.title:r.title,icon:resourceIcon(r,asset.sub_link_id),reference:resourceReference(r,asset.tab_id,asset.sub_link_id)};
  }
  function taskIcon(task,o=objective()) {const asset=taskAssets(task).find(a=>a.id===task.icon_asset_id)||taskAssets(task)[0];return assetInfo(asset,o)?.icon||'<span aria-hidden="true">☑</span>';}
  function associatedAsset(target) {const t=focusedTask();return !!t&&taskAssets(t).some(a=>sameAsset(a,target));}
  function markTaskAssets(host) {
    host.querySelectorAll('[data-objective-resource]').forEach(node=>node.classList.toggle('objective-task-asset-highlight',taskFocus()?.mode==='semi'&&associatedAsset(sidebarTarget(node))));
    const sidebar=document.getElementById('sidebar');if(!sidebar)return;
    sidebar.dataset.objectiveTaskMode=taskFocus()?.mode||'off';
    const references=new Set(taskFocus()?.mode==='semi'?taskAssets(focusedTask()).map(a=>assetInfo(a)?.reference?.split('#')[0]).filter(Boolean):[]);
    host.querySelectorAll('[data-select-worktree]').forEach(node=>{const scope=scopeRows().find(t=>t.id===node.dataset.selectWorktree);node.closest('.sidebar-scope-chip').classList.toggle('objective-task-asset-highlight',references.has(scope?.path)||references.has(scope?.resolved_path));});
    sidebar.querySelectorAll('[data-filepath]').forEach(node=>{
      const path=node.dataset.filepath,root=node.dataset.entryRoot||bridge.scopeRoot?.()||context()?.path;
      const full=path?.startsWith('/')?path:root?.replace(/\/$/,'')+'/'+path;
      node.classList.toggle('objective-task-asset-highlight',references.has(full));
    });
    sidebar.querySelectorAll('[data-entry-kind=folder]').forEach(node=>{const root=node.dataset.entryRoot||bridge.scopeRoot?.(),path=node.dataset.entryPath;node.classList.toggle('objective-task-asset-highlight',references.has(root?.replace(/\/$/,'')+'/'+path));});
  }
  function taskFocusHtml(task) {
    const mode=taskFocus().mode,count=taskAssets(task).length;return `<section class="objective-task-focus" data-task-id="${esc(task.id)}"><button type="button" class="objective-focused-task" data-open-task="${esc(task.id)}" draggable="true">${taskIcon(task)}<span>${esc(task.title)}</span></button><div class="objective-task-modes" role="group" aria-label="Task focus mode">${[['off','Off'],['semi','Semi'],['focus','Focus']].map(([id,label])=>`<button type="button" data-task-focus-mode="${id}" aria-pressed="${id===mode}" title="${esc({off:'Show all assets',semi:'Highlight task assets in their usual order',focus:'Show only task assets'}[id])}">${label}</button>`).join('')}<button type="button" data-task-assets="${esc(task.id)}" aria-label="Manage assets and icon for ${esc(task.title)}">${count} asset${count===1?'':'s'}</button></div></section>`;
  }
  function taskAssetRow(asset) {
    const info=assetInfo(asset);if(!info)return '';
    const selected=state().selected,r=info.resource,active=r?selected?.resource===r.id&&(selected.tab||null)===(asset.tab_id||null)&&(selected.subLink||null)===(asset.sub_link_id||null):false;
    return `<button type="button" class="sidebar-scope-link objective-resource${r?.kind==='link'?' objective-link':''}${active?' active':''}" data-task-asset="${esc(asset.id)}" ${r?`data-objective-resource="${esc(r.id)}" ${asset.tab_id?`data-objective-tab="${esc(asset.tab_id)}"`:''} ${asset.sub_link_id?`data-objective-sublink="${esc(asset.sub_link_id)}"`:''}`:''} draggable="true" title="${esc(info.title)}">${info.icon}<span>${esc(info.title)}</span></button>`;
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
    const rows=r.kind==='link'?subLinksFor(r):tabsFor(r),reveal=state().revealed.has(r.id),pins=state().pins[r.id]||[];
    if(r.kind==='link')return `<div class="objective-resource-group" data-resource-group="${esc(r.id)}"><div class="objective-resource-head"><button type="button" class="sidebar-scope-link objective-resource objective-link${selected?' active':''}" data-objective-resource="${esc(r.id)}" draggable="true" title="${esc(r.title)}">${icon}<span>${esc(r.title)}</span></button>${rows.length?'<span class="objective-sublinks-marker" aria-hidden="true">'+(reveal?'▾':'▸')+'</span>':''}</div>${reveal&&rows.length?`<div class="objective-subtabs objective-sublinks" role="tree" aria-label="${esc(r.title)} sublinks">${rows.map(row=>`<div class="objective-subtab-row" style="--objective-tab-depth:${row.depth}" role="treeitem" aria-level="${row.depth+1}"><button type="button" class="objective-subtab${state().selected?.resource===r.id&&state().selected?.subLink===row.id?' active':''}" data-objective-resource="${esc(r.id)}" data-objective-sublink="${esc(row.id)}" draggable="true" title="${esc(row.title)}">${window.LabScopeLinks?.icon({kind:'external',url:row.url})||'↗'}<span>${esc(row.title)}</span></button></div>`).join('')}</div>`:''}</div>`;
    return `<div class="objective-resource-group" data-resource-group="${esc(r.id)}"><div class="objective-resource-head"><button type="button" class="sidebar-scope-link objective-resource${r.kind==='link'?' objective-link':''}${selected?' active':''}" data-objective-resource="${esc(r.id)}" draggable="true" title="${esc(r.title)}">${icon}<span>${esc(r.title)}</span></button>${rows.length?`<button type="button" class="objective-tree-toggle" data-reveal-resource="${esc(r.id)}" aria-label="Show subtabs for ${esc(r.title)}" aria-expanded="${reveal}">${reveal?'▾':'▸'}</button>`:''}</div>
      ${rows.length?`<div class="objective-subtabs" role="tree" aria-label="${esc(r.title)} subtabs">${rows.filter(t=>reveal||pins.includes(t.id)).map(t=>`<div class="objective-subtab-row" style="--objective-tab-depth:${t.depth}" role="treeitem" aria-level="${t.depth+1}"><button type="button" class="objective-subtab${state().selected?.resource===r.id&&state().selected.tab===t.id?' active':''}" data-objective-resource="${esc(r.id)}" data-objective-tab="${esc(t.id)}" draggable="true" title="${esc(t.title)}"><span aria-hidden="true">▤</span><span>${esc(t.title)}</span></button><button type="button" class="objective-pin" data-pin-resource="${esc(r.id)}" data-pin-tab="${esc(t.id)}" aria-label="Pin ${esc(t.title)}" aria-pressed="${pins.includes(t.id)}">${pins.includes(t.id)?'◆':'◇'}</button></div>`).join('')}</div>`:''}</div>`;
  }
  function paint() {
    bridge.refreshTabs?.();
    if(switchMenu)paintSwitchMenu();
    refreshLinkDetails();
    const scope=context(),host=document.querySelector('[data-objectives-sidebar]');if(!host||!scope)return;
    const d=data();if(!d)return;
    if(!d.enabled){host.innerHTML='<button type="button" class="sidebar-objective-add" data-new-objective>+ Objective</button>';return;}
    const o=objective();if(!o)return;state().objective=o.id;
    host.dataset.taskFocusMode=taskFocus()?.mode||'off';
    const task=focusedTask(),taskButton=`<button type="button" class="sidebar-scope-link objective-tasks" data-open-objective-tasks draggable="true"><span aria-hidden="true">☑</span><span>Tasks</span>${badge(o)}</button>`;
    if(task&&taskFocus().mode==='focus'){
      host.innerHTML=taskButton+taskFocusHtml(task)+'<div class="sidebar-title">Task assets</div><div class="objective-resources">'+taskAssets(task).map(taskAssetRow).join('')+'</div>';
      markTaskAssets(host);return;
    }
    const t=tree(o),general=o.resources.filter(r=>!r.worktree),scoped=o.resources.filter(r=>r.worktree&&(r.worktree===t?.id||r.worktree===t?.membership));
    host.innerHTML=taskButton+(task?taskFocusHtml(task):'')+`
      <div class="sidebar-title objective-title">${esc(o.name)}<button type="button" data-objective-settings aria-label="Objective settings">⚙</button></div>
      <section data-objective-shared><div class="sidebar-title objective-title">Documents & notebooks<button type="button" data-add-resource="document" aria-label="Add objective document">+</button></div><div class="objective-resources">${general.filter(r=>r.kind!=='link').map(r=>resourceRow(o,r)).join('')}</div><div class="sidebar-title objective-title">Links<button type="button" data-add-resource="link" aria-label="Add objective link">+</button></div><div class="objective-resources">${general.filter(r=>r.kind==='link').map(r=>resourceRow(o,r)).join('')}</div>
      </section>
      <div class="sidebar-title objective-title">Worktrees<button type="button" data-associate-worktree aria-label="Associate worktree">+</button></div><div class="objective-worktrees">${scopeRows(o).map(item=>`<div class="sidebar-scope-chip${item.id===t?.id?' active':''}" style="--sidebar-workspace-color:${esc(item.color)}" ${item.fixed?'data-objective-root':'data-objective-worktree'}="${esc(item.id)}"><span class="objective-worktree-icon" aria-hidden="true">${item.fixed?'⌂':'⑂'}</span><button type="button" class="sidebar-file-scope-button" data-select-worktree="${esc(item.id)}" draggable="true" aria-pressed="${item.id===t?.id}" title="${esc(item.path)}"><span>${esc(item.label)}</span></button><span class="sidebar-scope-tag">${esc(item.kind==='folder'?'Folder':'Worktree')}</span></div>`).join('')}</div>
      ${scoped.length?`<div class="sidebar-title">For this ${t?.kind==='folder'?'folder':'worktree'}</div><div class="objective-resources">${scoped.map(r=>resourceRow(o,r)).join('')}</div>`:''}`;
    host.querySelectorAll('[data-resource-group]').forEach(row=>{row.onmouseenter=()=>{clearTimeout(hoverTimer);const id=row.dataset.resourceGroup;if(state().revealed.has(id))return;const resource=o.resources.find(r=>r.id===id);hoverTimer=setTimeout(()=>{if(row.isConnected&&key(context())===key(scope)){state().revealed.add(id);paint();}},resource?.kind==='link'?1000:1500);};row.onmouseleave=()=>clearTimeout(hoverTimer);});
    markTaskAssets(host);
  }
  function selectObjective(id) {
    const o=data()?.objectives.find(o=>o.id===id);if(!o)return;closeSwitchMenu();collapse();state().focus=null;state().objective=id;state().view='objective';state().selected=null;persistView();paint();renderTasks();bridge.refreshTerminals?.();
    const t=tree(o)||{path:context().path,kind:'folder'};if(bridge.scopeRoot?.()!==t.path)bridge.selectWorktree?.(t);
  }
  function tabsHtml(path,working=true) {
    if(context()?.path!==path)return '';
    const s=state(),all=working&&s.view==='all',o=objective(),selected=!!(working&&!all&&o),task=working&&focusedTask();
    return `<button type="button" class="repo-tab vault-context-tab objective-tab${all?' active':''}" data-all-objectives aria-pressed="${all}">Objectives</button>`+
      (o?`<button type="button" class="repo-tab vault-context-tab objective-tab${selected?' active':''}" style="--vault-color:${esc(o.color)}" data-current-objective data-select-objective="${esc(o.id)}" draggable="true" aria-pressed="${selected}" aria-haspopup="menu" aria-expanded="${!!switchMenu}" aria-controls="objective-switch-menu" title="${esc(o.name+(task?' / '+task.title:''))}">${task?`<span class="objective-task-tab-icon">${taskIcon(task)}</span>`:'<span class="vault-mark" aria-hidden="true"></span>'}<span class="objective-tab-name">${esc(task?task.title:o.name)}</span><span class="objective-switch-arrow" data-toggle-objective-switch aria-hidden="true">▾</span></button>`:'');
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
      return `<button type="button" role="menuitemradio" aria-checked="${selected}" ${o?`data-select-objective="${esc(o.id)}"`:`data-choose-objective-slot="${slot}"`} style="--vault-color:${esc(o?.color||d.slot_palettes?.[slot]?.[0]||'#8b949e')}"><span class="objective-switch-number">${slot+1}</span><span class="vault-mark" aria-hidden="true"></span><span class="objective-tab-name">${esc(o?.name||'Choose an objective…')}</span></button>`;
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
    if(!data()){const scope=key(context());void load().then(result=>{if(result&&key(context())===scope)showAll();});return;}
    closeSwitchMenu();state().view='all';state().focus=null;state().selected=null;collapse();persistView();
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
  function showCenter(type) {releaseDraft();bridge.prepareCenter?.();openView={type,scope:key(context()),objective:objective()?.id};return document.getElementById('content');}
  function taskHref(task) {const url=new URL(location.pathname,location.origin);url.searchParams.set('workspace',context().path);url.searchParams.set('objective',objective().id);url.searchParams.set('objective_task',task.id);return url.pathname+url.search;}
  function taskRow(task,parent=null) {
    const done=parent?task.done:complete(task);return `<div class="objective-task-row${parent?' child':''}" data-task-id="${esc(task.id)}"><input type="checkbox" aria-label="Complete ${esc(task.title)}" data-task-done="${esc(task.id)}" ${done?'checked':''}><a class="objective-task-title${done?' done':''}" href="${esc(taskHref(task))}" data-open-task="${esc(task.id)}" draggable="true">${esc(task.title)}</a><button type="button" data-task-assets="${esc(task.id)}" aria-label="Assets and icon for ${esc(task.title)}" title="${taskAssets(task).length} assets · choose task icon">${taskIcon(task)}</button><input type="date" aria-label="Due date for ${esc(task.title)}" data-task-due="${esc(task.id)}" value="${esc(task.due||'')}" title="${parent&&!task.due?'Inherits '+(parent.due||'parent deadline'):'Due date'}"><button type="button" data-add-subtask="${esc(task.id)}" ${parent?'hidden':''} aria-label="Add subtask to ${esc(task.title)}">+</button></div>`;
  }
  function renderTasks() {
    const o=objective();if(!o)return;state().focus=null;state().view='objective';persistView();const host=showCenter('tasks'),p=progress(o);state().selected=null;
    host.innerHTML=`<section class="objective-working"><header><h2>Tasks</h2><button type="button" data-new-objective-task>+ Task</button></header><p class="objective-purpose">${esc(o.name)} · ${esc(o.purpose)}</p><div class="objective-task-progress">${badge(o)}<span>${esc(p.label)}</span></div><div class="objective-task-list">${o.tasks.map(t=>taskRow(t)+t.children.map(c=>taskRow(c,t)).join('')).join('')||'<p>No tasks yet. Add a task and its details document will be created with it.</p>'}</div></section>`;
    paint();
  }
  function openTask(id,mode='focus') {
    const o=objective(),task=tasks(o).find(t=>t.id===id);if(!task)return;
    state().focus={objective:o.id,task:id,mode:['focus','semi','off'].includes(mode)?mode:'focus'};
    state().view='objective';persistView();openResource(task.document_id,task.tab_id);
  }
  function openTaskAssets(id) {
    const task=tasks().find(t=>t.id===id);if(!task)return;
    form('Task assets',`<p class="objective-purpose">${esc(task.title)} · Drop documents, notebooks, links or folders here or onto its task row. Choose an asset’s icon for this task.</p><div class="objective-task-asset-list" data-task-id="${esc(id)}">${taskAssets(task).map(a=>{const info=assetInfo(a);return info?`<div class="objective-task-asset-choice"><button type="button" data-pick-task-icon="${esc(a.id)}" data-icon-task="${esc(id)}" aria-label="Use icon from ${esc(info.title)}" aria-pressed="${(task.icon_asset_id||'details')===a.id}">${info.icon}</button><button type="button" data-open-task-asset="${esc(a.id)}" data-asset-task="${esc(id)}">${esc(info.title)}</button>${a.required?'<span class="objective-purpose">Details</span>':`<button type="button" data-remove-task-asset="${esc(a.id)}" data-asset-task="${esc(id)}" aria-label="Detach ${esc(info.title)}">×</button>`}</div>`:'';}).join('')}</div>`,async()=>{});
    dialog.querySelector('[type=submit]').textContent='Done';
  }
  function openAsset(asset) {
    if(asset.folder){bridge.openFolder?.(asset.folder);return;}
    openResource(asset.resource_id,asset.tab_id||null,asset.sub_link_id||null);
  }
  function openResource(resourceId,tabId=null,subLink=null) {
    const o=objective(),r=o?.resources.find(r=>r.id===resourceId);if(!r)return;
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
  function openLinkUrl(url) {
    if(!validLinkUrl(url)){notify('Use a full http or https URL.',true);return;}
    void window.LabExternalLinks?.open(url,{clientOnly:true,reuseTab:true});
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
  function renderLinkDetails(o,r,subLink=null) {
    const host=showCenter('link');openView.resource=r.id;openView.subLink=subLink;
    const scope={...context()},id=JSON.stringify([key(scope),o.id,r.id,subLink]),target=linkTarget(r,subLink);let d=linkDrafts.get(id);
    if(!d){d={scope,objective:o.id,resource:r.id,subLink};resetLinkDraft(d,target);linkDrafts.set(id,d);}
    else if(!dirtyLink(d)&&!d.saving&&d.base!==linkSnapshot(target))resetLinkDraft(d,target);
    mountLinkDetails(d,o,target,host);
    for(const [id,entry] of linkDrafts){if(linkDrafts.size<=32)break;if(entry!==d&&!entry.saving&&!dirtyLink(entry))linkDrafts.delete(id);}
  }
  function refreshLinkDetails() {
    const d=activeLinkDraft;if(!d?.node?.isConnected||key(d.scope)!==key(context()))return;
    const o=data()?.objectives.find(o=>o.id===d.objective),r=linkTarget(o?.resources.find(r=>r.id===d.resource),d.subLink);if(!r)return;
    if(!dirtyLink(d)&&!d.saving&&d.base!==linkSnapshot(r)){resetLinkDraft(d,r);mountLinkDetails(d,o,r,document.getElementById('content'));}
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
    resetLinkDraft(d,r);if(activeLinkDraft===d&&d.node?.isConnected)mountLinkDetails(d,o,r,document.getElementById('content'));
  }
  const dirtyDraft=draft=>draft.body!==draft.base;
  function draftResource(draft,value=cache.get(key(draft.scope))) {return value?.objectives.find(o=>o.id===draft.objective)?.resources.find(r=>r.id===draft.resource);}
  function draftBody(resource,tab) {return tab?resource?.content?.tabs.find(t=>t.id===tab)?.body:resource?.content?.body;}
  function draftControls(draft) {
    if(activeDraft!==draft||!draft.node.isConnected)return;
    const host=draft.node.closest('.objective-document'),status=host.querySelector('.objective-document-status');
    host.querySelector('[data-save-objective-document]').disabled=!dirtyDraft(draft)||draft.saving;
    host.querySelector('[data-revert-objective-document]').disabled=draft.saving;
    status.textContent=draft.error||draft.loadingError||(draft.saving?'Saving…':dirtyDraft(draft)?'Unsaved · saves after 10s idle':draft.saved?'Saved at '+new Date(draft.saved).toLocaleTimeString():'Click to edit · / for commands');
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
    activeLinkDraft=null;
    const draft=activeDraft;if(!draft)return;
    activeDraft=null;clearTimeout(draft.timer);
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
    activeDraft=draft;host.replaceChildren(draft.node);
    const mount=()=>{
      if(activeDraft!==draft||!draft.node.isConnected||draft.input)return;
      draft.loadingError='';
      draft.node.replaceChildren();
      draft.input=window.LabMarkdownEditor.create(draft.node,{body:draft.body,
        onChange:text=>{if(draft.syncing)return;draft.body=text;draft.edited=Date.now();draftControls(draft);scheduleDraft(draft);},
        onSave:()=>saveDraft(draft,true)});
      draftControls(draft);
    };
    if(window.LabMarkdownEditor&&window.marked&&window.DOMPurify)mount();
    else{
      // Resources can open while the lazy editor/parser scripts are still in
      // flight. Rendering the preview also needs Marked and DOMPurify.
      draft.node.textContent='Loading document…';
      Promise.resolve().then(()=>bridge.readyContent?.()).then(()=>{
        if(activeDraft!==draft||!draft.node.isConnected||draft.input)return;
        if(!window.marked||!window.DOMPurify)throw new Error('Could not load Markdown rendering');
        if(window.LabMarkdownEditor)mount();
        else{
          draft.node.innerHTML=window.LabMarkdown.render(draft.body);
          return window.ensureLiveMarkdownEditor().then(mount);
        }
      }).catch(error=>{draft.loadingError=error.message;if(activeDraft===draft&&!draft.input)draft.node.textContent=draft.body;draftControls(draft);});
    }
    draftControls(draft);scheduleDraft(draft);
    for(const [entry,value] of drafts){
      if(drafts.size<=32)break;
      if(value!==activeDraft&&!value.saving&&!dirtyDraft(value)){value.input?.destroy();drafts.delete(entry);}
    }
  }
  async function revertDraft(draft) {
    if(!draft||draft.saving)return;
    clearTimeout(draft.timer);await load(draft.scope,true);
    const body=draftBody(draftResource(draft),draft.tab);if(typeof body!=='string')return;
    draft.base=draft.body=body;draft.error='';draft.syncing=true;if(draft.input)draft.input.value=body;draft.syncing=false;draftControls(draft);
  }
  function form(title,fields,submit) {
    dialog?.remove();const node=document.createElement('dialog');node.className='objective-dialog';node.innerHTML=`<form><header><h2>${esc(title)}</h2></header>${fields}<footer><button type="button" data-cancel>Cancel</button><button type="submit">Save</button></footer><p role="status"></p></form>`;document.body.append(node);dialog=node;node.showModal();node.querySelector('[data-cancel]').onclick=()=>{node.close();node.remove();};node.querySelector('form').onsubmit=async e=>{e.preventDefault();const button=node.querySelector('[type=submit]');button.disabled=true;try{await submit(new FormData(e.target));node.close();node.remove();}catch(error){node.querySelector('[role=status]').textContent=error.message;button.disabled=false;}};return node;
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
  function addTask(parentId=null) {const o=objective();form(parentId?'New subtask':'New task',input('Task','title')+input('Due date','due','','date',false),async values=>{await change({type:'task',objective_id:o.id,parent_id:parentId,title:values.get('title'),due:values.get('due')});renderTasks();});}
  function associate(row) {return change({type:'worktree',objective_id:objective().id,path:row.path,label:row.label||row.name||row.path.split('/').pop(),repo:row.projectPath||row.path,branch:row.branch,kind:row.kind||'worktree'}).then(d=>{const o=d.objectives.find(o=>o.id===objective().id);state().tree[o.id]=o.worktrees.at(-1).id;persistView();return o.worktrees.at(-1);});}
  function terminalIdentity(t) {return t.session_id||t.name;}
  function taskForTerminal(t) {const d=data(),link=d?.terminal_links[terminalIdentity(t)],o=d?.objectives.find(o=>o.id===link?.objective_id),task=tasks(o).find(t=>t.id===link?.task_id);return task?{title:task.title,icon:taskIcon(task,o)}:null;}
  function terminalObjective(t) {const d=data();if(!d?.enabled)return null;const link=d.terminal_links[terminalIdentity(t)];return d.objectives.find(o=>o.id===link?.objective_id)||d.objectives.find(o=>o.worktrees.some(w=>[w.path,w.resolved_path].includes(t.linked_scope?.root)||[w.path,w.resolved_path].includes(t.cwd)))||d.objectives[0];}
  function terminalHtml(sessions,pill,newButton) {
    if(!active(context()?.path))return null;
    const d=data(),rows=sessions.map((t,index)=>({t,index,objective:terminalObjective(t)?.id}));
    return d.focused.map(id=>{
      const o=d.objectives.find(o=>o.id===id);if(!o)return '';
      const groups=new Map();
      for(const row of rows.filter(row=>row.objective===id)){
        const root=row.t.linked_scope?.root||row.t.cwd||context().path;
        const worktree=o.worktrees.find(w=>w.path===root||w.resolved_path===root);
        const path=worktree?.path||root;
        if(!groups.has(path))groups.set(path,{worktree,items:[]});
        groups.get(path).items.push(row);
      }
      const terminals=[...groups].map(([path,{worktree,items}])=>
        `<div class="objective-terminal-worktree" role="group" aria-label="${esc(worktree?.label||(path===context().path?'Objective folder':path.split('/').filter(Boolean).slice(-2).join('/')))}">${items.map(row=>pill(row.t,row.index)).join('')}</div>`).join('');
      return `<section class="objective-terminal-group" data-objective-active="${id===objective()?.id}" style="--objective-color:${esc(o.color)}"><button type="button" class="objective-terminal-heading" data-select-objective="${esc(id)}" title="${esc(o.name)}">${esc(o.name)}</button><div class="objective-terminal-rows">${terminals}</div></section>`;
    }).join('')+newButton;
  }
  function openForTerminal(t) {
    const link=data()?.terminal_links[terminalIdentity(t)],o=terminalObjective(t);if(!o||!link)return false;
    state().objective=o.id;state().view='objective';
    const resource=o.resources.find(r=>r.id===link.resource_id),root=link.folder?.root||link.file?.root||t.linked_scope?.root;
    const w=scopeRows(o).find(w=>w.id===resource?.worktree||[w.path,w.resolved_path].includes(root));
    let selected;if(w){state().tree[o.id]=w.id;if(bridge.scopeRoot?.()!==w.path)selected=bridge.selectWorktree?.(w);}persistView();
    if(link.task_id){openTask(link.task_id);}
    else if(link.view==='tasks'||link.folder){
      state().selected=null;renderTasks();
      if(link.folder){const view=openView,scope=key(context());Promise.resolve(selected).then(()=>{if(openView===view&&key(context())===scope)bridge.openFolder?.(link.folder);});}
    }else if(link.resource_id)openResource(link.resource_id,link.tab_id,link.sub_link_id);else if(link.file)bridge.openFile?.(link.file);
    paint();return true;
  }
  function sidebarTarget(node,o=objective()) {
    const task=node.closest?.('[data-open-task],[data-task-id]');if(task)return {task_id:task.dataset.openTask||task.dataset.taskId};
    const asset=node.closest?.('[data-task-asset]');if(asset){const a=taskAssets(focusedTask()).find(a=>a.id===asset.dataset.taskAsset);if(a)return assetTarget(a);}
    const resource=node.closest?.('[data-objective-resource]');if(resource)return {resource_id:resource.dataset.objectiveResource,tab_id:resource.dataset.objectiveTab||null,sub_link_id:resource.dataset.objectiveSublink||null};
    if(node.closest?.('[data-objectives-sidebar] [data-open-objective-tasks]'))return {view:'tasks'};
    const row=node.closest?.('[data-objective-root],[data-objective-worktree]'),tree=scopeRows(o).find(t=>t.id===(row?.dataset.objectiveRoot||row?.dataset.objectiveWorktree));
    return tree?{folder:{root:tree.path,path:'.'}}:null;
  }
  function linkTerminal(t,target,o=objective()) {
    if(!t)throw new Error('Choose a terminal in this workspace');
    return change({type:'terminal',objective_id:o.id,session_id:terminalIdentity(t),source:t.document_source,...target}).then(()=>notify('Terminal linked.'));
  }
  function fileDropTarget(transfer) {
    const raw=transfer.getData('application/x-lab-file-context');
    if(raw){const file=JSON.parse(raw);if(!['file','folder'].includes(file.kind)||!file.root?.startsWith('/')||typeof file.path!=='string')throw new Error('Choose a file or folder in this objective');return {[file.kind]:{root:file.root,path:file.path}};}
    const path=JSON.parse(transfer.getData('application/x-lab-file-path'))[0];
    const root=scopeRows().map(t=>t.path).filter(root=>typeof path==='string'&&(path===root||path.startsWith(root.replace(/\/+$/,'')+'/'))).sort((a,b)=>b.length-a.length)[0];
    if(!root)throw new Error('Choose a file in this objective');return {file:{root,path}};
  }
  function handleClick(e) {
    const host=e.target.closest?.('[data-objectives-sidebar],.objective-working,.objective-dialog,.objective-terminal-group,[data-objective-notebook-controls],.repo-tabs,.objective-switch-menu');
    if(!host)return;
    const node=e.target.closest('button,input,a');if(!node)return;
    if(node.dataset.openTask){if(node.tagName==='A'&&(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey))return;e.preventDefault();openTask(node.dataset.openTask);return;}
    if(node.hasAttribute('data-task-focus-mode')){const f=taskFocus();if(f){f.mode=node.dataset.taskFocusMode;persistView();paint();}return;}
    if(node.dataset.taskAssets){openTaskAssets(node.dataset.taskAssets);return;}
    if(node.dataset.pickTaskIcon){const id=node.dataset.iconTask;void change({type:'task-update',objective_id:objective().id,task_id:id,icon_asset_id:node.dataset.pickTaskIcon}).then(()=>openTaskAssets(id)).catch(()=>{});return;}
    if(node.dataset.removeTaskAsset){const id=node.dataset.assetTask;void change({type:'task-remove-asset',objective_id:objective().id,task_id:id,asset_id:node.dataset.removeTaskAsset}).then(()=>openTaskAssets(id)).catch(()=>{});return;}
    if(node.dataset.openTaskAsset){const task=tasks().find(t=>t.id===node.dataset.assetTask),asset=task&&taskAssets(task).find(a=>a.id===node.dataset.openTaskAsset);if(asset){dialog?.remove();dialog=null;openTask(task.id);openAsset(asset);}return;}
    if(node.dataset.taskAsset&&!node.dataset.objectiveResource){const asset=taskAssets(focusedTask()).find(a=>a.id===node.dataset.taskAsset);if(asset)openAsset(asset);return;}
    if(e.target.closest('[data-toggle-objective-switch]')){switchMenu?closeSwitchMenu():showSwitchMenu();return;}
    if(node.hasAttribute('data-choose-objective-slot')){closeSwitchMenu();showAll();data()?.objectives.length?focusDialog(null,Number(node.dataset.chooseObjectiveSlot)):newObjective(Number(node.dataset.chooseObjectiveSlot));return;}
    if(node.dataset.selectObjective){const fromMenu=!!node.closest('.objective-switch-menu');selectObjective(node.dataset.selectObjective);if(fromMenu)document.querySelector('[data-current-objective]')?.focus({preventScroll:true});return;}
    if(node.hasAttribute('data-all-objectives')){showAll();return;}
    if(node.hasAttribute('data-objective-slot')){data()?.objectives.length?focusDialog(null,Number(node.dataset.objectiveSlot)):newObjective(Number(node.dataset.objectiveSlot));return;}
    if(node.dataset.libraryObjective){data().focused.includes(node.dataset.libraryObjective)?selectObjective(node.dataset.libraryObjective):focusDialog(node.dataset.libraryObjective);return;}
    if(node.dataset.placeObjective){focusDialog(node.dataset.placeObjective);return;}
    if(node.hasAttribute('data-new-objective')){newObjective();return;}
    if(node.hasAttribute('data-focus-objective')){focusDialog();return;}
    if(node.hasAttribute('data-open-objective-tasks')){collapse();renderTasks();return;}
    if(node.dataset.objectiveResource){const r=objective()?.resources.find(r=>r.id===node.dataset.objectiveResource),sub=node.dataset.objectiveSublink||null;if(r?.kind==='link'&&(e.metaKey||e.ctrlKey)){e.preventDefault();openLinkUrl(linkTarget(r,sub)?.url);}else openResource(node.dataset.objectiveResource,node.dataset.objectiveTab||null,sub);return;}
    if(node.dataset.openParentLink){openResource(node.dataset.openParentLink);return;}
    if(node.hasAttribute('data-add-objective-sublink')){const d=activeLinkDraft;form('Add sublink',input('Title','title')+input('URL','url','','url'),values=>change({type:'link-sublink',objective_id:d.objective,resource_id:d.resource,parent_id:d.subLink,title:values.get('title'),url:values.get('url')},{scope:d.scope}));return;}
    if(node.dataset.removeObjectiveSublink){const d=activeLinkDraft;void change({type:'link-remove-sublink',objective_id:d.objective,resource_id:d.resource,sub_link_id:node.dataset.removeObjectiveSublink},{scope:d.scope}).catch(()=>{});return;}
    if(node.hasAttribute('data-open-objective-link')){openLinkUrl(activeLinkDraft.url.trim());return;}
    if(node.hasAttribute('data-revert-objective-link')){void revertLinkDetails(activeLinkDraft);return;}
    if(node.hasAttribute('data-add-link-property')){const d=activeLinkDraft;d.properties.push({name:'',value:''});d.node.querySelector('[data-link-properties]').innerHTML=linkPropertiesHtml(d);updateLinkHeader(d);d.node.querySelector('.objective-link-property:last-child input').focus();return;}
    if(node.hasAttribute('data-remove-link-property')){const d=activeLinkDraft;d.properties.splice(Number(node.dataset.removeLinkProperty),1);d.node.querySelector('[data-link-properties]').innerHTML=linkPropertiesHtml(d);updateLinkHeader(d);return;}
    if(node.dataset.revealResource){const id=node.dataset.revealResource;if(state().revealed.has(id))state().revealed.delete(id);else state().revealed.add(id);paint();return;}
    if(node.dataset.pinResource){const id=node.dataset.pinResource,tab=node.dataset.pinTab,pins=state().pins[id]||[];state().pins[id]=pins.includes(tab)?pins.filter(t=>t!==tab):[...pins,tab];persistView();paint();return;}
    if(node.dataset.selectWorktree){const o=objective(),t=scopeRows(o).find(t=>t.id===node.dataset.selectWorktree);collapse();state().tree[o.id]=t.id;persistView();paint();bridge.selectWorktree?.(t);return;}
    if(node.hasAttribute('data-associate-worktree')){collapse();bridge.addWorktree?.(node);return;}
    if(node.dataset.addResource){addResource(node.dataset.addResource);return;}
    if(node.hasAttribute('data-new-objective-task')){addTask();return;}
    if(node.dataset.addSubtask){addTask(node.dataset.addSubtask);return;}
    if(node.dataset.taskDocument){openTask(node.dataset.taskDocument);return;}
    if(node.hasAttribute('data-objective-settings')){const o=objective();form('Objective settings',input('Name','name',o.name)+input('Outcome','purpose',o.purpose,'text',false),v=>change({type:'settings',objective_id:o.id,name:v.get('name'),purpose:v.get('purpose')}));return;}
    if(node.dataset.renameObjectiveResource){const r=objective().resources.find(r=>r.id===node.dataset.renameObjectiveResource),tab=r.kind==='document'&&openView?.resource===r.id?openView.tab:null;form(tab?'Rename subtab':'Rename resource',input('Name','title',r.content?.tabs?.find(t=>t.id===tab)?.title||r.title),async v=>{await change({type:'rename',objective_id:objective().id,resource_id:r.id,tab_id:tab,title:v.get('title')});openResource(r.id,tab);});return;}
    if(node.dataset.addObjectiveSubtab){form('New document subtab',input('Name','title'),async v=>{await change({type:'subtab',objective_id:objective().id,resource_id:node.dataset.addObjectiveSubtab,title:v.get('title'),body:''});openResource(node.dataset.addObjectiveSubtab);});return;}
    if(node.hasAttribute('data-save-objective-document'))void saveDraft(activeDraft,true);
    if(node.hasAttribute('data-revert-objective-document'))void revertDraft(activeDraft);
  }
  document.addEventListener('click',handleClick);
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
  window.addEventListener('resize',closeSwitchMenu);
  document.addEventListener('scroll',event=>{if(switchMenu&&event.target.matches?.('.repo-tabs'))closeSwitchMenu();},true);
  document.addEventListener('click',event=>{
    if(active(context()?.path)&&event.target.closest?.('#sidebar,.repo-tabs,#termSessionList')
      &&!event.target.closest('[data-objectives-sidebar],.objective-tab')){
      releaseDraft();collapse();state().selected=null;if(event.target.closest('[data-open-file],#termSessionList .sess')){state().view='objective';persistView();}paint();
    }
  },true);
  document.addEventListener('input',event=>{
    const node=event.target,d=activeLinkDraft;
    if(d&&node.closest('.objective-link-details')===d.node){
      if(node.hasAttribute('data-objective-link-field'))d[node.dataset.objectiveLinkField]=node.value;
      else if(node.closest('[data-link-property]')){const item=d.properties[Number(node.closest('[data-link-property]').dataset.linkProperty)];item[node.hasAttribute('data-link-property-name')?'name':'value']=node.value;}
      d.error='';updateLinkHeader(d);return;
    }
    if(!node.matches('[data-objective-search],[data-objective-filter],[data-objective-status-filter]'))return;
    state()[node.hasAttribute('data-objective-search')?'query':node.hasAttribute('data-objective-filter')?'filter':'statusFilter']=node.value;paintLibrary();
  });
  document.addEventListener('change',e=>{const node=e.target;if(!node.matches('[data-task-done],[data-task-due]'))return;const o=objective(),id=node.dataset.taskDone||node.dataset.taskDue,patch=node.dataset.taskDone?{done:node.checked}:{due:node.value};change({type:'task-update',objective_id:o.id,task_id:id,...patch},{optimistic:d=>{const t=d.objectives.find(item=>item.id===o.id).tasks.flatMap(t=>[t,...t.children]).find(t=>t.id===id);Object.assign(t,patch);if('done'in patch)t.children.forEach(c=>c.done=patch.done);}}).catch(()=>{});});
  document.addEventListener('dragstart',e=>{
    const project=e.target.closest?.('[data-drag-objective],.objective-tab[data-select-objective]');
    if(project){e.dataTransfer.setData(objectiveMime,JSON.stringify({scope:key(context()),objective_id:project.dataset.dragObjective||project.dataset.selectObjective}));e.dataTransfer.effectAllowed='move';return;}
    const o=objective(),taskNode=e.target.closest?.('[data-open-task]'),task=taskNode&&tasks(o).find(t=>t.id===taskNode.dataset.openTask);
    if(task){if(dragReference(e.dataTransfer,taskReferences(task)))e.dataTransfer.setData(resourceMime,JSON.stringify({scope:key(context()),objective_id:o.id,task_id:task.id}));else{e.preventDefault();notify('Some task assets are unavailable. Check its assets before passing it to the agent.',true);}return;}
    const assetNode=e.target.closest?.('[data-task-asset]');if(assetNode&&!assetNode.dataset.objectiveResource){const asset=taskAssets(focusedTask()).find(a=>a.id===assetNode.dataset.taskAsset);if(asset&&dragReference(e.dataTransfer,assetInfo(asset)?.reference))e.dataTransfer.setData(resourceMime,JSON.stringify({scope:key(context()),objective_id:o.id,...assetTarget(asset)}));else e.preventDefault();return;}
    const row=e.target.closest?.('[data-objective-resource]');
    if(row&&o){const resource=o.resources.find(r=>r.id===row.dataset.objectiveResource);if(!dragReference(e.dataTransfer,resourceReference(resource,row.dataset.objectiveTab,row.dataset.objectiveSublink))) {e.preventDefault();return;}e.dataTransfer.setData(resourceMime,JSON.stringify({scope:key(context()),objective_id:o.id,resource_id:row.dataset.objectiveResource,tab_id:row.dataset.objectiveTab||null,sub_link_id:row.dataset.objectiveSublink||null}));return;}
    const folder=e.target.closest?.('[data-select-worktree]');if(folder){const tree=scopeRows(o).find(t=>t.id===folder.dataset.selectWorktree);if(dragReference(e.dataTransfer,tree?.path))e.dataTransfer.setData(resourceMime,JSON.stringify({scope:key(context()),objective_id:o.id,folder:{root:tree.path,path:'.'}}));return;}
    if(o&&e.target.closest?.('[data-objectives-sidebar] [data-open-objective-tasks]')){
      const documents=[...new Set(o.tasks.map(t=>t.document_id))].map(id=>o.resources.find(r=>r.id===id)),resource=documents[0];
      // Empty lists still have an actual source: the objective's task registry.
      const reference=documents.length===1?resourceReference(resource):context().path+'/.lab/objectives.json#objective='+encodeURIComponent(o.id)+'&view=tasks';
      if(dragReference(e.dataTransfer,reference))e.dataTransfer.setData(resourceMime,JSON.stringify({scope:key(context()),objective_id:o.id,view:'tasks'}));
    }
  });
  document.addEventListener('dragover',e=>{const slot=e.target.closest?.('[data-objective-slot]');if(slot&&e.dataTransfer.types.includes(objectiveMime)){e.preventDefault();e.dataTransfer.dropEffect='move';slot.classList.add('objective-drop-target');}},true);
  document.addEventListener('dragleave',e=>e.target.closest?.('[data-objective-slot]')?.classList.remove('objective-drop-target'));
  document.addEventListener('dragend',()=>document.querySelectorAll('.objective-drop-target').forEach(n=>n.classList.remove('objective-drop-target')));
  const linkDropSelector='[data-task-id],[data-task-asset],[data-objective-resource],[data-objective-root],[data-objective-worktree],[data-objective-shared],[data-objectives-sidebar] [data-open-objective-tasks],#termSessionList .sess';
  document.addEventListener('dragover',e=>{if(!active(context()?.path))return;const target=e.target.closest?.(linkDropSelector);if(target&&[resourceMime,documentMime,'application/x-lab-file-path','application/x-lab-terminal',...(target.closest('[data-task-id]')?['text/uri-list','application/x-lab-reference']:[])].some(m=>e.dataTransfer.types.includes(m))){e.preventDefault();e.dataTransfer.dropEffect='link';if(target.hasAttribute('data-task-id'))target.classList.add('objective-drop-target');}},true);
  document.addEventListener('dragleave',e=>{const row=e.target.closest?.('[data-task-id]');if(row&&!row.contains(e.relatedTarget))row.classList.remove('objective-drop-target');});
  document.addEventListener('drop',e=>{
    const project=e.dataTransfer.getData(objectiveMime),slot=e.target.closest?.('[data-objective-slot]');
    if(project&&slot){e.preventDefault();e.stopImmediatePropagation();slot.classList.remove('objective-drop-target');try{const item=JSON.parse(project);if(item.scope!==key(context()))throw new Error('Choose an objective in this workspace');void placeObjective(item.objective_id,Number(slot.dataset.objectiveSlot)).catch(()=>{});}catch(error){notify(error.message,true);}return;}
    if(!active(context()?.path))return;const target=e.target.closest?.(linkDropSelector);if(!target)return;
    const raw=e.dataTransfer.getData(resourceMime),assistant=e.dataTransfer.getData(documentMime),file=e.dataTransfer.getData('application/x-lab-file-path'),terminal=e.dataTransfer.getData('application/x-lab-terminal'),external=target.closest('[data-task-id]')&&(e.dataTransfer.getData('text/uri-list')||e.dataTransfer.getData('application/x-lab-reference'));if(!raw&&!assistant&&!file&&!terminal&&!external)return;e.preventDefault();e.stopImmediatePropagation();
    const taskNode=target.closest('[data-task-id]');
    if(taskNode){taskNode.classList.remove('objective-drop-target');const id=taskNode.dataset.taskId;try{
      if(terminal){void linkTerminal(bridge.session?.(terminal),{task_id:id}).catch(()=>{});return;}
      let item;if(raw){const {scope,...source}=JSON.parse(raw);if(scope!==key(context())||source.objective_id!==objective().id)throw new Error('Choose an asset in this objective');if(source.task_id||source.view)throw new Error('Drop a document, notebook, link or folder onto a task');item=source;}
      else if(assistant){const ref=JSON.parse(assistant);item={reference:{...ref,kind:'assistant',title:ref.title||'Assistant document'}};}
      else if(file){const source=fileDropTarget(e.dataTransfer),scope=scopeRows().find(t=>[t.path,t.resolved_path].includes(source.file?.root));item=source.folder?source:{reference:{kind:'file',title:source.file.path.split('/').pop(),file_root:source.file.root,path:source.file.path,worktree:scope&&!scope.fixed?scope.id:null}};}
      else if(external){let urls;try{urls=JSON.parse(external);}catch{urls=external.split(/\r?\n/).filter(line=>line&&!line.startsWith('#'));}if(!Array.isArray(urls)||urls.length!==1||!validLinkUrl(urls[0]))throw new Error('Drop one full http or https link');item={reference:{kind:'link',title:new URL(urls[0]).hostname,url:urls[0]}};}
      if(item)void change({...item,type:'task-asset',objective_id:objective().id,task_id:id}).then(()=>{if(dialog?.querySelector('[data-task-id]')?.dataset.taskId===id)openTaskAssets(id);notify('Asset attached to task.');}).catch(()=>{});
    }catch(error){notify(error.message,true);}return;}
    try{if(raw){const {scope,...item}=JSON.parse(raw);if(scope!==key(context())||item.objective_id!==objective().id)throw new Error('Choose a resource in this objective');if(target.classList.contains('sess'))linkTerminal(bridge.session?.(target.dataset.name),item).catch(()=>{});else if(item.resource_id&&!target.hasAttribute('data-open-objective-tasks'))change({type:'scope',...item,worktree:target.dataset.objectiveWorktree||null}).catch(()=>{});}
      else if(assistant){const ref=JSON.parse(assistant),o=objective();change({type:'resource',objective_id:o.id,kind:'assistant',title:ref.title||'Assistant document',document_id:ref.document_id,assistant_root:ref.assistant_root,worktree:target.dataset.objectiveWorktree||null}).then(d=>{if(target.classList.contains('sess'))return change({type:'terminal',objective_id:o.id,session_id:terminalIdentity(bridge.session(target.dataset.name)),source:bridge.session(target.dataset.name).document_source,resource_id:d.objectives.find(item=>item.id===o.id).resources.at(-1).id});}).catch(()=>{});}
      else if(file&&target.classList.contains('sess'))linkTerminal(bridge.session?.(target.dataset.name),fileDropTarget(e.dataTransfer)).catch(()=>{});
      else if(terminal){const item=sidebarTarget(target);if(item)linkTerminal(bridge.session?.(terminal),item).catch(()=>{});}
    }catch(error){notify(error.message,true);}
  },true);
  window.LabObjectives={connect(adapter){bridge=adapter;},load,active,sidebarHtml,paint,worktrees,tree,associate,terminalHtml,taskForTerminal,openForTerminal,collapse,progress,complete,change,selectObjective,renderTasks,tabsHtml,showAll,
    openCurrent(){const params=new URLSearchParams(location.search),o=data()?.objectives.find(o=>o.id===params.get('objective'));if(o&&tasks(o).some(t=>t.id===params.get('objective_task'))){state().objective=o.id;openTask(params.get('objective_task'));return;}const f=taskFocus();if(f){openTask(f.task,f.mode);return;}state().view==='objective'&&objective()?selectObjective(objective().id):showAll();},
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
    leave(){closeSwitchMenu();releaseDraft();if(context()){collapse();state().focus=null;state().selected=null;persistView();}document.getElementById('sidebar')?.removeAttribute('data-objective-task-mode');document.querySelectorAll('.objective-task-asset-highlight').forEach(n=>n.classList.remove('objective-task-asset-highlight'));openView=null;dialog?.remove();dialog=null;clearTimeout(hoverTimer);}};
  document.addEventListener('keydown',event=>{if(activeLinkDraft?.node?.contains(event.target)&&(event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='s'){event.preventDefault();void saveLinkDetails(activeLinkDraft);}});
  window.addEventListener('beforeunload',event=>{if([...drafts.values()].some(dirtyDraft)||[...linkDrafts.values()].some(dirtyLink)){event.preventDefault();event.returnValue='';}});
})();
