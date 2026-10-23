/* One durable workspace conversation beside inspectable missions and evidence. */
(() => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const labels = {queued:'Queued',running:'Working',paused:'Paused',blocked:'Needs input',review:'Review',completed:'Completed',cancelled:'Cancelled',failed:'Failed'};
  const providerLabels = {codex:'Codex CLI',copilot:'Copilot CLI',claude:'Claude Code'};
  const views = new Map();
  let bridge, scope, host, data, timer, layoutObserver, mountObserver, generation = 0, loading = false, taskDialog, taskDetail, preview, previewVersion = 0;
  let selectedTask = null, detailTab = 'result', lastState = '', lastDetail = '', returnFocus, eventHistory = new Map(), allHistory = false;
  const key = s => `${s.vault || ''}:${s.workspace_id}`;
  const view = () => views.get(key(scope));
  const url = (path='', owner=scope) => `/api/agentic/${encodeURIComponent(owner.workspace_id)}${path}${path.includes('?')?'&':'?'}` + new URLSearchParams(owner.vault ? {vault:owner.vault} : {});
  const markdown = value => window.LabMarkdown?.render(String(value || '')) || `<pre>${esc(value)}</pre>`;
  const when = value => value ? new Date(value * 1000).toLocaleString() : '—';
  let notificationTimer, notificationsLoading=false;
  async function pollNotifications(){
    if(notificationsLoading)return;notificationsLoading=true;
    try{const response=await fetch('/api/agentic-notifications');if(response.ok){const result=await response.json();window.LabTerminalNotifications?.updateAgentic?.(result.notifications||[]);}}
    catch{}finally{notificationsLoading=false;}
  }
  async function openNotification(item){
    await bridge.navigate(item.workspace_path);
    if(scope?.workspace_id!==item.workspace_id||scope?.path!==item.workspace_path)throw Error('Could not open the notifying workspace.');
    if(item.task_id)await openTask(item.task_id);
    await request('/notifications/'+encodeURIComponent(item.report_id)+'/review',{method:'POST'},{workspace_id:item.workspace_id,vault:item.vault});
    await pollNotifications();
  }
  async function request(path='', options={}, owner=scope) {
    const response = await fetch(url(path,owner), options);
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw Error(result.detail || `Request failed (${response.status})`);
    return result;
  }
  function error(message) {host?.querySelectorAll('[data-agentic-error]').forEach(el=>{el.textContent=message;el.hidden=!message;});}
  async function action(actions) {
    const owner=scope;
    await request('/actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({actions})},owner);
    if(scope===owner)await refresh(true);
  }
  function leave() {
    generation++; clearInterval(timer);timer=null;loading=false;closeTask();
    mountObserver?.disconnect();mountObserver=null;
    layoutObserver?.disconnect();layoutObserver=null;document.body.classList.remove('agentic-workspace-open');
    host=null;scope=null;data=null;lastState='';
  }
  async function open(container, nextScope) {
    if (host?.isConnected && host.parentElement === container && scope?.path === nextScope.path) return refresh();
    leave();scope=nextScope;
    if(!views.has(key(scope))){let saved;try{saved=JSON.parse(localStorage.getItem('lab.agentic:'+key(scope)));}catch{}views.set(key(scope),{mission:saved?.mission||'',page:'missions',draft:saved?.draft||'',taskContext:null});}
    const owner=scope, version=generation;
    host=document.createElement('div');host.className='agentic-workspace';host.dataset.agenticWorkspace=scope.workspace_id;
    host.innerHTML=`<section class="agentic-center"><header class="agentic-header"><div><span class="agentic-eyebrow">AGENTIC WORKSPACE</span><h1>Missions</h1></div><div class="agentic-tabs"><button data-agentic-page="missions">Missions</button><button data-agentic-page="schedules">Schedules</button><button data-agentic-page="settings">Settings</button></div></header><div data-agentic-error class="agentic-error" role="alert" hidden></div><div data-agentic-main></div></section><aside class="agentic-chat" aria-label="Workspace coordinator"><header><strong>Coordinator</strong><span data-agentic-provider></span><small data-agentic-status></small><button data-coordinator-inspect>Inspect coordinator</button></header><div class="agentic-messages" data-agentic-messages role="log" aria-live="polite"></div><form data-agentic-compose><div data-agentic-context></div><label class="sr-only" for="agentic-message">Message to coordinator</label><textarea id="agentic-message" data-agentic-input rows="3" placeholder="Describe a mission, ask a question, or change priorities…"></textarea><footer><span>Your work stays in Lab</span><button type="submit">Send</button></footer></form></aside>`;
    container.replaceChildren(host);
    mountObserver=new MutationObserver(()=>{if(scope===owner&&!host?.isConnected)leave();});
    mountObserver.observe(container,{childList:true});
    document.body.classList.add('agentic-workspace-open');
    const size=()=>{if(scope===owner&&host?.isConnected)host.style.setProperty('--agentic-top',Math.max(0,container.getBoundingClientRect().top)+'px');};
    layoutObserver=new ResizeObserver(size);layoutObserver.observe(container);size();
    host.querySelector('[data-agentic-input]').value=view().draft;
    host.querySelector('[data-agentic-input]').oninput=event=>{view().draft=event.target.value;persist();};
    host.querySelector('[data-agentic-input]').onkeydown=event=>{if(event.key==='Enter'&&(event.metaKey||event.ctrlKey)){event.preventDefault();host.querySelector('form').requestSubmit();}};
    host.querySelector('form').onsubmit=send;
    host.querySelector('[data-coordinator-inspect]').onclick=()=>openTask('__coordinator__');
    host.querySelectorAll('[data-agentic-page]').forEach(button=>button.onclick=()=>{view().page=button.dataset.agenticPage;renderMain();});
    try{await bridge?.ready?.();if(scope!==owner||generation!==version)return;await refresh(true);timer=setInterval(()=>void refresh(),2000);}catch(e){if(scope===owner)error(e.message);}
  }
  function persist(){try{localStorage.setItem('lab.agentic:'+key(scope),JSON.stringify({mission:view().mission,draft:view().draft}));}catch{}}
  async function send(event) {
    event.preventDefault();const owner=scope,input=host.querySelector('[data-agentic-input]'),content=input.value.trim();if(!content)return;
    const button=host.querySelector('[type=submit]');button.disabled=true;
    const sentDraft=input.value,requestKey=JSON.stringify([content,view().mission,view().taskContext]);
    if(view().requestKey!==requestKey){view().requestKey=requestKey;view().requestId=crypto.randomUUID();}
    const requestId=view().requestId;
    try{
      await request('/messages',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content,request_id:requestId,mission_id:view().mission||null,task_id:view().taskContext})},owner);
      if(scope!==owner)return;
      view().requestId=null;view().requestKey=null;
      if(input.value===sentDraft){input.value='';view().draft='';persist();}
      view().taskContext=null;renderContext();error('');await refresh(true);
    }catch(e){if(scope===owner)error(e.message);}finally{if(scope===owner)button.disabled=false;}
  }
  async function refresh(force=false) {
    if(!scope||!host?.isConnected||loading)return;
    const owner=scope,version=generation;loading=true;
    try{
      const next=await request('',{},owner);if(scope!==owner||generation!==version)return;
      const encoded=JSON.stringify(next);data=next;
      if(force||encoded!==lastState){lastState=encoded;renderMain();renderChat();}
      if(selectedTask)await refreshTask(force);
      if(preview?.kind==='notebook')await previewAsset(preview.asset,true);
    }catch(e){if(scope===owner&&generation===version)error(e.message);}finally{if(scope===owner&&generation===version)loading=false;}
  }
  function renderChat() {
    if(!host||!data)return;
    host.querySelector('[data-agentic-provider]').textContent=providerLabels[data.provider]+(data.model?' · '+data.model:'');
    const active=data.runs.filter(r=>['starting','running','stopping'].includes(r.status));
    host.querySelector('[data-agentic-status]').textContent=`${active.filter(r=>r.role==='executor').length}/${data.settings.max_workers} executors · ${active.some(r=>r.role==='coordinator')?'Coordinating':data.settings.enabled?'Available':'Paused'}`;
    const messages=host.querySelector('[data-agentic-messages]'),atBottom=messages.scrollHeight-messages.scrollTop-messages.clientHeight<80;
    const html=data.messages.filter(m=>m.role!=='event').map(m=>`<article class="agentic-message ${esc(m.role)}"><div><strong>${m.role==='user'?'You':m.role==='notice'?'Needs attention':'Coordinator'}</strong><time>${esc(when(m.created))}</time></div><div class="doc">${markdown(m.content)}</div>${m.task_id?`<button data-message-task="${esc(m.task_id)}">Open task</button>`:''}${['pending','processing','failed'].includes(m.status)?`<small>${esc(m.status==='pending'?'Queued':m.status==='processing'?'Understanding your request…':'Could not process; your request is saved')}</small>`:''}</article>`).join('')||'<div class="agentic-welcome"><h2>What shall we work on?</h2><p>Describe the outcome. Your coordinator will confirm the plan, organize the tasks and keep you informed.</p></div>';
    if(messages.dataset.content!==html){messages.innerHTML=html;messages.dataset.content=html;messages.querySelectorAll('[data-message-task]').forEach(button=>button.onclick=()=>openTask(button.dataset.messageTask));if(atBottom)messages.scrollTop=messages.scrollHeight;}
    if(data.supervisor_error)error(data.supervisor_error);
    renderContext();
  }
  function renderContext(){if(!host)return;const task=data?.tasks.find(t=>t.id===view().taskContext);host.querySelector('[data-agentic-context]').innerHTML=task?`<span>About: ${esc(task.title)}</span><button type="button" aria-label="Clear task context">×</button>`:'';host.querySelector('[data-agentic-context] button')?.addEventListener('click',()=>{view().taskContext=null;renderContext();});}
  function taskRows(tasks,parent=null,depth=0) {
    return tasks.filter(t=>(t.parent_id||null)===parent).map(t=>`<button class="agentic-task" data-agentic-task="${esc(t.id)}" style="--depth:${depth}"><span class="agentic-task-title">${t.group?'▾ ':''}${esc(t.title)}</span><span class="agentic-state ${esc(t.status)}">${esc(labels[t.status])}</span><small>${esc(t.blocker||t.result||t.instruction).slice(0,240)}</small></button>${taskRows(tasks,t.id,depth+1)}`).join('');
  }
  function renderMain() {
    if(!host||!data)return;
    const body=host.querySelector('[data-agentic-main]'),s=view();
    host.querySelectorAll('[data-agentic-page]').forEach(button=>button.classList.toggle('active',button.dataset.agenticPage===s.page));
    // Avoid replacing a settings form while the user edits it.
    if(s.page==='settings'&&body.querySelector('form')?.contains(document.activeElement))return;
    if(s.page==='settings'){
      body.innerHTML=`<form class="agentic-settings"><h2>Workspace settings</h2><label>Agent<select name="provider"><option value="">Inherit Lab Settings (${esc(providerLabels[data.provider])})</option>${data.providers.map(p=>`<option value="${p.id}"${data.settings.provider===p.id?' selected':''}>${providerLabels[p.id]}${p.available?'':' — not installed'}</option>`).join('')}</select></label><label>Model override<input name="model" value="${esc(data.settings.model||'')}" placeholder="Inherit Lab Settings"></label><label>Concurrent executors<input name="max_workers" type="number" min="1" max="5" value="${data.settings.max_workers}"></label><label>Reminder interval (hours)<input name="reminder_hours" type="number" min="0.017" max="168" step="any" value="${data.settings.reminder_seconds/3600}"></label><label>Schedule timezone<input name="timezone" value="${esc(data.settings.timezone)}"></label><label class="agentic-check"><input name="enabled" type="checkbox"${data.settings.enabled?' checked':''}> Start new work automatically</label><button type="submit">Save settings</button><p>Running tasks keep their current agent. Changes apply to subsequent executions.</p><h2>Workspace memory</h2>${data.memory.map(m=>`<details><summary>${esc(m.id)}</summary><div class="doc">${markdown(m.content)}</div></details>`).join('')||'<p>No durable facts recorded yet.</p>'}</form>`;
      body.querySelector('form').onsubmit=async event=>{event.preventDefault();const owner=scope,form=new FormData(event.target);try{await request('/settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider:form.get('provider')||null,model:form.get('model')||null,max_workers:Number(form.get('max_workers')),reminder_seconds:Math.round(Number(form.get('reminder_hours'))*3600),timezone:form.get('timezone'),enabled:form.has('enabled')})},owner);if(scope===owner){document.activeElement?.blur();await refresh(true);error('');}}catch(e){if(scope===owner)error(e.message);}};
      return;
    }
    if(s.page==='schedules'){
      body.innerHTML=`<h2>Schedules</h2><p>Ask the coordinator to create a recurring check or a cron schedule.</p>${data.schedules.map(row=>`<article class="agentic-mission"><h3>${esc(row.title)}</h3><p>${esc(row.instruction)}</p><small>${row.cron?esc(row.cron)+' · '+esc(row.timezone):'Every '+row.interval_seconds/60+' minutes'} · Next: ${esc(when(row.next_due))}</small><button data-schedule="${esc(row.id)}" data-enable="${!row.enabled}">${row.enabled?'Pause':'Resume'}</button></article>`).join('')||'<p>No schedules yet.</p>'}`;
      body.querySelectorAll('[data-schedule]').forEach(button=>button.onclick=()=>action([{type:button.dataset.enable==='true'?'schedule-resume':'schedule-pause',id:button.dataset.schedule}]).catch(e=>error(e.message)));
      return;
    }
    if(s.mission&&!data.missions.some(m=>m.id===s.mission))s.mission='';
    const mission=data.missions.find(m=>m.id===s.mission);
    const tasks=mission?data.tasks.filter(t=>t.mission_id===mission.id):data.tasks;
    body.innerHTML=`<div class="agentic-mission-picker"><label>Mission<select data-agentic-mission><option value="">All missions</option>${data.missions.map(m=>`<option value="${esc(m.id)}"${s.mission===m.id?' selected':''}>${esc(m.title)}</option>`).join('')}</select></label><span>${tasks.filter(t=>!t.group&&t.status==='completed').length}/${tasks.filter(t=>!t.group).length} tasks completed</span></div>${mission?`<article class="agentic-mission"><h2>${esc(mission.title)}</h2><div class="doc">${markdown(mission.objective)}</div>${mission.result?`<details open><summary>Mission outcome</summary><div class="doc">${markdown(mission.result)}</div></details>`:''}</article>`:''}<div class="agentic-task-list">${mission?taskRows(tasks):data.missions.map(m=>`<section><h2><button data-open-mission="${esc(m.id)}">${esc(m.title)}</button><small>${esc(m.status)}</small></h2>${taskRows(tasks.filter(t=>t.mission_id===m.id))||'<p>No tasks yet.</p>'}</section>`).join('')||'<div class="agentic-empty"><span>◎</span><h2>A mission starts with a conversation</h2><p>Tell the coordinator what you want to accomplish. Tasks, outcomes and supporting files will appear here.</p></div>'}</div>`;
    body.querySelector('[data-agentic-mission]').onchange=event=>{s.mission=event.target.value;persist();renderMain();};
    body.querySelectorAll('[data-open-mission]').forEach(button=>button.onclick=()=>{s.mission=button.dataset.openMission;persist();renderMain();});
    body.querySelectorAll('[data-agentic-task]').forEach(button=>button.onclick=()=>openTask(button.dataset.agenticTask));
  }
  function closeTask(){previewVersion++;preview=null;selectedTask=null;taskDetail=null;taskDialog?.remove();taskDialog=null;lastDetail='';eventHistory=new Map();allHistory=false;returnFocus?.focus?.({preventScroll:true});}
  async function openTask(id) {
    if(!data || (id!=='__coordinator__'&&!data.tasks.some(t=>t.id===id)))return;
    closeTask();returnFocus=document.activeElement;selectedTask=id;detailTab='result';
    taskDialog=document.createElement('section');taskDialog.className='agentic-task-dialog';taskDialog.setAttribute('role','dialog');taskDialog.setAttribute('aria-label','Task details');
    taskDialog.innerHTML='<header><div data-task-heading></div><button data-task-close aria-label="Close task details">×</button></header><nav data-task-tabs></nav><div data-task-controls></div><div data-agentic-error class="agentic-error" role="alert" hidden></div><div data-task-body></div>';
    host.querySelector('.agentic-center').append(taskDialog);taskDialog.querySelector('[data-task-close]').onclick=closeTask;taskDialog.querySelector('[data-task-close]').focus();
    await refreshTask(true);
  }
  async function refreshTask(force=false) {
    const owner=scope,id=selectedTask,dialog=taskDialog;if(!id||!dialog)return;
    try{const result=await request('/tasks/'+encodeURIComponent(id),{},owner);if(scope!==owner||selectedTask!==id||taskDialog!==dialog)return;const encoded=JSON.stringify(result);taskDetail=result;result.events.forEach(row=>eventHistory.set(row.seq,row));if(force||encoded!==lastDetail){lastDetail=encoded;renderTask();}}catch(e){if(scope===owner&&taskDialog===dialog)dialog.querySelector('[data-task-body]').textContent=e.message;}
  }
  function renderTask() {
    if(!taskDialog||!taskDetail)return;
    const task=taskDetail.task;
    taskDialog.querySelector('[data-task-heading]').innerHTML=`<small>${esc(data.missions.find(m=>m.id===task.mission_id)?.title)}</small><h2>${esc(task.title)}</h2><span class="agentic-state ${esc(task.status)}">${esc(labels[task.status])}</span>`;
    taskDialog.querySelector('[data-task-tabs]').innerHTML=['result','assignment','activity','files'].map(tab=>`<button data-task-tab="${tab}" class="${tab===detailTab?'active':''}">${{result:'Result',assignment:'Assignment',activity:'Activity',files:'Files & sources'}[tab]}</button>`).join('');
    taskDialog.querySelectorAll('[data-task-tab]').forEach(button=>button.onclick=()=>{detailTab=button.dataset.taskTab;preview=null;previewVersion++;renderTask();});
    const controls=[];
    if(task.status==='review')controls.push(['approve','Approve']);
    if(['running','queued'].includes(task.status))controls.push(['pause','Pause']);
    if(['paused','blocked'].includes(task.status)&&!task.active_run)controls.push(['resume','Resume']);
    if(task.status==='failed')controls.push(['retry','Retry']);
    if(!['completed','cancelled'].includes(task.status))controls.push(['cancel','Stop task']);
    if(['blocked','review'].includes(task.status))controls.push(['snooze','Remind in 2 hours']);
    taskDialog.querySelector('[data-task-controls]').hidden=!!taskDetail.coordinator;
    taskDialog.querySelector('[data-task-controls]').innerHTML=controls.map(([control,label])=>`<button data-task-control="${control}">${label}</button>`).join('')+'<button data-task-discuss>Discuss in chat</button>';
    taskDialog.querySelectorAll('[data-task-control]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await action([{type:'task-'+button.dataset.taskControl,id:task.id,...(button.dataset.taskControl==='snooze'?{seconds:7200}:{})}]);}catch(e){error(e.message);}finally{button.disabled=false;}});
    taskDialog.querySelector('[data-task-discuss]').onclick=()=>{view().taskContext=task.id;renderContext();host.querySelector('[data-agentic-input]').focus();};
    if(preview)return;
    const body=taskDialog.querySelector('[data-task-body]'),scroll=body.scrollTop;
    if(detailTab==='result')body.innerHTML=`${task.blocker?`<div class="agentic-blocker"><strong>${task.status==='review'?'Waiting for your review':'Needs input'}</strong><div class="doc">${markdown(task.blocker)}</div><small>Next reminder: ${esc(when(task.next_reminder))}</small></div>`:''}<article class="doc">${markdown(task.result||'No outcome yet. The task’s results and verification will appear here.')}</article>${task.checkpoint?`<details><summary>Saved checkpoint</summary><div class="doc">${markdown(task.checkpoint)}</div></details>`:''}${fileList(taskDetail.assets.filter(a=>a.role==='output'))}`;
    if(detailTab==='assignment')body.innerHTML=`<h3>Current task instruction</h3><pre>${esc(task.instruction)}</pre>${task.context?`<h3>Task context</h3><pre>${esc(task.context)}</pre>`:''}<h3>Assignments actually sent</h3>${taskDetail.runs.map((run,index)=>`<details${index===taskDetail.runs.length-1?' open':''}><summary>${esc(providerLabels[run.provider])} · ${esc(when(run.created))} · ${esc(run.status)}</summary><p>Run ${esc(run.id)}</p><pre>${esc(run.prompt||'Preparing assignment…')}</pre><details><summary>Launch command</summary><pre>${esc(JSON.stringify(run.argv,null,2))}</pre></details></details>`).join('')||'<p>No executor has been assigned yet.</p>'}`;
    if(detailTab==='activity'){
      const events=[...eventHistory.values()].sort((a,b)=>a.seq-b.seq);
      body.innerHTML=(!allHistory&&events.length?'<button data-events-earlier>Load earlier activity</button>':'')+events.map(event=>`<details class="agentic-event"><summary><time>${esc(when(event.at))}</time> ${esc(event.kind)}</summary><pre>${esc(JSON.stringify(event.body,null,2))}</pre></details>`).join('')||'<p>No activity yet.</p>';
      body.querySelector('[data-events-earlier]')?.addEventListener('click',async()=>{const owner=scope,id=selectedTask;try{const response=await request('/events?'+new URLSearchParams({task_id:id,before:events[0].seq,latest:true}),{},owner);if(scope!==owner||selectedTask!==id)return;response.events.forEach(row=>eventHistory.set(row.seq,row));allHistory=response.events.length<500;renderTask();}catch(e){error(e.message);}});
    }
    if(detailTab==='files'){
      body.innerHTML=(fileList(taskDetail.assets)||'<p>No assets have been registered yet.</p>')+(taskDetail.files?.length?'<h3>Reported file changes</h3>'+taskDetail.files.map((file,index)=>`<button class="agentic-file-change" data-reported-file="${index}"${file.operation==='deleted'?' disabled':''}><strong>${esc(file.path)}</strong><small>${esc(file.operation)} · Run ${esc(file.run_id)}</small></button>`).join(''):'');
      body.querySelectorAll('[data-reported-file]').forEach(button=>button.onclick=()=>bridge.openFile(taskDetail.files[Number(button.dataset.reportedFile)].path.slice(scope.path.length+1),scope.path));
    }
    const permissions=(taskDetail.permissions||[]).filter(p=>['pending','decided'].includes(p.status));
    if(detailTab==='result'&&permissions.length){
      body.insertAdjacentHTML('afterbegin',permissions.map(p=>`<section class="agentic-blocker"><strong>Copilot permission: ${esc(p.request.toolCall?.title||'Operation')}</strong><pre>${esc(JSON.stringify(p.request.toolCall,null,2))}</pre>${p.status==='decided'?'<p>Decision saved; waiting for execution capacity.</p>':p.request.options.filter(o=>['allow_once','reject_once'].includes(o.kind)).map(o=>`<button data-permission="${esc(p.id)}" data-option="${esc(o.optionId)}">${esc(o.name)}</button>`).join('')}</section>`).join(''));
      body.querySelectorAll('[data-permission]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await action([{type:'permission-respond',id:button.dataset.permission,option_id:button.dataset.option}]);}catch(e){error(e.message);}finally{button.disabled=false;}});
    }
    body.querySelectorAll('[data-agentic-asset]').forEach(button=>button.onclick=()=>previewAsset(taskDetail.assets.find(a=>a.id===button.dataset.agenticAsset)));
    body.scrollTop=scroll;
  }
  function fileList(assets){return assets.length?`<div class="agentic-assets">${assets.map(a=>`<button data-agentic-asset="${esc(a.id)}"><strong>${esc(a.title)}</strong><span>${esc(a.role)} · ${esc(a.origin)}</span><small>${esc(a.description||a.target)}</small></button>`).join('')}</div>`:'';}
  async function previewAsset(asset, polling=false) {
    if(!asset||!taskDialog)return;
    if(asset.kind==='url'){window.open(asset.target,'_blank','noopener,noreferrer');return;}
    const owner=scope,dialog=taskDialog,version=polling?previewVersion:++previewVersion;
    try{
      const result=await request('/assets/'+encodeURIComponent(asset.id),{},owner);if(scope!==owner||taskDialog!==dialog||version!==previewVersion)return;
      const signature=JSON.stringify(result);if(polling&&preview?.signature===signature)return;
      preview={asset,kind:result.kind,signature};
      const body=dialog.querySelector('[data-task-body]'),scroll=body.scrollTop,source=url('/assets/'+encodeURIComponent(asset.id)+'/content',owner);
      body.innerHTML=`<div class="agentic-preview-head"><button data-preview-back>← Back</button><strong>${esc(asset.title)}</strong><a href="${source}&download=true" download>Download</a></div><p>${esc(asset.description)}<br><small>${esc(asset.target)} · ${esc(asset.role)} · Run ${esc(asset.run_id||'user')}</small></p><div data-asset-preview></div>`;
      body.querySelector('[data-preview-back]').onclick=()=>{preview=null;previewVersion++;renderTask();};
      const target=body.querySelector('[data-asset-preview]');
      if(result.kind==='notebook'){bridge.renderNotebook(result.cells,target);}
      else if(result.kind==='markdown')target.innerHTML=`<article class="doc">${markdown(result.content)}</article>`;
      else if(result.kind==='text')target.innerHTML=`<pre>${esc(result.content)}</pre>`;
      else if(result.kind==='image')target.innerHTML=`<img src="${source}" alt="${esc(asset.title)}">`;
      else if(result.kind==='video')target.innerHTML=`<video src="${source}" controls></video>`;
      else if(result.kind==='audio')target.innerHTML=`<audio src="${source}" controls></audio>`;
      else if(result.kind==='pdf')target.innerHTML=`<iframe title="${esc(asset.title)}" src="${source}"></iframe>`;
      else target.textContent='Use Download to open this file.';
      if(polling)body.scrollTop=scroll;
    }catch(e){if(scope===owner&&taskDialog===dialog)error(e.message);}
  }
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&taskDialog){event.preventDefault();closeTask();}});
  window.LabAgentic={connect(adapter){bridge=adapter;if(adapter.navigate){clearInterval(notificationTimer);void pollNotifications();notificationTimer=setInterval(pollNotifications,8000);}},open,leave,openTask,refresh,openNotification};
})();
