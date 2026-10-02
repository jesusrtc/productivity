/* Links belong to an exact folder/checkout, shared across Lab workspaces. */
(function () {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const cache = new Map();
  const lastDocument = new Map();
  const documentMime = 'application/x-lab-assistant-document';
  const rootKey = path => String(path || '').replace(/\/+$/, '') || '/';
  const services = window.LAB_LINK_SERVICES || [];
  let domainMappings = [], domainMappingsVersion = 0;
  let editor = null;
  async function api(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw Object.assign(new Error(typeof data.detail === 'string' ? data.detail : 'Could not load links.'),{status:response.status});
    return data;
  }
  function serviceFor(link, useType = true, mappings = domainMappings) {
    if (link.kind === 'internal') return null;
    try {
      const url = new URL(link.url), host = url.hostname.toLowerCase().replace(/\.$/, ''), path = url.pathname.toLowerCase();
      if (!['http:', 'https:'].includes(url.protocol)) return null;
      const domainMatches = domain => host === domain || host.endsWith('.' + domain);
      for (const mapping of [...mappings].sort((a,b) => b.domain.length-a.domain.length)) {
        if (host !== mapping.domain && !(mapping.includeSubdomains && domainMatches(mapping.domain))) continue;
        if (mapping.service === 'custom') return {id:'url',name:mapping.name || mapping.domain,iconData:mapping.icon,mapped:true};
        const service = services.find(row => row.id === mapping.service);
        if (service) return {...service,name:mapping.name || service.name,mapped:true};
      }
      for (const service of services) {
        if (service.rules.some(rule => domainMatches(rule.domain) && (path === rule.path || path.startsWith(rule.path + '/')))
          || service.domains.some(domainMatches)
          || service.host_labels.some(label => host.split('.').some(part => part === label || part.startsWith(label + '-') || part.endsWith('-' + label)))) return service;
      }
    } catch (_) { /* Unfinished URLs retain the generic link glyph. */ }
    if (useType && !link.auto_type) {
      const names = [link.type, link.base_type_name || link.type_name].map(value => String(value || '').toLowerCase().replace(/[\s_]+/g, '-'));
      return services.find(service => names.some(name => name === service.id || name === service.name.toLowerCase().replace(/\s+/g, '-') || service.aliases.includes(name))) || null;
    }
    return null;
  }
  function icon(link) {
    const service = serviceFor(link);
    if (service?.iconData && /^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(service.iconData))
      return `<span class="scope-link-icon" data-link-custom="true" style="${esc('background-image:url("'+service.iconData+'")')}" aria-hidden="true"></span>`;
    return `<span class="scope-link-icon" ${service ? `data-link-service="${esc(service.id)}"` : ''} aria-hidden="true">${service ? '' : link.kind === 'internal' ? '▤' : '↗'}</span>`;
  }
  function setDomainMappings(mappings) {
    if (!Array.isArray(mappings) || JSON.stringify(mappings) === JSON.stringify(domainMappings)) return;
    domainMappings = mappings;domainMappingsVersion++;
    document.querySelectorAll('[data-scope-links]').forEach(host => {
      if (host.isConnected && host._scopeLinksCurrent?.() && host._scopeLinksData)
        render(host,host._scopeLinksData,() => host.isConnected && host._scopeLinksCurrent());
    });
    editor?.dialog.querySelectorAll('[data-link-card]').forEach(updateCard);
  }
  function typeName(link) { return link.auto_type ? 'Link' : link.base_type_name || link.type_name; }
  function label(link) { return link.label || link.title || serviceFor(link)?.name || typeName(link) || link.url || 'Document'; }
  function tabs(tree, depth = 0) {
    return (tree?.children || []).flatMap(row => [{id:row.id, title:'· '.repeat(depth) + row.title, name:row.title, depth}, ...tabs(row, depth + 1)]);
  }
  async function read(path, fresh = false) {
    const saved = cache.get(path);
    if (!fresh && saved && Date.now() - saved.at < 60000) return saved.data;
    if (saved?.pending) return saved.pending;
    const mappingsVersion = domainMappingsVersion;
    const pending = api('/api/scope-links?path=' + encodeURIComponent(path)).then(data => {
      if (mappingsVersion === domainMappingsVersion) setDomainMappings(data.linkDomainMappings);
      cache.set(path, {data, at:Date.now()}); return data;
    }).catch(error => { if (cache.get(path)?.pending === pending) cache.delete(path); throw error; });
    cache.set(path, {...saved, pending});
    return pending;
  }
  function matchesTerminal(session, scope) {
    return !session.document_source && !!session.linked_scope?.root && rootKey(session.linked_scope.root) === rootKey(scope.root)
      && (!session.workspace_id || session.workspace_id === scope.workspace_id)
      && (!session.vault || session.vault === scope.vault);
  }
  async function terminals(scope, signal) {
    if (!scope.workspace_id) return [];
    const rows = await api('/api/term/sessions?' + new URLSearchParams({workspace_id:scope.workspace_id,
      ...(scope.vault ? {vault:scope.vault} : {})}), {signal});
    return rows.filter(session => matchesTerminal(session, scope));
  }
  async function openDocument(link, path, options = {}) {
    const current = options.isCurrent || (() => true);
    if (!current()) return false;
    const context = window.LabTaskTerminalBridge?.context?.() || {};
    const scope = options.terminalScope || {...context, root:path};
    const opened = await window.AssistantView.openLinkedTask(link, {...options, terminalScope:scope,
      wholeDocument:options.wholeDocument ?? !link.tab_id, isCurrent:current,
      beforeOpen:async valid => {
        if (options.selectTerminal === false) return;
        const rows = await terminals(scope);
        if (!valid()) return;
        const terminal = rows.find(row => row.name === context.session_name && row.state === 'running')
          || rows.find(row => row.state === 'running');
        if (terminal) await window.LabTaskTerminalBridge?.show?.(terminal, {openDocument:false,isCurrent:valid,terminalScope:scope});
      }});
    if (opened === true && current()) lastDocument.set(rootKey(path), link.id);
    return opened !== false;
  }
  async function openForTerminal(session, options = {}) {
    if (session.document_source || !session.linked_scope?.root) return false;
    const path = session.linked_scope.root;
    const documentCurrent = window.AssistantView.navigationGuard?.() || (() => true);
    let data;
    try { data = await read(path); }
    catch (error) { if ([403,404].includes(error.status)) return false;throw error; }
    if (options.isCurrent && !options.isCurrent()) return false;
    // A later document click or close owns navigation, including while this
    // checkout's metadata is still loading. Do not fall back to another link.
    if (!documentCurrent()) return true;
    const links = data.links.filter(link => link.kind === 'internal' && !link.unavailable);
    const explicit = links.find(link => link.document_id === session.linked_task?.document_id
      && link.assistant_root === session.linked_task?.assistant_root);
    const link = explicit || links.find(link => link.id === lastDocument.get(rootKey(path))) || links[0];
    if (!link) return false;
    const scope = {...window.LabTaskTerminalBridge?.context?.(), root:path, session_name:session.name};
    return openDocument(explicit && session.linked_task?.task_id ? {...link,task_id:session.linked_task.task_id} : link,
      path, {...options,terminalScope:scope,selectTerminal:false});
  }
  async function addDocument(path, doc, current = () => true) {
    const data = await read(path, true), type = data.types.find(type => type.kind === 'internal');
    if (!type) throw new Error('Add an internal document link type in Settings first.');
    const same = data.links.some(link => link.kind === 'internal' && link.assistant_root === doc.assistant_root
      && link.document_id === doc.document_id && (link.tab_id || null) === (doc.tab_id || null));
    if (!same) {
      const link = {id:crypto.randomUUID(),type:type.id,assistant_root:doc.assistant_root,
        document_id:doc.document_id,tab_id:doc.tab_id || null};
      const saved = await api('/api/scope-links', {method:'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({path,links:[...data.links,link],expected:data.revision})});
      cache.set(path,{data:saved,at:Date.now()});
    }
    if (current()) document.querySelectorAll('[data-scope-links]').forEach(host => {
      if (rootKey(host.dataset.scopeLinks) === rootKey(path)) void mount(host, host._scopeLinksCurrent || current);
    });
  }
  function render(host, data, current) {
    host.innerHTML = `<div class="sidebar-scope-links-head"><span>Links</span><button type="button" data-edit-links aria-label="Edit links for this folder" title="Edit links">+</button></div><div class="sidebar-scope-links-list">${data.links.map((link, index) => `<button type="button" data-scope-link="${index}" class="sidebar-scope-link" ${link.unavailable ? 'disabled' : ''} title="${esc(link.unavailable ? link.error : ((serviceFor(link)?.name || typeName(link)) + ' · ' + (link.title || link.url)))}">${icon(link)}<span>${esc(label(link))}</span></button>`).join('')}</div>`;
    host.querySelector('[data-edit-links]').onclick = () => edit(host.dataset.scopeLinks, host._scopeLinksCurrent, host._scopeLinksScope);
    host.querySelectorAll('[data-scope-link]').forEach(button => button.onclick = async () => {
      if (!current()) return;
      const link = data.links[Number(button.dataset.scopeLink)];
      try {
        // Folder links belong to the clicking client, including SSH-forwarded
        // loopback sessions where the server's browser is on another desktop.
        if (link.kind === 'external') await window.LabExternalLinks.open(link.url, {clientOnly:true});
        else await openDocument(link, host.dataset.scopeLinks, {isCurrent:current});
      } catch (error) { if (current()) window.alert(error.message); }
    });
  }
  async function mount(host, current) {
    if (!host || !current()) return;
    const path = host.dataset.scopeLinks;
    host._scopeLinksCurrent = current;
    const token = host._scopeLinksToken = {};
    const valid = () => host.isConnected && host._scopeLinksToken === token && current();
    try {
      const data = await read(path);
      if (valid() && host._scopeLinksData !== data) {
        host._scopeLinksData = data;
        render(host, data, () => host.isConnected && host._scopeLinksCurrent());
      }
    }
    catch (error) {
      if (!valid()) return;
      host.innerHTML = '<button type="button" class="sidebar-scope-links-retry">Retry links</button>';
      host.title = error.message;
      host.firstElementChild.onclick = () => mount(host, current);
    }
  }
  function close(force = false) {
    if (!editor || !force && editor.dirty && !confirm('Discard your unsaved link changes?')) return;
    const old = editor; editor = null; old.abort.abort(); old.dialog.close(); old.dialog.remove();
    if (old.focus?.isConnected) old.focus.focus();
  }
  async function edit(path, current = () => true, scope = {}) {
    if (editor) { close(); if (editor) return; }
    const dialog = document.createElement('dialog'); dialog.className = 'scope-links-dialog';dialog.setAttribute('aria-labelledby','scopeMetadataTitle');
    dialog.innerHTML = `<form novalidate><div class="scope-links-heading"><div><span class="scope-links-eyebrow">${scope.kind === 'worktree' ? 'Worktree' : 'Project / folder'}</span><h2 id="scopeMetadataTitle">${esc(scope.label || path.split('/').pop())}</h2></div><button type="button" data-close aria-label="Close">×</button></div><p class="scope-links-path" title="${esc(path)}">${esc(path)}</p><p class="scope-links-intro">Click a link to edit it. Paste a URL to identify its service.</p><div data-link-cards>Loading…</div><div class="scope-links-add"><button type="button" data-add-link disabled>+ Add link</button><button type="button" data-add-document hidden>+ Internal document</button></div><div class="scope-links-footer"><span data-message role="status"></span><button type="submit" disabled>Save links</button></div></form>`;
    const s = editor = {dialog, path, current, abort:new AbortController(), dirty:false, focus:document.activeElement};
    document.body.append(dialog); dialog.showModal();
    const message = (value, error = false) => { const node=dialog.querySelector('[data-message]');node.textContent=value;node.classList.toggle('error',error); };
    dialog.querySelector('[data-close]').onclick = () => close();
    dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
    dialog.addEventListener('input', event => { if (!event.target.matches('[data-document-search],[data-tab-search]')) s.dirty=true; });
    dialog.addEventListener('change', event => { if (!event.target.matches('[data-document-search],[data-tab-search]')) s.dirty=true; });
    try {
      s.data = await read(path, true);
      if (editor !== s) return;
      dialog.querySelector('[data-link-cards]').replaceChildren();
      s.data.links.forEach(link => card(s, link));
      dialog.querySelector('[data-add-link]').disabled = false;
      dialog.querySelector('[type="submit"]').disabled = false;
      dialog.querySelector('[data-add-link]').onclick = () => { card(s);s.dirty=true; };
      const internalType = s.data.types.find(type => type.kind === 'internal');
      const addDocument = dialog.querySelector('[data-add-document]');
      addDocument.hidden = !internalType;
      addDocument.onclick = () => { card(s, {kind:'internal', type:internalType.id});s.dirty=true; };
      dialog.querySelector('form').onsubmit = async event => {
        event.preventDefault();
        const button=dialog.querySelector('[type="submit"]');button.disabled=true;message('Saving…');
        try {
          const links=[...dialog.querySelectorAll('[data-link-card]')].map(node => {
            if (!validateCard(node)) throw new Error('Complete the highlighted link before saving.');
            const row={id:node.dataset.linkCard,type:node._link.type,auto_type:node._link.auto_type,label:node.querySelector('[data-label]').value.trim()};
            if (node._kind === 'internal') {
              if(node._targetLoading)throw new Error('Wait for the document and its tabs to load before saving.');
              if(node._targetError)throw new Error(node._targetError);
              const doc=s.documents?.documents.find(doc=>doc.id===node._internalTarget?.documentId);
              if (!doc) throw new Error('Choose an internal document for each internal link.');
              return {...row,assistant_root:s.documents.root,document_id:doc.id,tab_id:node._internalTarget.tabId||null};
            }
            const url=node.querySelector('[data-url]').value.trim();
            // Preserve saved custom types on untouched URLs. Changed and new
            // URLs are inferred by the backend from the same service registry.
            const knownType=s.data.types.some(type=>type.id===row.type&&type.kind==='external') || services.some(service=>service.id===row.type) || row.type==='url';
            return {...row,...(url === node._link.url && knownType ? {} : {kind:'external'}),url};
          });
          const data=await api('/api/scope-links',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({path,links,expected:s.data.revision}),signal:s.abort.signal});
          cache.set(path,{data,at:Date.now()});
          if(editor!==s)return;
          if(current()) document.querySelectorAll('[data-scope-links]').forEach(host=>{
            if(host.dataset.scopeLinks===path) mount(host,current);
          });
          close(true);
        } catch(error) { if(editor===s&&error.name!=='AbortError') message(error.message,true); }
        finally { button.disabled=false; }
      };
    } catch(error) { if(editor===s&&error.name!=='AbortError') message(error.message,true); }
  }
  function card(s, link = {}) {
    const node=document.createElement('div');node.dataset.linkCard=link.id||crypto.randomUUID();node.className='scope-link-row';
    node._link=link;node._kind=link.kind || s.data.types.find(type=>type.id===link.type)?.kind || 'external';
    node.innerHTML=`<div class="scope-link-row-head"><button type="button" class="scope-link-row-toggle" data-edit-link aria-expanded="false" aria-controls="scope-link-fields-${esc(node.dataset.linkCard)}"><span data-row-icon>${icon({...link,kind:node._kind})}</span><span data-row-label></span><small data-row-service></small></button><button type="button" class="scope-link-remove" data-remove aria-label="Remove link" title="Remove link">×</button></div><div class="scope-link-fields" data-link-fields id="scope-link-fields-${esc(node.dataset.linkCard)}" hidden><label>Display name <span class="scope-links-hint">(optional)</span><input data-label maxlength="200" value="${esc(link.label||'')}" placeholder="Use the document title or site name"></label><div data-target></div><button type="button" data-done-link>Done</button></div>`;
    s.dialog.querySelector('[data-link-cards]').append(node);
    node.querySelector('[data-remove]').onclick=()=>{node.remove();s.dirty=true;};
    node.querySelector('[data-edit-link]').onclick=()=>setCardOpen(node,node.querySelector('[data-link-fields]').hidden);
    node.querySelector('[data-done-link]').onclick=()=>{
      if(validateCard(node)&&!node._targetLoading&&!node._targetError)setCardOpen(node,false);
    };
    node.querySelector('[data-label]').oninput=()=>updateCard(node);
    updateCard(node);
    void target(s,node,link);
    if(!link.id)setCardOpen(node,true);
  }
  function setCardOpen(node, open) {
    node.querySelector('[data-link-fields]').hidden=!open;
    node.querySelector('[data-edit-link]').setAttribute('aria-expanded',String(open));
    node.classList.toggle('is-editing',open);
    if(open)(node.querySelector('[data-url]') || node.querySelector('[data-label]')).focus();
    else node.querySelector('[data-edit-link]').focus();
  }
  function validateCard(node) {
    for(const input of node.querySelectorAll('[data-label],[data-url]')) {
      if(!input.checkValidity()) {setCardOpen(node,true);input.reportValidity();return false;}
    }
    return true;
  }
  function updateCard(node) {
    const original=node._link,url=node.querySelector('[data-url]')?.value.trim() ?? original.url;
    const service=serviceFor({url,...(url===original.url ? {type:original.type,auto_type:original.auto_type,type_name:original.base_type_name || original.type_name} : {})});
    const doc=node._documentTitle || original.title || 'Choose an internal document';
    const text=node.querySelector('[data-label]').value.trim() || (node._kind==='internal' ? doc : service?.name || url || 'New link');
    node.querySelector('[data-row-label]').textContent=text;
    node.querySelector('[data-row-service]').textContent=node._kind==='internal' ? node._documentDestination || 'Internal document' : service?.name || 'Link';
    node.querySelector('[data-row-icon]').innerHTML=icon({kind:node._kind,url,type:service?.id});
    node.querySelector('[data-edit-link]').title=node._kind==='internal' ? doc : url || 'Paste a URL';
    node.querySelector('[data-remove]').setAttribute('aria-label','Remove '+text);
  }
  function documentMatches(doc, query) {
    const text=`${doc.title} ${doc.search_text || ''}`.toLocaleLowerCase();
    return query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean).every(word=>text.includes(word));
  }
  async function documentDetail(s, doc) {
    if(!s.details) s.details=new Map();
    if(!s.details.has(doc.id)) {
      const pending=api('/api/assistant/note?path='+encodeURIComponent(doc.path),{signal:s.abort.signal});
      s.details.set(doc.id,pending);
      pending.catch(()=>{if(s.details.get(doc.id)===pending)s.details.delete(doc.id);});
    }
    return s.details.get(doc.id);
  }
  async function target(s,node,link) {
    const token=node._targetToken={};
    node._targetLoading=false;node._targetError='';
    const valid=()=>editor===s&&node.isConnected&&node._targetToken===token;
    const host=node.querySelector('[data-target]');
    node._externalUrl=host.querySelector('[data-url]')?.value ?? node._externalUrl ?? link.url ?? '';
    const internal=node._kind==='internal';
    if(!internal) {
      host.innerHTML=`<label>URL<input data-url type="url" value="${esc(node._externalUrl)}" placeholder="https://…" required maxlength="4096"></label>`;
      const input=host.querySelector('[data-url]');
      input.oninput=()=>{
        input.setCustomValidity('');
        if(input.value.trim())try{if(!['http:','https:'].includes(new URL(input.value.trim()).protocol))input.setCustomValidity('Use a full http or https URL.');}catch(_){input.setCustomValidity('Use a full http or https URL.');}
        updateCard(node);
      };
      input.oninput();return;
    }
    node._targetLoading=true;
    host.innerHTML='<p class="scope-links-hint">Loading internal documents…</p>';
    try {
      if(!s.documentsPromise) {
        s.documentsPromise=api('/api/assistant',{signal:s.abort.signal});
        s.documentsPromise.catch(()=>{s.documentsPromise=null;});
      }
      s.documents=await s.documentsPromise;
      if(!valid())return;
      if(!s.documents.configured) throw new Error('Configure an Assistant library to link internal documents.');
      if(!Array.isArray(s.documents.documents))throw new Error('No internal documents are available in this library.');
      const selected=node._internalTarget ||= {documentId:link.document_id||'',tabId:link.tab_id||''};
      let availableTabs=[],version=0,limit=80;
      host.innerHTML=`<div class="scope-document-summary" data-document-summary><span class="scope-document-glyph" aria-hidden="true">▤</span><span><strong data-document-title>Choose an internal document</strong><small data-document-destination>Link its whole content or a specific tab</small></span><button type="button" data-change-document>Choose document</button></div>
        <div class="scope-document-picker" data-document-picker>
          <div class="scope-document-search"><label>Search internal documents<input data-document-search type="search" placeholder="Search by title or content…" autocomplete="off"></label><small data-document-count role="status"></small></div>
          <div class="scope-document-columns"><section aria-label="Internal documents"><div class="scope-document-list" data-document-list></div><button type="button" data-more-documents hidden>Show more documents</button></section>
          <section class="scope-document-targets" aria-label="Document and tab destination"><h3>Open</h3><label class="scope-links-hint" data-tab-filter hidden>Find a tab<input data-tab-search type="search" placeholder="Filter tabs…"></label><div data-document-targets><p class="scope-document-empty">Choose a document to see its tabs.</p></div></section></div>
          <div class="scope-document-picker-footer"><span class="scope-links-hint">Choose the document, then where it opens.</span><button type="button" data-finish-document disabled>Done</button></div>
        </div><p class="scope-links-hint error" data-target-message role="status"></p>`;
      const picker=host.querySelector('[data-document-picker]'),search=host.querySelector('[data-document-search]');
      const status=host.querySelector('[data-target-message]'),finish=host.querySelector('[data-finish-document]');
      const doc=()=>s.documents.documents.find(doc=>doc.id===selected.documentId);
      const showPicker=open=>{
        picker.hidden=!open;host.querySelector('[data-change-document]').setAttribute('aria-expanded',String(open));
        if(open)search.focus();else host.querySelector('[data-change-document]').focus();
      };
      const summary=()=>{
        const chosen=doc(),tab=availableTabs.find(row=>row.id===selected.tabId);
        host.querySelector('[data-document-title]').textContent=chosen?.title || 'Choose an internal document';
        host.querySelector('[data-document-destination]').textContent=chosen ? (selected.tabId ? 'Tab · '+(tab?.name || 'Unavailable tab') : 'Whole document') : 'Link its whole content or a specific tab';
        host.querySelector('[data-change-document]').textContent=chosen?'Change':'Choose document';
        finish.disabled=!chosen||node._targetLoading||!!node._targetError;
        node._documentTitle=chosen ? chosen.title+(selected.tabId&&tab ? ' / '+tab.name : '') : '';
        node._documentDestination=host.querySelector('[data-document-destination]').textContent;
        updateCard(node);
      };
      function renderDocuments() {
        const matches=s.documents.documents.filter(doc=>documentMatches(doc,search.value));
        host.querySelector('[data-document-count]').textContent=matches.length+' document'+(matches.length===1?'':'s');
        host.querySelector('[data-document-list]').innerHTML=matches.slice(0,limit).map(row=>`<button type="button" class="scope-document-option" data-document="${esc(row.id)}" aria-pressed="${row.id===selected.documentId}"><span class="scope-document-glyph" aria-hidden="true">▤</span><span><strong>${esc(row.title)}</strong><small>${esc(row.workspace_name || row.summary?.slice(0,100) || 'Internal document')}</small></span><span class="scope-document-check" aria-hidden="true">${row.id===selected.documentId?'✓':''}</span></button>`).join('')||'<p class="scope-document-empty">No documents match this search.</p>';
        host.querySelector('[data-more-documents]').hidden=matches.length<=limit;
        host.querySelectorAll('[data-document]').forEach(button=>button.onclick=()=>{
          if(selected.documentId===button.dataset.document&&!node._targetError)return;
          selected.documentId=button.dataset.document;selected.tabId='';s.dirty=true;
          host.querySelector('[data-tab-search]').value='';
          renderDocuments();void loadTabs();
        });
      }
      function renderTabs() {
        const query=host.querySelector('[data-tab-search]').value.trim().toLocaleLowerCase();
        const matches=availableTabs.filter(row=>row.name.toLocaleLowerCase().includes(query));
        host.querySelector('[data-document-targets]').innerHTML=`<button type="button" class="scope-document-option scope-document-whole" data-tab="" aria-pressed="${!selected.tabId&&!node._targetError}"><span class="scope-document-glyph" aria-hidden="true">▤</span><span><strong>Whole document</strong><small>Open the main content</small></span><span class="scope-document-check" aria-hidden="true">${!selected.tabId&&!node._targetError?'✓':''}</span></button>${availableTabs.length?'<p class="scope-document-section-label">Document tabs</p>':'<p class="scope-document-empty">This document has no additional tabs.</p>'}${matches.map(row=>`<button type="button" class="scope-document-option" data-tab="${esc(row.id)}" style="--tab-depth:${Math.min(row.depth,6)}" aria-pressed="${row.id===selected.tabId}"><span class="scope-document-tab-glyph" aria-hidden="true">↳</span><span><strong>${esc(row.name)}</strong><small>Only this tab</small></span><span class="scope-document-check" aria-hidden="true">${row.id===selected.tabId?'✓':''}</span></button>`).join('')}${query&&!matches.length?'<p class="scope-document-empty">No tabs match this search.</p>':''}`;
        host.querySelectorAll('[data-tab]').forEach(button=>button.onclick=()=>{
          selected.tabId=button.dataset.tab;node._targetError='';status.textContent='';s.dirty=true;
          renderTabs();summary();host.querySelector('[data-finish-document]').focus();
        });
      }
      async function loadTabs() {
        const request=++version,chosen=doc();availableTabs=[];
        node._targetLoading=!!chosen;node._targetError='';status.textContent='';summary();
        host.querySelector('[data-tab-filter]').hidden=true;
        if(!chosen) {
          node._targetLoading=false;
          if(selected.documentId){node._targetError='The previously selected document is unavailable. Choose another document.';status.textContent=node._targetError;}
          summary();return;
        }
        host.querySelector('[data-document-targets]').innerHTML='<p class="scope-document-empty">Loading document tabs…</p>';
        try {
          const detail=await documentDetail(s,chosen);
          if(!valid()||request!==version)return;
          availableTabs=tabs(detail.tree);
          if(selected.tabId&&!availableTabs.some(row=>row.id===selected.tabId)) {
            node._targetError='The previously selected tab is unavailable. Choose a target before saving.';
            status.textContent=node._targetError;
          }
          host.querySelector('[data-tab-filter]').hidden=availableTabs.length<6;
          renderTabs();
        }catch(error){if(valid()&&request===version&&error.name!=='AbortError'){
          node._targetError=error.message;status.textContent=error.message;
          host.querySelector('[data-document-targets]').innerHTML='<button type="button" data-retry-tabs>Retry loading tabs</button>';
          host.querySelector('[data-retry-tabs]').onclick=()=>void loadTabs();
        }}
        finally{if(valid()&&request===version){node._targetLoading=false;summary();}}
      }
      search.oninput=()=>{limit=80;renderDocuments();};
      search.onkeydown=event=>{
        if(event.key==='ArrowDown'){event.preventDefault();host.querySelector('[data-document]')?.focus();}
        if(event.key==='Enter')event.preventDefault();
      };
      host.querySelector('[data-tab-search]').oninput=renderTabs;
      host.querySelector('[data-tab-search]').onkeydown=event=>{if(event.key==='Enter')event.preventDefault();};
      host.querySelector('[data-more-documents]').onclick=()=>{limit+=80;renderDocuments();};
      host.querySelector('[data-change-document]').onclick=()=>showPicker(picker.hidden);
      finish.onclick=()=>showPicker(false);
      renderDocuments();summary();
      // Keep saved links compact; open the browser for new or unavailable targets.
      picker.hidden=!!doc();host.querySelector('[data-change-document]').setAttribute('aria-expanded',String(!picker.hidden));
      await loadTabs();
      if(node._targetError){setCardOpen(node,true);showPicker(true);}
    }catch(error){if(valid()&&error.name!=='AbortError'){node._targetError=error.message;node._targetLoading=false;host.textContent=error.message;}}
  }
  function dropTarget(target) {
    const row = target.closest?.('.sidebar-scope-chip, .sidebar-scope-links[data-scope-links]');
    const path = row?.dataset.scopeLinks || row?.dataset.folderPath || row?.dataset.baseRoot;
    return path ? {row,path} : null;
  }
  function clearDrop() { document.querySelectorAll('.scope-document-drop').forEach(row => row.classList.remove('scope-document-drop')); }
  document.addEventListener('dragover', event => {
    if (!event.dataTransfer?.types.includes(documentMime)) return;
    clearDrop();const target = dropTarget(event.target);if (!target) return;
    event.preventDefault();event.stopPropagation();event.dataTransfer.dropEffect='link';target.row.classList.add('scope-document-drop');
  }, true);
  document.addEventListener('drop', async event => {
    if (!event.dataTransfer?.types.includes(documentMime)) return;
    clearDrop();const target = dropTarget(event.target);if (!target) return;
    event.preventDefault();event.stopPropagation();
    document.querySelector('.drag-document-out')?.classList.remove('drag-document-out');
    try {
      await addDocument(target.path, JSON.parse(event.dataTransfer.getData(documentMime)),
        () => target.row.isConnected);
      if (typeof explorerToast === 'function') explorerToast('Document linked to folder/worktree. Uses its checkout terminal.');
    } catch (error) { if (typeof explorerToast === 'function') explorerToast(error.message,true); }
  }, true);
  document.addEventListener('dragend', clearDrop);
  window.LabScopeLinks={mount,edit,label,serviceFor,icon,setDomainMappings,tabs,documentMatches,openDocument,openForTerminal,addDocument,terminals,matchesTerminal};
})();
