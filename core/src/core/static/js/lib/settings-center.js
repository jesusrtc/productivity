/* One settings surface. Scope is captured in every read/save; opening it never
   changes the active workspace or starts a terminal. No background polling. */
(function () {
  'use strict';
  const labels = {claude:'Claude Code',codex:'Codex',copilot:'Copilot',terminal:'Terminal',attach:'Attach tmux session'};
  const globalScope = {key:'global',label:'Global',kind:'global'};
  const sections = scope => scope.kind === 'global'
    ? [['general','General'],['appearance','Appearance'],['terminals','Terminal appearance'],['documents','Document terminals']]
    : [['general','Agent'],['terminals','Terminal sessions'],['files','File sidebar']];
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
      else if(section==='appearance') appearance(panel);
      else if(section==='documents') documents(panel,s);
      else if(section==='terminals') terminals(panel,scope,s);
      else files(panel,scope,s);
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
    bridge()?.settingsSaved(s.config);
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
        <p class="settings-hint">Drag the border beside vertical tabs to resize them. Labels appear when there is room.</p>
        ${field('Recent tab window',choices('recentMinutes',p.recentMinutes,[15,30,60,180,360,720,1440].map(n=>[n,n<60?n+' minutes':n/60+' hours'])))}
        ${field('Recent tab color',input('recentColor',p.recentColor,'color'))}
        ${field('Stop blinking after viewing (seconds)',input('completionReadSeconds',p.completionReadSeconds,'number','min="1" max="3600" step="1" required'),'Default: 20 seconds. Keep the terminal visible in the active Lab window for this long. Switching away resets the timer.')}`,async f=>bridge().saveAppearance({orientation:f.elements.orientation.value,recentMinutes:Number(f.elements.recentMinutes.value),recentColor:f.elements.recentColor.value,completionReadSeconds:Number(f.elements.completionReadSeconds.value)}));
      return;
    }
    const selected=bridge().terminalOptions(scope);
    form(panel,`<p class="settings-intro">Options shown in <strong>+ New</strong> for ${esc(scope.label)}, in this browser. These switches control the menu; choose the default under <strong>Agent</strong>.</p>
      ${Object.entries(labels).map(([id,label])=>check(id,label,selected.includes(id),id in s.available?(s.available[id]?'Installed':'Not installed on the computer running Lab'):'')).join('')}
      <button type="button" data-appearance>Configure Lab-wide tab appearance</button>
      <details class="settings-danger"><summary>Stop terminal sessions</summary><p>Running work will stop. Attached external sessions are detached without stopping their originals.</p><button type="button" data-stop ${bridge().canStop(scope)?'':'disabled'}>Stop sessions in ${esc(scope.label)}</button>${bridge().canStop(scope)?'':'<small>Open this workspace first to stop its sessions.</small>'}</details>`,async f=>bridge().saveTerminalOptions(scope,Object.keys(labels).filter(id=>f.elements[id].checked)));
    panel.querySelector('[data-appearance]').onclick=()=>select(globalScope,'terminals');
    panel.querySelector('[data-stop]').onclick=()=>bridge().stop(scope);
  }
  function files(panel,scope,s) {
    const draft=bridge().sidebar(scope), root=scope.path;
    const modes=[['none','Hidden'],['mtime','Recently modified'],['uncommitted','Uncommitted'],['origin-main','Compared with origin/main'],['local-main','Compared with local main'],['last-2-commits','Last two commits']];
    const sort=[['name','Name'],['updated','Updated'],['type','File type']];
    const node=form(panel,`<p class="settings-intro">File sidebar preferences for <strong>${esc(scope.label)}</strong>, saved in this browser.</p>
      ${check('showHidden','Show hidden files and folders',draft.showHidden)}
      <div class="settings-grid">${field('Files sort order',choices('filesSort',draft.filesSort,sort))}${field('Recently updated sort order',choices('recentSort',draft.recentSort,sort))}</div>
      ${field('Recently updated section',choices('recentMode',draft.recentMode,modes))}
      ${field('Consider files recent for',choices('recentMinutes',draft.recentMinutes,[[15,'15 minutes'],[60,'1 hour'],[120,'2 hours'],[360,'6 hours'],[1440,'24 hours']]))}
      ${field('Track file types',choices('trackMode',draft.trackMode,[['all','All file types'],['extensions','Selected extensions']]))}
      ${field('Extensions',input('extensions',draft.extensions.join(', ')),'Comma-separated, for example md, py, ipynb. Use __none__ for files without an extension.')}
      <fieldset><legend>Workspace folders</legend><p class="settings-hint">Each folder appears as a colored shortcut in Files and Recently updated.</p><div data-folders></div><button type="button" data-add-folder>+ Add folder</button></fieldset>
      <details><summary>Worktree colors</summary><div data-worktree-colors></div></details>`,async f=>{
        const value={...draft,showHidden:f.elements.showHidden.checked,filesSort:f.elements.filesSort.value,recentSort:f.elements.recentSort.value,recentMode:f.elements.recentMode.value,recentMinutes:Number(f.elements.recentMinutes.value),trackMode:f.elements.trackMode.value,extensions:f.elements.extensions.value.split(',').map(v=>v.trim().replace(/^\./,'').toLowerCase()).filter(Boolean)};
        value.rootScopeColors={...draft.rootScopeColors};value.rootWorktreeFolders={...draft.rootWorktreeFolders};value.folderScopes=[];
        const seen=new Set([root]);
        for(const card of node.querySelectorAll('[data-folder-card]')) {
          const color=card.querySelector('[data-color]').value, worktree=card.querySelector('[data-worktree]').value.trim();
          if(card.dataset.folderCard==='root') {value.rootScopeColors[root]=color;value.rootWorktreeFolders[root]=worktree;continue;}
          const raw=card.querySelector('[data-path]').value.trim();
          if(!raw)throw new Error('Every folder needs a path.');
          const path=normalizePath(raw,root);
          if(seen.has(path))throw new Error('Each folder must have a different path.');seen.add(path);
          value.folderScopes.push({path,label:card.querySelector('[data-label]').value.trim()||path.split('/').pop(),color,worktreeFolder:worktree});
        }
        value.selectedFolders=Object.fromEntries(Object.entries(draft.selectedFolders).filter(([,path])=>value.folderScopes.some(row=>row.path===path)));
        value.worktreeColors={...draft.worktreeColors};
        node.querySelectorAll('[data-worktree-color]').forEach(input=>value.worktreeColors[input.dataset.worktreeColor]=input.value);
        bridge().saveSidebar(scope,value);Object.assign(draft,value);
      });
    function colors() {
      node.querySelector('[data-worktree-colors]').innerHTML=Object.entries(draft.worktreeColors).map(([path,color])=>`<label class="settings-field">${esc(path)}<input type="color" value="${esc(color)}" data-worktree-color="${esc(path)}"></label>`).join('')||'<p class="settings-hint">Scan a worktree folder to choose its colors.</p>';
    }
    function add(row,isRoot=false) {
      const card=document.createElement('div');card.className='settings-folder';card.dataset.folderCard=isRoot?'root':'folder';
      card.innerHTML=`${isRoot?`<strong>Root</strong><code>${esc(root)}</code>`:`${field('Name',`<input data-label value="${esc(row.label||'')}">`)}${field('Folder or subfolder',`<input data-path value="${esc(row.path||'')}">`)}<button type="button" data-remove>Remove folder</button>`}
        ${field('Color',`<input type="color" data-color value="${esc(row.color||'#6e7681')}">`)}
        ${field('Folder containing Git worktrees',`<input data-worktree value="${esc(row.worktreeFolder||'')}" placeholder="Optional">`)}<button type="button" data-scan>Scan worktrees</button><small data-scan-status></small>`;
      node.querySelector('[data-folders]').append(card);
      card.querySelector('[data-remove]')?.addEventListener('click',()=>{card.remove();s.dirty=true;message('Unsaved changes');});
      card.querySelector('[data-scan]').onclick=async()=>{
        const status=card.querySelector('[data-scan-status]'),button=card.querySelector('[data-scan]');
        try {
          const workspace=isRoot?root:normalizePath(card.querySelector('[data-path]').value,root);
          const folder=card.querySelector('[data-worktree]').value.trim();if(!folder)throw new Error('Enter a worktree folder first.');
          button.disabled=true;status.textContent='Scanning…';
          const params=new URLSearchParams({path:folder.startsWith('~/')?folder:normalizePath(folder,workspace),repo:workspace,scope:workspace});
          const data=await api('/api/sidebar-worktrees?'+params,undefined,s.abort.signal);
          if(!card.isConnected)return;
          node.querySelectorAll('[data-worktree-color]').forEach(input=>draft.worktreeColors[input.dataset.worktreeColor]=input.value);
          for(const row of data.folders||[])draft.worktreeColors[row.path]||='#6e7681';
          colors();s.dirty=true;message('Unsaved changes');status.textContent=(data.folders||[]).length+' worktrees found';
        }catch(error){if(error.name!=='AbortError')status.textContent=error.message;}
        finally{button.disabled=false;}
      };
    }
    add({color:draft.rootScopeColors[root],worktreeFolder:draft.rootWorktreeFolders[root]||draft.worktreeFolder},true);
    draft.folderScopes.forEach(row=>add(row));colors();
    node.querySelector('[data-add-folder]').onclick=()=>{add({});s.dirty=true;message('Unsaved changes');};
  }
  function normalizePath(value,root) {
    const parts=[];
    for(const part of (value.startsWith('/')?value:root+'/'+value).split('/')) {if(part==='..')parts.pop();else if(part&&part!=='.')parts.push(part);}
    return '/'+parts.join('/');
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
