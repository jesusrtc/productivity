/* One visible renderer/connection, bounded server agents, no hidden pane cache. */
(function () {
  'use strict';
  let current = null;
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
  }
  function show(state, result, error = '') {
    if (state !== current) return;
    state.result = result;
    const label = state.host.querySelector('[data-terminal-status]');
    const waiting = result.reason === 'memory_check' ? 'Checking available memory — will retry automatically' : 'Waiting for memory — will resume automatically';
    label.textContent = error || (result.state === 'waiting' ? waiting : '') || ({running:({busy:'Working',idle:'Ready',draft:'Unsent text kept open'}[result.work_state] || 'Running'),sleeping:'Sleeping — memory released',absent:'Ready to open',disabled:'Document terminals are off'}[result.state] || 'Ready');
    label.classList.toggle('error',Boolean(error));
    state.host.querySelector('[data-terminal-agent]').textContent = result.agent || 'Default agent';
    const wake = state.host.querySelector('[data-terminal-wake]');
    wake.hidden = result.state === 'running' && !error;
    wake.disabled = result.state === 'disabled';
    wake.textContent = result.state === 'sleeping' ? 'Wake' : result.state === 'absent' ? 'Open terminal' : 'Try again';
    state.host.querySelector('[data-terminal-sleep]').hidden = result.state !== 'running';
    if (result.state !== 'running') releaseView(state);
  }
  function used(state) {
    if (state !== current || state.result?.state !== 'running') return;
    
    if (state.activityTimer) return;
    state.activityTimer = setTimeout(() => {
      state.activityTimer = null;
      if (state !== current) return;
      void request(state.path,'activity',state.abort.signal).catch(() => {});
    }, 30000); // At most two activity writes/minute; WS keystrokes stay in RAM.
  }
  async function attach(state, result) {
    if (state !== current || document.hidden || state.socket || result.state !== 'running') return;
    if (typeof window.ensureTerminalLibs !== 'function') throw new Error('Terminal support is loading. Try again.');
    await Promise.all([window.ensureTerminalLibs(), window.loadStyleOnce?.('/static/vendor/xterm@5.3.0/xterm.min.css')]);
    if (state !== current || document.hidden || state.socket) return;
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
        state.connectionEnded = true;
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
  async function refresh(state) {
    if (state !== current || document.hidden || state.checking || state.opening) return;
    if (state.result?.state === 'waiting') return wake(state);
    state.checking = true;
    try {
      const result = await request(state.path,'status',state.abort.signal);
      if (state !== current) return;
      show(state,result,state.connectionEnded && result.state === 'running' ? 'Connection closed. Reopen the terminal to reconnect.' : '');
      if (result.state === 'running' && !state.socket && !state.connectionEnded) await attach(state,result);
    } catch (error) {
      if (error.name !== 'AbortError') show(state,state.result || {},error.message);
    } finally { state.checking = false; }
  }
  async function wake(state) {
    if (state !== current || state.opening) return;
    state.opening = true;
    state.host.querySelector('[data-terminal-status]').textContent = 'Opening terminal…';
    try {
      const result = await request(state.path,'open',state.abort.signal);
      if (state !== current) return;
      state.connectionEnded = false;
      show(state,result); await attach(state,result);
    } catch (error) {
      if (error.name !== 'AbortError') show(state,state.result || {},error.message);
    } finally { state.opening = false; }
  }
  function open(detail) {
    const host = document.getElementById('assistantDocumentTerminal');
    if (!host || detail?.metadata?.schema !== 2) return;
    const key = detail.root_path || detail.path;
    if (current?.key === key) {
      if (current.path !== detail.path) { current.path = detail.path; void wake(current); }
      return;
    }
    close();
    const state = current = {key,path:detail.path,host,abort:new AbortController()};
    host.hidden = false;
    host.innerHTML = `<div class="assistant-terminal-toolbar"><strong>Terminal</strong><span data-terminal-agent>Default agent</span><span role="status" data-terminal-status>Opening terminal…</span><button type="button" data-terminal-wake hidden>Wake</button><button type="button" data-terminal-sleep hidden>Sleep</button><button type="button" data-terminal-settings>Settings</button></div><div class="assistant-terminal-screen" aria-label="Document agent terminal"></div>`;
    host.querySelector('[data-terminal-wake]').onclick = () => void wake(state);
    host.querySelector('[data-terminal-settings]').onclick = () => void openSettings();
    host.querySelector('[data-terminal-sleep]').onclick = async () => {
      try { show(state,await request(state.path,'sleep',state.abort.signal)); }
      catch (error) { if (error.name !== 'AbortError') show(state,state.result || {},error.message); }
    };
    for (const event of ['pointerdown','keydown','wheel']) host.addEventListener(event,() => used(state),{signal:state.abort.signal,passive:true});
    state.poll = setInterval(() => void refresh(state),30000);
    void wake(state);
  }
  async function openSettings() {
    if (window.LabSettings) return window.LabSettings.open({section:current && !['running','sleeping'].includes(current.result?.state) ? 'general' : 'documents'});
    if (document.getElementById('documentTerminalSettings')) return;
    const dialog = document.createElement('dialog'); dialog.id = 'documentTerminalSettings';
    dialog.className = 'assistant-terminal-settings';
    dialog.innerHTML = `<form><h2>Document terminals</h2><p>Use the default agent when you open a document. Sleep releases the process and memory; reopening resumes its saved conversation.</p><label><input name="enabled" type="checkbox"> Open automatically</label><label>Sleep hidden idle terminals after (minutes)<input name="sleepMinutes" type="number" min="1" max="10080" required></label><label>Remove unused terminal bookmarks after (hours)<input name="expireHours" type="number" min="1" max="8760" required></label><label>Idle terminals to keep ready<input name="maxRunning" type="number" min="1" max="20" required></label><p>Working agents and unsent text stay protected. Saved conversations remain linked to their documents. Low memory delays new starts automatically. Ordinary terminals are unchanged.</p><p role="alert"></p><div><button type="button" data-cancel>Cancel</button><button type="submit" disabled>Save</button></div></form>`;
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
  window.LabDocumentTerminal = {open,close,settings:openSettings};
})();
