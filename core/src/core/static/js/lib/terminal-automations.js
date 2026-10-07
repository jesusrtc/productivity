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

  function editor(host, rows, dirty) {
    host.innerHTML='<div data-recipes></div><p class="settings-hint" data-empty>No automations yet. Add one to save a group of commands.</p><button type="button" data-add-automation>+ Automation</button>';
    const list=host.querySelector('[data-recipes]');
    const refresh=()=>{host.querySelector('[data-empty]').hidden=!!list.children.length;host.querySelector('[data-add-automation]').disabled=list.children.length>=32;};
    const label=(name,control)=>`<label class="term-automation-field"><span>${name}</span>${control}</label>`;
    function add(row={id:crypto.randomUUID(),name:'',steps:[{label:'',cwd:'',command:''}]}) {
      const card=document.createElement('details');card.className='settings-folder term-automation-recipe';card.dataset.automation=row.id;card.open=true;
      card.innerHTML=`<summary>${esc(row.name||'New automation')}</summary>${label('Automation name',`<input data-name value="${esc(row.name)}" required maxlength="120" placeholder="Development services">`)}<div data-steps></div><div class="term-automation-actions"><button type="button" data-add-step>+ Child terminal</button><button type="button" data-remove-automation>Remove automation</button></div>`;
      const steps=card.querySelector('[data-steps]');
      function reorder() { [...steps.children].forEach((step,index)=>{step.querySelector('[data-up]').disabled=index===0;step.querySelector('[data-down]').disabled=index===steps.children.length-1;});card.querySelector('[data-add-step]').disabled=steps.children.length>=20; }
      function step(row={}) {
        const child=document.createElement('div');child.className='term-automation-step';child.dataset.step='';
        child.innerHTML=`${label('Terminal name',`<input data-label value="${esc(row.label)}" required maxlength="120" placeholder="Frontend">`)}${label('Working directory',`<input data-cwd value="${esc(row.cwd)}" maxlength="4096" placeholder="Parent folder, or e.g. ./frontend">`)}${label('Command',`<textarea data-command rows="3" required maxlength="16000" spellcheck="false" placeholder="npm run dev">${esc(row.command)}</textarea>`)}<div class="term-automation-actions"><button type="button" data-up aria-label="Start this terminal earlier">↑</button><button type="button" data-down aria-label="Start this terminal later">↓</button><button type="button" data-remove-step>Remove terminal</button></div>`;
        child.querySelector('[data-remove-step]').onclick=()=>{child.remove();reorder();dirty();};
        child.querySelector('[data-up]').onclick=()=>{if(child.previousElementSibling)steps.insertBefore(child,child.previousElementSibling);reorder();dirty();};
        child.querySelector('[data-down]').onclick=()=>{if(child.nextElementSibling)steps.insertBefore(child.nextElementSibling,child);reorder();dirty();};
        steps.append(child);reorder();return child;
      }
      row.steps.forEach(step);
      card.querySelector('[data-name]').oninput=event=>{card.querySelector('summary').textContent=event.target.value||'New automation';};
      card.querySelector('[data-add-step]').onclick=()=>{step().querySelector('input').focus();dirty();};
      card.querySelector('[data-remove-automation]').onclick=()=>{card.remove();refresh();dirty();};
      list.append(card);refresh();return card;
    }
    rows.forEach(add);refresh();
    host.querySelector('[data-add-automation]').onclick=()=>{add().querySelector('input').focus();dirty();};
    return () => [...list.children].map(card=>{
      const steps=[...card.querySelector('[data-steps]').children].map(step=>({label:step.querySelector('[data-label]').value.trim(),cwd:step.querySelector('[data-cwd]').value.trim(),command:step.querySelector('[data-command]').value}));
      const name=card.querySelector('[data-name]').value.trim();
      if(!name||!steps.length||steps.some(step=>!step.label||!step.command.trim()))throw new Error('Each automation needs a name and at least one named terminal with a command.');
      return {id:card.dataset.automation,name,steps};
    });
  }

  let active=null;
  async function open({scope,parent,current,adopt,configure}) {
    if(active)return;
    const focus=document.activeElement,dialog=document.createElement('dialog');
    dialog.id='termAutomationLauncher';dialog.className='lab-settings-center term-automation-launcher';dialog.setAttribute('aria-labelledby','termAutomationTitle');
    dialog.innerHTML=`<header><strong id="termAutomationTitle">Launch automation</strong><button type="button" data-close aria-label="Close automation launcher">×</button></header><div class="term-automation-body"><p>Open child terminals under <strong>${esc(parent.label||parent.logical_name)}</strong> in ${esc(scope.label)}.</p><label class="term-automation-field"><span>Automation</span><select data-choice disabled><option>Loading…</option></select></label><p class="settings-hint" data-hint>Commands start in order and run independently. Exited commands keep their logs and open a shell.</p><div data-preview></div></div><footer><span role="status" aria-live="polite" data-status></span><div class="term-automation-actions"><button type="button" data-configure>Configure automations</button><button type="button" class="settings-save" data-launch disabled>Launch</button></div></footer>`;
    document.body.append(dialog);dialog.showModal();active=dialog;
    const status=dialog.querySelector('[data-status]'),choice=dialog.querySelector('[data-choice]'),launch=dialog.querySelector('[data-launch]'),preview=dialog.querySelector('[data-preview]');
    let running=false,review=0,catalog,closed=false;
    const valid=()=>!closed&&active===dialog&&current();
    const message=(text,error=false)=>{if(!closed){status.textContent=text;status.classList.toggle('error',error);}};
    const close=()=>{if(running)return;closed=true;review++;active=null;dialog.close();dialog.remove();if(focus?.isConnected)focus.focus();};
    dialog.querySelector('[data-close]').onclick=close;
    dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
    dialog.addEventListener('click',event=>{if(event.target===dialog)close();});
    dialog.querySelector('[data-configure]').onclick=()=>{close();configure();};
    const base=()=>({workspace_id:scope.id,vault:scope.vault,parent:parent.name,automation_id:choice.value,revision:catalog.revision,run_id:crypto.randomUUID()});
    async function show() {
      const token=++review;launch.disabled=true;preview.replaceChildren();message('Checking working directories…');
      if(!valid()){message('The workspace or parent context changed. Close and reopen this launcher.',true);return;}
      try {
        const data=await api('/api/term/automations/launch',{...base(),preview:true});
        if(token!==review||closed)return;
        if(!valid()){message('The workspace or parent context changed. Close and reopen this launcher.',true);return;}
        preview.innerHTML=data.steps.map((step,index)=>`<section class="term-automation-preview"><strong>${index+1}. ${esc(step.label)}</strong><small>${esc(step.cwd)}</small><pre>${esc(step.command)}</pre></section>`).join('');
        launch.disabled=false;message(`${data.steps.length} child terminal${data.steps.length===1?'':'s'} ready`);
      }catch(error){if(token===review)message(error.message,true);}
    }
    choice.onchange=()=>void show();
    launch.onclick=async()=>{
      if(running||launch.disabled)return;
      if(!valid()){launch.disabled=true;message('The workspace or parent context changed. Close and reopen this launcher.',true);return;}
      running=true;launch.disabled=true;choice.disabled=true;dialog.querySelector('[data-configure]').disabled=true;dialog.querySelector('[data-close]').disabled=true;message('Starting child terminals…');
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
  window.LabTerminalAutomations={editor,open,url};
})();
