/* Task links reuse existing sessions. Opening a document never starts a process. */
(function () {
  'use strict';
  let current = null, dragged = null;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const sessionLabel = session => window.LabTaskTerminalBridge?.display?.(session)
    || session.label || session.linked_task?.title || session.logical_name || session.name || '';
  async function api(url, options = {}) {
    const response = await fetch(url, options), result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Could not load terminals');
    return result;
  }
  function remembered(state, value) {
    const key = 'lab.task-terminal:' + state.database + ':' + state.documentId + (state.scope
      ? ':'+JSON.stringify([state.scope.workspace_id,state.scope.vault,state.scope.root]) : '');
    try {
      if (value !== undefined) localStorage.setItem(key, JSON.stringify(value));
      return JSON.parse(localStorage.getItem(key) || 'null');
    } catch (_) { return null; }
  }
  async function request(path, action, signal) {
    const response = await fetch('/api/assistant/document-terminal', {method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify({path,action}), signal});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Could not open the terminal');
    return result;
  }
  function releaseView(state) {
    state.viewAbort?.abort(); state.viewAbort = null;
    state.observer?.disconnect(); state.observer = null;
    if (state.frame) cancelAnimationFrame(state.frame);
    state.frame = null;
    const socket = state.socket; state.socket = null;
    if (socket) { socket.onclose = socket.onmessage = socket.onerror = socket.onopen = null; socket.close(); }
    state.input?.dispose(); state.input = null;
    state.terminal?.dispose(); state.terminal = null;
    state.host.querySelector('.assistant-terminal-screen')?.replaceChildren();
  }
  function close() {
    if (!current) return;
    const state = current; current = null;
    state.abort.abort(); clearInterval(state.poll); clearTimeout(state.activityTimer);
    releaseView(state); state.host.replaceChildren(); state.host.hidden = true;
    for (const row of [state.host, document.querySelector('#assistantDocumentModal .assistant-modal-header'), document.getElementById('assistantModalTitle')]) {
      if (!row) continue;
      delete row.dataset.terminalDocument; delete row.dataset.assistantRoot; delete row.dataset.documentPath;
    }
    requestAnimationFrame(() => { if (typeof termRenderSessionList === 'function') termRenderSessionList(); });
  }
  function show(state, result, error = '') {
    if (state !== current) return;
    state.result = result;
    const label = state.host.querySelector('[data-terminal-status]');
    const waiting = result.reason === 'memory_check' ? 'Memory check unavailable — retry when ready' : 'Low memory — retry when ready';
    label.textContent = error || (result.state === 'waiting' ? waiting : '') || ({running:({busy:'Working',idle:'Ready',draft:'Unsent text kept open'}[result.work_state] || 'Running'),sleeping:'Sleeping — memory released',absent:'Drag a terminal onto a task or choose an existing terminal',stopped:'Linked terminal is stopped',disabled:'Previous document terminals are disabled'}[result.state] || 'Ready');
    label.classList.toggle('error',Boolean(error));
    if (state.scope && !error) label.textContent = result.state === 'running' ? 'Uses this folder/worktree terminal'
      : result.state === 'stopped' ? 'Checkout terminal is stopped. Resume it from the terminal bar.'
      : 'Attach a terminal to this folder/worktree to work on the document.';
    state.host.querySelector('[data-terminal-agent]').textContent = result.linked ? sessionLabel(result) : result.label || result.agent || '';
    state.host.classList.toggle('has-terminal', !state.inline && result.state === 'running');
    state.host.querySelector('[data-terminal-show]').hidden = !state.inline || !result.linked || result.state !== 'running';
    const wake = state.host.querySelector('[data-terminal-wake]');
    wake.hidden = result.linked ? !(result.state === 'stopped' && result.kind !== 'attached' || result.state === 'running' && error) : !['sleeping','waiting'].includes(result.state) && !error;
    if (state.inline) wake.hidden = true;
    wake.disabled = result.state === 'disabled';
    wake.textContent = result.linked ? (result.state === 'stopped' ? 'Resume terminal' : 'Reconnect') : result.state === 'sleeping' ? 'Resume previous conversation' : 'Try again';
    state.host.querySelector('[data-terminal-sleep]').hidden = state.inline || result.linked || result.state !== 'running' || Boolean(error);
    if (result.state !== 'running') releaseView(state);
  }
  function used(state) {
    if (state !== current || state.result?.state !== 'running' || state.result.linked) return;
    
    if (state.activityTimer) return;
    state.activityTimer = setTimeout(() => {
      state.activityTimer = null;
      if (state !== current) return;
      void request(state.path,'activity',state.abort.signal).catch(() => {});
    }, 30000); // At most two activity writes/minute; WS keystrokes stay in RAM.
  }
  async function attach(state, result) {
    if (state !== current || state.inline || state.result !== result || document.hidden || state.socket || result.state !== 'running') return;
    if (typeof window.ensureTerminalLibs !== 'function') throw new Error('Terminal support is loading. Try again.');
    await Promise.all([window.ensureTerminalLibs(), window.loadStyleOnce?.('/static/vendor/xterm@5.3.0/xterm.min.css')]);
    if (state !== current || state.result !== result || document.hidden || state.socket) return;
    const screen = state.host.querySelector('.assistant-terminal-screen');
    state.viewAbort = new AbortController();
    const terminal = state.terminal = new Terminal({fontSize:12,scrollback:2000,cursorBlink:false,
      fontFamily:'ui-monospace, SFMono-Regular, Menlo, monospace',
      theme:{background:'#0a0e13',foreground:'#e6edf3',cursor:'#58a6ff'},
      linkHandler:{activate:(_,url) => window.LabExternalLinks?.open(url,{clientOnly:true})}});
    window._termGuardViewportDisposal?.(terminal);
    const fit = new FitAddon.FitAddon(); terminal.loadAddon(fit); terminal.open(screen); fit.fit();
    const socket = state.socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/term/${encodeURIComponent(result.name)}?cols=${terminal.cols}&rows=${terminal.rows}`);
    const send = message => { if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message)); };
    state.input = terminal.onData(data => { used(state); send({type:'input',data}); });
    // Keep native text selection while forwarding wheel gestures to tmux.
    // Otherwise mouse tracking consumes click/drag selection in the agent TUI.
    let wheel = 0;
    screen.addEventListener('wheel', event => {
      if (socket.readyState !== WebSocket.OPEN) return;
      event.preventDefault(); event.stopPropagation(); used(state);
      if (Math.sign(wheel) !== Math.sign(event.deltaY)) wheel = 0;
      wheel += event.deltaY;
      const ticks = Math.trunc(wheel / 100); wheel -= ticks * 100;
      const rect = screen.getBoundingClientRect();
      const col = Math.max(1, Math.min(terminal.cols, Math.floor((event.clientX - rect.left) / (rect.width / terminal.cols)) + 1));
      const row = Math.max(1, Math.min(terminal.rows, Math.floor((event.clientY - rect.top) / (rect.height / terminal.rows)) + 1));
      for (let i = 0; i < Math.min(20, Math.abs(ticks)); i++) send({type:'input', data:`\x1b[<${ticks < 0 ? 64 : 65};${col};${row}M`});
    }, {capture:true,passive:false,signal:state.viewAbort.signal});
    state.observer = new ResizeObserver(() => {
      if (state.frame) return;
      state.frame = requestAnimationFrame(() => {
        state.frame = null;
        if (state !== current || state.terminal !== terminal) return;
        fit.fit(); send({type:'resize',cols:terminal.cols,rows:terminal.rows});
      });
    });
    state.observer.observe(screen);
    socket.onmessage = event => {
      if (state !== current || state.socket !== socket) return;
      let message; try { message = JSON.parse(event.data); } catch { return; }
      if (message.type === 'data') terminal.write(window._termStripModes ? window._termStripModes(message.data) : message.data);
      if (message.type === 'exit') {
        state.connectionEnded = !state.sleepRequested;
        releaseView(state);
        void refresh(state).catch(() => {});
      }
    };
    socket.onclose = () => {
      if (state !== current || state.socket !== socket) return;
      state.connectionEnded = true;
      releaseView(state);
      show(state,result,'Connection closed. Reopen the terminal to reconnect.');
    };
  }
  function decorate(host = document) {
    if (!current) return;
    for (const row of host.querySelectorAll('[data-terminal-task]')) {
      if (row.dataset.terminalDocument !== current.documentId) continue;
      const slot = row.querySelector(':scope > .assistant-tasks-task-row > [data-linked-terminal]');
      if (!slot) continue;
      const linked = current.scope ? current.result?.linked && current.result
        : current.links?.find(item => item.linked_task?.task_id === row.dataset.terminalTask);
      slot.replaceChildren();
      if (linked) {
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'assistant-linked-terminal';
        button.textContent = '›_ Terminal'; button.title = sessionLabel(linked);
        button.onclick = () => selectTask(row.dataset.terminalTask, true);
        slot.append(button);
      }
    }
  }
  function selectTask(taskId, reveal = false) {
    if (!current) return;
    const state = current;
    state.taskId = taskId || null; remembered(state,state.taskId);
    state.connectionEnded = false; state.result = null; releaseView(state);
    state.host.querySelector('[data-terminal-show]').hidden = true;
    void refresh(state).then(() => {
      if (reveal && state === current && state.inline && state.result?.linked) void showInPanel(state);
    });
  }
  async function showInPanel(state) {
    try {
      const shown = await window.LabTaskTerminalBridge?.show?.(state.result, state.scope
        ? {openDocument:false,isCurrent:() => state === current,terminalScope:state.scope} : {});
      if (!shown && state === current) state.host.querySelector('[data-terminal-status]').textContent='This terminal is not available in the current workspace. Open its workspace to view it.';
    } catch (error) { if (state === current) show(state,state.result || {},error.message); }
  }
  function renderLinks(state) {
    const select = state.host.querySelector('[data-terminal-target]');
    const tasks = state.root.document_tasks?.tasks || [];
    select.innerHTML = '<option value="">Document</option>' + tasks.map(task => `<option value="${esc(task.id)}">${esc(task.title)}</option>`).join('');
    select.value = state.taskId || '';
    state.host.querySelector('[data-terminal-unlink]').hidden = Boolean(state.scope) || !state.links.some(row => (row.linked_task.task_id || null) === state.taskId);
    state.host.querySelector('[data-terminal-choose]').hidden = Boolean(state.scope);
    decorate();
  }
  async function refresh(state) {
    if (state !== current || document.hidden || state.opening) return;
    if (state.checking) { state.refreshAgain = true; return; }
    state.refreshAgain = false; state.checking = true;
    state.host.querySelector('[data-terminal-show]').disabled = true;
    const taskId = state.taskId;
    try {
      if (state.scope) {
        state.links = await window.LabScopeLinks.terminals(state.scope,state.abort.signal);
        if (state !== current || state.taskId !== taskId) return;
        const selected = window.LabTaskTerminalBridge?.context?.()?.session_name;
        const linked = state.links.find(row => row.name === selected && row.state === 'running')
          || state.links.find(row => row.name === state.scope.session_name && row.state === 'running')
          || state.links.find(row => row.state === 'running') || state.links[0];
        show(state, linked ? {...linked,linked:true} : {state:'absent'});
        renderLinks(state);return;
      }
      state.links = await api('/api/term/task-terminals?document_id=' + encodeURIComponent(state.documentId), {signal:state.abort.signal});
      if (state !== current || state.taskId !== taskId) return;
      renderLinks(state);
      const linked = state.links.find(row => (row.linked_task.task_id || null) === state.taskId);
      const result = linked ? {...linked,linked:true} : state.taskId ? {state:'absent'} : await request(state.path,'status',state.abort.signal);
      if (state !== current || state.taskId !== taskId) return;
      if (state.result?.name !== result.name) releaseView(state);
      show(state,result,state.connectionEnded ? 'Terminal disconnected. Reconnect when ready.' : '');
      if (result.state === 'running' && !state.socket && !state.connectionEnded) await attach(state,result);
    } catch (error) {
      if (state === current && error.name !== 'AbortError') show(state,state.result || {},error.message);
    } finally {
      state.checking = false;
      if (state === current) state.host.querySelector('[data-terminal-show]').disabled = false;
      if (state === current && (state.taskId !== taskId || state.refreshAgain)) void refresh(state);
    }
  }
  async function wake(state) {
    if (state !== current || state.opening) return;
    if (state.result?.linked) {
      const linked=state.result;
      if (linked.state === 'stopped') {
        if (linked.kind === 'attached') return;
        state.opening=true;
        try {
          await api('/api/term/sessions',{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({workspace_id:linked.workspace_id,vault:linked.vault,
              name:linked.logical_name,kind:linked.kind || 'terminal',agent:linked.agent})});
        } catch (error) {
          if (state === current) show(state,linked,error.message);
          return;
        } finally { state.opening=false; }
      }
      if (state !== current) return;
      state.connectionEnded = false; releaseView(state); return refresh(state);
    }
    // Only an explicit click resumes an existing managed conversation.
    if (!['sleeping','waiting','running'].includes(state.result?.state)) return refresh(state);
    state.opening = true; state.sleepRequested = false;
    try {
      const result = await request(state.path,'open',state.abort.signal);
      if (state !== current) return;
      state.connectionEnded = false; show(state,result); await attach(state,result);
    } catch (error) {
      if (error.name !== 'AbortError') show(state,state.result || {},error.message);
    } finally { state.opening = false; }
  }
  function dropContext(target) {
    const row = target?.closest?.('[data-terminal-document]');
    if (!row?.dataset.terminalDocument || row.closest('[aria-busy="true"]') || row.closest('.workspace-document')?.querySelector('button:disabled')) return null;
    return {kind:'task',row,documentId:row.dataset.terminalDocument,taskId:row.dataset.terminalTask || null,
      database:row.dataset.assistantRoot || undefined,path:row.dataset.documentPath || undefined};
  }
  async function link(ctx, session, context) {
    if (!session?.logical_name || !context?.workspaceId) return;
    if (current?.scope && ctx.documentId === current.documentId && (!ctx.database || ctx.database === current.database)) {
      if (!window.LabScopeLinks.matchesTerminal(session,current.scope)) {
        if (typeof explorerToast === 'function') explorerToast('Use a terminal attached to this folder/worktree.',true);
        return;
      }
      const state=current,task=state.root.document_tasks?.tasks?.find(task=>task.id===ctx.taskId);
      if(task) {
        try {
          const saved=await window.LabTaskTerminalBridge.patch(session,{label:task.title},context);
          session={...session,label:saved.label};
        } catch(error) { if(typeof explorerToast==='function')explorerToast(error.message,true);return; }
      }
      state.scope.session_name = session.name;state.taskId = ctx.taskId || null;
      remembered(state,state.taskId);show(state,{...session,linked:true});renderLinks(state);
      await showInPanel(state);if(state===current)await refresh(state);return;
    }
    try {
      const saved = await window.LabTaskTerminalBridge.patch(session,{linked_task:{document_id:ctx.documentId,
        task_id:ctx.taskId,assistant_root:ctx.database,path:ctx.path},rename_to_task:Boolean(ctx.taskId)},context);
      window.labFeatureUsage?.('Link terminal to task');
      if (current?.documentId === ctx.documentId && (!ctx.database || current.database === ctx.database)) {
        current.taskId = ctx.taskId; remembered(current,ctx.taskId);
        current.connectionEnded = false; current.result = null; releaseView(current);
        current.host.querySelector('[data-terminal-picker]').hidden = true;
        await refresh(current);
      }
      if (typeof explorerToast === 'function') explorerToast(`Terminal linked${saved?.linked_task?.title ? ' to ' + saved.linked_task.title : ''}. Existing conversation kept.`);
    } catch (error) {
      if (current) current.host.querySelector('[data-terminal-status]').textContent = error.message;
      if (typeof explorerToast === 'function') explorerToast(error.message,true);
    }
  }
  async function choose(taskId) {
    const state = current;
    if (!state || state.scope) return;
    if (taskId !== undefined) { state.taskId=taskId || null; remembered(state,state.taskId); state.result=null; releaseView(state); void refresh(state); }
    const picker = state.host.querySelector('[data-terminal-picker]');
    picker.hidden = false; picker.textContent = 'Loading existing terminals…';
    try {
      const sessions = await api('/api/term/task-terminals',{signal:state.abort.signal});
      if (state !== current) return;
      picker.innerHTML = '<p>Drag a terminal onto a task, or click one to link it to the selected task. No new terminal is created.</p>';
      if (!sessions.length) picker.append(document.createTextNode('No running terminals. Create one with + New in the terminal bar.'));
      for (const session of sessions) {
        const button = document.createElement('button'); button.type = 'button'; button.draggable = true;
        button.textContent = sessionLabel(session) + ' · ' + session.workspace_name;
        const context = {workspaceId:session.workspace_id,vaultId:session.vault};
        button.onclick = () => link({documentId:state.documentId,taskId:state.taskId,database:state.database || undefined,path:state.root.path},session,context);
        button.ondragstart = event => { dragged={session,context}; event.dataTransfer.effectAllowed='link'; event.dataTransfer.setData('application/x-lab-task-terminal',session.name); };
        button.ondragend = () => { dragged=null; document.querySelectorAll('.term-link-drop-target').forEach(row=>row.classList.remove('term-link-drop-target')); };
        picker.append(button);
      }
      const dismiss = document.createElement('button'); dismiss.type='button'; dismiss.textContent='Cancel'; dismiss.onclick=()=>picker.hidden=true; picker.append(dismiss);
    } catch (error) { if (error.name !== 'AbortError') picker.textContent=error.message; }
  }
  document.addEventListener('dragover',event=>{
    if (!dragged) return;
    const ctx=dropContext(event.target);
    document.querySelectorAll('.term-link-drop-target').forEach(row=>row.classList.remove('term-link-drop-target'));
    if (!ctx) return;
    event.preventDefault(); event.dataTransfer.dropEffect='link'; ctx.row.classList.add('term-link-drop-target');
  });
  document.addEventListener('drop',event=>{
    if (!dragged) return;
    const ctx=dropContext(event.target), source=dragged; dragged=null;
    if (!ctx) return;
    event.preventDefault(); event.stopPropagation(); ctx.row.classList.remove('term-link-drop-target');
    void link(ctx,source.session,source.context);
  });
  function updateRoot(root) {
    if (!current || (root.tree?.id || root.metadata.id) !== current.documentId) return;
    current.root=root;
    if (current.taskId && !root.document_tasks?.tasks?.some(task=>task.id===current.taskId)) return selectTask(null);
    renderLinks(current);
  }
  function open(detail, root = detail, database = '', {inline = false,scope = null} = {}) {
    const host = document.getElementById('assistantDocumentTerminal');
    if (!host || detail?.metadata?.schema !== 2) return;
    const key = detail.root_path || detail.path;
    if (current?.key === key && current.inline === inline && JSON.stringify(current.scope) === JSON.stringify(scope)) { current.path=detail.path; updateRoot(root); return; }
    close();
    const state = current = {key,inline:inline || Boolean(scope),scope:scope && {...scope},path:detail.path,root,documentId:root.tree?.id || root.metadata.id,database,links:[],host,abort:new AbortController()};
    inline = state.inline;
    state.taskId = remembered(state);
    if (state.taskId && !root.document_tasks?.tasks?.some(task=>task.id===state.taskId)) state.taskId=null;
    host.hidden = false; host.dataset.terminalDocument=state.documentId; host.dataset.assistantRoot=database; host.dataset.documentPath=root.path;
    const header = document.querySelector('#assistantDocumentModal .assistant-modal-header');
    if (header) {
      header.dataset.terminalDocument=state.documentId;
      header.dataset.assistantRoot=database; header.dataset.documentPath=root.path;
      const title=header.querySelector('h2');
      if (title) { title.draggable=true; title.dataset.assistantDocumentDrag=''; title.dataset.terminalDocument=state.documentId; title.dataset.assistantRoot=database; title.dataset.documentPath=root.path; }
    }
    host.innerHTML = `<div class="assistant-terminal-toolbar"><strong>Terminal</strong><select data-terminal-placement aria-label="Terminal position"><option value="bottom">Bottom</option><option value="right">Right</option></select><select data-terminal-target aria-label="Terminal for task"></select><span data-terminal-agent></span><span role="status" data-terminal-status>Checking linked terminals…</span><button type="button" data-terminal-show hidden>Show terminal</button><button type="button" data-terminal-choose>Link terminal…</button><button type="button" data-terminal-unlink hidden>Unlink</button><button type="button" data-terminal-context>Copy context</button><button type="button" data-terminal-wake hidden>Reconnect</button><button type="button" data-terminal-sleep hidden>Sleep</button><button type="button" data-terminal-settings>Settings</button></div><div class="assistant-terminal-picker" data-terminal-picker hidden></div><div class="assistant-terminal-screen" aria-label="Linked task terminal"></div>`;
    const placementKey='labDocumentTerminalPlacement:' + JSON.stringify([database,state.documentId]);
    const position=host.querySelector('[data-terminal-placement]');
    const modal=host.closest('.assistant-document-modal');
    try { position.value=localStorage.getItem(placementKey)==='right' ? 'right' : 'bottom'; } catch {}
    modal.dataset.terminalPlacement=inline ? 'inline' : position.value;
    position.hidden=inline;
    position.onchange=() => { modal.dataset.terminalPlacement=position.value; try { localStorage.setItem(placementKey,position.value); } catch {} };
    host.querySelector('[data-terminal-target]').onchange = event => selectTask(event.target.value);
    host.querySelector('[data-terminal-show]').onclick = () => {
      if (state.result?.linked && state.result.state === 'running') void showInPanel(state);
    };
    host.querySelector('[data-terminal-choose]').onclick = () => void choose();
    host.querySelector('[data-terminal-wake]').onclick = () => void wake(state);
    host.querySelector('[data-terminal-settings]').onclick = () => void openSettings();
    host.querySelector('[data-terminal-unlink]').onclick = async () => {
      const session=state.links.find(row=>(row.linked_task.task_id || null)===state.taskId);
      if (!session) return;
      try {
        const context={workspaceId:session.workspace_id,vaultId:session.vault};
        if (window.LabWorkspaceDocuments) { if (!await window.LabWorkspaceDocuments.unlink(session,context)) return; }
        else await window.LabTaskTerminalBridge.patch(session,{linked_task:null},context);
        if (state !== current) return;
        releaseView(state); await refresh(state);
      } catch (error) { if (state === current) show(state,state.result,error.message); }
    };
    host.querySelector('[data-terminal-context]').onclick = async () => {
      const task=state.root.document_tasks?.tasks?.find(task=>task.id===state.taskId);
      const path=state.database ? state.database.replace(/\/$/,'') + '/' + state.root.path : state.root.path;
      try { await navigator.clipboard.writeText(path + (task ? '\nTask: ' + task.title + '\nTask ID: ' + task.id : '')); host.querySelector('[data-terminal-status]').textContent='Context copied — paste it when ready'; }
      catch (_) { host.querySelector('[data-terminal-status]').textContent='Could not copy context'; }
    };
    host.querySelector('[data-terminal-sleep]').onclick = async () => {
      state.sleepRequested = true;
      try { show(state,await request(state.path,'sleep',state.abort.signal)); }
      catch (error) { state.sleepRequested = false; if (error.name !== 'AbortError') show(state,state.result || {},error.message); }
    };
    for (const event of ['pointerdown','keydown','wheel']) host.addEventListener(event,() => used(state),{signal:state.abort.signal,passive:true});
    renderLinks(state);
    state.poll = setInterval(() => void refresh(state),30000);
    void refresh(state);
  }
  async function openSettings() {
    if (window.LabSettings) return window.LabSettings.open({section:'documents'});
    if (document.getElementById('documentTerminalSettings')) return;
    const dialog = document.createElement('dialog'); dialog.id = 'documentTerminalSettings';
    dialog.className = 'assistant-terminal-settings';
    dialog.innerHTML = `<form><h2>Document terminals</h2><p>Tasks link to existing terminals. These settings only control previous managed document conversations.</p><label><input name="enabled" type="checkbox"> Allow resuming previous document conversations</label><label>Sleep hidden idle terminals after (minutes)<input name="sleepMinutes" type="number" min="1" max="10080" required></label><label>Remove unused terminal bookmarks after (hours)<input name="expireHours" type="number" min="1" max="8760" required></label><label>Idle terminals to keep ready<input name="maxRunning" type="number" min="1" max="20" required></label><p>Working agents and unsent text stay protected. Saved conversations remain linked to their documents. Low memory delays new starts automatically. Ordinary terminals are unchanged.</p><p role="alert"></p><div><button type="button" data-cancel>Cancel</button><button type="submit" disabled>Save</button></div></form>`;
    document.body.append(dialog); dialog.showModal();
    dialog.addEventListener('close',() => dialog.remove());
    dialog.querySelector('[data-cancel]').onclick = () => dialog.close();
    const form = dialog.querySelector('form'), errorBox = dialog.querySelector('[role="alert"]');
    try {
      const response = await fetch('/api/assistant/document-terminal/settings');
      if (!response.ok) throw new Error('Could not load terminal settings');
      const policy = await response.json();
      if (!dialog.isConnected) return;
      for (const [key,value] of Object.entries(policy)) {
        const field = form.elements[key]; if (field) field.type === 'checkbox' ? field.checked = value : field.value = value;
      }
      form.querySelector('[type="submit"]').disabled = false;
    } catch (error) { errorBox.textContent = error.message; }
    form.onsubmit = async event => {
      event.preventDefault();
      const policy = {enabled:form.elements.enabled.checked};
      for (const key of ['sleepMinutes','expireHours','maxRunning']) policy[key] = Number(form.elements[key].value);
      if (policy.expireHours * 60 <= policy.sleepMinutes) { errorBox.textContent = 'Removal must be later than sleep.'; return; }
      try {
        const response = await fetch('/api/assistant/document-terminal/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(policy)});
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || 'Could not save settings');
        dialog.close(); if (current) void refresh(current);
      } catch (error) { errorBox.textContent = error.message; }
    };
  }
  document.addEventListener('visibilitychange',() => {
    if (!current) return;
    if (document.hidden) releaseView(current); else void refresh(current);
  });
  window.addEventListener('pagehide',close);
  window.LabDocumentTerminal = {open,close,settings:openSettings,dropContext,link,choose,decorate,updateRoot,focusTask:selectTask,refresh:() => current && refresh(current)};
})();
