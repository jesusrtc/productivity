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
    return (tree?.children || []).flatMap(row => [{id:row.id, title:'· '.repeat(depth) + row.title}, ...tabs(row, depth + 1)]);
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
    host.querySelector('[data-edit-links]').onclick = () => edit(host.dataset.scopeLinks, host._scopeLinksCurrent);
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
  async function edit(path, current) {
    if (editor) { close(); if (editor) return; }
    const dialog = document.createElement('dialog'); dialog.className = 'scope-links-dialog';
    dialog.innerHTML = `<form><div class="scope-links-heading"><h2>Folder links</h2><button type="button" data-close aria-label="Close">×</button></div><p class="scope-links-path">${esc(path)}</p><div data-link-cards>Loading…</div><button type="button" data-add-link disabled>+ Add link</button><div class="scope-links-footer"><span data-message role="status"></span><button type="submit" disabled>Save links</button></div><p class="scope-links-hint">Manage allowed link types in Settings → Global → Link types.</p></form>`;
    const s = editor = {dialog, path, current, abort:new AbortController(), dirty:false, focus:document.activeElement};
    document.body.append(dialog); dialog.showModal();
    const message = (value, error = false) => { const node=dialog.querySelector('[data-message]');node.textContent=value;node.classList.toggle('error',error); };
    dialog.querySelector('[data-close]').onclick = () => close();
    dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
    dialog.addEventListener('input', () => { s.dirty=true; });
    dialog.addEventListener('change', () => { s.dirty=true; });
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
              const doc=s.documents?.documents.find(doc=>doc.id===node.querySelector('[data-document]')?.value);
              if (!doc) throw new Error('Choose an internal document for each internal link.');
              return {...row,assistant_root:s.documents.root,document_id:doc.id,tab_id:node.querySelector('[data-tab]')?.value||null};
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
  async function target(s,node,link) {
    const token=node._targetToken={};
    node._targetLoading=false;node._targetError='';
    const valid=()=>editor===s&&node.isConnected&&node._targetToken===token;
    const host=node.querySelector('[data-target]');
    const internal=s.data.types.find(row=>row.id===node.querySelector('[data-type]').value)?.kind==='internal';
    if(!internal) {host.innerHTML=`<label>URL<input data-url type="url" value="${esc(link.url||'')}" placeholder="https://…" required></label>`;return;}
    node._targetLoading=true;
    host.innerHTML='<p class="scope-links-hint">Loading internal documents…</p>';
    try {
      if(!s.documentsPromise) s.documentsPromise=api('/api/assistant',{signal:s.abort.signal});
      s.documents=await s.documentsPromise;
      if(!valid())return;
      if(!s.documents.configured) throw new Error('Configure an Assistant library to link internal documents.');
      host.innerHTML=`<label>Find a document<input data-document-search type="search" placeholder="Filter documents…"></label><label>Internal document<select data-document required><option value="">Choose a document…</option></select></label><label>Open<select data-tab><option value="">Entire document</option></select></label><p class="scope-links-hint" data-target-message></p>`;
      const select=host.querySelector('[data-document]'),search=host.querySelector('[data-document-search]');
      let chosen=link.document_id||'';
      const filter=()=>{
        const query=search.value.trim().toLowerCase();
        select.innerHTML='<option value="">Choose a document…</option>'+s.documents.documents.filter(doc=>doc.id===chosen||`${doc.title} ${doc.search_text||''}`.toLowerCase().includes(query)).map(doc=>`<option value="${esc(doc.id)}" ${doc.id===chosen?'selected':''}>${esc(doc.title)}</option>`).join('');
      };
      search.oninput=filter;filter();
      let version=0;
      const loadTabs=async(selectedTab='')=>{
        const request=++version,tab=host.querySelector('[data-tab]');
        node._targetLoading=true;node._targetError='';
        tab.innerHTML='<option value="">Entire document</option>';tab.disabled=true;
        const doc=s.documents.documents.find(doc=>doc.id===select.value);
        if(!doc){node._targetLoading=false;return;}
        try {
          const detail=await api('/api/assistant/note?path='+encodeURIComponent(doc.path),{signal:s.abort.signal});
          if(!valid()||version!==request)return;
          tab.innerHTML='<option value="">Entire document</option>'+tabs(detail.tree).map(row=>`<option value="${esc(row.id)}" ${row.id===selectedTab?'selected':''}>Tab: ${esc(row.title)}</option>`).join('');
          tab.disabled=false;
          if(selectedTab&&!tabs(detail.tree).some(row=>row.id===selectedTab)) {
            node._targetError='The previously selected tab is unavailable. Choose a target before saving.';
            host.querySelector('[data-target-message]').textContent=node._targetError;
            tab.onchange=()=>{node._targetError='';host.querySelector('[data-target-message]').textContent='';};
          }
        }catch(error){if(valid()&&error.name!=='AbortError'){node._targetError=error.message;host.querySelector('[data-target-message]').textContent=error.message;}}
        finally{if(valid()&&version===request)node._targetLoading=false;}
      };
      select.onchange=()=>{chosen=select.value;host.querySelector('[data-target-message]').textContent='';void loadTabs();};
      if(chosen)await loadTabs(link.tab_id);
      else node._targetLoading=false;
    }catch(error){if(valid()&&error.name!=='AbortError'){node._targetError=error.message;node._targetLoading=false;host.textContent=error.message;}}
  }
  window.LabScopeLinks={mount,edit,label,tabs};
})();
