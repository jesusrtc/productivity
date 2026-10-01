/* Links belong to an exact folder/checkout, shared across Lab workspaces. */
(function () {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const cache = new Map();
  let editor = null;
  async function api(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not load links.');
    return data;
  }
  function label(link) { return link.label || link.title || link.type_name || link.url || 'Document'; }
  function tabs(tree, depth = 0) {
    return (tree?.children || []).flatMap(row => [{id:row.id, title:'· '.repeat(depth) + row.title, name:row.title, depth}, ...tabs(row, depth + 1)]);
  }
  async function read(path, fresh = false) {
    const saved = cache.get(path);
    if (!fresh && saved && Date.now() - saved.at < 60000) return saved.data;
    if (saved?.pending) return saved.pending;
    const pending = api('/api/scope-links?path=' + encodeURIComponent(path)).then(data => {
      cache.set(path, {data, at:Date.now()}); return data;
    }).catch(error => { if (cache.get(path)?.pending === pending) cache.delete(path); throw error; });
    cache.set(path, {...saved, pending});
    return pending;
  }
  function render(host, data, current) {
    host.innerHTML = `<div class="sidebar-scope-links-head"><span>Links</span><button type="button" data-edit-links aria-label="Edit links for this folder" title="Edit links">+</button></div><div class="sidebar-scope-links-list">${data.links.map((link, index) => `<button type="button" data-scope-link="${index}" class="sidebar-scope-link" ${link.unavailable ? 'disabled' : ''} title="${esc(link.unavailable ? link.error : (link.type_name + ' · ' + (link.title || link.url)))}"><span aria-hidden="true">${link.kind === 'internal' ? '▤' : '↗'}</span><span>${esc(label(link))}</span></button>`).join('')}</div>`;
    host.querySelector('[data-edit-links]').onclick = () => edit(host.dataset.scopeLinks, host._scopeLinksCurrent, host._scopeLinksScope);
    host.querySelectorAll('[data-scope-link]').forEach(button => button.onclick = async () => {
      if (!current()) return;
      const link = data.links[Number(button.dataset.scopeLink)];
      try {
        if (link.kind === 'external') await window.LabExternalLinks.open(link.url);
        else await window.AssistantView.openLinkedTask(link, {inline:true, wholeDocument:!link.tab_id, isCurrent:current});
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
    dialog.innerHTML = `<form><div class="scope-links-heading"><div><span class="scope-links-eyebrow">${scope.kind === 'worktree' ? 'Worktree' : 'Project / folder'}</span><h2 id="scopeMetadataTitle">${esc(scope.label || path.split('/').pop())}</h2></div><button type="button" data-close aria-label="Close">×</button></div><p class="scope-links-path">${esc(path)}</p><p class="scope-links-intro">Keep documents, tickets, and useful links with this checkout.</p><div data-link-cards>Loading…</div><button type="button" data-add-link disabled>+ Add link</button><div class="scope-links-footer"><span data-message role="status"></span><button type="submit" disabled>Save links</button></div><p class="scope-links-hint">Manage allowed link types in Settings → Global → Link types.</p></form>`;
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
      dialog.querySelector('form').onsubmit = async event => {
        event.preventDefault();
        const button=dialog.querySelector('[type="submit"]');button.disabled=true;message('Saving…');
        try {
          const links=[...dialog.querySelectorAll('[data-link-card]')].map(node => {
            const type=node.querySelector('[data-type]').value;
            const row={id:node.dataset.linkCard,type,label:node.querySelector('[data-label]').value.trim()};
            if (s.data.types.find(row=>row.id===type)?.kind==='internal') {
              if(node._targetLoading)throw new Error('Wait for the document and its tabs to load before saving.');
              if(node._targetError)throw new Error(node._targetError);
              const doc=s.documents?.documents.find(doc=>doc.id===node._internalTarget?.documentId);
              if (!doc) throw new Error('Choose an internal document for each internal link.');
              return {...row,assistant_root:s.documents.root,document_id:doc.id,tab_id:node._internalTarget.tabId||null};
            }
            return {...row,url:node.querySelector('[data-url]')?.value.trim()||''};
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
    const node=document.createElement('fieldset');node.dataset.linkCard=link.id||crypto.randomUUID();
    node.innerHTML=`<legend>Link</legend><div class="scope-links-card-head"><label>Type<select data-type required>${link.type&&!s.data.types.some(type=>type.id===link.type)?'<option value="" selected>Choose an allowed type…</option>':''}${s.data.types.map(type=>`<option value="${esc(type.id)}" ${type.id===link.type?'selected':''}>${esc(type.name)}</option>`).join('')}</select></label><button type="button" data-remove>Remove</button></div><label>Display name <span class="scope-links-hint">(optional)</span><input data-label value="${esc(link.label||'')}" placeholder="Use document title or link type"></label><div data-target></div>`;
    s.dialog.querySelector('[data-link-cards]').append(node);
    node.querySelector('[data-remove]').onclick=()=>{node.remove();s.dirty=true;};
    const type=node.querySelector('[data-type]');
    type.onchange=()=>target(s,node,link);
    void target(s,node,link);
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
    const internal=s.data.types.find(row=>row.id===node.querySelector('[data-type]').value)?.kind==='internal';
    if(!internal) {host.innerHTML=`<label>URL<input data-url type="url" value="${esc(node._externalUrl)}" placeholder="https://…" required></label>`;return;}
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
      if(node._targetError)showPicker(true);
    }catch(error){if(valid()&&error.name!=='AbortError'){node._targetError=error.message;node._targetLoading=false;host.textContent=error.message;}}
  }
  window.LabScopeLinks={mount,edit,label,tabs,documentMatches};
})();
