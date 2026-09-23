// A document reference never copies content or starts a terminal.
(() => {
  const mime = 'application/x-lab-assistant-document';
  let bridge, attention = {}, polling = false, lastPoll = 0;
  let selected = null, opened = null;
  const terminalLinks = new Map();
  const cache = new Map();
  const escape = value => String(value || '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const scopeKey = scope => `${scope.vault || 'framework'}::${scope.workspace_id}`;
  const documentKey = doc => doc?.assistant_root && doc?.document_id ? JSON.stringify([doc.assistant_root, doc.document_id]) : '';
  const notify = (text, error = false) => typeof explorerToast === 'function' && explorerToast(text, error);
  async function api(path = '', body, method = 'POST') {
    const response = await fetch('/api/workspace-documents' + path, body ? {
      method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(body),
    } : undefined);
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Could not update document link.');
    return result;
  }
  function render(host, documents, scope) {
    const assistant = scope.workspace_id === '__assistant__';
    const html = `<div class="sidebar-title">${assistant ? 'Linked documents' : 'Documents'} <span class="sidebar-title-count">${documents.length || ''}</span></div>` +
      (documents.length ? documents.map(doc => `<div class="sidebar-file workspace-document" ${doc.missing ? '' : 'draggable="true" data-assistant-document-drag'} data-assistant-root="${escape(doc.assistant_root)}" data-terminal-document="${escape(doc.document_id)}" data-document-identity="${escape(documentKey(doc))}">
        <button type="button" class="workspace-document-open" ${doc.missing ? 'disabled' : ''} title="${escape(doc.missing ? 'Document unavailable' : doc.path)}"><span aria-hidden="true">▤</span><span>${escape(doc.title || doc.document_id)}</span></button>
        ${assistant ? '' : `<button type="button" class="workspace-document-remove" aria-label="Unlink ${escape(doc.title || 'document')}" title="Remove workspace link">×</button>`}</div>`).join('')
        : `<p class="workspace-documents-empty">${assistant ? 'Documents linked to Assistant terminals appear here.' : 'Drag an Assistant document here or onto the workspace tab.'}</p>`);
    if (host._documentsHtml === html) { paintSelection(); return; }
    host._documentsHtml = html; host.innerHTML = html;
    host.querySelectorAll('.workspace-document').forEach((row, index) => {
      const doc = documents[index];
      window.AssistantView.bindDocumentLink(row.querySelector('.workspace-document-open'), options =>
        window.AssistantView.openLinkedTask(doc, options).catch(error => notify(error.message, true)));
      const remove = row.querySelector('.workspace-document-remove');
      if (remove) remove.onclick = async () => {
        try {
          await api('', {...scope, document_id:doc.document_id, assistant_root:doc.assistant_root}, 'DELETE');
          cache.delete(scopeKey(scope)); await mount(scope, host.parentElement, true);
          await bridge?.refresh(); void poll(true);
        } catch (error) { notify(error.message, true); }
      };
    });
    paintSelection();
  }
  function paintSelection() {
    document.querySelectorAll('[data-workspace-documents]').forEach(host => {
      const key = scopeKey({workspace_id:host.dataset.workspaceId,vault:host.dataset.vault});
      host.querySelectorAll('[data-document-identity]').forEach(row => {
        const active = selected?.scope === key && selected.key === row.dataset.documentIdentity;
        const isOpen = opened?.key === row.dataset.documentIdentity;
        row.classList.toggle('terminal-selected', active);
        row.classList.toggle('document-open', isOpen);
        const button = row.querySelector('.workspace-document-open');
        if (active || isOpen) button.setAttribute('aria-current', active ? 'true' : 'page');
        else button.removeAttribute('aria-current');
      });
    });
  }
  async function mount(scope, sidebar, force = false) {
    const host = sidebar?.querySelector('[data-workspace-documents]');
    if (!host || !scope) return;
    const key = scopeKey(scope);
    host.dataset.workspaceId = scope.workspace_id; host.dataset.vault = scope.vault || '';
    const saved = cache.get(key);
    render(host, saved?.documents || [], scope);
    if (!force && saved?.at > Date.now() - 10000) return;
    const token = {}; host._documentRequest = token;
    try {
      const documents = await api('?' + new URLSearchParams({workspace_id:scope.workspace_id, ...(scope.vault ? {vault:scope.vault} : {})}));
      cache.set(key, {documents, at:Date.now()});
      if (host.isConnected && host._documentRequest === token && scopeKey({workspace_id:host.dataset.workspaceId,vault:host.dataset.vault}) === key) render(host, documents, scope);
    } catch (error) {
      if (host.isConnected && host._documentRequest === token) {
        const message = document.createElement('p'); message.className = 'workspace-documents-error'; message.textContent = error.message;
        host.querySelector('.workspace-documents-error')?.remove(); host.append(message);
      }
    }
  }
  function dropTarget(target) {
    const row = target.closest?.('.workspace-tab[data-kind="workspace"], [data-workspace-documents]');
    return row?.dataset.workspaceId && row.dataset.workspaceId !== '__assistant__' ? row : null;
  }
  function clearDrop() { document.querySelectorAll('.workspace-document-drop').forEach(row => row.classList.remove('workspace-document-drop')); }
  document.addEventListener('dragstart', event => {
    const row = event.target.closest?.('[data-assistant-document-drag]');
    if (!row || event.target.closest('input,textarea,select,a,button:not(.assistant-document-row):not(.workspace-document-open)')) return;
    event.dataTransfer.setData(mime, JSON.stringify({document_id:row.dataset.terminalDocument, assistant_root:row.dataset.assistantRoot}));
    event.dataTransfer.effectAllowed = 'link';
    row.closest('.assistant-document-overlay')?.classList.add('drag-document-out');
  });
  document.addEventListener('dragover', event => {
    if (!event.dataTransfer.types.includes(mime)) return;
    clearDrop();
    const target = dropTarget(event.target);
    if (!target) return;
    event.preventDefault(); event.stopPropagation(); event.dataTransfer.dropEffect = 'link'; target.classList.add('workspace-document-drop');
  }, true);
  document.addEventListener('drop', async event => {
    if (!event.dataTransfer.types.includes(mime)) return;
    clearDrop();
    document.querySelector('.drag-document-out')?.classList.remove('drag-document-out');
    const target = dropTarget(event.target);
    if (!target) return;
    event.preventDefault(); event.stopPropagation();
    const scope = {workspace_id:target.dataset.workspaceId, vault:target.dataset.vault || null};
    try {
      const doc = JSON.parse(event.dataTransfer.getData(mime));
      await api('', {...scope, document_id:doc.document_id, assistant_root:doc.assistant_root});
      cache.delete(scopeKey(scope));
      const current = bridge?.workspace();
      if (current && scopeKey(current) === scopeKey(scope)) await mount(current, document.getElementById('sidebar'), true);
      await bridge?.refresh(); void poll(true); notify('Document linked to workspace.');
    } catch (error) { notify(error.message, true); }
  }, true);
  document.addEventListener('dragend', () => { clearDrop(); document.querySelector('.drag-document-out')?.classList.remove('drag-document-out'); });

  async function unlink(session, context) {
    const scope = bridge?.workspace();
    if (!scope) {
      await window.LabTaskTerminalBridge.patch(session, {linked_task:null}, context);
      return true;
    }
    const choice = await new Promise(resolve => {
      const dialog = document.createElement('dialog'); dialog.className = 'workspace-document-unlink';
      dialog.innerHTML = '<h2>Unlink terminal</h2><p>Where should this terminal belong after removing its document link? Its running work and conversation will stay intact.</p><p role="alert"></p><div><button value="workspace">Keep in workspace</button><button value="assistant">Move to Assistant</button><button value="cancel">Cancel</button></div>';
      document.body.append(dialog);
      dialog.addEventListener('close', () => { const value = dialog.returnValue; dialog.remove(); resolve(value); }, {once:true});
      dialog.querySelectorAll('button').forEach(button => button.onclick = () => dialog.close(button.value));
      dialog.showModal();
    });
    if (!['workspace','assistant'].includes(choice)) return false;
    const source = session.document_source || {workspace_id:session.workspace_id || context?.workspaceId || scope.workspace_id,
      vault:session.vault || context?.vaultId || scope.vault, logical_name:session.logical_name};
    await api('/unlink-terminal', {...scope, source_workspace_id:source.workspace_id, source_vault:source.vault,
      name:source.logical_name, linked_task:session.linked_task, destination:choice});
    await bridge?.refresh(); await window.LabDocumentTerminal?.refresh(); void poll(true);
    return true;
  }
  function paintAttention() {
    const completion = window.LabTerminalCompletion;
    if (!completion) return;
    document.querySelectorAll('.workspace-tab[data-kind="workspace"]').forEach(tab => {
      const scope = scopeKey({workspace_id:tab.dataset.workspaceId, vault:tab.dataset.vault});
      const ready = (attention[scope] || []).some(session => completion.meta(scope, session));
      let dot = tab.querySelector('.workspace-attention-dot');
      if (ready && !dot) {
        dot = document.createElement('span'); dot.className = 'workspace-attention-dot'; dot.setAttribute('role','img');
        dot.setAttribute('aria-label','Terminal work ready to review'); dot.title = 'Terminal work ready to review';
        tab.querySelector('.x')?.before(dot);
      } else if (!ready && dot) dot.remove();
    });
  }
  async function poll(force = false) {
    if (polling || document.hidden || (!force && Date.now() - lastPoll < 10000)) { paintAttention(); return; }
    polling = true;
    try {
      attention = await api('/attention'); lastPoll = Date.now(); paintAttention();
      const scope = bridge?.context?.();
      if (scope) void mount(scope, document.getElementById('sidebar'));
    }
    catch { /* Keep the last verified state during a transient disconnect. */ }
    finally { polling = false; }
  }
  window.addEventListener('lab-terminal-completion-change', paintAttention);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) void poll(true); });
  window.LabWorkspaceDocuments = {mount, unlink, paintAttention, poll,
    configure(value) { bridge = value; },
    selectTerminal(session, scope) { selected = {scope:scopeKey(scope),key:documentKey(session?.linked_task)}; paintSelection(); },
    openDocument(doc) { opened = doc ? {key:documentKey(doc)} : null; paintSelection(); },
    updateSessions(scope, sessions) {
      attention[scope] = sessions; paintAttention();
      const context = bridge?.context?.();
      if (context?.workspace_id !== '__assistant__' || scopeKey(context) !== scope) return;
      const signature = JSON.stringify(sessions.map(row => [row.name,row.linked_task]));
      if (terminalLinks.get(scope) === signature) return;
      terminalLinks.set(scope,signature); cache.delete(scope);
      void mount(context, document.getElementById('sidebar'), true);
    }};
})();
