(function () {
  'use strict';

  const state = {
    data: null,
    selectedPath: '',
    detail: null,
    view: 'open',
    status: 'open',
    priority: '',
    project: '',
    search: '',
    request: 0,
    poll: null,
  };

  const e = value => String(value == null ? '' : value).replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);

  function labelStatus(value) {
    return String(value || 'inbox').replace(/_/g, ' ');
  }

  function displayDate(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat(undefined, {month: 'short', day: 'numeric'}).format(date);
  }

  function isRecentDone(task) {
    if (task.status !== 'done') return false;
    const raw = task.completed || task.updated;
    const time = raw ? new Date(raw).getTime() : Number(task.mtime || 0) * 1000;
    return Number.isFinite(time) && Date.now() - time <= 7 * 86400000;
  }

  function filteredTasks() {
    const tasks = state.data && Array.isArray(state.data.tasks) ? state.data.tasks : [];
    const needle = state.search.trim().toLowerCase();
    return tasks.filter(task => {
      if (state.view === 'recent' && !isRecentDone(task)) return false;
      if (state.view === 'p0' && task.priority !== 'P0') return false;
      if (state.view === 'in_progress' && task.status !== 'in_progress') return false;
      if (state.view === 'open' && task.status === 'done') return false;
      if (state.status === 'open' && task.status === 'done') return false;
      if (state.status && state.status !== 'open' && task.status !== state.status) return false;
      if (state.priority && task.priority !== state.priority) return false;
      if (state.project && task.project !== state.project) return false;
      if (needle) {
        const haystack = [task.title, task.summary, task.project_name, task.project, task.workspace]
          .join(' ').toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      return true;
    });
  }

  function setView(view) {
    state.view = view;
    state.status = view === 'recent' ? '' : 'open';
    state.priority = view === 'p0' ? 'P0' : '';
    render();
  }

  function countWhere(predicate) {
    const tasks = state.data && state.data.tasks || [];
    return tasks.filter(predicate).length;
  }

  function renderSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;
    const projects = state.data && state.data.projects || [];
    const viewRows = [
      ['open', 'Open', countWhere(task => task.status !== 'done')],
      ['in_progress', 'In progress', countWhere(task => task.status === 'in_progress')],
      ['p0', 'P0', countWhere(task => task.priority === 'P0' && task.status !== 'done')],
      ['recent', 'Recently completed', countWhere(isRecentDone)],
    ];
    let html = '<div class="sidebar-title">Views</div>';
    html += viewRows.map(([key, label, count]) => `
      <button type="button" class="assistant-side-row${state.view === key ? ' active' : ''}" data-assistant-view="${e(key)}">
        <span>${e(label)}</span><span class="assistant-side-count">${count}</span>
      </button>`).join('');
    html += '<div class="sidebar-title">Projects</div>';
    html += `<button type="button" class="assistant-side-row${!state.project ? ' active-project' : ''}" data-assistant-project=""><span>All projects</span><span class="assistant-side-count">${(state.data && state.data.tasks || []).length}</span></button>`;
    html += projects.map(project => {
      const count = countWhere(task => task.project === project.id && task.status !== 'done');
      return `<button type="button" class="assistant-side-row${state.project === project.id ? ' active-project' : ''}" data-assistant-project="${e(project.id)}" title="${e(project.project_path || '')}"><span>${e(project.name || project.id)}</span><span class="assistant-side-count">${count}</span></button>`;
    }).join('');
    html += '<div class="sidebar-title">Database</div>';
    html += `<div class="assistant-db-path" title="${e(state.data && state.data.root || '')}">${e(state.data && state.data.root || 'Not configured')}</div>`;
    sidebar.innerHTML = html;
    sidebar.querySelectorAll('[data-assistant-view]').forEach(button => {
      button.addEventListener('click', () => setView(button.dataset.assistantView));
    });
    sidebar.querySelectorAll('[data-assistant-project]').forEach(button => {
      button.addEventListener('click', () => {
        state.project = button.dataset.assistantProject || '';
        render();
      });
    });
  }

  function taskCard(task) {
    const selected = task.path === state.selectedPath ? ' selected' : '';
    const due = task.due ? `<span class="assistant-task-due">Due ${e(displayDate(task.due))}</span>` : '';
    return `<button type="button" class="assistant-task-card${selected}" data-assistant-task="${e(task.path)}">
      <div class="assistant-task-card-top">
        <span class="assistant-priority ${e(String(task.priority || '').toLowerCase())}">${e(task.priority || 'P2')}</span>
        <span class="assistant-status status-${e(task.status || 'inbox')}">${e(labelStatus(task.status))}</span>
        ${due}
      </div>
      <strong>${e(task.title)}</strong>
      <span class="assistant-task-project">${e(task.project_name || task.project)}${task.workspace ? ` · ${e(task.workspace)}` : ''}</span>
      ${task.summary ? `<span class="assistant-task-summary">${e(task.summary)}</span>` : ''}
    </button>`;
  }

  function renderSetup(content) {
    const root = state.data && state.data.root;
    const message = !state.data || !state.data.configured
      ? 'Set LAB_ASSISTANT_HOME in this Lab checkout’s .env, then restart Lab.'
      : `Create the configured directory, then run lab assistant init.`;
    content.innerHTML = `<div class="assistant-setup">
      <span class="assistant-kicker">Global task workspace</span>
      <h1>Assistant needs a database</h1>
      <p>${e(message)}</p>
      ${root ? `<code>${e(root)}</code>` : '<code>LAB_ASSISTANT_HOME=/absolute/path/to/assistant</code>'}
    </div>`;
  }

  function render() {
    if (!document.body.classList.contains('assistant-active')) return;
    renderSidebar();
    const content = document.getElementById('content');
    if (!content) return;
    if (!state.data || !state.data.configured || !state.data.exists) {
      renderSetup(content);
      return;
    }
    const tasks = filteredTasks();
    if (!tasks.some(task => task.path === state.selectedPath)) {
      state.selectedPath = tasks[0] ? tasks[0].path : '';
      state.detail = null;
    }
    const openCount = countWhere(task => task.status !== 'done');
    const inProgress = countWhere(task => task.status === 'in_progress');
    const blocked = countWhere(task => task.status === 'blocked');
    const p0 = countWhere(task => task.priority === 'P0' && task.status !== 'done');
    content.innerHTML = `<div class="assistant-shell">
      <header class="assistant-head">
        <div><span class="assistant-kicker">Global task workspace</span><h1>Assistant</h1></div>
        <button type="button" class="refresh-btn" id="assistantRefresh">Refresh</button>
      </header>
      <div class="assistant-metrics">
        <div><span>Open</span><strong>${openCount}</strong></div>
        <div><span>In progress</span><strong>${inProgress}</strong></div>
        <div><span>Blocked</span><strong>${blocked}</strong></div>
        <div><span>P0</span><strong>${p0}</strong></div>
      </div>
      <div class="assistant-filters">
        <input type="search" id="assistantSearch" value="${e(state.search)}" placeholder="Search tasks…" aria-label="Search Assistant tasks">
        <select id="assistantStatus" aria-label="Filter by status">
          <option value="open"${state.status === 'open' ? ' selected' : ''}>Open statuses</option>
          <option value=""${state.status === '' ? ' selected' : ''}>All statuses</option>
          ${(state.data.statuses || []).map(status => `<option value="${e(status)}"${state.status === status ? ' selected' : ''}>${e(labelStatus(status))}</option>`).join('')}
        </select>
        <select id="assistantPriority" aria-label="Filter by priority">
          <option value="">All priorities</option>
          ${(state.data.priorities || []).map(priority => `<option value="${e(priority)}"${state.priority === priority ? ' selected' : ''}>${e(priority)}</option>`).join('')}
        </select>
        <span class="assistant-filter-count">${tasks.length} task${tasks.length === 1 ? '' : 's'}</span>
      </div>
      <div class="assistant-workarea">
        <section class="assistant-list" aria-label="Tasks">
          ${tasks.length ? tasks.map(taskCard).join('') : '<div class="assistant-empty">No tasks match these filters.</div>'}
        </section>
        <article class="assistant-detail" id="assistantDetail">
          ${state.selectedPath ? '<div class="loading">Loading task…</div>' : '<div class="assistant-empty assistant-empty-detail">Select a task to see its context and outputs.</div>'}
        </article>
      </div>
    </div>`;
    document.getElementById('assistantRefresh')?.addEventListener('click', refresh);
    const search = document.getElementById('assistantSearch');
    search?.addEventListener('input', () => {
      state.search = search.value;
      clearTimeout(state.searchTimer);
      state.searchTimer = setTimeout(() => {
        render();
        const next = document.getElementById('assistantSearch');
        if (next) {
          next.focus();
          next.setSelectionRange(next.value.length, next.value.length);
        }
      }, 120);
    });
    document.getElementById('assistantStatus')?.addEventListener('change', event => {
      state.status = event.target.value;
      state.view = state.status === 'open' ? 'open' : '';
      render();
    });
    document.getElementById('assistantPriority')?.addEventListener('change', event => {
      state.priority = event.target.value;
      state.view = state.priority === 'P0' ? 'p0' : '';
      render();
    });
    content.querySelectorAll('[data-assistant-task]').forEach(button => {
      button.addEventListener('click', () => selectTask(button.dataset.assistantTask, true));
    });
    if (state.selectedPath) loadDetail(state.selectedPath);
  }

  async function selectTask(path, push) {
    state.selectedPath = path || '';
    state.detail = null;
    if (push) {
      const url = new URL(window.location);
      if (state.selectedPath) url.searchParams.set('task', state.selectedPath);
      else url.searchParams.delete('task');
      history.pushState({nav: 'assistant', task: state.selectedPath}, '', url.pathname + url.search + url.hash);
    }
    render();
  }

  function localImageUrl(taskPath, src) {
    return '/api/assistant/asset?task=' + encodeURIComponent(taskPath) + '&src=' + encodeURIComponent(src);
  }

  function rewriteImages(host, taskPath) {
    host.querySelectorAll('img').forEach(img => {
      const src = img.getAttribute('src') || '';
      if (!src || src.startsWith('http://') || src.startsWith('https://') || src.startsWith('data:')) return;
      img.src = localImageUrl(taskPath, src);
    });
  }

  function projectMeta(detail) {
    const metadata = detail.metadata || {};
    const project = detail.project || {};
    const rows = [
      ['Status', labelStatus(metadata.status)],
      ['Priority', metadata.priority],
      ['Project', project.name || metadata.project],
      ['Workspace', project.workspace],
      ['Due', metadata.due],
      ['Owner', metadata.owner],
      ['Updated', displayDate(metadata.updated)],
    ].filter(row => row[1]);
    return rows.map(([key, value]) => `<div><span>${e(key)}</span><strong>${e(value)}</strong></div>`).join('');
  }

  async function loadDetail(path) {
    const request = ++state.request;
    try {
      const response = await fetch('/api/assistant/task?path=' + encodeURIComponent(path));
      const detail = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(detail.detail || response.statusText);
      if (request !== state.request || path !== state.selectedPath || !document.body.classList.contains('assistant-active')) return;
      state.detail = detail;
      await renderDetail(detail);
    } catch (error) {
      const host = document.getElementById('assistantDetail');
      if (host && request === state.request) host.innerHTML = `<div class="assistant-empty">${e(error.message || error)}</div>`;
    }
  }

  async function renderDetail(detail) {
    const host = document.getElementById('assistantDetail');
    if (!host) return;
    if (typeof window.ensureMarked === 'function') await window.ensureMarked().catch(() => {});
    const body = detail.body || '';
    const markdown = window.marked ? window.marked.parse(body) : `<pre>${e(body)}</pre>`;
    const metadata = detail.metadata || {};
    const project = detail.project || {};
    host.innerHTML = `<div class="assistant-detail-head">
      <div>
        <div class="assistant-detail-badges"><span class="assistant-priority ${e(String(metadata.priority || '').toLowerCase())}">${e(metadata.priority || 'P2')}</span><span class="assistant-status status-${e(metadata.status || 'inbox')}">${e(labelStatus(metadata.status))}</span></div>
        <h2>${e(metadata.title || metadata.id || 'Task')}</h2>
        <code>${e(metadata.id || '')}</code>
      </div>
      <div class="assistant-detail-actions">
        ${project.project_path ? '<button type="button" class="refresh-btn" id="assistantOpenProject">Open project</button>' : ''}
        <button type="button" class="refresh-btn" id="assistantCopyTask">Copy Markdown</button>
      </div>
    </div>
    <div class="assistant-meta">${projectMeta(detail)}</div>
    ${project.project_path ? `<div class="assistant-path"><span>Project path</span><code>${e(project.project_path)}</code></div>` : ''}
    <div class="nb-markdown assistant-markdown" id="assistantMarkdown">${markdown}</div>`;
    const markdownHost = document.getElementById('assistantMarkdown');
    rewriteImages(markdownHost, detail.path);
    addCopyButtons(markdownHost, body, detail.path);
    document.getElementById('assistantCopyTask')?.addEventListener('click', event => copyPlain(body, event.currentTarget));
    document.getElementById('assistantOpenProject')?.addEventListener('click', () => {
      if (project.project_path && typeof window.goToProject === 'function') window.goToProject(project.project_path);
    });
  }

  function markdownSection(body, headingText, level) {
    const lines = body.split('\n');
    const prefix = '#'.repeat(level) + ' ';
    let start = lines.findIndex(line => line.trimStart().startsWith(prefix)
      && line.replace(/^\s*#+\s+/, '').trim() === headingText);
    if (start < 0) return '';
    let end = lines.length;
    for (let index = start + 1; index < lines.length; index += 1) {
      const match = lines[index].match(/^\s*(#{1,6})\s/);
      if (match && match[1].length <= level) { end = index; break; }
    }
    return lines.slice(start, end).join('\n').trim();
  }

  function addCopyButtons(host, body, taskPath) {
    host.querySelectorAll('h1, h2, h3').forEach(heading => {
      const level = Number(heading.tagName.slice(1));
      const title = heading.textContent.trim();
      const actions = document.createElement('span');
      actions.className = 'assistant-copy-actions';
      const slack = document.createElement('button');
      slack.type = 'button';
      slack.textContent = 'Slack';
      slack.title = 'Copy this Markdown section';
      slack.addEventListener('click', () => copyPlain(markdownSection(body, title, level), slack));
      const gdoc = document.createElement('button');
      gdoc.type = 'button';
      gdoc.textContent = 'GDoc';
      gdoc.title = 'Copy this section as formatted rich text';
      gdoc.addEventListener('click', () => copyRich(markdownSection(body, title, level), taskPath, gdoc));
      actions.append(slack, gdoc);
      heading.appendChild(actions);
    });
  }

  async function copyPlain(text, button) {
    const original = button.textContent;
    try {
      await navigator.clipboard.writeText(text || '');
      button.textContent = 'Copied';
    } catch (_) {
      button.textContent = 'Failed';
    }
    setTimeout(() => { button.textContent = original; }, 1200);
  }

  async function copyRich(markdown, taskPath, button) {
    const original = button.textContent;
    if (typeof window.ensureMarked === 'function') await window.ensureMarked().catch(() => {});
    const container = document.createElement('div');
    container.innerHTML = window.marked ? window.marked.parse(markdown) : `<pre>${e(markdown)}</pre>`;
    rewriteImages(container, taskPath);
    await Promise.all(Array.from(container.querySelectorAll('img')).map(async img => {
      try {
        const response = await fetch(img.src);
        const blob = await response.blob();
        img.src = await new Promise(resolve => {
          const reader = new FileReader();
          reader.onloadend = () => resolve(reader.result);
          reader.readAsDataURL(blob);
        });
      } catch (_) {}
    }));
    container.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach(node => {
      node.style.fontFamily = 'Arial, sans-serif';
    });
    container.querySelectorAll('p,li,td,th').forEach(node => {
      node.style.fontFamily = 'Arial, sans-serif';
      node.style.fontSize = '11pt';
      node.style.color = '#000';
    });
    try {
      const html = new Blob([container.innerHTML], {type: 'text/html'});
      const plain = new Blob([markdown], {type: 'text/plain'});
      await navigator.clipboard.write([new ClipboardItem({'text/html': html, 'text/plain': plain})]);
      button.textContent = 'Copied';
    } catch (_) {
      await copyPlain(markdown, button);
      return;
    }
    setTimeout(() => { button.textContent = original; }, 1200);
  }

  async function refresh(options = {}) {
    const request = ++state.request;
    try {
      const response = await fetch('/api/assistant');
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || response.statusText);
      if (request !== state.request || !document.body.classList.contains('assistant-active')) return;
      state.data = data;
      if (options.task !== undefined) state.selectedPath = options.task || '';
      render();
    } catch (error) {
      const content = document.getElementById('content');
      if (content && request === state.request) content.innerHTML = `<div class="assistant-setup"><h1>Assistant</h1><p>${e(error.message || error)}</p></div>`;
    }
  }

  function init(taskPath) {
    state.selectedPath = taskPath || '';
    state.detail = null;
    state.view = 'open';
    state.status = 'open';
    state.priority = '';
    state.project = '';
    state.search = '';
    refresh({task: state.selectedPath});
    if (!state.poll) {
      state.poll = setInterval(() => {
        if (document.body.classList.contains('assistant-active') && !document.hidden) refresh();
      }, 5000);
    }
  }

  window.AssistantView = {init, refresh, selectTask};
})();
