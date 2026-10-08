/* One settings surface. Scope is captured in every read/save; opening it never
   changes the active workspace or starts a terminal. No background polling. */
(function () {
  'use strict';
  const labels = {claude:'Claude Code',codex:'Codex',copilot:'Copilot',terminal:'Terminal',attach:'Attach tmux session'};
  const globalScope = {key:'global',label:'Global',kind:'global'};
  const sections = scope => scope.kind === 'global'
    ? [['general','General'],['projects','Projects and worktrees'],['links','Links and icons'],['appearance','Appearance'],['terminals','Terminal appearance'],['documents','Document terminals']]
    : [['general','Agent'],['terminals','Terminal sessions'],['automations','Terminal automations'],['files','File sidebar']];
  const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let state = null;
  const typographyKey = 'labModalTypography-v1';
  const typographyDefaults = {modalFontSize:14,documentFontSize:18};
  function readTypography() {
    let saved;
    try { saved=JSON.parse(localStorage.getItem(typographyKey)); } catch {}
    return Object.fromEntries(Object.entries(typographyDefaults).map(([name,fallback])=>{
      const value=saved?.[name], max=name==='modalFontSize'?24:32;
      return [name,typeof value==='number'&&Number.isFinite(value)?Math.max(12,Math.min(max,Math.round(value))):fallback];
    }));
  }
  function applyTypography(value) {
    document.documentElement.style.setProperty('--lab-modal-font-size',value.modalFontSize+'px');
    document.documentElement.style.setProperty('--lab-document-font-size',value.documentFontSize+'px');
  }
  applyTypography(readTypography());
  window.addEventListener('storage',event=>{
    if(event.key===typographyKey||event.key===null) {
      applyTypography(readTypography());
      if(state?.section==='appearance') appearance(state.dialog.querySelector('[data-panel]'));
    }
  });
  const bridge = () => window.LabSettingsBridge;
  async function api(url, body, signal) {
    const response = await fetch(url,body === undefined ? {signal} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});
    const data = await response.json().catch(()=>({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not save settings. Try again.');
    return data;
  }
  function message(text, error = false) {
    if (!state) return;
    const host = state.dialog.querySelector('[data-message]');
    host.textContent = text; host.classList.toggle('error',error);
  }
  function mayLeave() { return !state?.dirty || confirm('Discard your unsaved settings changes?'); }
  function close() {
    if (!state || !mayLeave()) return;
    const old = state; state = null; old.abort.abort(); old.dialog.close(); old.dialog.remove();
    if (old.focus?.isConnected) old.focus.focus();
  }
  function nav() {
    if (!state) return;
    const needle = state.dialog.querySelector('[data-search]').value.trim().toLowerCase();
    const scopeMatches=scope=>`${scope.label} ${scope.vaultLabel||''} ${scope.path||''}`.toLowerCase().includes(needle);
    const sectionMatches=([id,label])=>(label+(id==='appearance'?' font size text modal document reading':'' )).toLowerCase().includes(needle);
    const items = [...state.scopes.values()].filter(scope=>!needle||scopeMatches(scope)||sections(scope).some(sectionMatches));
    state.dialog.querySelector('[data-nav]').innerHTML = items.map(scope=>`<div class="settings-scope"><button type="button" class="settings-scope-button${state.scope.key===scope.key?' selected':''}" data-scope="${esc(scope.key)}" title="${esc(scope.path||'Applies across Lab')}">${esc(scope.label)}${scope.vaultLabel?`<small>${esc(scope.vaultLabel)}</small>`:''}</button>${state.scope.key===scope.key||needle?sections(scope).filter(row=>!needle||scopeMatches(scope)||sectionMatches(row)).map(([id,label])=>`<button type="button" class="settings-section-button${state.scope.key===scope.key&&state.section===id?' selected':''}" data-section="${id}" data-section-scope="${esc(scope.key)}"${state.scope.key===scope.key&&state.section===id?' aria-current="page"':''}>${label}</button>`).join(''):''}</div>`).join('')||'<p class="settings-hint">No matching settings.</p>';
    state.dialog.querySelectorAll('[data-scope]').forEach(button=>button.onclick=()=>select(state.scopes.get(button.dataset.scope),'general'));
    state.dialog.querySelectorAll('[data-section]').forEach(button=>button.onclick=()=>select(state.scopes.get(button.dataset.sectionScope),button.dataset.section));
  }
  async function select(scope, section = 'general', force = false) {
    if (!state || (!force && !mayLeave())) return;
    const s = state, token = ++s.version;
    s.dirty=false; s.scope=scope; s.section=section; nav(); message('');
    s.dialog.querySelector('[data-title]').textContent=scope.label+' · '+(sections(scope).find(row=>row[0]===section)?.[1]||section);
    s.dialog.querySelector('[data-scope-caption]').textContent=scope.kind==='global'?'Defaults for the entire Lab':scope.path||'';
    const panel=s.dialog.querySelector('[data-panel]'); panel.innerHTML='<p class="settings-hint">Loading…</p>';
    try {
      if (!s.config) await s.ready;
      if (s!==state||token!==s.version) return;
      if (section==='general') await general(panel,scope,s,token);
      else if(section==='projects') projects(panel,s);
      else if(section==='links') linkTypes(panel,s);
      else if(section==='appearance') appearance(panel);
      else if(section==='documents') documents(panel,s);
      else if(section==='terminals') terminals(panel,scope,s);
      else if(section==='automations') await automations(panel,scope,s,token);
      else files(panel,scope);
    } catch(error) {
      if (s===state&&token===s.version&&error.name!=='AbortError') {panel.innerHTML='';message(error.message,true);}
    }
  }
  function form(panel, html, save) {
    const s=state, token=s.version;
    panel.innerHTML=`<form class="settings-form">${html}<div class="settings-actions"><button class="settings-save" type="submit">Save changes</button><span>Changes apply after saving.</span></div></form>`;
    const node=panel.querySelector('form');
    node.addEventListener('input',()=>{if(s===state){s.dirty=true;message('Unsaved changes');}});
    node.addEventListener('change',()=>{if(s===state){s.dirty=true;message('Unsaved changes');}});
    node.onsubmit=async event=>{
      event.preventDefault(); const button=node.querySelector('[type="submit"]');button.disabled=true;
      try {await save(node);if(s===state&&token===s.version){s.dirty=false;message('Saved');}}
      catch(error){if(s===state&&token===s.version)message(error.message,true);}
      finally{button.disabled=false;}
    };
    return node;
  }
  const field=(label,control,hint='')=>`<label class="settings-field"><span class="settings-field-copy"><span>${label}</span>${hint?`<small>${hint}</small>`:''}</span><span class="settings-control">${control}</span></label>`;
  const input=(name,value,type='text',extra='')=>`<input name="${name}" type="${type}" value="${esc(value)}" ${extra}>`;
  const check=(name,label,checked,hint='')=>`<label class="settings-check"><span class="settings-field-copy"><span>${label}</span>${hint?`<small>${hint}</small>`:''}</span><input name="${name}" type="checkbox" role="switch" ${checked?'checked':''}></label>`;
  function choices(name,value,rows) {return `<select name="${name}">${rows.map(([id,label,disabled])=>`<option value="${esc(id)}" ${String(value??'')===String(id)?'selected':''} ${disabled?'disabled':''}>${esc(label)}</option>`).join('')}</select>`;}
  function agentOptions(s,supported=Object.keys(s.available)) {return Object.keys(labels).filter(id=>['claude','codex','copilot'].includes(id)).map(id=>[id,labels[id]+(!s.available[id]?' — Not installed':!supported.includes(id)?' — Disabled in vault':''),!s.available[id]||!supported.includes(id)]);}
  async function saveGlobal(patch,s) {
    s.config=await api('/api/settings/global',patch,s.abort.signal);
    window.LabScopeLinks?.setDomainMappings(s.config.linkDomainMappings);
    bridge()?.settingsSaved(s.config);
  }
  function projects(panel,s) {
    const node=form(panel,`<p class="settings-intro">Choose where your projects live. Folders directly inside the projects folder appear in each workspace’s project picker.</p>
      ${field('Projects folder',input('projectsFolder',s.config.projectsFolder||'~/src','text','required'),'Default: ~/src. Projects can also live in custom folders.')}
      ${field('Worktrees folder',input('worktreesFolder',s.config.worktreesFolder||'~/src/.worktrees','text','required'),'Each project gets its own folder, then a folder for each branch.')}
      <p class="settings-notice" data-layout></p>
      <fieldset><legend>Custom project locations</legend><p class="settings-hint">Additional projects and worktree overrides available throughout Lab. Leave a worktree folder empty to inherit the default.</p><div data-project-locations></div><button type="button" data-add-location>+ Custom project</button></fieldset>`,async f=>{
        const projectLocations=[...node.querySelectorAll('[data-location]')].map(card=>({path:card.querySelector('[data-path]').value.trim(),worktreeFolder:card.querySelector('[data-worktree]').value.trim()}));
        await saveGlobal({projectsFolder:f.elements.projectsFolder.value.trim(),worktreesFolder:f.elements.worktreesFolder.value.trim(),projectLocations},s);
      });
    const preview=()=>{node.querySelector('[data-layout]').textContent=(node.elements.worktreesFolder.value.trim()||'~/src/.worktrees').replace(/\/+$/,'')+'/lab/new-feature-branch';};
    node.elements.worktreesFolder.addEventListener('input',preview);preview();
    function add(row={}) {
      const card=document.createElement('div');card.className='settings-folder';card.dataset.location='';
      card.innerHTML=`${field('Project folder',`<input data-path value="${esc(row.path||'')}" placeholder="~/other-projects/my-project" required>`)}${field('Worktree folder for this project',`<input data-worktree value="${esc(row.worktreeFolder||'')}" placeholder="Use default">`)}<button type="button" data-remove>Remove custom location</button>`;
      card.querySelector('[data-remove]').onclick=()=>{card.remove();s.dirty=true;message('Unsaved changes');};
      node.querySelector('[data-project-locations]').append(card);
    }
    (s.config.projectLocations||[]).forEach(add);
    node.querySelector('[data-add-location]').onclick=()=>{add();s.dirty=true;message('Unsaved changes');};
  }
  function linkTypes(panel,s) {
    const node=form(panel,`<p class="settings-intro">Link icons are detected from the URL. Map your company’s domains to a service icon, or upload an icon for a custom tool.</p><div data-domain-mappings></div><button type="button" data-add-domain>+ Domain mapping</button><details><summary>Document and legacy link types</summary><p class="settings-hint">Internal documents open in Lab. Existing custom link types keep their saved names; new external links are identified automatically.</p><div data-link-types></div><button type="button" data-add-type>+ Link type</button></details>`,async()=>{
      const scopeLinkTypes=[...node.querySelectorAll('[data-link-type]')].map(card=>({id:card.dataset.linkType,name:card.querySelector('[data-name]').value.trim(),kind:card.querySelector('[data-kind]').value}));
      const linkDomainMappings=[...node.querySelectorAll('[data-domain-mapping]')].map(card=>{
        if(card._uploading)throw new Error('Wait for the icon upload to finish before saving.');
        if(card._iconError)throw new Error(card._iconError);
        const service=card.querySelector('[data-domain-service]').value;
        if(service==='custom'&&!card._icon)throw new Error('Upload an icon for each custom tool.');
        return {domain:card.querySelector('[data-domain]').value.trim(),service,name:card.querySelector('[data-tool-name]').value.trim(),includeSubdomains:card.querySelector('[data-subdomains]').checked,...(service==='custom'?{icon:card._icon}:{})};
      });
      await saveGlobal({scopeLinkTypes,linkDomainMappings},s);
      node.querySelectorAll('[data-domain-mapping]').forEach((card,index)=>{card.querySelector('[data-domain]').value=s.config.linkDomainMappings[index].domain;});
    });
    function add(row={id:'link-'+crypto.randomUUID(),name:'',kind:'external'}) {
      const card=document.createElement('div');card.className='settings-folder';card.dataset.linkType=row.id;
      card.innerHTML=`${field('Name',`<input data-name value="${esc(row.name)}" required maxlength="80" placeholder="Design, pull request, wiki…">`)}${field('Opens in',`<select data-kind><option value="external" ${row.kind==='external'?'selected':''}>Default browser</option><option value="internal" ${row.kind==='internal'?'selected':''}>Lab internal document</option></select>`)}<button type="button" data-remove>Remove type</button>`;
      card.querySelector('[data-remove]').onclick=()=>{card.remove();s.dirty=true;message('Unsaved changes');};
      node.querySelector('[data-link-types]').append(card);
    }
    (s.config.scopeLinkTypes||[]).forEach(add);
    node.querySelector('[data-add-type]').onclick=()=>{add();s.dirty=true;message('Unsaved changes');};
    function addDomain(row={}) {
      const card=document.createElement('div');card.className='settings-folder settings-domain-mapping';card.dataset.domainMapping='';card._icon=row.icon||'';card._uploadVersion=0;
      card.innerHTML=`<div class="settings-domain-heading"><label>Domain<input data-domain value="${esc(row.domain||'')}" placeholder="mygrafana.mycompany.com" required></label><label>Icon<span class="settings-icon-choice"><span data-icon-preview aria-hidden="true"></span><select data-domain-service required><option value="">Choose an icon…</option>${(window.LAB_LINK_SERVICES||[]).map(service=>`<option value="${esc(service.id)}" ${row.service===service.id?'selected':''}>${esc(service.name)}</option>`).join('')}<option value="custom" ${row.service==='custom'?'selected':''}>Custom icon…</option></select></span></label></div><div data-custom-upload hidden><button type="button" class="settings-icon-upload" data-choose-icon>Upload icon</button><input data-upload-icon type="file" accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml,image/x-icon,image/vnd.microsoft.icon" hidden><span data-upload-status class="settings-hint"></span><p class="settings-hint">PNG, JPG, WebP, GIF, SVG, or ICO. Images are resized to 64 pixels and stored locally.</p></div>${field('Tool name (optional)',`<input data-tool-name maxlength="80" value="${esc(row.name||'')}" placeholder="Use the service name">`)}<label class="settings-check"><span class="settings-field-copy"><span>Include subdomains</span><small>Also match tools hosted below this domain.</small></span><input type="checkbox" role="switch" data-subdomains ${row.includeSubdomains?'checked':''}></label><button type="button" data-remove-domain>Remove mapping</button>`;
      node.querySelector('[data-domain-mappings]').append(card);
      const select=card.querySelector('[data-domain-service]'),status=card.querySelector('[data-upload-status]');
      const preview=()=>{
        const custom=select.value==='custom';card.querySelector('[data-custom-upload]').hidden=!custom;
        const host=card.querySelector('[data-icon-preview]');host.replaceChildren();
        if(custom&&card._icon){const image=document.createElement('img');image.src=card._icon;image.alt='';host.append(image);}
        else host.innerHTML=window.LabScopeLinks?.icon({type:select.value})||'';
        status.textContent=card._icon?'Icon ready':'';
      };
      select.onchange=()=>{card._uploadVersion++;card._uploading=false;card._iconError='';status.classList.remove('error');preview();};
      card.querySelector('[data-choose-icon]').onclick=()=>card.querySelector('[data-upload-icon]').click();
      card.querySelector('[data-upload-icon]').onchange=async event=>{
        const file=event.target.files[0];if(!file)return;
        const version=++card._uploadVersion;card._uploading=true;card._iconError='';status.classList.remove('error');status.textContent='Loading icon…';
        const current=()=>state===s&&card.isConnected&&card._uploadVersion===version;
        try {
          const icon=await prepareIcon(file);
          if(!current())return;
          card._icon=icon;preview();s.dirty=true;message('Unsaved changes');
        }catch(error){if(current()){card._iconError=error.message;status.textContent=error.message;status.classList.add('error');}}
        finally{if(current())card._uploading=false;event.target.value='';}
      };
      card.querySelector('[data-remove-domain]').onclick=()=>{card._uploadVersion++;card.remove();s.dirty=true;message('Unsaved changes');};
      preview();return card;
    }
    (s.config.linkDomainMappings||[]).forEach(addDomain);
    node.querySelector('[data-add-domain]').onclick=()=>{addDomain().querySelector('[data-domain]').focus();s.dirty=true;message('Unsaved changes');};
  }
  async function prepareIcon(file) {
    if(file.size>2*1024*1024)throw new Error('Choose an icon file smaller than 2 MB.');
    const url=URL.createObjectURL(file),image=new Image();
    try {
      image.src=url;await image.decode();
      const scale=Math.min(1,64/Math.max(image.naturalWidth,image.naturalHeight));
      const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(image.naturalWidth*scale));canvas.height=Math.max(1,Math.round(image.naturalHeight*scale));
      const context=canvas.getContext('2d');context.drawImage(image,0,0,canvas.width,canvas.height);
      const icon=canvas.toDataURL('image/png');
      if(icon.length>90000)throw new Error('Choose a smaller or simpler icon.');
      return icon;
    }catch(error){if(error.message.startsWith('Choose'))throw error;throw new Error('Could not read this image. Choose a PNG, JPG, WebP, GIF, SVG, or ICO.');}
    finally{URL.revokeObjectURL(url);}
  }
  function appearance(panel) {
    const value=readTypography();
    const slider=(name,label,hint,max)=>`<div class="settings-field"><div class="settings-field-copy"><label for="settings-${name}">${label}</label><small>${hint}</small></div><div class="settings-font-control"><button type="button" data-reset="${name}" aria-label="Reset ${label.toLowerCase()}" title="Reset to ${typographyDefaults[name]} px">↺</button><output for="settings-${name}" data-size="${name}">${value[name]} px</output><input id="settings-${name}" name="${name}" type="range" min="12" max="${max}" step="1" value="${value[name]}" aria-valuetext="${value[name]} pixels"></div></div>`;
    panel.innerHTML=`<div class="settings-form"><p class="settings-intro">Make dialogs and documents easier to read. Font sizes apply immediately and are saved in this browser.</p><div class="settings-group">
      ${slider('documentFontSize','Document font size','Text in document modals, Markdown, and document editors.',32)}
      ${slider('modalFontSize','Modal interface font size','Settings, dialog labels, buttons, and document navigation.',24)}
      </div><section class="settings-preview" aria-label="Document font preview"><small>Document preview</small><div class="settings-preview-document"><h3>A little more room to read</h3><p>Your notes, ideas, and documents at a size that feels comfortable.</p><p>Headings, <strong>bold text</strong>, and <code>inline code</code> scale together.</p></div></section></div>`;
    function update(name,size) {
      value[name]=size;
      const input=panel.querySelector(`[name="${name}"]`);input.value=size;input.setAttribute('aria-valuetext',size+' pixels');
      panel.querySelector(`[data-size="${name}"]`).value=size+' px';
      applyTypography(value);
      try {localStorage.setItem(typographyKey,JSON.stringify(value));message('Font sizes saved');}
      catch {message('Font sizes applied. Browser storage is unavailable; they will reset after reloading.',true);}
    }
    panel.querySelectorAll('input[type="range"]').forEach(input=>input.oninput=()=>update(input.name,Number(input.value)));
    panel.querySelectorAll('[data-reset]').forEach(button=>button.onclick=()=>update(button.dataset.reset,typographyDefaults[button.dataset.reset]));
  }
  async function general(panel,scope,s,token) {
    if(scope.kind==='global') {
      const config=s.config;
      const installed=Object.entries(s.available).filter(([,on])=>on).map(([id])=>labels[id]).join(', ')||'None';
      const node=form(panel,`<p class="settings-intro">Choose the agent for new terminals and document terminals. Workspace overrides appear under each workspace.</p>
        <div class="settings-notice">Installed on the computer running Lab: <strong>${esc(installed)}</strong>.</div>
        ${field('Default agent',choices('defaultAgent',config.defaultAgent,agentOptions(s)),s.available[config.defaultAgent]?'Used unless a workspace overrides it.':'The current default is not installed. Choose an installed agent below.')}
        ${field('Default model',input('model',config.model||'','','placeholder="Agent default"'),'Leave empty to use the agent’s own default.')}
        ${field('Theme',choices('theme',config.theme,[['dark','Dark'],['light','Light']]))}
        <fieldset><legend>Autopilot</legend><p class="settings-hint">Permission mode for newly launched agent sessions.</p>${['claude','codex','copilot'].map(id=>check('auto_'+id,labels[id],config.autopilot?.[id],esc(config.autopilotFlags?.[id]||''))).join('')}</fieldset>`,async f=>{
          const patch={};
          for(const name of ['defaultAgent','model','theme']) if(touched.has(name)) patch[name]=f.elements[name].value||null;
          if([...touched].some(name=>name.startsWith('auto_'))) patch.autopilot=Object.fromEntries(['claude','codex','copilot'].map(id=>[id,f.elements['auto_'+id].checked]));
          if(Object.keys(patch).length) await saveGlobal(patch,s);
          if(s===state&&token===s.version){await select(scope,'general',true);message('Saved');}
        });
      const touched=new Set();node.addEventListener('input',event=>touched.add(event.target.name));node.addEventListener('change',event=>touched.add(event.target.name));
      node.elements.defaultAgent.onchange=()=>{node.elements.model.value='';touched.add('model');};
      return;
    }
    if(scope.kind!=='workspace') {
      panel.innerHTML=`<p class="settings-intro">${esc(scope.label)} uses the Lab-wide default agent: <strong>${esc(labels[s.config.defaultAgent]||s.config.defaultAgent)}</strong>.</p><button type="button" data-global-agent>Configure global agent</button>`;
      panel.querySelector('[data-global-agent]').onclick=()=>select(globalScope,'general'); return;
    }
    const query='?vault='+encodeURIComponent(scope.vault);
    const [workspace,policy,effective]=await Promise.all([
      api('/api/workspaces/'+encodeURIComponent(scope.id)+query,undefined,s.abort.signal),
      api('/api/vault/agents'+query,undefined,s.abort.signal),
      api('/api/settings'+query,undefined,s.abort.signal),
    ]);
    if(s!==state||token!==s.version)return;
    const chosen=workspace.agent||effective.defaultAgent;
    const effectiveAgent=policy.supported.includes(chosen)?chosen:policy.default;
    const node=form(panel,`<p class="settings-intro">Effective agent: <strong>${esc(labels[effectiveAgent]||effectiveAgent)}</strong>${s.available[effectiveAgent]?'':' · Not installed'}. ${workspace.agent?'This workspace has an override.':'This workspace inherits its default.'}</p>
      ${field('Agent for this workspace',choices('agent',workspace.agent||'',[['','Inherit global default'],...agentOptions(s,policy.supported)]))}
      ${field('Model for this workspace',input('model',workspace.model||'','','placeholder="Inherit default model"'))}
      <details><summary>Agents allowed in ${esc(scope.vaultLabel||scope.vault)}</summary><p class="settings-hint">This availability applies to every workspace in this vault.</p>${['claude','codex','copilot'].map(id=>check('allowed_'+id,labels[id],policy.supported.includes(id),s.available[id]?'Installed':'Not installed')).join('')}<button type="button" data-save-allowed>Save vault availability</button></details>`,async f=>{
        await api('/api/workspaces/'+encodeURIComponent(scope.id)+'/agent'+query,{agent:f.elements.agent.value||null,model:f.elements.model.value||null},s.abort.signal);
        bridge()?.settingsSaved(s.config);
        if(s===state&&token===s.version){await select(scope,'general',true);message('Saved');}
      });
    node.querySelector('[data-save-allowed]').onclick=async()=>{
      try {
        const supported=['claude','codex','copilot'].filter(id=>node.elements['allowed_'+id].checked);
        if(!supported.length)throw new Error('Keep at least one agent enabled.');
        const updated=await api('/api/vault/agents',{vault:scope.vault,supported},s.abort.signal);
        if(s!==state||token!==s.version)return;
        bridge()?.settingsSaved(s.config);
        const selected=node.elements.agent.value;
        node.elements.agent.innerHTML=choices('agent',selected,[['','Inherit global default'],...agentOptions(s,updated.supported)]).replace(/^<select[^>]*>|<\/select>$/g,'');
        message('Vault availability saved. Agent/model changes still require Save changes.');
      }catch(error){if(s===state&&token===s.version)message(error.message,true);}
    };
  }
  function documents(panel,s) {
    const p=s.config.documentTerminals;
    form(panel,`<p class="settings-intro">Drag an existing terminal onto a task or document to link it. Opening a document never starts a new terminal. These settings apply only to previous managed document conversations.</p>
      <button type="button" data-global-agent>Change default agent</button>
      ${check('enabled','Allow resuming previous document conversations',p.enabled)}
      ${field('Sleep hidden idle terminals after (minutes)',input('sleepMinutes',p.sleepMinutes,'number','min="1" max="10080" required'))}
      ${field('Remove unused terminal bookmarks after (hours)',input('expireHours',p.expireHours,'number','min="1" max="8760" required'))}
      ${field('Idle terminals to keep ready',input('maxRunning',p.maxRunning,'number','min="1" max="20" required'))}
      <p class="settings-hint">Working agents, approval waits and unsent text stay protected. Saved conversations remain linked to their documents. Low memory delays new starts automatically.</p>`,async f=>{
        const policy={enabled:f.elements.enabled.checked};
        for(const key of ['sleepMinutes','expireHours','maxRunning'])policy[key]=Number(f.elements[key].value);
        if(policy.expireHours*60<=policy.sleepMinutes)throw new Error('Removal must be later than sleep.');
        await saveGlobal({documentTerminals:policy},s);
      });
    panel.querySelector('[data-global-agent]').onclick=()=>select(globalScope,'general');
  }
  function terminals(panel,scope,s) {
    if(scope.kind==='global') {
      const p=bridge().appearance();
      form(panel,`<p class="settings-intro">Appearance for terminal tabs throughout Lab in this browser.</p>
        ${field('Tab layout',choices('orientation',p.orientation,[['vertical','Vertical'],['horizontal','Horizontal']]))}
        <p class="settings-hint">Hover over vertical tabs to show their names. Click the tab bar to keep it open; click inside the terminal to hide it. Drag its border to resize the names.</p>
        ${field('Keep terminal tabs and sidebar open after hovering (seconds)',input('tabHoverPinSeconds',p.tabHoverPinSeconds ?? 3,'number','min="0" max="60" step="0.1" required'),'Default: 3 seconds. A shorter hover closes when you leave. Clicking the sidebar keeps it open until you click the main work area. Zero keeps it open immediately.')}
        ${check('wipOnly','Show In progress and selected task terminals in Objectives',p.wipOnly ?? true)}
        <p class="settings-hint">On by default. Show In progress tasks, the selected task at any status and children that inherit its context. The workspace main stays visible; only the active Objective's main appears. Use Show all beside its header to reveal that Objective's terminals, or turn this off to reveal all Objectives and statuses.</p>
        ${check('recentEnabled','Show recency bar on terminal tabs',p.recentEnabled)}
        <p class="settings-hint">Off by default. Marks inactive tabs selected within the recent window.</p>
        ${field('Recent tab window',choices('recentMinutes',p.recentMinutes,[15,30,60,180,360,720,1440].map(n=>[n,n<60?n+' minutes':n/60+' hours'])))}
        ${field('Recent tab color',input('recentColor',p.recentColor,'color'))}
        ${field('Stop blinking after viewing (seconds)',input('completionReadSeconds',p.completionReadSeconds,'number','min="1" max="3600" step="1" required'),'Default: 20 seconds. Keep the terminal visible in the active Lab window for this long. Switching away resets the timer.')}`,async f=>bridge().saveAppearance({orientation:f.elements.orientation.value,tabHoverPinSeconds:Number(f.elements.tabHoverPinSeconds.value),wipOnly:f.elements.wipOnly.checked,recentEnabled:f.elements.recentEnabled.checked,recentMinutes:Number(f.elements.recentMinutes.value),recentColor:f.elements.recentColor.value,completionReadSeconds:Number(f.elements.completionReadSeconds.value)}));
      return;
    }
    const selected=bridge().terminalOptions(scope);
    form(panel,`<p class="settings-intro">Options shown in <strong>+ New</strong> for ${esc(scope.label)}, in this browser. These switches control the menu; choose the default under <strong>Agent</strong>.</p>
      ${Object.entries(labels).map(([id,label])=>check(id,label,selected.includes(id),id in s.available?(s.available[id]?'Installed':'Not installed on the computer running Lab'):'')).join('')}
      <button type="button" data-appearance>Configure Lab-wide tab appearance</button>
      <button type="button" data-automations>Configure terminal automations</button>
      <details class="settings-danger"><summary>Stop terminal sessions</summary><p>Running work will stop. Attached external sessions are detached without stopping their originals.</p><button type="button" data-stop ${bridge().canStop(scope)?'':'disabled'}>Stop sessions in ${esc(scope.label)}</button>${bridge().canStop(scope)?'':'<small>Open this workspace first to stop its sessions.</small>'}</details>`,async f=>bridge().saveTerminalOptions(scope,Object.keys(labels).filter(id=>f.elements[id].checked)));
    panel.querySelector('[data-appearance]').onclick=()=>select(globalScope,'terminals');
    panel.querySelector('[data-automations]').onclick=()=>select(scope,'automations');
    panel.querySelector('[data-stop]').onclick=()=>bridge().stop(scope);
  }
  async function automations(panel,scope,s,token) {
    let catalog=await api(window.LabTerminalAutomations.url(scope),undefined,s.abort.signal);
    if(s!==state||token!==s.version)return;
    const node=form(panel,`<p class="settings-intro">Save command groups with <strong>${esc(scope.label)}</strong>, available from every browser. Right-click a terminal and choose <strong>Launch automation…</strong> to review and start a group as child terminals.</p><p class="settings-hint">Each terminal has its own command and fixed working directory. Leave the path empty to use its parent’s folder, use a relative path within that folder, or specify an absolute path or ~/folder. Commands start in order and run independently. Saving never launches commands.</p><div data-automation-editor></div>`,async()=>{
      catalog=await api('/api/term/automations',{workspace_id:scope.id,vault:scope.vault,revision:catalog.revision,automations:read()},s.abort.signal);
    });
    const read=window.LabTerminalAutomations.editor(node.querySelector('[data-automation-editor]'),catalog.automations,()=>{s.dirty=true;message('Unsaved changes');});
  }
  function files(panel,scope) {
    const draft=bridge().sidebar(scope);
    const modes=[['none','Hidden'],['mtime','Recently modified'],['uncommitted','Uncommitted'],['local-main','Compared with main (including uncommitted)']];
    const sort=[['name','Name'],['updated','Updated'],['type','File type']];
    form(panel,`<p class="settings-intro">File sidebar preferences for <strong>${esc(scope.label)}</strong>, saved in this browser.</p>
      ${check('showHidden','Show hidden files and folders',draft.showHidden)}
      <div class="settings-grid">${field('Files sort order',choices('filesSort',draft.filesSort,sort))}${field('Recently updated sort order',choices('recentSort',draft.recentSort,sort))}</div>
      ${field('Recently updated section',choices('recentMode',draft.recentMode,modes),'Only Git-tracked files; ignored and untracked files are excluded.')}
      ${field('Consider files recent for',choices('recentMinutes',draft.recentMinutes,[[15,'15 minutes'],[60,'1 hour'],[120,'2 hours'],[360,'6 hours'],[1440,'24 hours']]))}
      ${field('Track file types',choices('trackMode',draft.trackMode,[['all','All file types'],['extensions','Selected extensions']]))}
      ${field('Extensions',input('extensions',draft.extensions.join(', ')),'Comma-separated, for example md, py, ipynb. Use __none__ for files without an extension.')}`,async f=>{
        const value={...draft,showHidden:f.elements.showHidden.checked,filesSort:f.elements.filesSort.value,recentSort:f.elements.recentSort.value,recentMode:f.elements.recentMode.value,recentMinutes:Number(f.elements.recentMinutes.value),trackMode:f.elements.trackMode.value,extensions:f.elements.extensions.value.split(',').map(v=>v.trim().replace(/^\./,'').toLowerCase()).filter(Boolean)};
        bridge().saveSidebar(scope,value);Object.assign(draft,value);
      });
  }
  async function open(options={}) {
    if(window.LAB_IS_ADMIN===false)return;
    if(!bridge())return;
    if(state) {if(options.scope)state.scopes.set(options.scope.key,options.scope);return select(options.scope||globalScope,options.section||'general');}
    const dialog=document.createElement('dialog');dialog.id='labSettingsCenter';dialog.className='lab-settings-center';dialog.setAttribute('aria-labelledby','labSettingsTitle');
    dialog.innerHTML=`<header><div><strong id="labSettingsTitle">Settings</strong><span>⌘,</span></div><button type="button" data-close aria-label="Close settings">×</button></header><div class="settings-layout"><aside><input data-search type="search" placeholder="Search settings…" aria-label="Search settings"><nav data-nav aria-label="Settings scopes"></nav><small data-catalog-status></small></aside><main><h2 data-title></h2><p class="settings-scope-caption" data-scope-caption></p><div data-panel></div></main></div><footer><span role="status" data-message></span><button type="button" data-done>Done</button></footer>`;
    const s=state={dialog,abort:new AbortController(),version:0,dirty:false,focus:document.activeElement,scopes:new Map([['global',globalScope]]),scope:options.scope||globalScope,section:options.section||'general'};
    for(const scope of bridge().initialScopes())s.scopes.set(scope.key,scope);
    if(options.scope)s.scopes.set(options.scope.key,options.scope);
    document.body.append(dialog);dialog.showModal();
    dialog.querySelector('[data-close]').onclick=dialog.querySelector('[data-done]').onclick=close;
    dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
    dialog.addEventListener('click',event=>{if(event.target===dialog)close();});
    dialog.querySelector('[data-search]').oninput=nav;
    s.ready=Promise.all([api('/api/settings/global',undefined,s.abort.signal),api('/api/agents/available',undefined,s.abort.signal)]).then(([config,available])=>{s.config=config;s.available=available;});
    void select(s.scope,s.section,true);
    try {
      const catalog=await api('/api/vaults/workspaces',undefined,s.abort.signal);
      if(s!==state)return;
      let unavailable=0;
      for(const vault of catalog.vaults||[]) {
        if(vault.unavailable)++unavailable;
        for(const row of vault.workspace_rows||[]) {
          if(!row.path||row.is_workspace===false)continue;
          s.scopes.set(row.path,{key:row.path,id:row.name,path:row.path,label:row.display_name||row.name,vault:vault.id,vaultLabel:vault.name,kind:'workspace'});
        }
      }
      nav();s.dialog.querySelector('[data-catalog-status]').textContent=unavailable?unavailable+(unavailable===1?' vault is currently unavailable.':' vaults are currently unavailable.'):'';
    }catch(error){if(s===state&&error.name!=='AbortError')s.dialog.querySelector('[data-catalog-status]').textContent='Could not load all workspaces. Close and reopen to retry.';}
  }
  // Capture before xterm and modal shortcuts so ⌘, works while typing anywhere.
  document.addEventListener('keydown',event=>{
    if((event.metaKey||event.ctrlKey)&&!event.altKey&&(event.key===','||event.code==='Comma')) {
      event.preventDefault();event.stopImmediatePropagation();void open();
    } else if(state&&event.key==='Escape') {event.preventDefault();event.stopImmediatePropagation();close();}
  },true);
  window.LabSettings={open,close};
})();
