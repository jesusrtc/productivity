(function () {
  'use strict';

  const state = {
    data: null,
    section: 'tasks',
    noteFiles: [],
    notesError: '',
    selectedTaskPath: '',
    selectedSubtaskPath: '',
    selectedMeetingPath: '',
    view: 'all_open',
    status: '',
    priority: '',
    workspace: '',
    search: '',
    selectedSeriesPath: '',
    modalMeetingPart: 'summary',
    modalRoot: null,
    modalCurrent: null,
    modalKind: '',
    request: 0,
    modalRequest: 0,
    poll: null,
    searchTimer: null,
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
    return state.section === 'tasks';
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

  function isDueSoon(task) {
    if (task.status === 'done' || !task.due) return false;
    const due = localDayValue(task.due);
    if (!Number.isFinite(due)) return false;
    const end = new Date();
    end.setHours(23, 59, 59, 999);
    end.setDate(end.getDate() + 3);
    return due <= end.getTime();
  }

  function needsAttention(task) {
    return task.status !== 'done' && (
      task.priority === 'P0'
      || task.status === 'in_progress'
      || hasReview(task)
      || isDueSoon(task)
    );
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

  function calendarDate(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000')) return '';
    const day = new Date(value + 'T00:00:00Z');
    return Number.isFinite(day.getTime()) && day.toISOString().slice(0, 10) === value ? value : '';
  }

  function taskCreatedDate(value) {
    if (typeof value !== 'string') return '';
    const date = calendarDate(value.slice(0, 10));
    return date && (value === date || value.startsWith(date + 'T') && Number.isFinite(new Date(value).getTime())) ? date : '';
  }

  function localToday(day = new Date()) {
    return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`;
  }

  function weekEnd() {
    const day = new Date();
    day.setDate(day.getDate() + (7 - day.getDay()) % 7);
    return localToday(day);
  }

  function dateGroups(rows, renderRow, dateFor, kind) {
    const groups = new Map();
    rows.forEach(row => {
      const date = dateFor(row);
      if (!groups.has(date)) groups.set(date, []);
      groups.get(date).push(row);
    });
    return [...groups.keys()].sort((a, b) => b.localeCompare(a)).map(day =>
      `<section class="assistant-date-group" data-assistant-${kind}-date="${e(day || 'Undated')}"><h3 class="assistant-date-header">${e(day || 'Undated')}</h3>${groups.get(day).map(renderRow).join('')}</section>`).join('');
  }

  function sortedMeetings(rows, key = 'date') {
    return [...rows].sort((a, b) => calendarDate(b[key]).localeCompare(calendarDate(a[key])) || String(a.path).localeCompare(String(b.path)));
  }

  function meetingName(row) { return row.series_title || row.title || 'Meeting'; }
  function meetingLabel(row) { return `${calendarDate(row.date) || 'Undated'} ${meetingName(row)}`; }

  function filteredSeries() {
    const needle = state.search.toLowerCase().trim();
    return (state.data?.meeting_series || []).filter(row => (!state.workspace || row.workspace === state.workspace)
      && (!needle || [row.title, row.summary, row.workspace_name].join(' ').toLowerCase().includes(needle)
        || filteredMeetings().some(meeting => meeting.series_path === row.path)));
  }

  function filteredTasks() {
    const needle = state.search.trim().toLowerCase();
    return tasks().filter(task => {
      if (state.view === 'recent' && !isRecentDone(task)) return false;
      if (state.view !== 'recent' && task.status === 'done') return false;
      const today = localToday();
      if (state.view === 'today' && !(calendarDate(task.scheduled) && task.scheduled <= today || calendarDate(task.due) && task.due <= today)) return false;
      if (state.view === 'week' && ![task.scheduled, task.due].some(date => calendarDate(date) && date <= weekEnd())) return false;
      if (['today', 'week'].includes(state.view) && calendarDate(task.defer_until) && task.defer_until > today && !(calendarDate(task.due) && task.due <= today)) return false;
      if (state.view === 'recurring' && !task.recurrence) return false;
      if (state.view === 'someday' && !(task.priority === 'P3' || calendarDate(task.defer_until) && task.defer_until > today)) return false;
      if (state.view === 'p0' && task.priority !== 'P0') return false;
      if (state.view === 'in_progress' && task.status !== 'in_progress') return false;
      if (state.view === 'ready_to_review' && !hasReview(task)) return false;
      if (state.view === 'waiting' && task.status !== 'waiting') return false;
      if (state.view === 'inbox' && task.status !== 'inbox') return false;
      if (state.view === 'focus' && task.status === 'done') return false;
      if (state.view === 'all_open' && task.status === 'done') return false;
      if (state.status && task.status !== state.status) return false;
      if (state.priority && task.priority !== state.priority) return false;
      if (state.workspace && task.workspace !== state.workspace) return false;
      if (needle) {
        const haystack = [task.title, task.tldr, task.summary, task.group, task.workspace_name, task.workspace, task.vault]
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
      if (state.workspace && meeting.workspace !== state.workspace) return false;
      if (needle) {
        const haystack = [
          meeting.title, meeting.summary, meeting.workspace_name, meeting.workspace,
          meeting.vault, meeting.series_title, ...(meeting.attendees || []),
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
    closeDocumentModal(false);
    const previousSection = state.section;
    state.section = ['notes', 'meetings'].includes(section) ? 'notes' : 'tasks';
    if (state.section !== previousSection) { state.search = ''; clearTimeout(state.searchTimer); }
    if (state.section === 'notes' && previousSection !== 'notes') state.workspace = '';
    state.view = isTaskSection() ? 'all_open' : 'meetings';
    state.status = '';
    state.priority = '';
    if (isTaskSection() && !workspaceRows().some(workspace => workspace.id === state.workspace)) {
      const available = workspaceRows();
      state.workspace = available.length ? available[0].id : '';
    }
    if (!options.history) {
      const url = new URL(window.location);
      url.searchParams.set('view', 'assistant');
      if (state.section === 'notes') { url.searchParams.set('subview', 'notes'); url.searchParams.delete('assistant_workspace'); }
      else if (state.section === 'tasks') {
        url.searchParams.set('subview', 'tasks');
        if (state.workspace) url.searchParams.set('assistant_workspace', state.workspace);
      }
      if (state.section !== 'tasks') url.searchParams.delete('task');
      url.searchParams.delete('meeting');
      url.searchParams.delete('series');
      history.pushState({nav: 'assistant', subview: state.section}, '', url.pathname + url.search + url.hash);
    }
    if (window.assistantSectionShell) window.assistantSectionShell(state.section);
    syncSectionTabs();
    render();
    if (state.section === 'notes') void refresh();
  }

  function progressLabel(done, total, noun = 'subtasks') {
    if (!total) return '';
    return `${done}/${total} ${noun}`;
  }

  function taskCard(task) {
    const selected = task.path === state.selectedTaskPath;
    const due = task.due ? `<span class="assistant-task-due">Due ${e(displayDate(task.due))}</span>` : '';
    const progress = progressLabel(task.subtasks_done, task.subtasks_total);
    const reviews = reviewCount(task);
    const tldr = task.tldr || task.summary || 'No TLDR yet.';
    return `<article class="assistant-list-item${selected ? ' selected' : ''}" data-assistant-entry-wrap="${e(task.path)}">
      <div role="button" tabindex="0" class="assistant-compact-row assistant-task-row" data-assistant-task="${e(task.path)}" data-testid="assistant-task-row" aria-label="Open ${e(task.title)}">

        <span class="assistant-row-content">
          <span class="assistant-row-title"><span class="assistant-priority ${e(String(task.priority || '').toLowerCase())}">${e(task.priority || 'P2')}</span><strong>${e(task.title)}</strong></span>
          <span class="assistant-row-tldr"><b>TLDR</b>${e(tldr)}</span>
        </span>
        <span class="assistant-row-meta">${task.group ? `<span class="assistant-task-group-label" title="Workstream: ${e(task.group)}">${e(task.group)}</span>` : ''}${task.recurrence ? `<span class="assistant-repeat" title="${task.due ? 'Next due: ' + e(task.due) : 'Due date needs confirmation'}">↻ ${e(task.recurrence)}${task.due ? '' : ' · Date needed'}</span>` : ''}${task.scheduled ? `<span class="assistant-task-due">Planned ${e(displayDate(task.scheduled))}</span>` : ''}${task.defer_until ? `<span class="assistant-task-due">Later · ${e(displayDate(task.defer_until))}</span>` : ''}${task.source === 'demo' ? '<span class="assistant-demo">Demo</span>' : ''}${reviews ? `<span class="assistant-review-count">${reviews} to review</span>` : ''}${progress ? `<span class="assistant-progress-label">${e(progress)}</span>` : ''}<span class="assistant-status status-${e(task.status || 'inbox')}">${e(labelStatus(task.status))}</span>${task.status === 'waiting' ? `<button type="button" class="assistant-nudge" data-assistant-nudge="${e(task.path)}">Nudge</button>` : ''}${due}</span>
      </div>
    </article>`;
  }

  function meetingCard(meeting) {
    return `<article class="assistant-list-item"><button type="button" class="assistant-compact-row assistant-meeting-row" data-assistant-meeting="${e(meeting.path)}" data-testid="assistant-meeting-row" title="${e(meetingLabel(meeting))}"><span class="assistant-meeting-label">${e(meetingName(meeting))}</span>${(meeting.tags || []).includes('demo') ? '<span class="assistant-demo">Demo</span>' : ''}</button></article>`;
  }

  function seriesCard(series) {
    return `<article class="assistant-list-item"><button type="button" class="assistant-compact-row assistant-meeting-row" data-assistant-series="${e(series.path)}"><span class="assistant-meeting-label">${e(series.title)}</span><small>${series.meeting_count || 0} meetings</small></button></article>`;
  }

  function renderSetup(content) {
    const root = state.data && state.data.root;
    const message = !state.data || !state.data.configured
      ? 'Choose the Assistant folder from Home → Admin.'
      : 'Open Home → Admin and choose an available Assistant folder.';
    content.innerHTML = `<div class="assistant-setup">
      <span class="assistant-kicker">Global vault</span>
      <h1>Assistant needs a database</h1>
      <p>${e(message)}</p>
      ${root ? `<code>${e(root)}</code>` : '<code>Home → Admin → Assistant</code>'}
    </div>`;
  }

  function otherNotes() {
    const workspaces = state.data?.workspaces || [];
    const needle = state.search.trim().toLowerCase();
    return (state.noteFiles || []).filter(file => {
      const path = String(file.path || '');
      if (file.type === 'dir' || !/\.(md|markdown|txt)$/i.test(path)) return false;
      if (path.split('/').some(part => part.startsWith('.'))) return false;
      if (/^(workspaces|projects)\/[^/]+\/(tasks|subtasks|meetings|meeting-series)(\/|$)/i.test(path)) return false;
      return !/^(AGENTS|CLAUDE|README|SKILL|workspace|project)\.md$/i.test(path.split('/').pop());
    }).map(file => {
      const workspace = workspaces.find(row => row.path && file.path.startsWith(row.path.slice(0, row.path.lastIndexOf('/') + 1)));
      return {...file, workspace: workspace?.id || '', title: file.path.split('/').pop().replace(/\.(md|markdown|txt)$/i, '').replace(/[-_]/g, ' ')};
    }).filter(note => (!state.workspace || note.workspace === state.workspace)
      && (!needle || `${note.title} ${note.path}`.toLowerCase().includes(needle)))
      .sort((a, b) => Number(b.mtime || 0) - Number(a.mtime || 0) || a.path.localeCompare(b.path));
  }

  function renderOtherNotes() {
    const rows = otherNotes();
    return `<div class="assistant-filters">
      <input type="search" id="assistantSearch" value="${e(state.search)}" placeholder="Search notes…" aria-label="Search Assistant notes">
      ${workspaceSelect(rows)}<span class="assistant-filter-count">${rows.length} note${rows.length === 1 ? '' : 's'}</span>
    </div><section class="assistant-list assistant-list-single" aria-label="Other notes">
      ${state.notesError ? `<div class="assistant-empty">${e(state.notesError)}</div>` : rows.map(note => `<article class="assistant-list-item">
        <button type="button" class="assistant-compact-row assistant-note-row" data-assistant-note="${e(note.path)}">
          <span class="assistant-row-content"><strong>${e(note.title)}</strong><small>${e(note.path)}</small></span>
        </button></article>`).join('') || '<div class="assistant-empty">No other notes yet.</div>'}
    </section>`;
  }

  function workspaceRows() {
    const workspaces = [...((state.data && state.data.workspaces) || [])];
    return workspaces.sort((left, right) => {
      const leftCount = countWhere(tasks(), task => task.workspace === left.id && needsAttention(task));
      const rightCount = countWhere(tasks(), task => task.workspace === right.id && needsAttention(task));
      return rightCount - leftCount || String(left.name || left.id).localeCompare(String(right.name || right.id));
    });
  }

  function attentionBreakdown(rows) {
    return [
      [countWhere(rows, task => task.status !== 'done' && task.priority === 'P0'), 'P0'],
      [countWhere(rows, task => task.status === 'in_progress'), 'active'],
      [countWhere(rows, task => task.status !== 'done' && hasReview(task)), 'review'],
      [countWhere(rows, isDueSoon), 'due soon'],
    ].filter(item => item[0]).map(item => `${item[0]} ${item[1]}`).join(' · ') || 'No attention items';
  }

  function labWorkspaceNav() {
    return `<nav class="assistant-lab-workspaces" aria-label="Lab workspaces">${workspaceRows().map(workspace => {
      const rows = tasks().filter(task => task.workspace === workspace.id);
      const count = countWhere(rows, needsAttention);
      return `<button type="button" class="${state.workspace === workspace.id ? 'active' : ''}" data-assistant-workspace="${e(workspace.id)}" title="${e(attentionBreakdown(rows))}">
        <span class="assistant-lab-workspace-name">${e(workspace.name || workspace.id)}</span><small>${count}</small>
      </button>`;
    }).join('')}</nav>`;
  }

  function workspaceSelect(source) {
    const workspaces = state.data && state.data.workspaces || [];
    return `<select id="assistantWorkspace" aria-label="Filter by workspace">
      <option value="">All workspaces (${source.length})</option>
      ${workspaces.map(workspace => {
        const count = countWhere(source, row => row.workspace === workspace.id);
        return `<option value="${e(workspace.id)}"${state.workspace === workspace.id ? ' selected' : ''}>${e(workspace.name || workspace.id)} (${count})</option>`;
      }).join('')}
    </select>`;
  }

  function filterBar(rows) {
    const isTasks = isTaskSection();
    const advanced = isTasks ? `
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
      ${isTasks ? '' : workspaceSelect(meetings())}${advanced}
      <span class="assistant-filter-count">${rows.length} ${isTasks ? `task${rows.length === 1 ? '' : 's'}` : state.view === 'meeting_series' ? 'series' : `meeting${rows.length === 1 ? '' : 's'}`}</span>
    </div>`;
  }

  function emptyTasks() {
    return '<div class="assistant-empty">No tasks match this view.</div>';
  }

  function renderTasks(rows) {
    const views = [['all_open', 'All open'], ['today', 'Today'], ['week', 'This week'],
      ['inbox', 'Inbox'], ['ready_to_review', 'To review'], ['waiting', 'Waiting'],
      ['recurring', 'Recurring'], ['someday', 'Someday'], ['recent', 'Completed']];
    return `${labWorkspaceNav()}<nav class="assistant-quick-views compact" aria-label="Task views">${views.map(([id, name]) =>
      `<button type="button" class="${state.view === id ? 'active' : ''}" data-assistant-view="${id}">${name}</button>`).join('')}</nav>${filterBar(rows)}
      <p class="assistant-list-order">Created date · Newest day first</p>
      <section class="assistant-list assistant-list-single assistant-task-date-list" aria-label="Tasks by creation date" data-testid="assistant-list">${dateGroups(rows, taskCard, row => taskCreatedDate(row.created), 'task') || emptyTasks()}</section>`;
  }

  function renderNotes(rows) {
    const seriesView = state.view === 'meeting_series';
    const visible = seriesView ? filteredSeries() : rows;
    return `<nav class="assistant-quick-views compact" aria-label="Note views">
      ${[['meetings', 'Meeting notes'], ['other_notes', 'Other notes'], ['meeting_series', 'Series'], ['meeting_actions', 'Open action items']].map(([id, title]) => `<button type="button" class="${state.view === id ? 'active' : ''}" data-assistant-view="${id}">${title}</button>`).join('')}
    </nav>${state.view === 'other_notes' ? renderOtherNotes() : `${filterBar(visible)}<section class="assistant-list assistant-list-single" aria-label="Meeting notes" data-testid="assistant-list">${dateGroups(sortedMeetings(visible, seriesView ? 'latest_date' : 'date'), seriesView ? seriesCard : meetingCard, row => calendarDate(row[seriesView ? 'latest_date' : 'date']), 'meeting') || '<div class="assistant-empty">No meetings match this view.</div>'}</section>`}`;
  }

  function render() {
    if (!document.body.classList.contains('assistant-active')) return;
    if (window.LAB_ASSISTANT_DOCUMENT_OPEN) return;
    syncSectionTabs();
    const content = document.getElementById('content');
    if (!content) return;
    if (!state.data || !state.data.configured || !state.data.exists) {
      renderSetup(content);
      return;
    }
    const rows = isTaskSection() ? filteredTasks() : filteredMeetings();
    const workspace = workspaceRows().find(item => item.id === state.workspace);
    const proposal = isTaskSection()
      ? `Lab workspace · ${workspace ? workspace.name || workspace.id : 'Tasks'}`
      : 'Global Assistant';
    const title = isTaskSection() ? 'Tasks' : 'Notes';
    const body = isTaskSection() ? renderTasks(rows) : renderNotes(rows);
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
    content.querySelectorAll('[data-assistant-workspace]').forEach(button => {
      button.addEventListener('click', () => selectWorkspace(button.dataset.assistantWorkspace));
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
      state.view = state.status || 'all_open';
      render();
    });
    document.getElementById('assistantPriority')?.addEventListener('change', event => {
      state.priority = event.target.value;
      state.view = state.priority === 'P0' ? 'p0' : 'all_open';
      render();
    });
    document.getElementById('assistantWorkspace')?.addEventListener('change', event => {
      state.workspace = event.target.value;
      render();
    });
    content.querySelectorAll('[data-assistant-task]').forEach(button => bindRow(button, 'task'));
    content.querySelectorAll('[data-assistant-meeting]').forEach(button => bindRow(button, 'meeting'));
    bindSeries(content);
    content.querySelectorAll('[data-assistant-note]').forEach(button => {
      button.addEventListener('click', () => {
        window.openWorkspaceDocModal(button.dataset.assistantNote, {root: state.data.root});
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

  function selectWorkspace(workspaceId) {
    if (!workspaceId || workspaceId === state.workspace) return;
    state.workspace = workspaceId;
    state.selectedTaskPath = '';
    const url = new URL(window.location);
    url.searchParams.set('view', 'assistant');
    url.searchParams.set('assistant_workspace', workspaceId);
    url.searchParams.delete('task');
    history.pushState({nav: 'assistant', assistant_workspace: workspaceId}, '', url.pathname + url.search + url.hash);
    render();
  }

  function bindRow(button, kind) {
    const attribute = kind === 'task' ? 'assistantTask' : 'assistantMeeting';
    const path = button.dataset[attribute];
    button.addEventListener('click', event => {
      if (event.target.closest('[data-assistant-nudge]')) return;
      selectEntry(kind, path, true);
      openDocumentModal(kind, path);
    });
    button.addEventListener('keydown', event => {
      if (event.target.closest('[data-assistant-nudge]')) return;
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
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
      url.searchParams.delete('series');
      if (kind === 'task') {
        url.searchParams.set('subview', 'tasks');
        if (state.workspace) url.searchParams.set('assistant_workspace', state.workspace);
        url.searchParams.delete('meeting');
        if (path) url.searchParams.set('task', path);
      } else {
        url.searchParams.set('subview', 'notes');
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
      <header class="assistant-modal-header">
        <div class="assistant-modal-heading"><span id="assistantModalKind">Assistant</span><h2 id="assistantModalTitle">Loading…</h2></div>
        <div class="assistant-modal-actions"><button type="button" id="assistantCopyRich">Copy for Google Docs</button><button type="button" id="assistantCopyPlain">Copy plain text</button><button type="button" class="assistant-modal-close" aria-label="Close Assistant document">×</button></div>
        <div class="assistant-modal-metadata" id="assistantModalMetadata"></div>
      </header>
      <div class="assistant-modal-body" id="assistantModalBody"><aside class="assistant-document-nav" id="assistantDocumentNav"></aside><main class="assistant-document-pane" id="assistantModalDocument"><div class="loading">Loading…</div></main></div>
    </section>`;
    overlay.addEventListener('click', event => {
      if (event.target === overlay) closeDocumentModal();
      else if (!event.target.closest('.assistant-metadata-more')) {
        const more = overlay.querySelector('.assistant-metadata-more');
        if (more) more.open = false;
      }
    });
    overlay.querySelector('.assistant-modal-close').addEventListener('click', closeDocumentModal);
    document.body.appendChild(overlay);
    return overlay;
  }

  function closeDocumentModal(updateHistory = true) {
    ++state.modalRequest;
    if (updateHistory) {
      const url = new URL(window.location);
      const selected = ['meeting', 'series', 'task'].some(key => url.searchParams.has(key));
      url.searchParams.delete('meeting'); url.searchParams.delete('series'); url.searchParams.delete('task');
      if (selected) history.pushState({nav:'assistant'}, '', url.pathname + url.search + url.hash);
      state.selectedMeetingPath = ''; state.selectedSeriesPath = '';
    }
    const overlay = document.getElementById('assistantDocumentModal');
    if (overlay) overlay.classList.remove('active');
  }

  async function fetchDocument(kind, path) {
    const endpoint = kind === 'task' ? '/api/assistant/task?path='
      : kind === 'subtask' ? '/api/assistant/subtask?path='
      : kind === 'series' ? '/api/assistant/meeting-series?path='
      : kind === 'content' ? '/api/assistant/meeting-content?path=' : '/api/assistant/meeting?path=';
    const response = await fetch(endpoint + encodeURIComponent(path));
    const detail = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(detail.detail || response.statusText);
    return detail;
  }

  async function openDocumentModal(kind, path, focusHeading = '') {
    const overlay = ensureModal();
    const title = document.getElementById('assistantModalTitle');
    const label = document.getElementById('assistantModalKind');
    const host = document.getElementById('assistantModalDocument');
    const nav = document.getElementById('assistantDocumentNav');
    label.textContent = kind === 'meeting' ? 'Meeting note' : 'Task documents';
    title.textContent = 'Loading…';
    document.getElementById('assistantModalMetadata').replaceChildren();
    host.innerHTML = '<div class="loading">Loading document…</div>';
    nav.innerHTML = '';
    resetCopy();
    overlay.classList.add('active');
    const request = ++state.modalRequest;
    try {
      const detail = await fetchDocument(kind, path);
      if (request !== state.modalRequest || !overlay.classList.contains('active')) return;
      if (kind === 'subtask') {
        const metadata = detail.metadata || {};
        const parent = tasks().find(task => task.workspace === (metadata.parent_workspace || metadata.workspace) && task.id === metadata.parent);
        state.modalRoot = parent ? await fetchDocument('task', parent.path) : detail;
        state.modalKind = parent ? 'task' : 'subtask';
      } else {
        state.modalRoot = detail;
        state.modalKind = kind;
      }
      if (request !== state.modalRequest || !overlay.classList.contains('active')) return;
      state.modalCurrent = detail;
      state.modalMeetingPart = 'summary';
      await renderModal(focusHeading);
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

  function metadataSelect(field, label, value, choices) {
    const options = choices.map(choice => Array.isArray(choice) ? choice : [choice, labelStatus(choice)]);
    if (value && !options.some(([key]) => key === value)) options.push([value, value]);
    return `<label class="assistant-metadata-field"><span>${e(label)}</span><select data-metadata-field="${e(field)}" aria-label="${e(label)}">${options.map(([key, title]) => `<option value="${e(key)}"${key === (value || '') ? ' selected' : ''}>${e(title)}</option>`).join('')}</select></label>`;
  }

  function metadataInput(field, label, value, type = 'text') {
    return `<label class="assistant-metadata-field"><span>${e(label)}</span><input type="${type}" data-metadata-field="${e(field)}" aria-label="${e(label)}" value="${e(value || '')}"${type === 'date' ? ' min="0001-01-01" max="9999-12-31"' : ''}></label>`;
  }

  function renderDocumentHeader(detail, kind) {
    // Related documents share their meeting's properties; original notes stay read-only.
    const record = ['content', 'meeting'].includes(kind) ? state.modalRoot : detail;
    const recordKind = kind === 'content' ? 'meeting' : kind;
    const metadata = record.metadata || {};
    const workspace = record.workspace || {};
    const task = ['task', 'subtask'].includes(recordKind);
    const bar = document.getElementById('assistantModalMetadata');
    const heading = document.getElementById('assistantModalTitle');
    heading.textContent = kind === 'content'
      ? `${metadata.title || 'Meeting'} · ${detail.format === 'text' ? 'Raw notes' : detail.metadata?.title || 'Document'}`
      : metadata.title || metadata.id || 'Document';
    heading.title = heading.textContent;
    document.getElementById('assistantModalKind').textContent = ({task:'Task', subtask:'Subtask', meeting:'Note', series:'Series', content:'Note'})[kind] || 'Document';
    const primary = task ? [
      metadataSelect('status', 'Status', metadata.status || 'inbox', state.data?.statuses?.length ? state.data.statuses : ['inbox', 'ready', 'in_progress', 'waiting', 'blocked', 'ready_to_review', 'done']),
      metadataSelect('priority', 'Priority', metadata.priority || 'P2', ['P0', 'P1', 'P2', 'P3'].map(value => [value, value])),
      metadataInput('due', 'Due', metadata.due, 'date'),
      metadataSelect('recurrence', 'Repeats', metadata.recurrence, [['', 'Never'], ['weekly', 'Weekly'], ['monthly', 'Monthly'], ['yearly', 'Yearly']]),
    ] : recordKind === 'meeting' ? [
      metadataInput('date', 'Date', metadata.date, 'date'),
      metadataSelect('series', 'Series', metadata.series, [['', 'Standalone'], ...(state.data?.meeting_series || [])
        .filter(row => row.workspace === (metadata.workspace || workspace.id || record.path.split('/')[1]))
        .map(row => [row.id, row.title])]),
    ] : [];
    const fields = [['title', 'Title'], ['tldr', 'Summary'], ...(task ? [
      ['group', 'Group'], ['owner', 'Owner'], ['scheduled', 'Planned', 'date'],
      ['defer_until', 'Deferred until', 'date'], ['waiting_on', 'Waiting on'], ['follow_up_at', 'Follow up', 'date'],
    ] : [])];
    const info = [
      ['Workspace', workspace.name || metadata.workspace], ['Vault', workspace.vault],
      ['Attendees', Array.isArray(metadata.attendees) ? metadata.attendees.join(', ') : metadata.attendees],
      ['Parent', metadata.parent], ['Created', metadata.created], ['Updated', metadata.updated],
      ['Workspace path', workspace.workspace_path],
    ].filter(([, value]) => value);
    bar.innerHTML = `${primary.join('')}<details class="assistant-metadata-more"><summary aria-label="More metadata" title="More metadata">···</summary><div class="assistant-metadata-popover">${fields.map(([field, label, type]) => metadataInput(field, label, metadata[field], type)).join('')}<dl>${info.map(([label, value]) => `<div><dt>${e(label)}</dt><dd>${e(value)}</dd></div>`).join('')}</dl></div></details><span class="assistant-metadata-message" role="status" aria-live="polite"></span>`;
    const more = bar.querySelector('details');
    more.addEventListener('toggle', () => {
      const popup = more.querySelector('.assistant-metadata-popover');
      if (more.open && window.innerWidth > 760) {
        const right = bar.getBoundingClientRect().right;
        popup.style.left = Math.min(0, right - more.getBoundingClientRect().left - popup.offsetWidth) + 'px';
      } else popup.style.left = '';
    });
    bar.querySelectorAll('[data-metadata-field]').forEach(control => {
      control.addEventListener('change', () => saveDocumentMetadata(record, control));
      if (control.type === 'date') control.addEventListener('click', () => {
        try { control.showPicker?.(); } catch (_) { /* Native keyboard editing remains available. */ }
      });
      if (control.tagName === 'INPUT' && control.type !== 'date') control.addEventListener('keydown', event => {
        if (event.key === 'Enter') { event.preventDefault(); control.blur(); }
      });
    });
  }

  async function saveDocumentMetadata(record, control) {
    if (!control.reportValidity()) return;
    const field = control.dataset.metadataField;
    const previous = record.metadata?.[field] ?? null;
    const value = control.value.trim() || null;
    if (value === previous) return;
    const request = state.modalRequest;
    const bar = document.getElementById('assistantModalMetadata');
    const message = bar.querySelector('[role="status"]');
    const controls = [...bar.querySelectorAll('input, select')];
    controls.forEach(input => { input.disabled = true; });
    message.textContent = 'Saving…';
    message.classList.remove('error');
    const host = document.getElementById('assistantModalDocument');
    const scroll = host.scrollTop;
    const moreOpen = bar.querySelector('details').open;
    try {
      const response = await fetch('/api/assistant/metadata', {
        method: 'PATCH', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: record.path, field, value, expected: previous}),
      });
      const saved = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(saved.detail || 'Could not save this change.');
      if (request !== state.modalRequest) return;
      if (state.modalRoot.path === saved.path) state.modalRoot = saved;
      else if (Array.isArray(state.modalRoot.subtasks)) state.modalRoot.subtasks = state.modalRoot.subtasks.map(child => child.path === saved.path ? {...child, ...saved.metadata} : child);
      if (state.modalCurrent.path === saved.path) state.modalCurrent = saved;
      await renderModal();
      if (request !== state.modalRequest) return;
      host.scrollTop = scroll;
      bar.querySelector('details').open = moreOpen;
      bar.querySelector('[role="status"]').textContent = 'Saved';
      bar.querySelector(`[data-metadata-field="${field}"]`)?.focus();
      refresh();
    } catch (error) {
      if (request !== state.modalRequest) return;
      control.value = previous || '';
      message.textContent = error.message || 'Could not save this change.';
      message.classList.add('error');
    } finally {
      controls.forEach(input => { input.disabled = false; });
    }
  }

  function modalDocumentButton(detail, label, kind) {
    const metadata = detail.metadata || detail || {};
    const selected = state.modalCurrent && state.modalCurrent.path === detail.path;
    return `<button type="button" class="assistant-document-nav-item${selected ? ' active' : ''}" data-assistant-modal-document="${e(detail.path)}" data-assistant-modal-kind="${e(kind)}">
      <span class="assistant-document-type">MD</span><span><strong>${e(label)}</strong><small>${e(metadata.title || metadata.id || '')}</small></span>${metadata.status ? `<i class="status-${e(metadata.status)}">${e(labelStatus(metadata.status))}</i>` : ''}
    </button>`;
  }

  async function selectModalDocument(kind, path, focusHeading = '') {
    const request = ++state.modalRequest;
    const host = document.getElementById('assistantModalDocument');
    resetCopy();
    host.innerHTML = '<div class="loading">Loading document…</div>';
    try {
      const detail = kind === 'task' && state.modalRoot && state.modalRoot.path === path
        ? state.modalRoot : await fetchDocument(kind, path);
      if (request !== state.modalRequest) return;
      state.modalCurrent = detail;
      await renderModal(focusHeading);
    } catch (error) {
      if (request === state.modalRequest) host.innerHTML = `<div class="assistant-empty">${e(error.message || error)}</div>`;
    }
  }

  async function renderModal(focusHeading = '') {
    if (['meeting', 'series'].includes(state.modalKind)) { await renderMeetingModal(); return; }
    const root = state.modalRoot || state.modalCurrent;
    const detail = state.modalCurrent || root;
    const rootMetadata = root.metadata || {};
    const title = document.getElementById('assistantModalTitle');
    const label = document.getElementById('assistantModalKind');
    const nav = document.getElementById('assistantDocumentNav');
    title.textContent = rootMetadata.title || rootMetadata.id || (state.modalKind === 'meeting' ? 'Meeting note' : 'Task');
    label.textContent = state.modalKind === 'meeting' ? 'Meeting note' : state.modalKind === 'subtask' ? 'Subtask' : 'Task documents';
    if (state.modalKind === 'task' && Array.isArray(root.subtasks)) {
      nav.innerHTML = `<div class="assistant-document-nav-label">Documents</div>${modalDocumentButton(root, 'Main task', 'task')}${root.subtasks.map(child => modalDocumentButton(child, 'Subtask', 'subtask')).join('')}`;
    } else {
      nav.innerHTML = `<div class="assistant-document-nav-label">Document</div>${modalDocumentButton(root, state.modalKind === 'meeting' ? 'Meeting note' : 'Subtask', state.modalKind)}`;
    }
    nav.querySelectorAll('[data-assistant-modal-document]').forEach(button => {
      button.addEventListener('click', () => selectModalDocument(button.dataset.assistantModalKind, button.dataset.assistantModalDocument));
    });
    const detailKind = state.modalKind === 'meeting' ? 'meeting'
      : state.modalKind === 'subtask' ? 'subtask' : (detail.path === root.path ? 'task' : 'subtask');
    await renderDocumentPane(detail, detailKind, focusHeading);
  }

  async function renderDocumentPane(detail, kind, focusHeading = '') {
    const request = state.modalRequest;
    if (typeof window.ensureMarked === 'function') await window.ensureMarked().catch(() => {});
    if (request !== state.modalRequest) return;
    const body = detail.body || '';
    const markdown = window.marked && window.DOMPurify ? window.LabMarkdown.render(body) : `<pre>${e(body)}</pre>`;
    const host = document.getElementById('assistantModalDocument');
    renderDocumentHeader(detail, kind);
    host.innerHTML = `<div class="nb-markdown assistant-markdown" id="assistantModalMarkdown">${markdown}</div>`;
    const markdownHost = document.getElementById('assistantModalMarkdown');
    rewriteImages(markdownHost, detail.path);
    addCopyButtons(markdownHost);
    resetCopy(true);
    document.getElementById('assistantCopyPlain').onclick = event => window.LabMarkdown.copy(markdownHost, {button: event.currentTarget, plainOnly: true});
    document.getElementById('assistantCopyRich').onclick = event => window.LabMarkdown.copy(markdownHost, {button: event.currentTarget});
    if (focusHeading) {
      const target = Array.from(markdownHost.querySelectorAll('h1, h2, h3'))
        .find(heading => heading.firstChild && heading.firstChild.textContent.trim() === focusHeading);
      if (target) {
        target.classList.add('assistant-content-target');
        requestAnimationFrame(() => target.scrollIntoView({block: 'start'}));
      }
    }
  }

  function resetCopy(enabled = false) {
    if (!enabled) document.getElementById('assistantModalMetadata')?.replaceChildren();
    for (const id of ['assistantCopyPlain', 'assistantCopyRich']) {
      const button = document.getElementById(id);
      if (button) { button.disabled = !enabled; button.onclick = null; }
    }
    const plain = document.getElementById('assistantCopyPlain');
    if (plain) plain.textContent = 'Copy plain text';
  }

  function bindSeries(host) {
    host.querySelectorAll('[data-assistant-series]').forEach(button => button.addEventListener('click', () => {
      const path = button.dataset.assistantSeries;
      const url = new URL(window.location);
      url.searchParams.set('view', 'assistant'); url.searchParams.set('subview', 'notes');
      url.searchParams.set('series', path); url.searchParams.delete('meeting'); url.searchParams.delete('task');
      url.searchParams.delete('assistant_workspace');
      history.pushState({nav:'assistant', series:path}, '', url.pathname + url.search + url.hash);
      state.selectedSeriesPath = path; state.selectedMeetingPath = '';
      openDocumentModal('series', path);
    }));
  }

  function meetingHistory(rows) {
    return dateGroups(sortedMeetings(rows), meetingCard, row => calendarDate(row.date), 'meeting')
      || '<p class="assistant-nav-empty">No meetings yet.</p>';
  }

  async function renderMeetingModal() {
    const root = state.modalRoot;
    const request = state.modalRequest;
    const nav = document.getElementById('assistantDocumentNav');
    const host = document.getElementById('assistantModalDocument');
    const series = state.modalKind === 'series';
    const title = series ? root.metadata.title : meetingLabel({...root.metadata, series_title: root.series?.title});
    document.getElementById('assistantModalTitle').textContent = title;
    document.getElementById('assistantModalKind').textContent = series ? 'Meeting series' : 'Meeting';
    const partButton = (part, title, subtitle = '') => `<button type="button" class="assistant-document-nav-item${state.modalMeetingPart === part ? ' active' : ''}" data-meeting-part="${e(part)}"><span class="assistant-document-type">${part.endsWith('raw.txt') ? 'TXT' : 'MD'}</span><span><strong>${e(title)}</strong><small>${e(subtitle)}</small></span></button>`;
    if (series) {
      nav.innerHTML = '<div class="assistant-document-nav-label">Meeting history</div>' + meetingHistory(root.meetings || []);
      await renderDocumentPane(root, 'series');
      if (request !== state.modalRequest) return;
      host.insertAdjacentHTML('beforeend', `<section class="assistant-series-history"><h2>Meeting history</h2>${meetingHistory(root.meetings || [])}</section>`);
    } else {
      const related = (kind, label) => {
        const rows = (root.contents || []).filter(row => row.kind === kind);
        return `<div class="assistant-document-nav-label">${label}</div>${rows.map(row => partButton(row.path, row.title)).join('') || `<p class="assistant-nav-empty">No ${label.toLowerCase()} yet.</p>`}`;
      };
      nav.innerHTML = `<div class="assistant-document-nav-label">This meeting</div>${partButton('summary', 'Summary', 'Highlights & action items')}
        ${root.raw ? partButton(root.raw.path, 'Raw notes', 'Original content') : '<p class="assistant-nav-empty">Raw notes not captured.</p>'}
        ${root.notes ? partButton('notes', 'Supporting notes') : ''}${related('question', 'Questions')}${related('document', 'Documents')}
        ${root.series ? `<div class="assistant-document-nav-label">Series</div><button class="assistant-series-link" data-assistant-series="${e(root.series.path)}">${e(root.series.title)} · All meetings</button>${meetingHistory(root.series.meetings || [])}` : '<p class="assistant-nav-empty">Standalone meeting</p>'}`;
      const part = state.modalMeetingPart;
      if (part === 'summary' || part === 'notes') {
        await renderDocumentPane({...root, metadata:{...root.metadata, title, tldr:''},
          tldr: part === 'summary' && !root.tldr ? 'No summary yet.' : '',
          body: part === 'summary' ? root.overview || '# Summary\n\nNo summary yet.' : root.notes}, 'meeting');
      } else if (state.modalCurrent.format === 'text') {
        const raw = state.modalCurrent.body || '';
        renderDocumentHeader(state.modalCurrent, 'content');
        host.innerHTML = '<pre class="assistant-raw-notes"></pre>';
        host.querySelector('pre').textContent = raw;
        resetCopy(true);
        document.getElementById('assistantCopyRich').disabled = true;
        const button = document.getElementById('assistantCopyPlain');
        button.textContent = 'Copy raw notes';
        button.onclick = async () => {
          try { await navigator.clipboard.writeText(raw); button.textContent = 'Copied'; }
          catch (_) { button.textContent = 'Copy failed'; }
        };
      } else {
        await renderDocumentPane(state.modalCurrent, 'content');
      }
      if (request !== state.modalRequest) return;
      if (root.warnings?.length) host.insertAdjacentHTML('afterbegin', `<div class="assistant-meeting-warning" role="status">${root.warnings.map(e).join('<br>')}</div>`);
      nav.querySelectorAll('[data-meeting-part]').forEach(button => button.addEventListener('click', async () => {
        const part = button.dataset.meetingPart;
        const next = ++state.modalRequest;
        resetCopy(); host.innerHTML = '<div class="loading">Loading meeting content…</div>';
        try {
          const detail = ['summary', 'notes'].includes(part) ? root : await fetchDocument('content', part);
          if (next !== state.modalRequest) return;
          state.modalCurrent = detail; state.modalMeetingPart = part;
          await renderMeetingModal();
        } catch (error) {
          if (next === state.modalRequest) host.innerHTML = `<div class="assistant-empty">${e(error.message)}</div>`;
        }
      }));
    }
    if (request !== state.modalRequest) return;
    for (const surface of [nav, host]) {
      surface.querySelectorAll('[data-assistant-meeting]').forEach(button => bindRow(button, 'meeting'));
      bindSeries(surface);
    }
  }

  function addCopyButtons(host) {
    host.querySelectorAll('h1, h2, h3').forEach(heading => {
      const headingText = heading.textContent.trim();
      const actions = document.createElement('span');
      actions.className = 'assistant-copy-actions';
      if (headingText.toLowerCase() === 'generate content') {
        const copy = document.createElement('button');
        copy.type = 'button';
        copy.className = 'primary';
        copy.textContent = 'Copy content';
        copy.title = 'Copy formatted content and embedded images for email or another app';
        copy.addEventListener('click', () => window.LabMarkdown.copy(host, {heading, includeHeading: false, button: copy}));
        const plain = document.createElement('button');
        plain.type = 'button';
        plain.textContent = 'Plain text';
        plain.title = 'Copy expanded content as plain text';
        plain.addEventListener('click', () => window.LabMarkdown.copy(host, {heading, includeHeading: false, button: plain, plainOnly: true}));
        actions.append(copy, plain);
        heading.appendChild(actions);
        return;
      }
      const slack = document.createElement('button');
      slack.type = 'button';
      slack.textContent = 'Slack';
      slack.title = 'Copy expanded section text';
      slack.addEventListener('click', () => window.LabMarkdown.copy(host, {heading, button: slack, plainOnly: true}));
      const gdoc = document.createElement('button');
      gdoc.type = 'button';
      gdoc.textContent = 'GDoc';
      gdoc.title = 'Copy this section as formatted rich text';
      gdoc.addEventListener('click', () => window.LabMarkdown.copy(host, {heading, button: gdoc}));
      actions.append(slack, gdoc);
      heading.appendChild(actions);
    });
  }

  async function refresh(options = {}) {
    const section = state.section;
    const request = ++state.request;
    try {
      const response = await fetch('/api/assistant');
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || response.statusText);
      if (request !== state.request || !document.body.classList.contains('assistant-active')) return;
      state.data = data;
      if (section === 'notes' && data.exists && data.root) {
        try {
          const filesResponse = await fetch('/api/workspace-files?path=' + encodeURIComponent(data.root));
          if (!filesResponse.ok) throw new Error('Could not load other notes. Use Refresh to try again.');
          const files = await filesResponse.json();
          if (request !== state.request || !document.body.classList.contains('assistant-active')) return;
          state.noteFiles = Array.isArray(files) ? files : [];
          state.notesError = '';
        } catch (error) {
          if (request !== state.request) return;
          state.notesError = error.message || 'Could not load other notes.';
        }
      }
      if (request !== state.request || !document.body.classList.contains('assistant-active')) return;
      if (section === state.section) {
        if (options.task !== undefined) state.selectedTaskPath = options.task || '';
        if (options.meeting !== undefined) state.selectedMeetingPath = options.meeting || '';
        if (options.series !== undefined) state.selectedSeriesPath = options.series || '';
        if (options.workspace !== undefined) state.workspace = options.workspace || '';
        const selected = isTaskSection() && options.task ? tasks().find(task => task.path === options.task) : null;
        if (selected) state.workspace = selected.workspace;
      }
      const available = workspaceRows();
      if (isTaskSection() && !available.some(workspace => workspace.id === state.workspace)) {
        state.workspace = available.length ? available[0].id : '';
      }
      render();
      if (options.open && section === state.section) {
        if (isTaskSection() && state.selectedTaskPath) await openDocumentModal('task', state.selectedTaskPath);
        else if (state.selectedMeetingPath) await openDocumentModal('meeting', state.selectedMeetingPath);
        else if (state.selectedSeriesPath) await openDocumentModal('series', state.selectedSeriesPath);
      }
    } catch (error) {
      const content = document.getElementById('content');
      if (content && request === state.request) content.innerHTML = `<div class="assistant-setup"><h1>Assistant</h1><p>${e(error.message || error)}</p></div>`;
    }
  }

  function init(initial = '') {
    closeDocumentModal(false);
    const options = typeof initial === 'object' && initial !== null ? initial : {task: initial};
    state.section = ['notes', 'meetings'].includes(options.section) ? 'notes' : 'tasks';
    state.selectedTaskPath = options.task || '';
    state.selectedSubtaskPath = '';
    state.selectedMeetingPath = options.meeting || '';
    state.selectedSeriesPath = options.series || '';
    state.view = isTaskSection() ? 'all_open' : 'meetings';
    state.status = '';
    state.priority = '';
    state.workspace = isTaskSection() ? options.workspace || new URL(window.location).searchParams.get('assistant_workspace') || '' : '';
    state.search = '';
    refresh({task: state.selectedTaskPath, meeting: state.selectedMeetingPath, series: state.selectedSeriesPath, workspace: state.workspace, open: true});
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
      const more = document.querySelector('#assistantModalMetadata details[open]');
      if (more) { more.open = false; more.querySelector('summary').focus(); }
      else closeDocumentModal();
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
