/* Saved workspace commands launch only after an explicit picker confirmation. */
(() => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const url = scope => '/api/term/automations?' + new URLSearchParams({workspace_id:scope.id,...(scope.vault?{vault:scope.vault}:{})});
  async function api(url, body) {
    const response=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Could not load or launch terminal automations.');
    return data;
  }

  const terminalIcon='<svg class="term-automation-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="3" width="20" height="18" rx="3"/><path d="M2 9h20M6 13l3 3-3 3m7-1h4"/></svg>';
  function iconHtml(icon) {
    if(icon?.emoji)return esc(icon.emoji);
    if(icon?.service&&/^[a-z][a-z0-9-]{0,63}$/.test(icon.service))return window.LabScopeLinks?.icon({kind:'external',type:icon.service})||`<span class="scope-link-icon" data-link-service="${esc(icon.service)}" aria-hidden="true"></span>`;
    if(icon?.image&&/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(icon.image))return `<img class="term-automation-icon" width="20" height="20" src="${esc(icon.image)}" alt="">`;
    return terminalIcon;
  }
  function inheritedAppearance(session, byLogical, parents) {
    const own=session.automation_appearance;
    if(own&&!own.inherit_icon)return own;
    const seen=new Set();let current=session,icon=own?.icon;
    while(current&&!seen.has(current.logical_name)){
      seen.add(current.logical_name);
      const appearance=current.automation_appearance;
      if(appearance){icon=appearance.icon||icon;if(!appearance.inherit_icon)break;}
      current=byLogical.get(parents[current.logical_name]);
    }
    return icon?{...(own||{color:null,role:'child'}),icon}:own||null;
  }
  function appearanceEditor(host, initial, {child=false, parentIcon=()=>null, name=()=>child?'Child terminal':'Main terminal', changed=()=>{}}={}) {
    let icon=initial.icon??(child?null:{builtin:'terminal'});
    const services=window.LAB_LINK_SERVICES||[{id:'github',name:'GitHub'}];
    host.innerHTML=`<details class="term-automation-appearance"><summary>Icon and text color</summary><div class="term-automation-look-preview"><span data-look-icon aria-hidden="true"></span><span data-look-name></span></div><label class="term-automation-field"><span>Icon</span><select data-icon-choice>${child?'<option value="inherit">Inherit main icon</option>':''}<option value="terminal">Terminal outline</option><optgroup label="Service icons">${services.map(s=>`<option value="service:${esc(s.id)}">${esc(s.name)}</option>`).join('')}</optgroup><optgroup label="Emoji"><option value="emoji:💻">💻 Computer</option><option value="emoji:⚙️">⚙️ Settings</option><option value="emoji:🚀">🚀 Launch</option><option value="emoji:📋">📋 Logs</option><option value="custom">Custom emoji…</option></optgroup><option value="image">Uploaded PNG…</option></select></label><label class="term-automation-field" data-custom-emoji><span>Emoji</span><input data-emoji maxlength="32" placeholder="Paste an emoji"></label><label class="term-automation-field" data-image-upload><span>PNG icon · up to 256 × 256 and 64 KB</span><input data-icon-file type="file" accept="image/png"></label><div class="term-automation-colors"><label><span>Text and icon color</span><input data-look-color type="color" value="${esc(initial.color|| (child?'#ffffff':'#3fb950'))}"></label><label><input data-look-default type="checkbox" ${!initial.color||!child&&initial.color==='#3fb950'?'checked':''}>${child?'White (default)':'Default green'}</label></div><small data-look-error role="status"></small></details>`;
    const choice=host.querySelector('[data-icon-choice]'),emoji=host.querySelector('[data-emoji]'),color=host.querySelector('[data-look-color]'),reset=host.querySelector('[data-look-default]');
    choice.value=icon?.image?'image':icon?.service?'service:'+icon.service:icon?.emoji?'custom':child&&!icon?'inherit':'terminal';
    emoji.value=icon?.emoji||'';
    const read=()=>({icon,color:reset.checked?(child?null:'#3fb950'):color.value});
    const paint=()=>{const value=read();host.querySelector('[data-look-icon]').innerHTML=iconHtml(value.icon||parentIcon());host.querySelector('[data-look-name]').textContent=name();host.querySelector('.term-automation-look-preview').style.color=value.color||'var(--text-primary)';host.querySelector('[data-custom-emoji]').hidden=choice.value!=='custom';host.querySelector('[data-image-upload]').hidden=choice.value!=='image';};
    choice.onchange=()=>{const value=choice.value;icon=value==='inherit'?null:value==='terminal'?{builtin:'terminal'}:value.startsWith('service:')?{service:value.slice(8)}:value.startsWith('emoji:')?{emoji:value.slice(6)}:value==='custom'?(emoji.value?{emoji:emoji.value}:null):icon;paint();changed();};
    emoji.oninput=()=>{icon=emoji.value?{emoji:emoji.value}:null;paint();changed();};
    color.oninput=()=>{reset.checked=false;paint();changed();};reset.onchange=()=>{paint();changed();};
    host.querySelector('[data-icon-file]').onchange=async event=>{
      const file=event.target.files[0],status=host.querySelector('[data-look-error]');if(!file)return;
      try{
        if(file.type!=='image/png'||file.size>65536)throw Error('Choose a PNG icon of at most 64 KB.');
        const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('Could not read this icon.'));reader.readAsDataURL(file);});
        const image=new Image();image.src=data;await image.decode();
        if(image.width>256||image.height>256)throw Error('Choose a PNG icon no larger than 256 × 256.');
        icon={image:data};status.textContent='';paint();changed();
      }catch(error){status.textContent=error.message;}
    };
    paint();return {read,paint};
  }

  function editor(host, rows, dirty) {
    host.innerHTML='<div data-recipes></div><p class="settings-hint" data-empty>No automations yet. Add one to save a group of commands.</p><button type="button" data-add-automation>+ Automation</button>';
    const list=host.querySelector('[data-recipes]');
    const refresh=()=>{host.querySelector('[data-empty]').hidden=!!list.children.length;host.querySelector('[data-add-automation]').disabled=list.children.length>=32;};
    const label=(name,control)=>`<label class="term-automation-field"><span>${name}</span>${control}</label>`;
    function add(row={id:crypto.randomUUID(),name:'',steps:[{label:'',cwd:'',command:''}]}) {
      const card=document.createElement('details');card.className='settings-folder term-automation-recipe';card.dataset.automation=row.id;card.open=true;
      card.innerHTML=`<summary>${esc(row.name||'New automation')}</summary>${label('Automation name',`<input data-name value="${esc(row.name)}" required maxlength="120" placeholder="Development services">`)}${label('Seconds between launches',`<input data-launch-delay type="number" min="0" max="300" step="any" required value="${esc(row.launch_delay_seconds??5)}">`)}<p class="settings-hint">Wait between initial launches and reconnecting this automation’s terminals. Default: 5 seconds. Set 0 to start without a delay (maximum 300 seconds).</p><div data-steps></div><div class="term-automation-actions"><button type="button" data-add-step>+ Terminal</button><button type="button" data-remove-automation>Remove automation</button></div>`;
      const steps=card.querySelector('[data-steps]');
      const look=document.createElement('div');steps.before(look);
      const paintChildren=()=>[...steps.children].forEach(step=>step._appearance?.paint());
      const appearance=appearanceEditor(look,row,{name:()=>card.querySelector('[data-name]').value||'Main terminal',changed:()=>{paintChildren();dirty();}});
      const hint=document.createElement('p');hint.className='settings-hint';hint.textContent='The first terminal is the main tab when launched on its own. An existing parent keeps its name. Children inherit the main icon and default to white text; override either below.';look.append(hint);
      card._appearance=appearance;
      function reorder() { [...steps.children].forEach((step,index)=>{step.querySelector('[data-up]').disabled=index===0;step.querySelector('[data-down]').disabled=index===steps.children.length-1;});card.querySelector('[data-add-step]').disabled=steps.children.length>=20;paintChildren(); }
      function step(row={}) {
        const child=document.createElement('div');child.className='term-automation-step';child.dataset.step='';
        child.innerHTML=`${label('Terminal name',`<input data-label value="${esc(row.label)}" required maxlength="120" placeholder="Frontend">`)}${label('Working directory',`<input data-cwd value="${esc(row.cwd)}" maxlength="4096" placeholder="Launch folder, or e.g. ./frontend">`)}${label('Command',`<textarea data-command rows="3" required maxlength="16000" spellcheck="false" placeholder="npm run dev">${esc(row.command)}</textarea>`)}<div class="term-automation-actions"><button type="button" data-up aria-label="Start this terminal earlier">↑</button><button type="button" data-down aria-label="Start this terminal later">↓</button><button type="button" data-remove-step>Remove terminal</button></div>`;
        const extras=document.createElement('div');
        extras.innerHTML=`<details class="term-automation-guides-editor" ${row.guidelines?.length?'open':''}><summary>Guidelines (optional)</summary><p class="settings-hint">Notes and commands to copy after opening this terminal. These are never executed automatically.</p><div data-guides></div><button type="button" data-add-guide>+ Guideline</button></details><details><summary>Background service check (optional)</summary><p class="settings-hint">Use when the launch command returns while its service keeps running. The check runs in this terminal's working directory: exit 0 means running, exit 1 means stopped. Other errors leave its status unknown.</p>${label('Health check',`<textarea data-health-command rows="2" maxlength="16000" spellcheck="false">${esc(row.health_command)}</textarea>`)}</details>`;
        child.append(extras);
        const look=document.createElement('div');extras.before(look);
        child._appearance=appearanceEditor(look,row,{child:true,parentIcon:()=>steps.firstElementChild?._appearance.read().icon||appearance.read().icon,name:()=>child.querySelector('[data-label]').value||'Child terminal',changed:()=>{paintChildren();dirty();}});
        child.querySelector('[data-label]').addEventListener('input',()=>child._appearance.paint());
        const guides=child.querySelector('[data-guides]');
        const addGuide=(guide={})=>{
          const node=document.createElement('div');node.className='term-automation-guide-editor';node.dataset.guide='';
          node.innerHTML=label('Label (optional)',`<input data-guide-title maxlength="160" value="${esc(guide.title)}" placeholder="Launch with debugger">`)+label('Instructions or command',`<textarea data-guide-text rows="3" required maxlength="16000" spellcheck="false">${esc(guide.text)}</textarea>`)+'<button type="button" data-remove-guide>Remove guideline</button>';
          node.querySelector('[data-remove-guide]').onclick=()=>{node.remove();child.querySelector('[data-add-guide]').disabled=false;dirty();};guides.append(node);
          child.querySelector('[data-add-guide]').disabled=guides.children.length>=20;return node;
        };
        (row.guidelines||[]).forEach(addGuide);
        child.querySelector('[data-add-guide]').onclick=()=>{addGuide().querySelector('textarea').focus();dirty();};
        child.querySelector('[data-remove-step]').onclick=()=>{child.remove();reorder();dirty();};
        child.querySelector('[data-up]').onclick=()=>{if(child.previousElementSibling)steps.insertBefore(child,child.previousElementSibling);reorder();dirty();};
        child.querySelector('[data-down]').onclick=()=>{if(child.nextElementSibling)steps.insertBefore(child.nextElementSibling,child);reorder();dirty();};
        steps.append(child);reorder();return child;
      }
      row.steps.forEach(step);
      card.querySelector('[data-name]').oninput=event=>{card.querySelector('summary').textContent=event.target.value||'New automation';appearance.paint();};
      card.querySelector('[data-add-step]').onclick=()=>{step().querySelector('input').focus();dirty();};
      card.querySelector('[data-remove-automation]').onclick=()=>{card.remove();refresh();dirty();};
      list.append(card);refresh();return card;
    }
    rows.forEach(add);refresh();
    host.querySelector('[data-add-automation]').onclick=()=>{add().querySelector('input').focus();dirty();};
    return () => [...list.children].map(card=>{
      const steps=[...card.querySelector('[data-steps]').children].map(step=>({...step._appearance.read(),label:step.querySelector('[data-label]').value.trim(),cwd:step.querySelector('[data-cwd]').value.trim(),command:step.querySelector('[data-command]').value,health_command:step.querySelector('[data-health-command]').value,guidelines:[...step.querySelector('[data-guides]').children].map(guide=>({title:guide.querySelector('[data-guide-title]').value.trim(),text:guide.querySelector('[data-guide-text]').value}))}));
      const name=card.querySelector('[data-name]').value.trim();
      const delay=card.querySelector('[data-launch-delay]'),launch_delay_seconds=delay.valueAsNumber;
      if(!delay.validity.valid||!Number.isFinite(launch_delay_seconds))throw new Error('Enter a launch delay from 0 to 300 seconds.');
      if(!name||!steps.length||steps.some(step=>!step.label||!step.command.trim()))throw new Error('Each automation needs a name and at least one named terminal with a command.');
      if(steps.some(step=>step.guidelines.some(guide=>!guide.text.trim())))throw new Error('Enter instructions or a command for each guideline, or remove it.');
      return {id:card.dataset.automation,name,launch_delay_seconds,...card._appearance.read(),steps};
    });
  }

  let active=null;
  async function open({scope,parent,tasks=[],task,current,adopt,configure}) {
    if(active)return;
    const focus=document.activeElement,dialog=document.createElement('dialog');
    dialog.id='termAutomationLauncher';dialog.className='lab-settings-center term-automation-launcher';dialog.setAttribute('aria-labelledby','termAutomationTitle');
    const description=parent?`Open an automation group under <strong>${esc(parent.label||parent.logical_name)}</strong> in ${esc(scope.label)}.`
      :'The first defined terminal becomes the chosen task’s primary terminal; the remaining terminals open beneath it.';
    dialog.innerHTML=`<header><strong id="termAutomationTitle">Launch automation</strong><button type="button" data-close aria-label="Close automation launcher">×</button></header><div class="term-automation-body"><p>${description}</p><label class="term-automation-field"><span>In progress task</span><select data-task-choice required><option value="">Choose an In progress task…</option>${tasks.map((t,index)=>`<option value="${index}">${esc(t.objective_name)} / ${esc(t.title)}</option>`).join('')}</select></label><p class="settings-hint" data-task-summary></p><label class="term-automation-field"><span>Automation</span><select data-choice disabled><option>Loading…</option></select></label><p class="settings-hint" data-hint>Commands start in order and run independently. Exited commands keep their logs and open a shell.</p><div data-preview></div></div><footer><span role="status" aria-live="polite" data-status></span><div class="term-automation-actions"><button type="button" data-configure>Configure automations</button><button type="button" class="settings-save" data-launch disabled>Launch</button></div></footer>`;
    document.body.append(dialog);dialog.showModal();active=dialog;
    const status=dialog.querySelector('[data-status]'),choice=dialog.querySelector('[data-choice]'),launch=dialog.querySelector('[data-launch]'),preview=dialog.querySelector('[data-preview]');
    const taskChoice=dialog.querySelector('[data-task-choice]');
    const selectedIndex=tasks.findIndex(t=>t.id===task?.id&&t.objective_id===task?.objective_id);
    if(selectedIndex>=0)taskChoice.value=String(selectedIndex);
    const selectedTask=()=>taskChoice.value===''?null:tasks[Number(taskChoice.value)];
    let running=false,review=0,catalog,closed=false;
    const valid=()=>!closed&&active===dialog&&current();
    const message=(text,error=false)=>{if(!closed){status.textContent=text;status.classList.toggle('error',error);}};
    const close=()=>{if(running)return;closed=true;review++;active=null;dialog.close();dialog.remove();if(focus?.isConnected)focus.focus();};
    dialog.querySelector('[data-close]').onclick=close;
    dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
    dialog.addEventListener('click',event=>{if(event.target===dialog)close();});
    dialog.querySelector('[data-configure]').onclick=()=>{close();configure();};
    const base=()=>({workspace_id:scope.id,vault:scope.vault,...(parent?{parent:parent.name}:{cwd:selectedTask().path}),objective_id:selectedTask().objective_id,task_id:selectedTask().id,automation_id:choice.value,revision:catalog.revision,run_id:crypto.randomUUID()});
    async function show() {
      const token=++review;launch.disabled=true;preview.replaceChildren();message('Checking working directories…');
      if(!valid()){message('The workspace or task context changed. Close and reopen this launcher.',true);return;}
      const task=selectedTask();
      dialog.querySelector('[data-task-summary]').textContent=task?`Attached to ${task.title}. Pausing this task hides the entire automation group.`:'';
      if(!task){message(tasks.length?'Choose an In progress task before launching.':'No In progress tasks. Set a task to In progress, then reopen this launcher.',true);return;}
      if(!catalog?.automations.length)return;
      try {
        const data=await api('/api/term/automations/launch',{...base(),preview:true});
        if(token!==review||closed)return;
        if(!valid()){message('The workspace or task context changed. Close and reopen this launcher.',true);return;}
        preview.innerHTML=data.steps.map((step,index)=>`<section class="term-automation-preview"><strong style="color:${esc(step.appearance?.color||'var(--text-primary)')}"><span class="term-automation-preview-icon">${iconHtml(step.appearance?.icon)}</span>${index+1}. ${esc(step.label)}${!parent&&index===0?' · Primary':''}</strong><small>${esc(step.cwd)}</small><pre>${esc(step.command)}</pre></section>`).join('');
        const delay=data.launch_delay_seconds??5;
        dialog.querySelector('[data-hint]').textContent=(data.steps.length===1?'One terminal starts immediately.':delay?`The first terminal starts immediately, then Lab waits ${delay} second${delay===1?'':'s'} between launches.`:'Terminals start in order with no delay between launches.')+' Commands run independently; exited commands keep their logs and open a shell.';
        launch.disabled=false;message(`${data.steps.length} ${parent?'child ':''}terminal${data.steps.length===1?'':'s'} ready`);
      }catch(error){if(token===review)message(error.message,true);}
    }
    choice.onchange=()=>void show();
    taskChoice.onchange=()=>void show();
    launch.onclick=async()=>{
      if(running||launch.disabled)return;
      if(!valid()){launch.disabled=true;message('The workspace or task context changed. Close and reopen this launcher.',true);return;}
      running=true;launch.disabled=true;choice.disabled=true;taskChoice.disabled=true;dialog.querySelector('[data-configure]').disabled=true;dialog.querySelector('[data-close]').disabled=true;message('Starting terminals…');
      try {
        const data=await api('/api/term/automations/launch',base());
        await adopt(data.sessions||[]);
        running=false;
        if(data.error){message(`${data.sessions.length} started. ${data.error}`,true);dialog.querySelector('[data-close]').disabled=false;return;}
        close();
      }catch(error){running=false;message(error.message+' Check the terminal tabs before launching again.',true);dialog.querySelector('[data-close]').disabled=false;}
    };
    try {
      catalog=await api(url(scope));
      if(closed)return;
      choice.innerHTML=catalog.automations.length?catalog.automations.map(row=>`<option value="${esc(row.id)}">${esc(row.name)}</option>`).join(''):'<option>No saved automations</option>';
      choice.disabled=!catalog.automations.length;
      if(catalog.automations.length){choice.focus();await show();}else message('Add an automation in this workspace’s settings first.');
    }catch(error){message(error.message,true);}
  }
  async function status(scope, rows) {
    const data=await api('/api/term/automations/status?'+new URLSearchParams({workspace_id:scope.id,...(scope.vault?{vault:scope.vault}:{})}));
    const merged=new Map(rows.map(row=>[row.logical_name,row]));
    for(const row of data.sessions||[]) merged.set(row.logical_name,{...(merged.get(row.logical_name)||{}),...row});
    return [...merged.values()];
  }

  function recoveryTargets(parent, sessions, parents) {
    const descendants=new Set([parent.logical_name]);
    let changed=true;
    while(changed){changed=false;for(const [child,owner] of Object.entries(parents)){if(descendants.has(owner)&&!descendants.has(child)){descendants.add(child);changed=true;}}}
    return sessions.filter(row=>descendants.has(row.logical_name)&&row.automation?.can_relaunch&&!row.document_source)
      .map(row=>({logical_name:row.logical_name,launch_id:row.automation.launch_id}));
  }

  function restartTargets(parent, sessions, parents) {
    const descendants=new Set();
    let owners=new Set([parent.logical_name]);
    while(owners.size){
      const next=new Set();
      for(const [child,owner] of Object.entries(parents))if(owners.has(owner)&&!descendants.has(child)){descendants.add(child);next.add(child);}
      owners=next;
    }
    return sessions.filter(row=>descendants.has(row.logical_name)&&row.automation?.can_restart&&!row.document_source)
      .map(row=>({logical_name:row.logical_name,launch_id:row.automation.launch_id}));
  }

  const pending=new Set();
  async function relaunch(scope, targets, {restart=false}={}) {
    const context={id:scope.id,vault:scope.vault},key=(context.vault||'')+'::'+context.id;
    if(pending.has(key))throw Error('A relaunch is already in progress');
    pending.add(key);
    try{
      const result={sessions:[],skipped:[],errors:[]},request_id=crypto.randomUUID();
      for(let offset=0;offset<targets.length;offset+=100){
        const batch=await api('/api/term/automations/relaunch',{workspace_id:context.id,vault:context.vault,targets:targets.slice(offset,offset+100),request_id,...(restart?{restart:true}:{})});
        for(const name of ['sessions','skipped','errors'])result[name].push(...(batch[name]||[]));
      }
      return result;
    }
    finally{pending.delete(key);}
  }

  function renderGuidelines(host, session) {
    if(!host)return;
    const guides=session?.automation?.guidelines||[],key=JSON.stringify([session?.name,guides]);
    host.hidden=!guides.length;
    if(host.dataset.guidelinesKey===key)return;
    host.dataset.guidelinesKey=key;host.replaceChildren();
    if(!guides.length)return;
    const details=document.createElement('details');details.open=true;details.innerHTML='<summary>Guidelines</summary>';
    for(const guide of guides){
      const row=document.createElement('div');row.className='term-automation-guideline';
      row.innerHTML=`${guide.title?`<strong>${esc(guide.title)}</strong>`:''}<pre>${esc(guide.text)}</pre><button type="button">Copy</button>`;
      const button=row.querySelector('button');
      button.onclick=async()=>{try{await navigator.clipboard.writeText(guide.text);button.textContent='Copied';setTimeout(()=>{if(button.isConnected)button.textContent='Copy';},1500);}catch{button.textContent='Select text to copy';}};
      details.append(row);
    }
    host.append(details);
  }

  window.LabTerminalAutomations={editor,open,url,status,recoveryTargets,restartTargets,relaunch,renderGuidelines,iconHtml,inheritedAppearance};
})();
