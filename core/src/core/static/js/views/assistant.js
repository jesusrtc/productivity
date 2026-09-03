(function () {
  'use strict';

  const state = {
    data: null,
    section: 'tasks-1',
    selectedTaskPath: '',
    selectedSubtaskPath: '',
    selectedMeetingPath: '',
    view: 'focus',
    status: '',
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

  function isTaskSection() {
    return state.section !== 'meetings';
  }

  function taskChildren(task) {
    if (Array.isArray(task.subtasks)) return task.subtasks;
    return Array.isArray(task.first_class_subtasks) ? task.first_class_subtasks : [];
  }

  function reviewCount(task) {
    return taskChildren(task).filter(item => item.status === 'ready_to_review').length;
  }

  function hasReview(task) {
    return task.status === 'ready_to_review' || reviewCount(task) > 0;
  }

  function localDayValue(value) {
    if (!value) return Number.NaN;
    const plain = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
    const date = plain
      ? new Date(Number(plain[1]), Number(plain[2]) - 1, Number(plain[3]))
      : new Date(value);
    return date.getTime();
  }

  function needsFollowUp(task) {
    if (task.status !== 'waiting') return false;
    if (!task.follow_up_at) return true;
    const today = new Date();
    today.setHours(23, 59, 59, 999);
    return localDayValue(task.follow_up_at) <= today.getTime();
  }

  function attentionBucket(task) {
    if (task.status === 'done') return 99;
    if (task.priority === 'P0') return 0;
    if (hasReview(task)) return 1;
    if (task.status === 'in_progress') return 2;
    if (needsFollowUp(task)) return 3;
    if (task.status === 'blocked') return 4;
    if (task.status === 'inbox') return 5;
    return 6;
  }

  function compareTasks(left, right) {
    const priority = {P0: 0, P1: 1, P2: 2, P3: 3};
    const bucket = attentionBucket(left) - attentionBucket(right);
    if (bucket) return bucket;
    const byPriority = (priority[left.priority] ?? 9) - (priority[right.priority] ?? 9);
    if (byPriority) return byPriority;
    const leftDate = localDayValue(left.due || left.follow_up_at);
    const rightDate = localDayValue(right.due || right.follow_up_at);
    if (Number.isFinite(leftDate) || Number.isFinite(rightDate)) {
      if (!Number.isFinite(leftDate)) return 1;
      if (!Number.isFinite(rightDate)) return -1;
      if (leftDate !== rightDate) return leftDate - rightDate;
    }
    return localDayValue(right.updated) - localDayValue(left.updated);
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
      if (state.view === 'ready_to_review' && !hasReview(task)) return false;
      if (state.view === 'waiting' && !needsFollowUp(task)) return false;
      if (state.view === 'inbox' && task.status !== 'inbox') return false;
      if (state.view === 'focus' && task.status === 'done') return false;
      if (state.view === 'all_open' && task.status === 'done') return false;
      if (state.status && task.status !== state.status) return false;
      if (state.priority && task.priority !== state.priority) return false;
      if (state.project && task.project !== state.project) return false;
      if (needle) {
        const haystack = [task.title, task.summary, task.project_name, task.project, task.workspace]
          .join(' ').toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      return true;
    }).sort(state.view === 'recent'
      ? (left, right) => localDayValue(right.completed || right.updated) - localDayValue(left.completed || left.updated)
      : compareTasks);
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
    state.status = '';
    state.priority = '';
    render();
  }

  function syncSectionTabs() {
    document.querySelectorAll('#repoTabs [data-assistant-section]').forEach(button => {
      button.classList.toggle('active', button.dataset.assistantSection === state.section);
    });
  }

  function setSection(section, options = {}) {
    state.section = ['tasks-2', 'tasks-3', 'meetings'].includes(section) ? section : 'tasks-1';
    state.view = isTaskSection() ? 'focus' : 'meetings';
    state.status = '';
    state.priority = '';
    if (!options.history) {
      const url = new URL(window.location);
      url.searchParams.set('view', 'assistant');
      if (state.section === 'meetings') url.searchParams.set('subview', 'meetings');
      else if (state.section === 'tasks-2' || state.section === 'tasks-3') url.searchParams.set('subview', state.section);
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
    sidebar.innerHTML = '';
  }

  function progressLabel(done, total, noun = 'subtasks') {
    if (!total) return '';
    return `${done}/${total} ${noun}`;
  }

  function checklist(items) {
    if (!items || !items.length) return '';
    return `<ul class="assistant-subtasks">${items.map(item => `
      <li class="${item.done ? 'done' : ''}${item.path === state.selectedSubtaskPath ? ' selected' : ''}">
        ${item.path ? `<button type="button" class="assistant-subtask-row" data-assistant-subtask="${e(item.path)}" title="Double-click to open subtask">
          <span class="assistant-subtask-check" aria-hidden="true">${item.done ? '✓' : ''}</span>
          <span>${e(item.title)}</span><small class="status-${e(item.status || 'inbox')}">${e(labelStatus(item.status))}</small>
        </button>` : `<div class="assistant-subtask-row legacy">
          <span class="assistant-subtask-check" aria-hidden="true">${item.done ? '✓' : ''}</span>
          <span>${e(item.title)}</span><small>${item.done ? 'Done' : 'Open'}</small>
        </div>`}
      </li>`).join('')}</ul>`;
  }

  function taskCard(task) {
    const selected = task.path === state.selectedTaskPath;
    const due = task.due ? `<span class="assistant-task-due">Due ${e(displayDate(task.due))}</span>` : '';
    const progress = progressLabel(task.subtasks_done, task.subtasks_total);
    const children = taskChildren(task);
    const reviews = reviewCount(task);
    const projectChip = `<span class="assistant-project-chip">${e(task.project_name || task.project)}</span>`;
    const previewImage = task.preview_image && task.preview_image.src
      ? `<img class="assistant-preview-image" src="${e(documentImageUrl(task.path, task.preview_image.src))}" alt="${e(task.preview_image.alt || '')}" loading="lazy">`
      : '';
    return `<article class="assistant-list-item${selected ? ' selected' : ''}" data-assistant-entry-wrap="${e(task.path)}">
      <div role="button" tabindex="0" class="assistant-compact-row" data-assistant-task="${e(task.path)}" data-testid="assistant-task-row" aria-expanded="${selected}">
        <span class="assistant-row-main"><span class="assistant-priority ${e(String(task.priority || '').toLowerCase())}">${e(task.priority || 'P2')}</span><strong>${e(task.title)}</strong></span>
        <span class="assistant-row-meta">${projectChip}${reviews ? `<span class="assistant-review-count">${reviews} to review</span>` : ''}${progress ? `<span class="assistant-progress-label">${e(progress)}</span>` : ''}<span class="assistant-status status-${e(task.status || 'inbox')}">${e(labelStatus(task.status))}</span>${task.status === 'waiting' ? `<button type="button" class="assistant-nudge" data-assistant-nudge="${e(task.path)}">Nudge</button>` : ''}${due}</span>
      </div>
      ${selected ? `<div class="assistant-inline-preview" data-testid="assistant-task-preview">
        <div class="assistant-preview-top"><div class="assistant-detail-badges"><span class="assistant-priority ${e(String(task.priority || '').toLowerCase())}">${e(task.priority || 'P2')}</span><span class="assistant-status status-${e(task.status || 'inbox')}">${e(labelStatus(task.status))}</span></div>${due}<span class="assistant-open-hint">Double-click to open</span></div>
        <h2>${e(task.title)}</h2>
        <div class="assistant-task-project">${e(task.project_name || task.project)}${task.workspace ? ` · ${e(task.workspace)}` : ''}</div>
        ${task.waiting_on ? `<p class="assistant-waiting-on"><span>Waiting on</span> ${e(task.waiting_on)}${task.follow_up_at ? ` · Follow up ${e(displayDate(task.follow_up_at))}` : ''}</p>` : ''}
        ${task.summary ? `<p class="assistant-task-summary">${e(task.summary)}</p>` : ''}
        ${previewImage}
        ${task.subtasks_total ? `<div class="assistant-subtask-head"><strong>Subtasks</strong><span>${e(progress)}</span></div>${checklist(children)}` : ''}
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

  function viewMatches(task, view) {
    if (view === 'p0') return task.priority === 'P0' && task.status !== 'done';
    if (view === 'in_progress') return task.status === 'in_progress';
    if (view === 'ready_to_review') return task.status !== 'done' && hasReview(task);
    if (view === 'waiting') return needsFollowUp(task);
    if (view === 'inbox') return task.status === 'inbox';
    if (view === 'recent') return isRecentDone(task);
    return task.status !== 'done';
  }

  function scopedTasks() {
    return tasks().filter(task => !state.project || task.project === state.project);
  }

  function quickViews() {
    const source = scopedTasks();
    const definitions = [
      ['focus', 'Focus'], ['p0', 'P0'], ['in_progress', 'In progress'],
      ['ready_to_review', 'Ready to review'], ['waiting', 'Follow up'],
      ['inbox', 'Inbox'], ['recent', 'Recently completed'],
    ];
    return `<nav class="assistant-quick-views" aria-label="Task views">${definitions.map(([key, label]) => {
      const count = countWhere(source, task => viewMatches(task, key));
      return `<button type="button" class="${state.view === key ? 'active' : ''}" data-assistant-view="${e(key)}"><span>${e(label)}</span><small>${count}</small></button>`;
    }).join('')}</nav>`;
  }

  function projectSelect(source) {
    const projects = state.data && state.data.projects || [];
    return `<select id="assistantProject" aria-label="Filter by project">
      <option value="">All projects (${source.length})</option>
      ${projects.map(project => {
        const count = countWhere(source, row => row.project === project.id);
        return `<option value="${e(project.id)}"${state.project === project.id ? ' selected' : ''}>${e(project.name || project.id)} (${count})</option>`;
      }).join('')}
    </select>`;
  }

  function filterBar(rows, options = {}) {
    const isTasks = isTaskSection();
    const advanced = isTasks && options.advanced ? `
      <select id="assistantStatus" aria-label="Filter by status">
        <option value="">Any status</option>
        ${(state.data.statuses || []).map(status => `<option value="${e(status)}"${state.status === status ? ' selected' : ''}>${e(labelStatus(status))}</option>`).join('')}
      </select>
      <select id="assistantPriority" aria-label="Filter by priority">
        <option value="">Any priority</option>
        ${(state.data.priorities || []).map(priority => `<option value="${e(priority)}"${state.priority === priority ? ' selected' : ''}>${e(priority)}</option>`).join('')}
      </select>` : '';
    return `<div class="assistant-filters">
      <input type="search" id="assistantSearch" value="${e(state.search)}" placeholder="Search ${isTasks ? 'tasks' : 'meeting notes'}…" aria-label="Search Assistant ${isTasks ? 'tasks' : 'meeting notes'}">
      ${projectSelect(isTasks ? tasks() : meetings())}${advanced}
      <span class="assistant-filter-count">${rows.length} ${isTasks ? 'task' : 'note'}${rows.length === 1 ? '' : 's'}</span>
    </div>`;
  }

  function emptyTasks() {
    return '<div class="assistant-empty">No tasks match this view.</div>';
  }

  function renderTasksOne(rows) {
    return `${quickViews()}${filterBar(rows, {advanced: true})}
      <section class="assistant-list assistant-list-single" aria-label="Tasks proposal 1" data-testid="assistant-list">
        ${rows.length ? rows.map(taskCard).join('') : emptyTasks()}
      </section>`;
  }

  function taskGroup(task) {
    if (task.priority === 'P0') return 'p0';
    if (hasReview(task)) return 'ready_to_review';
    if (task.status === 'in_progress') return 'in_progress';
    if (task.status === 'waiting') return 'waiting';
    if (task.status === 'blocked') return 'blocked';
    if (task.status === 'inbox') return 'inbox';
    return 'up_next';
  }

  function renderTasksTwo(rows) {
    const groups = [
      ['p0', 'P0'], ['ready_to_review', 'Ready to review'],
      ['in_progress', 'In progress'], ['waiting', 'Follow up'],
      ['blocked', 'Blocked'], ['inbox', 'Inbox'], ['up_next', 'Up next'],
    ];
    const sections = groups.map(([key, label]) => {
      const items = rows.filter(task => taskGroup(task) === key);
      if (!items.length) return '';
      return `<section class="assistant-queue-group" data-assistant-queue="${e(key)}">
        <header><h2>${e(label)}</h2><span>${items.length}</span></header>
        <div class="assistant-list">${items.map(taskCard).join('')}</div>
      </section>`;
    }).join('');
    return `${filterBar(rows)}<div class="assistant-focus-queue" data-testid="assistant-list">${sections || emptyTasks()}</div>`;
  }

  function projectAttention(rows) {
    const p0 = countWhere(rows, task => task.priority === 'P0' && task.status !== 'done');
    const review = countWhere(rows, hasReview);
    const waiting = countWhere(rows, task => task.status === 'waiting');
    return [[p0, 'P0'], [review, 'review'], [waiting, 'waiting']]
      .filter(item => item[0]).map(item => `${item[0]} ${item[1]}`).join(' · ') || `${rows.length} open`;
  }

  function renderTasksThree(rows) {
    const projects = state.data && state.data.projects || [];
    const sections = projects.map(project => {
      const items = rows.filter(task => task.project === project.id);
      if (!items.length) return '';
      return `<section class="assistant-project-ledger" data-assistant-project-group="${e(project.id)}">
        <header><div><h2>${e(project.name || project.id)}</h2><span>${e(project.workspace || '')}</span></div><small>${e(projectAttention(items))}</small></header>
        <div class="assistant-list">${items.map(taskCard).join('')}</div>
      </section>`;
    }).join('');
    return `${quickViews()}${filterBar(rows)}<div class="assistant-ledgers" data-testid="assistant-list">${sections || emptyTasks()}</div>`;
  }

  function renderMeetings(rows) {
    return `<nav class="assistant-quick-views compact" aria-label="Meeting views">
      <button type="button" class="${state.view === 'meetings' ? 'active' : ''}" data-assistant-view="meetings"><span>All notes</span><small>${meetings().length}</small></button>
      <button type="button" class="${state.view === 'meeting_actions' ? 'active' : ''}" data-assistant-view="meeting_actions"><span>Open action items</span><small>${countWhere(meetings(), meeting => meeting.action_items_total > meeting.action_items_done)}</small></button>
    </nav>${filterBar(rows)}
      <section class="assistant-list assistant-list-single" aria-label="Meeting notes" data-testid="assistant-list">
        ${rows.length ? rows.map(meetingCard).join('') : '<div class="assistant-empty">No meeting notes match these filters.</div>'}
      </section>`;
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
    const rows = isTaskSection() ? filteredTasks() : filteredMeetings();
    const proposal = state.section === 'tasks-1' ? 'Proposal 1 · Filter strip'
      : state.section === 'tasks-2' ? 'Proposal 2 · Focus queue'
      : state.section === 'tasks-3' ? 'Proposal 3 · Project ledger' : 'Global Assistant';
    const title = isTaskSection() ? 'Tasks' : 'Meeting notes';
    const body = state.section === 'tasks-1' ? renderTasksOne(rows)
      : state.section === 'tasks-2' ? renderTasksTwo(rows)
      : state.section === 'tasks-3' ? renderTasksThree(rows) : renderMeetings(rows);
    content.innerHTML = `<div class="assistant-shell assistant-minimal-shell assistant-layout-${e(state.section)}">
      <header class="assistant-head">
        <div><span class="assistant-kicker">${e(proposal)}</span><h1>${e(title)}</h1></div>
        <button type="button" class="refresh-btn" id="assistantRefresh">Refresh</button>
      </header>${body}
    </div>`;
    document.getElementById('assistantRefresh')?.addEventListener('click', refresh);
    content.querySelectorAll('[data-assistant-view]').forEach(button => {
      button.addEventListener('click', () => setView(button.dataset.assistantView));
    });
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
      state.view = state.status || 'focus';
      render();
    });
    document.getElementById('assistantPriority')?.addEventListener('change', event => {
      state.priority = event.target.value;
      state.view = state.priority === 'P0' ? 'p0' : 'focus';
      render();
    });
    document.getElementById('assistantProject')?.addEventListener('change', event => {
      state.project = event.target.value;
      render();
    });
    content.querySelectorAll('[data-assistant-task]').forEach(button => bindRow(button, 'task'));
    content.querySelectorAll('[data-assistant-meeting]').forEach(button => bindRow(button, 'meeting'));
    content.querySelectorAll('[data-assistant-subtask]').forEach(button => bindSubtask(button));
    content.querySelectorAll('[data-assistant-generate]').forEach(button => {
      button.addEventListener('click', event => {
        event.stopPropagation();
        openDocumentModal('task', button.dataset.assistantGenerate, 'Generate content');
      });
    });
    content.querySelectorAll('[data-assistant-nudge]').forEach(button => {
      button.addEventListener('click', event => {
        event.stopPropagation();
        const task = tasks().find(item => item.path === button.dataset.assistantNudge);
        openDocumentModal('task', button.dataset.assistantNudge, task && task.has_generated_content ? 'Generate content' : '');
      });
    });
  }

  function bindRow(button, kind) {
    const attribute = kind === 'task' ? 'assistantTask' : 'assistantMeeting';
    const path = button.dataset[attribute];
    button.addEventListener('click', event => {
      if (event.target.closest('[data-assistant-nudge], [data-assistant-subtask]')) return;
      clearTimeout(state.clickTimer);
      state.clickTimer = setTimeout(() => selectEntry(kind, path, true), 190);
    });
    button.addEventListener('dblclick', event => {
      if (event.target.closest('[data-assistant-nudge], [data-assistant-subtask]')) return;
      event.preventDefault();
      clearTimeout(state.clickTimer);
      selectEntry(kind, path, true);
      openDocumentModal(kind, path);
    });
    button.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      selectEntry(kind, path, true);
      openDocumentModal(kind, path);
    });
  }

  function bindSubtask(button) {
    const path = button.dataset.assistantSubtask;
    button.addEventListener('click', event => {
      event.stopPropagation();
      clearTimeout(state.clickTimer);
      state.clickTimer = setTimeout(() => {
        state.selectedSubtaskPath = path;
        render();
      }, 190);
    });
    button.addEventListener('dblclick', event => {
      event.preventDefault();
      event.stopPropagation();
      clearTimeout(state.clickTimer);
      state.selectedSubtaskPath = path;
      openDocumentModal('subtask', path);
    });
    button.addEventListener('keydown', event => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      event.stopPropagation();
      state.selectedSubtaskPath = path;
      openDocumentModal('subtask', path);
    });
  }

  function selectEntry(kind, path, push) {
    if (kind === 'task') state.selectedTaskPath = path || '';
    else state.selectedMeetingPath = path || '';
    if (push) {
      const url = new URL(window.location);
      url.searchParams.set('view', 'assistant');
      if (kind === 'task') {
        if (state.section === 'tasks-2' || state.section === 'tasks-3') {
          url.searchParams.set('subview', state.section);
        } else {
          url.searchParams.delete('subview');
        }
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
    label.textContent = kind === 'task' ? 'Task' : kind === 'subtask' ? 'Subtask' : 'Meeting note';
    title.textContent = 'Loading…';
    host.innerHTML = '<div class="loading">Loading document…</div>';
    overlay.classList.add('active');
    const request = ++state.modalRequest;
    try {
      const endpoint = kind === 'task' ? '/api/assistant/task?path='
        : kind === 'subtask' ? '/api/assistant/subtask?path=' : '/api/assistant/meeting?path=';
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
    const rows = kind !== 'meeting' ? [
      ['Status', labelStatus(metadata.status)], ['Priority', metadata.priority],
      ['Project', project.name || metadata.project], ['Workspace', project.workspace],
      ['Parent', metadata.parent], ['Due', metadata.due], ['Owner', metadata.owner],
      ['Waiting on', metadata.waiting_on], ['Follow up', metadata.follow_up_at],
      ['Updated', displayDate(metadata.updated)],
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
    const badges = kind !== 'meeting'
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
    state.section = ['tasks-2', 'tasks-3', 'meetings'].includes(options.section) ? options.section : 'tasks-1';
    state.selectedTaskPath = options.task || '';
    state.selectedSubtaskPath = '';
    state.selectedMeetingPath = options.meeting || '';
    state.view = isTaskSection() ? 'focus' : 'meetings';
    state.status = '';
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
