(function () {
  'use strict';

  const state = {
    data: null,
    section: 'tasks',
    selectedTaskPath: '',
    selectedMeetingPath: '',
    view: 'open',
    status: 'open',
    priority: '',
    project: '',
    search: '',
    request: 0,
    modalRequest: 0,
    poll: null,
    searchTimer: null,
    clickTimer: null,
  };

  const e = value => String(value == null ? '' : value).replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);

  function labelStatus(value) {
    return String(value || 'inbox').replace(/_/g, ' ');
  }

  function displayDate(value) {
    if (!value) return '';
    const plain = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
    const date = plain
      ? new Date(Number(plain[1]), Number(plain[2]) - 1, Number(plain[3]))
      : new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat(undefined, {month: 'short', day: 'numeric'}).format(date);
  }

  function isRecentDone(task) {
    if (task.status !== 'done') return false;
    const raw = task.completed || task.updated;
    const time = raw ? new Date(raw).getTime() : Number(task.mtime || 0) * 1000;
    return Number.isFinite(time) && Date.now() - time <= 7 * 86400000;
  }

  function tasks() {
    return state.data && Array.isArray(state.data.tasks) ? state.data.tasks : [];
  }

  function meetings() {
    return state.data && Array.isArray(state.data.meetings) ? state.data.meetings : [];
  }

  function filteredTasks() {
    const needle = state.search.trim().toLowerCase();
    return tasks().filter(task => {
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

  function filteredMeetings() {
    const needle = state.search.trim().toLowerCase();
    return meetings().filter(meeting => {
      if (state.view === 'meeting_actions'
          && !(meeting.action_items_total > meeting.action_items_done)) return false;
      if (state.project && meeting.project !== state.project) return false;
      if (needle) {
        const haystack = [
          meeting.title, meeting.summary, meeting.project_name, meeting.project,
          meeting.workspace, ...(meeting.attendees || []),
        ].join(' ').toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      return true;
    });
  }

  function countWhere(rows, predicate) {
    return rows.filter(predicate).length;
  }

  function setView(view) {
    state.view = view;
    if (state.section === 'tasks') {
      state.status = view === 'recent' ? '' : 'open';
      state.priority = view === 'p0' ? 'P0' : '';
    }
    render();
  }

  function syncSectionTabs() {
    document.querySelectorAll('#repoTabs [data-assistant-section]').forEach(button => {
      button.classList.toggle('active', button.dataset.assistantSection === state.section);
    });
  }

  function setSection(section, options = {}) {
    state.section = section === 'meetings' ? 'meetings' : 'tasks';
    state.view = state.section === 'tasks' ? 'open' : 'meetings';
    state.status = state.section === 'tasks' ? 'open' : '';
    state.priority = '';
    state.search = '';
    if (!options.history) {
      const url = new URL(window.location);
      url.searchParams.set('view', 'assistant');
      if (state.section === 'meetings') url.searchParams.set('subview', 'meetings');
      else url.searchParams.delete('subview');
      url.searchParams.delete(state.section === 'meetings' ? 'task' : 'meeting');
      history.pushState({nav: 'assistant', subview: state.section}, '', url.pathname + url.search + url.hash);
    }
    syncSectionTabs();
    render();
  }

  function renderSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;
    const projects = state.data && state.data.projects || [];
    const source = state.section === 'tasks' ? tasks() : meetings();
    const viewRows = state.section === 'tasks'
      ? [
          ['open', 'Open', countWhere(tasks(), task => task.status !== 'done')],
          ['in_progress', 'In progress', countWhere(tasks(), task => task.status === 'in_progress')],
          ['p0', 'P0', countWhere(tasks(), task => task.priority === 'P0' && task.status !== 'done')],
          ['recent', 'Recently completed', countWhere(tasks(), isRecentDone)],
        ]
      : [
          ['meetings', 'All notes', meetings().length],
          ['meeting_actions', 'Open action items', countWhere(meetings(), meeting => meeting.action_items_total > meeting.action_items_done)],
        ];
    let html = '<div class="sidebar-title">Views</div>';
    html += viewRows.map(([key, label, count]) => `
      <button type="button" class="assistant-side-row${state.view === key ? ' active' : ''}" data-assistant-view="${e(key)}">
        <span>${e(label)}</span><span class="assistant-side-count">${count}</span>
      </button>`).join('');
    html += '<div class="sidebar-title">Projects</div>';
    html += `<button type="button" class="assistant-side-row${!state.project ? ' active-project' : ''}" data-assistant-project=""><span>All projects</span><span class="assistant-side-count">${source.length}</span></button>`;
    html += projects.map(project => {
      const count = countWhere(source, row => row.project === project.id);
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

  function progressLabel(done, total, noun = 'subtasks') {
    if (!total) return '';
    return `${done}/${total} ${noun}`;
  }

  function checklist(items) {
    if (!items || !items.length) return '';
    return `<ul class="assistant-subtasks">${items.map(item => `
      <li class="${item.done ? 'done' : ''}">
        <span class="assistant-subtask-check" aria-hidden="true">${item.done ? '✓' : ''}</span>
        <span>${e(item.title)}</span><small>${item.done ? 'Done' : 'Open'}</small>
      </li>`).join('')}</ul>`;
  }

  function taskCard(task) {
    const selected = task.path === state.selectedTaskPath;
    const due = task.due ? `<span class="assistant-task-due">Due ${e(displayDate(task.due))}</span>` : '';
    const progress = progressLabel(task.subtasks_done, task.subtasks_total);
    const projectChip = `<span class="assistant-project-chip">${e(task.project_name || task.project)}</span>`;
    const previewImage = task.preview_image && task.preview_image.src
      ? `<img class="assistant-preview-image" src="${e(documentImageUrl(task.path, task.preview_image.src))}" alt="${e(task.preview_image.alt || '')}" loading="lazy">`
      : '';
    return `<article class="assistant-list-item${selected ? ' selected' : ''}" data-assistant-entry-wrap="${e(task.path)}">
      <button type="button" class="assistant-compact-row" data-assistant-task="${e(task.path)}" data-testid="assistant-task-row" aria-expanded="${selected}">
        <span class="assistant-row-main"><span class="assistant-priority ${e(String(task.priority || '').toLowerCase())}">${e(task.priority || 'P2')}</span><strong>${e(task.title)}</strong></span>
        <span class="assistant-row-meta">${projectChip}${progress ? `<span class="assistant-progress-label">${e(progress)}</span>` : ''}<span class="assistant-status status-${e(task.status || 'inbox')}">${e(labelStatus(task.status))}</span>${due}</span>
      </button>
      ${selected ? `<div class="assistant-inline-preview" data-testid="assistant-task-preview">
        <div class="assistant-preview-top"><div class="assistant-detail-badges"><span class="assistant-priority ${e(String(task.priority || '').toLowerCase())}">${e(task.priority || 'P2')}</span><span class="assistant-status status-${e(task.status || 'inbox')}">${e(labelStatus(task.status))}</span></div>${due}<span class="assistant-open-hint">Double-click to open</span></div>
        <h2>${e(task.title)}</h2>
        <div class="assistant-task-project">${e(task.project_name || task.project)}${task.workspace ? ` · ${e(task.workspace)}` : ''}</div>
        ${task.summary ? `<p class="assistant-task-summary">${e(task.summary)}</p>` : ''}
        ${previewImage}
        ${task.subtasks_total ? `<div class="assistant-subtask-head"><strong>Subtasks</strong><span>${e(progress)}</span></div>${checklist(task.subtasks)}` : ''}
        ${task.has_generated_content ? `<button type="button" class="assistant-generate-content" data-assistant-generate="${e(task.path)}">Generate content</button>` : ''}
      </div>` : ''}
    </article>`;
  }

  function meetingCard(meeting) {
    const selected = meeting.path === state.selectedMeetingPath;
    const actionProgress = progressLabel(meeting.action_items_done, meeting.action_items_total, 'actions');
    const attendees = Array.isArray(meeting.attendees) ? meeting.attendees.join(', ') : '';
    return `<article class="assistant-list-item${selected ? ' selected' : ''}" data-assistant-entry-wrap="${e(meeting.path)}">
      <button type="button" class="assistant-compact-row" data-assistant-meeting="${e(meeting.path)}" data-testid="assistant-meeting-row" aria-expanded="${selected}">
        <span class="assistant-row-main"><span class="assistant-meeting-date">${e(displayDate(meeting.date))}</span><strong>${e(meeting.title)}</strong></span>
        <span class="assistant-row-meta">${actionProgress ? `<span class="assistant-progress-label">${e(actionProgress)}</span>` : ''}<span class="assistant-task-project">${e(meeting.project_name || meeting.project)}</span></span>
      </button>
      ${selected ? `<div class="assistant-inline-preview" data-testid="assistant-meeting-preview">
        <div class="assistant-preview-top"><span class="assistant-meeting-date full">${e(displayDate(meeting.date))}</span><span class="assistant-open-hint">Double-click to open</span></div>
        <h2>${e(meeting.title)}</h2>
        <div class="assistant-task-project">${e(meeting.project_name || meeting.project)}${meeting.workspace ? ` · ${e(meeting.workspace)}` : ''}</div>
        ${attendees ? `<p class="assistant-attendees"><span>With</span> ${e(attendees)}</p>` : ''}
        ${meeting.summary ? `<p class="assistant-task-summary">${e(meeting.summary)}</p>` : ''}
        ${meeting.action_items_total ? `<div class="assistant-subtask-head"><strong>Action items</strong><span>${e(actionProgress)}</span></div>${checklist(meeting.action_items)}` : ''}
      </div>` : ''}
    </article>`;
  }

  function renderSetup(content) {
    const root = state.data && state.data.root;
    const message = !state.data || !state.data.configured
      ? 'Set LAB_ASSISTANT_HOME in this Lab checkout’s .env, then restart Lab.'
      : 'Create the configured directory, then run lab assistant init.';
    content.innerHTML = `<div class="assistant-setup">
      <span class="assistant-kicker">Global workspace</span>
      <h1>Assistant needs a database</h1>
      <p>${e(message)}</p>
      ${root ? `<code>${e(root)}</code>` : '<code>LAB_ASSISTANT_HOME=/absolute/path/to/assistant</code>'}
    </div>`;
  }

  function render() {
    if (!document.body.classList.contains('assistant-active')) return;
    renderSidebar();
    syncSectionTabs();
    const content = document.getElementById('content');
    if (!content) return;
    if (!state.data || !state.data.configured || !state.data.exists) {
      renderSetup(content);
      return;
    }
    const isTasks = state.section === 'tasks';
    const rows = isTasks ? filteredTasks() : filteredMeetings();
    const title = isTasks ? 'Tasks' : 'Meeting notes';
    const noun = isTasks ? 'task' : 'note';
    const controls = isTasks ? `
      <select id="assistantStatus" aria-label="Filter by status">
        <option value="open"${state.status === 'open' ? ' selected' : ''}>Open statuses</option>
        <option value=""${state.status === '' ? ' selected' : ''}>All statuses</option>
        ${(state.data.statuses || []).map(status => `<option value="${e(status)}"${state.status === status ? ' selected' : ''}>${e(labelStatus(status))}</option>`).join('')}
      </select>
      <select id="assistantPriority" aria-label="Filter by priority">
        <option value="">All priorities</option>
        ${(state.data.priorities || []).map(priority => `<option value="${e(priority)}"${state.priority === priority ? ' selected' : ''}>${e(priority)}</option>`).join('')}
      </select>` : '';
    content.innerHTML = `<div class="assistant-shell assistant-minimal-shell">
      <header class="assistant-head">
        <div><span class="assistant-kicker">Global Assistant</span><h1>${title}</h1></div>
        <button type="button" class="refresh-btn" id="assistantRefresh">Refresh</button>
      </header>
      <div class="assistant-filters">
        <input type="search" id="assistantSearch" value="${e(state.search)}" placeholder="Search ${isTasks ? 'tasks' : 'meeting notes'}…" aria-label="Search Assistant ${isTasks ? 'tasks' : 'meeting notes'}">
        ${controls}
        <span class="assistant-filter-count">${rows.length} ${noun}${rows.length === 1 ? '' : 's'}</span>
      </div>
      <section class="assistant-list assistant-list-single" aria-label="${title}" data-testid="assistant-list">
        ${rows.length ? rows.map(isTasks ? taskCard : meetingCard).join('') : `<div class="assistant-empty">No ${noun}s match these filters.</div>`}
      </section>
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
    content.querySelectorAll('[data-assistant-task]').forEach(button => bindRow(button, 'task'));
    content.querySelectorAll('[data-assistant-meeting]').forEach(button => bindRow(button, 'meeting'));
    content.querySelectorAll('[data-assistant-generate]').forEach(button => {
      button.addEventListener('click', event => {
        event.stopPropagation();
        openDocumentModal('task', button.dataset.assistantGenerate, 'Generate content');
      });
    });
  }

  function bindRow(button, kind) {
    const attribute = kind === 'task' ? 'assistantTask' : 'assistantMeeting';
    const path = button.dataset[attribute];
    button.addEventListener('click', () => {
      clearTimeout(state.clickTimer);
      state.clickTimer = setTimeout(() => selectEntry(kind, path, true), 190);
    });
    button.addEventListener('dblclick', event => {
      event.preventDefault();
      clearTimeout(state.clickTimer);
      selectEntry(kind, path, true);
      openDocumentModal(kind, path);
    });
  }

  function selectEntry(kind, path, push) {
    if (kind === 'task') state.selectedTaskPath = path || '';
    else state.selectedMeetingPath = path || '';
    if (push) {
      const url = new URL(window.location);
      url.searchParams.set('view', 'assistant');
      if (kind === 'task') {
        url.searchParams.delete('subview');
        url.searchParams.delete('meeting');
        if (path) url.searchParams.set('task', path);
      } else {
        url.searchParams.set('subview', 'meetings');
        url.searchParams.delete('task');
        if (path) url.searchParams.set('meeting', path);
      }
      history.pushState({nav: 'assistant', [kind]: path}, '', url.pathname + url.search + url.hash);
    }
    render();
  }

  function ensureModal() {
    let overlay = document.getElementById('assistantDocumentModal');
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.id = 'assistantDocumentModal';
    overlay.className = 'modal-overlay assistant-document-overlay';
    overlay.innerHTML = `<section class="assistant-document-modal" role="dialog" aria-modal="true" aria-labelledby="assistantModalTitle">
      <header class="assistant-modal-header"><div><span class="assistant-kicker" id="assistantModalKind">Assistant</span><h2 id="assistantModalTitle">Loading…</h2></div><button type="button" class="assistant-modal-close" aria-label="Close Assistant document">×</button></header>
      <div class="assistant-modal-body" id="assistantModalBody"><div class="loading">Loading…</div></div>
    </section>`;
    overlay.addEventListener('click', event => { if (event.target === overlay) closeDocumentModal(); });
    overlay.querySelector('.assistant-modal-close').addEventListener('click', closeDocumentModal);
    document.body.appendChild(overlay);
    return overlay;
  }

  function closeDocumentModal() {
    const overlay = document.getElementById('assistantDocumentModal');
    if (overlay) overlay.classList.remove('active');
  }

  async function openDocumentModal(kind, path, focusHeading = '') {
    const overlay = ensureModal();
    const title = document.getElementById('assistantModalTitle');
    const label = document.getElementById('assistantModalKind');
    const host = document.getElementById('assistantModalBody');
    label.textContent = kind === 'task' ? 'Task' : 'Meeting note';
    title.textContent = 'Loading…';
    host.innerHTML = '<div class="loading">Loading document…</div>';
    overlay.classList.add('active');
    const request = ++state.modalRequest;
    try {
      const endpoint = kind === 'task' ? '/api/assistant/task?path=' : '/api/assistant/meeting?path=';
      const response = await fetch(endpoint + encodeURIComponent(path));
      const detail = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(detail.detail || response.statusText);
      if (request !== state.modalRequest || !overlay.classList.contains('active')) return;
      await renderDocument(detail, kind, focusHeading);
    } catch (error) {
      if (request === state.modalRequest) host.innerHTML = `<div class="assistant-empty">${e(error.message || error)}</div>`;
    }
  }

  function localImageUrl(documentPath, src) {
    return '/api/assistant/asset?task=' + encodeURIComponent(documentPath) + '&src=' + encodeURIComponent(src);
  }

  function documentImageUrl(documentPath, src) {
    if (!src || src.startsWith('http://') || src.startsWith('https://') || src.startsWith('data:')) return src;
    return localImageUrl(documentPath, src);
  }

  function rewriteImages(host, documentPath) {
    host.querySelectorAll('img').forEach(img => {
      const src = img.getAttribute('src') || '';
      if (!src || src.startsWith('http://') || src.startsWith('https://') || src.startsWith('data:')) return;
      img.src = localImageUrl(documentPath, src);
    });
  }

  function documentMeta(detail, kind) {
    const metadata = detail.metadata || {};
    const project = detail.project || {};
    const rows = kind === 'task' ? [
      ['Status', labelStatus(metadata.status)], ['Priority', metadata.priority],
      ['Project', project.name || metadata.project], ['Workspace', project.workspace],
      ['Due', metadata.due], ['Owner', metadata.owner], ['Updated', displayDate(metadata.updated)],
    ] : [
      ['Date', metadata.date], ['Project', project.name || metadata.project],
      ['Workspace', project.workspace],
      ['Attendees', Array.isArray(metadata.attendees) ? metadata.attendees.join(', ') : metadata.attendees],
      ['Updated', displayDate(metadata.updated)],
    ];
    return rows.filter(row => row[1]).map(([key, value]) => `<div><span>${e(key)}</span><strong>${e(value)}</strong></div>`).join('');
  }

  async function renderDocument(detail, kind, focusHeading = '') {
    if (typeof window.ensureMarked === 'function') await window.ensureMarked().catch(() => {});
    const body = detail.body || '';
    const markdown = window.marked ? window.marked.parse(body) : `<pre>${e(body)}</pre>`;
    const metadata = detail.metadata || {};
    const project = detail.project || {};
    const title = document.getElementById('assistantModalTitle');
    const host = document.getElementById('assistantModalBody');
    title.textContent = metadata.title || metadata.id || (kind === 'task' ? 'Task' : 'Meeting note');
    const badges = kind === 'task'
      ? `<div class="assistant-detail-badges"><span class="assistant-priority ${e(String(metadata.priority || '').toLowerCase())}">${e(metadata.priority || 'P2')}</span><span class="assistant-status status-${e(metadata.status || 'inbox')}">${e(labelStatus(metadata.status))}</span></div>`
      : `<div class="assistant-detail-badges"><span class="assistant-meeting-date full">${e(displayDate(metadata.date))}</span></div>`;
    host.innerHTML = `<div class="assistant-document-toolbar">
      ${badges}<div class="assistant-detail-actions"><button type="button" class="refresh-btn" id="assistantCopyDocument">Copy Markdown</button></div>
    </div>
    <div class="assistant-meta">${documentMeta(detail, kind)}</div>
    ${project.project_path ? `<div class="assistant-path"><span>Project path</span><code>${e(project.project_path)}</code></div>` : ''}
    <div class="nb-markdown assistant-markdown" id="assistantModalMarkdown">${markdown}</div>`;
    const markdownHost = document.getElementById('assistantModalMarkdown');
    rewriteImages(markdownHost, detail.path);
    addCopyButtons(markdownHost, body, detail.path);
    document.getElementById('assistantCopyDocument')?.addEventListener('click', event => copyPlain(body, event.currentTarget));
    if (focusHeading) {
      const target = Array.from(markdownHost.querySelectorAll('h1, h2, h3'))
        .find(heading => heading.firstChild && heading.firstChild.textContent.trim() === focusHeading);
      if (target) {
        target.classList.add('assistant-content-target');
        requestAnimationFrame(() => target.scrollIntoView({block: 'start'}));
      }
    }
  }

  function markdownSection(body, headingText, level) {
    const lines = body.split('\n');
    const prefix = '#'.repeat(level) + ' ';
    const start = lines.findIndex(line => line.trimStart().startsWith(prefix)
      && line.replace(/^\s*#+\s+/, '').trim() === headingText);
    if (start < 0) return '';
    let end = lines.length;
    for (let index = start + 1; index < lines.length; index += 1) {
      const match = lines[index].match(/^\s*(#{1,6})\s/);
      if (match && match[1].length <= level) { end = index; break; }
    }
    return lines.slice(start, end).join('\n').trim();
  }

  function markdownSectionBody(body, headingText, level) {
    const section = markdownSection(body, headingText, level);
    return section.split('\n').slice(1).join('\n').trim();
  }

  function addCopyButtons(host, body, documentPath) {
    host.querySelectorAll('h1, h2, h3').forEach(heading => {
      const level = Number(heading.tagName.slice(1));
      const headingText = heading.textContent.trim();
      const actions = document.createElement('span');
      actions.className = 'assistant-copy-actions';
      if (headingText.toLowerCase() === 'generate content') {
        const generated = markdownSectionBody(body, headingText, level);
        const copy = document.createElement('button');
        copy.type = 'button';
        copy.className = 'primary';
        copy.textContent = 'Copy content';
        copy.title = 'Copy formatted content and embedded images for email or another app';
        copy.addEventListener('click', () => copyRich(generated, documentPath, copy));
        const plain = document.createElement('button');
        plain.type = 'button';
        plain.textContent = 'Plain text';
        plain.title = 'Copy the generated Markdown as plain text';
        plain.addEventListener('click', () => copyPlain(generated, plain));
        actions.append(copy, plain);
        heading.appendChild(actions);
        return;
      }
      const slack = document.createElement('button');
      slack.type = 'button';
      slack.textContent = 'Slack';
      slack.title = 'Copy this Markdown section';
      slack.addEventListener('click', () => copyPlain(markdownSection(body, headingText, level), slack));
      const gdoc = document.createElement('button');
      gdoc.type = 'button';
      gdoc.textContent = 'GDoc';
      gdoc.title = 'Copy this section as formatted rich text';
      gdoc.addEventListener('click', () => copyRich(markdownSection(body, headingText, level), documentPath, gdoc));
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

  async function copyRich(markdown, documentPath, button) {
    const original = button.textContent;
    if (typeof window.ensureMarked === 'function') await window.ensureMarked().catch(() => {});
    const container = document.createElement('div');
    container.innerHTML = window.marked ? window.marked.parse(markdown) : `<pre>${e(markdown)}</pre>`;
    rewriteImages(container, documentPath);
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
    container.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach(node => { node.style.fontFamily = 'Arial, sans-serif'; });
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
      if (options.task !== undefined) state.selectedTaskPath = options.task || '';
      if (options.meeting !== undefined) state.selectedMeetingPath = options.meeting || '';
      render();
    } catch (error) {
      const content = document.getElementById('content');
      if (content && request === state.request) content.innerHTML = `<div class="assistant-setup"><h1>Assistant</h1><p>${e(error.message || error)}</p></div>`;
    }
  }

  function init(initial = '') {
    const options = typeof initial === 'object' && initial !== null ? initial : {task: initial};
    state.section = options.section === 'meetings' ? 'meetings' : 'tasks';
    state.selectedTaskPath = options.task || '';
    state.selectedMeetingPath = options.meeting || '';
    state.view = state.section === 'tasks' ? 'open' : 'meetings';
    state.status = state.section === 'tasks' ? 'open' : '';
    state.priority = '';
    state.project = '';
    state.search = '';
    refresh({task: state.selectedTaskPath, meeting: state.selectedMeetingPath});
    if (!state.poll) {
      state.poll = setInterval(() => {
        if (document.body.classList.contains('assistant-active') && !document.hidden) refresh();
      }, 5000);
    }
  }

  document.addEventListener('keydown', event => {
    const overlay = document.getElementById('assistantDocumentModal');
    if (event.key === 'Escape' && overlay && overlay.classList.contains('active')) {
      event.preventDefault();
      event.stopImmediatePropagation();
      closeDocumentModal();
    }
  });

  window.AssistantView = {
    init,
    refresh,
    setSection,
    section: () => state.section,
    selectTask: path => selectEntry('task', path, true),
    openDocument: openDocumentModal,
    closeDocument: closeDocumentModal,
  };
})();
