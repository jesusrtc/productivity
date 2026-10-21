// A separate request/assignment history; never Objective task navigation.
(() => {
  let bridge, overlay, terminal, assignments = [], selected, generation = 0, returnFocus;
  let query = '', includeChildren = true, refreshTimer, lastData = '', loadVersion = 0, briefAssignment;
  const collapsed = new Set();
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const normalize = value => String(value || '').normalize('NFD').replace(/\p{M}/gu,'').toLowerCase();
  const asset = file => '/api/term/work/files/' + encodeURIComponent(file.id) + '/content';
  const identity = row => ({name:row.name, tmux_socket:row.tmux_socket || 'default',
    tmux_id:row.tmux_id, created:row.created ?? row.created_at});

  function close() {
    generation++; loadVersion++; clearInterval(refreshTimer);
    overlay?.remove(); overlay = null;
    document.removeEventListener('keydown', keydown, true);
    returnFocus?.focus?.({preventScroll:true});
  }
  function keydown(event) {
    if (!overlay) return;
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); }
    if (event.key === 'Tab') {
      const controls = [...overlay.querySelectorAll('button,input,a[href],summary')].filter(el => !el.disabled && el.getClientRects().length);
      if (!controls.length) return;
      if (event.shiftKey && document.activeElement === controls[0]) {event.preventDefault(); controls.at(-1).focus();}
      else if (!event.shiftKey && document.activeElement === controls.at(-1)) {event.preventDefault(); controls[0].focus();}
    }
  }
  async function request(url, options) {
    const response = await fetch(url, options);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw Error(body.detail || 'Could not load agent file history');
    return body;
  }
  function details(assignment) {
    return `<details class="agent-work-brief"><summary>Request / assignment brief</summary><h3>${esc(assignment.title)}</h3><p>${esc(assignment.status)} · ${esc(new Date(assignment.created * 1000).toLocaleString())}</p>${assignment.request ? '<pre>'+esc(assignment.request)+'</pre>' : ''}${assignment.context ? '<h4>Context passed by parent</h4><pre>'+esc(assignment.context)+'</pre>' : ''}${assignment.summary ? '<h4>Result</h4><p>'+esc(assignment.summary)+'</p>' : ''}</details>`;
  }
  function renderList() {
    const list = overlay?.querySelector('[data-agent-work-list]');
    if (!list) return;
    const terms = normalize(query).trim().split(/\s+/).filter(Boolean);
    const byId = new Map(assignments.map(row => [row.id, row]));
    const groups = assignments.map(row => ({...row, files:row.files.filter(file => terms.every(term =>
      normalize([row.title, row.request, file.path, file.operation, file.previous_path].join(' ')).includes(term)))}));
    const scroll = list.scrollTop;
    const focusedFile = list.contains(document.activeElement) ? document.activeElement.dataset.agentFile : null;
    list.innerHTML = groups.filter(row => !terms.length || row.files.length).map(row => {
      const parent = byId.get(row.parent_id);
      const own = row.terminal.name === terminal.name;
      return `<section class="agent-work-group"><details data-agent-group="${esc(row.id)}"${collapsed.has(row.id) ? '' : ' open'}><summary data-agent-assignment="${esc(row.id)}"><span>${esc(row.title)}</span><small>${row.files.length} files · ${esc(row.status)}</small></summary><div class="agent-work-origin">${own ? 'This agent' : esc(row.terminal.name)}${parent ? ' · From '+esc(parent.title) : row.parent_id ? ' · Delegated assignment' : ' · Request'}</div>${row.files.map(file => `<button type="button" class="doc-modal-file${selected === file.id ? ' active' : ''}" data-agent-file="${esc(file.id)}" aria-label="${esc(file.operation+' '+file.path)}" title="${esc(file.path)}">${bridge?.icon?.(file.path) || '📄'}<span><strong>${esc(file.path.split('/').pop())}</strong><small>${esc(file.operation)} · ${esc(file.path)}</small></span></button>`).join('')}${!row.files.length ? '<p class="agent-work-empty">No file changes reported.</p>' : ''}</details></section>`;
    }).join('') || '<p class="agent-work-empty">'+(assignments.length ? 'No matching files.' : 'No requests or file changes reported yet.')+'</p>';
    list.scrollTop = scroll;
    list.querySelectorAll('[data-agent-group]').forEach(group => group.ontoggle = () => {
      if (group.open) collapsed.delete(group.dataset.agentGroup); else collapsed.add(group.dataset.agentGroup);
    });
    list.querySelectorAll('[data-agent-assignment]').forEach(summary => summary.onclick = () => {
      const assignment = assignments.find(row => row.id === summary.dataset.agentAssignment);
      if (assignment) {generation++; selected = null; briefAssignment = assignment.id; overlay.querySelector('[data-agent-work-preview]').innerHTML = details(assignment) + '<p class="agent-work-empty">Select a reported file to preview it.</p>'; }
    });
    list.querySelectorAll('[data-agent-file]').forEach(button => button.onclick = () => void select(button.dataset.agentFile));
    if (focusedFile) [...list.querySelectorAll('[data-agent-file]')].find(button => button.dataset.agentFile === focusedFile)?.focus({preventScroll:true});
    overlay.querySelector('[data-agent-work-count]').textContent = assignments.reduce((count,row) => count + row.files.length, 0) + ' reported file changes';
  }
  async function select(id) {
    const assignment = assignments.find(row => row.files.some(file => file.id === id));
    const file = assignment?.files.find(file => file.id === id);
    if (!file || !overlay) return false;
    const version = ++generation; selected = id; briefAssignment = null; renderList();
    const body = overlay.querySelector('[data-agent-work-preview]');
    body.innerHTML = details(assignment) + '<p class="agent-work-empty">Loading file…</p>';
    try {
      const data = await request('/api/term/work/files/' + encodeURIComponent(id));
      if (data.kind === 'markdown') await bridge?.prepare?.();
      if (!overlay || version !== generation) return false;
      let content;
      if (data.kind === 'markdown') content = '<article class="doc">'+(window.LabMarkdown?.render(data.content) || '<pre>'+esc(data.content)+'</pre>')+'</article>';
      else if (data.kind === 'image') content = '<img class="agent-work-image" src="'+asset(file)+'" alt="'+esc(data.name)+'">';
      else if (data.kind === 'pdf') content = '<iframe class="agent-work-pdf" title="'+esc(data.name)+'" src="'+asset(file)+'"></iframe>';
      else if (data.kind === 'text') content = '<pre class="agent-work-code"><code>'+esc(data.content)+'</code></pre>';
      else content = '<p>Preview unavailable for this file type. Use Download to open it.</p>';
      body.innerHTML = details(assignment) + `<div class="agent-work-file-header"><span title="${esc(file.path)}">${esc(file.path)}</span><button type="button" data-agent-file-copy>Copy path</button><a href="${asset(file)}?download=true" download>Download</a></div><p class="agent-work-file-note">Current file · ${esc(file.operation)} reported ${esc(new Date(file.reported*1000).toLocaleString())}</p>` + content;
      body.querySelectorAll('article img[src]').forEach(img => {
        const source = img.getAttribute('src');
        if (!/^(?:[a-z][a-z\d+.-]*:|\/)/i.test(source)) {
          let path = source.split(/[?#]/)[0];
          try { path = decodeURIComponent(path); } catch (_) { /* Literal percent in a filename. */ }
          img.src = '/api/term/work/files/' + encodeURIComponent(id) + '/asset?file=' + encodeURIComponent(path);
        }
      });
      body.querySelectorAll('article a[href]').forEach(link => {link.target = '_blank'; link.rel = 'noopener noreferrer';});
      body.querySelector('[data-agent-file-copy]').onclick = () => navigator.clipboard.writeText(file.path).catch(error => bridge?.error?.(error.message));
      return true;
    } catch (error) {
      if (overlay && version === generation) body.innerHTML = details(assignment) + '<p class="agent-work-empty">'+esc(error.message)+'</p><pre>'+esc(file.previous_path ? file.previous_path+' → '+file.path : file.path)+'</pre>';
      return false;
    }
  }
  async function load() {
    const version = ++loadVersion;
    const data = await request('/api/term/work/history', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({parent:identity(terminal), include_children:includeChildren})});
    if (!overlay || version !== loadVersion) return;
    const fingerprint = JSON.stringify(data.assignments);
    if (lastData === fingerprint) return;
    lastData = fingerprint;
    assignments = data.assignments;
    renderList();
    const brief = assignments.find(row => row.id === briefAssignment);
    if (brief) { overlay.querySelector('[data-agent-work-preview]').innerHTML = details(brief) + '<p class="agent-work-empty">Select a reported file to preview it.</p>'; return; }
    const first = assignments.flatMap(row => row.files).find(file => file.id === selected) || assignments.flatMap(row => row.files)[0];
    if (first) await select(first.id);
    else overlay.querySelector('[data-agent-work-preview]').innerHTML = '<p class="agent-work-empty">'+(assignments.length ? 'No file changes reported for these requests yet.' : 'The agent will record its changed files here, grouped by request or delegated assignment.')+'</p>';
  }
  async function open(row) {
    if (!row?.tmux_id || !(row.created ?? row.created_at)) throw Error('Refresh this terminal before opening its file history');
    const focus = overlay ? returnFocus : document.activeElement;
    close(); returnFocus = focus; terminal = {...row}; query = ''; selected = null; briefAssignment = null; assignments = []; lastData = ''; collapsed.clear();
    overlay = document.createElement('div'); overlay.className = 'doc-modal-overlay active agent-work-overlay';
    overlay.innerHTML = `<div class="doc-modal-box" role="dialog" aria-modal="true" aria-labelledby="agentWorkTitle"><div class="doc-modal-header"><span class="doc-modal-title" id="agentWorkTitle">${esc(row.label || row.logical_name || row.name)} · Files changed</span><button class="doc-modal-close" type="button" data-agent-work-close aria-label="Close agent file history">×</button></div><div class="doc-modal-layout"><nav class="doc-modal-files" aria-label="Requests and delegated assignments"><div class="doc-modal-folder">Requests &amp; delegated assignments</div><div class="agent-work-filters"><input type="search" data-agent-work-search aria-label="Search agent files" placeholder="Search files or requests…"><label><input type="checkbox" data-agent-work-children${includeChildren ? ' checked' : ''}> Include delegated work</label><small data-agent-work-count>Loading…</small></div><div class="doc-modal-files-list" data-agent-work-list></div></nav><div class="doc-modal-body agent-work-preview" data-agent-work-preview><p class="agent-work-empty">Loading…</p></div></div></div>`;
    document.body.appendChild(overlay);
    const activeOverlay = overlay;
    overlay.addEventListener('click', event => { if (event.target === overlay) close(); });
    overlay.querySelector('[data-agent-work-close]').onclick = close;
    overlay.querySelector('[data-agent-work-search]').oninput = event => {query = event.target.value; renderList();};
    overlay.querySelector('[data-agent-work-children]').onchange = event => {includeChildren = event.target.checked; void load().catch(error => bridge?.error?.(error.message));};
    document.addEventListener('keydown', keydown, true);
    overlay.querySelector('[data-agent-work-search]').focus();
    refreshTimer = setInterval(() => { if (overlay && !document.hidden) void load().catch(() => {}); }, 8000);
    try { await load(); }
    catch (error) { if (overlay === activeOverlay) overlay.querySelector('[data-agent-work-preview]').textContent = error.message; }
    return {open:!!overlay, assignments:assignments.length};
  }
  window.LabAgentWorkHistory = {open, close, select, configure:value => {bridge = value;}};
})();
