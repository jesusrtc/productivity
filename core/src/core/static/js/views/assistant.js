(function () {
  'use strict';

  const state = {
    data: null,
    section: 'documents',
    noteFiles: [],
    notesError: '',
    selectedTaskPath: '',
    selectedSubtaskPath: '',
    selectedMeetingPath: '',
    view: 'dashboard',
    seriesFilters: new Map(),
    status: '',
    priority: '',
    workspace: '',
    project: '',
    search: '',
    selectedSeriesPath: '',
    modalMeetingPart: 'summary',
    modalRoot: null,
    modalCurrent: null,
    modalKind: '',
    inlineHost: null,
    inlinePending: false,
    inlineSidebarCollapsed: false,
    documentClickTimer: null,
    request: 0,
    modalRequest: 0,
    poll: null,
    searchTimer: null,
    renderedList: '',
    paneCache: new Map(),
    currentPane: null,
    modalIndex: false,
    headingMenu: null,
    noteDrafts: new Map(),
    tabActivity: null,
    tabActivityTimer: null,
  };

  const e = value => String(value == null ? '' : value).replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);

  function labelStatus(value) {
    return ({not_started:'Not started', in_progress:'In progress', done:'Completed', skipped:'Skipped', cancelled:'Cancelled'})[value] || String(value || 'inbox').replace(/_/g, ' ');
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
    if (Array.isArray(state.data?.documents)) return state.data.documents.filter(row => row.tracked);
    return state.data && Array.isArray(state.data.tasks) ? state.data.tasks : [];
  }

  function isTaskSection() {
    return state.section !== 'notes';
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

  function filteredTasks({workspace = state.workspace} = {}) {
    const needle = state.search.trim().toLowerCase();
    return tasks().filter(task => {
      if (state.view === 'recent' && !['done','skipped'].includes(task.status)) return false;
      if (state.view === 'cancelled' && task.status !== 'cancelled') return false;
      if (!['recent','cancelled'].includes(state.view) && ['done','skipped','cancelled'].includes(task.status)) return false;
      const today = localToday();
      const children = taskChildren(task);
      const pending = item => {
        if (['done','skipped','cancelled'].includes(item.status)) return false;
        const parent = item.parent && children.find(row => row.id === item.parent.id);
        return !parent || pending(parent);
      };
      const planned = Array.isArray(task.task_items) ? pendingWork(task) : [task, ...children.filter(pending)];
      const scheduledBy = limit => planned.some(item =>
        [item.scheduled,item.due].some(date => calendarDate(date) && date <= limit)
        && !(calendarDate(item.defer_until) && item.defer_until > today && !(calendarDate(item.due) && item.due <= today)));
      if (state.view === 'today' && !scheduledBy(today)) return false;
      if (state.view === 'week' && !scheduledBy(weekEnd())) return false;
      if (!task.task_items && ['today', 'week'].includes(state.view) && calendarDate(task.defer_until) && task.defer_until > today && !(calendarDate(task.due) && task.due <= today)) return false;
      if (state.view === 'recurring' && !(task.task_items ? planned.some(item => item.recurrence) : task.recurrence)) return false;
      if (state.view === 'someday' && !planned.some(item => item.priority === 'P3' || calendarDate(item.defer_until) && item.defer_until > today)) return false;
      if (state.view === 'p0' && task.priority !== 'P0') return false;
      if (state.view === 'in_progress' && !(task.task_items ? planned.some(item => item.status === 'in_progress') : task.status === 'in_progress')) return false;
      if (state.view === 'ready_to_review' && !hasReview(task)) return false;
      if (state.view === 'waiting' && task.status !== 'waiting') return false;
      if (state.view === 'inbox' && !['inbox','not_started'].includes(task.status)) return false;
      if (state.view === 'focus' && task.status === 'done') return false;
      if (state.view === 'all_open' && task.status === 'done') return false;
      if (state.status && task.status !== state.status) return false;
      if (state.priority && task.priority !== state.priority) return false;
      if (workspace && task.workspace !== workspace) return false;
      if (state.project && task.project !== state.project) return false;
      if (needle) {
        const haystack = [task.title, task.tldr, task.summary, task.group, task.workspace_name, task.workspace, task.vault, task.search_text]
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
      if (state.project && meeting.project !== state.project) return false;
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
      button.classList.toggle('active', button.dataset.assistantSection === (state.data?.documents ? 'documents' : state.section));
    });
  }

  let taskLoader;
  async function ensureDocumentTasks() {
    if (window.AssistantTasks) return;
    taskLoader ||= new Promise((resolve,reject) => {
      const script=document.createElement('script');script.src='/static/js/views/assistant-tasks.js';
      script.onload=resolve;script.onerror=()=>{taskLoader=null;script.remove();reject(new Error('Could not load document tasks. Refresh to retry.'))};document.head.appendChild(script);
    });
    await taskLoader;
  }

  function setSection(section, options = {}) {
    if (state.data?.documents || section === 'documents') {
      closeDocumentModal(false);
      state.section = 'documents';
      state.view = section === 'tasks' ? 'all_open' : section === 'notes' ? 'documents' : 'dashboard';
      state.status = ''; state.priority = '';
      if (!options.history) {
        const url = new URL(window.location);
        url.searchParams.set('view', 'assistant'); url.searchParams.set('subview', 'documents');
        for (const field of ['task','note','meeting','series']) url.searchParams.delete(field);
        history.pushState({nav:'assistant',subview:'documents'}, '', url.pathname + url.search + url.hash);
      }
      window.assistantSectionShell?.('documents');
      render();
      void refresh();
      return;
    }
    const nextSection = ['notes', 'meetings'].includes(section) ? 'notes' : 'tasks';
    if (nextSection === state.section && !window.LAB_ASSISTANT_DOCUMENT_OPEN) {
      if (document.getElementById('assistantDocumentModal')?.classList.contains('active')) closeDocumentModal();
      return;
    }
    closeDocumentModal(false);
    const previousSection = state.section;
    state.section = ['notes', 'meetings'].includes(section) ? 'notes' : 'tasks';
    if (state.section !== previousSection) { state.search = ''; clearTimeout(state.searchTimer); }
    if (state.section !== previousSection) state.workspace = '';
    state.view = isTaskSection() ? 'all_open' : 'meetings';
    state.status = '';
    state.priority = '';

    if (!options.history) {
      const url = new URL(window.location);
      url.searchParams.set('view', 'assistant');
      if (state.section === 'notes') { url.searchParams.set('subview', 'notes'); url.searchParams.delete('assistant_workspace'); }
      else if (state.section === 'tasks') {
        url.searchParams.set('subview', 'tasks');
        if (state.workspace) url.searchParams.set('assistant_workspace', state.workspace);
        else url.searchParams.delete('assistant_workspace');
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

  function progressLabel(done, total, noun = 'subtabs') {
    if (!total) return '';
    return `${done}/${total} ${noun}`;
  }

  function taskCard(task) {
    const selected = false; // Applied in place by selectEntry; excluded from list refresh comparison.
    const overdue = task.status !== 'done' && calendarDate(task.due) && task.due < localToday();
    const due = task.due ? `<span class="assistant-task-due${overdue ? ' overdue' : ''}">${overdue ? 'Overdue' : 'Due'} ${e(displayDate(task.due))}</span>` : '';
    const workspace = task.workspace_name || state.data?.workspaces?.find(row => row.id === task.workspace)?.name || task.workspace || '';
    const progress = progressLabel(task.subtasks_done, task.subtasks_total);
    const reviews = reviewCount(task);
    const tldr = task.tldr || task.summary || 'No TLDR yet.';
    return `<article class="assistant-list-item${selected ? ' selected' : ''}" data-assistant-entry-wrap="${e(task.path)}">
      <div role="button" tabindex="0" class="assistant-compact-row assistant-task-row" data-assistant-task="${e(task.path)}" data-testid="assistant-task-row" aria-label="Open ${e(task.title)}">

        <span class="assistant-row-content">
          <span class="assistant-row-title"><span class="assistant-priority ${e(String(task.priority || '').toLowerCase())}">${e(task.priority || 'P2')}</span><strong>${e(task.title)}</strong></span>
          <span class="assistant-row-tldr"><b>TLDR</b>${e(tldr)}</span>
        </span>
        <span class="assistant-row-meta">${workspace ? `<span class="assistant-task-workspace-label" title="Workspace: ${e(workspace)}">${e(workspace)}</span>` : ''}${task.group ? `<span class="assistant-task-group-label" title="Workstream: ${e(task.group)}">${e(task.group)}</span>` : ''}${task.scheduled ? `<span class="assistant-task-due">Planned ${e(displayDate(task.scheduled))}</span>` : ''}${task.defer_until ? `<span class="assistant-task-due">Later · ${e(displayDate(task.defer_until))}</span>` : ''}${task.source === 'demo' ? '<span class="assistant-demo">Demo</span>' : ''}${reviews ? `<span class="assistant-review-count">${reviews} to review</span>` : ''}${progress ? `<span class="assistant-progress-label">${e(progress)}</span>` : ''}<span class="assistant-status status-${e(task.status || 'inbox')}">${e(labelStatus(task.status))}</span>${task.status === 'waiting' ? `<button type="button" class="assistant-nudge" data-assistant-nudge="${e(task.path)}">Nudge</button>` : ''}${due}</span>
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
    if (state.data?.schema === 2) return (state.data.notes || []).filter(note =>
      (!state.workspace || note.workspace === state.workspace) && (!state.project || note.project === state.project)
      && (!needle || `${note.title} ${note.tldr || ''} ${note.search_text || ''} ${note.path}`.toLowerCase().includes(needle)));
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
      && (!needle || `${note.title} ${note.tldr || ''} ${note.search_text || ''} ${note.path}`.toLowerCase().includes(needle)))
      .sort((a, b) => Number(b.mtime || 0) - Number(a.mtime || 0) || a.path.localeCompare(b.path));
  }

  function renderOtherNotes() {
    const rows = otherNotes();
    return `<div class="assistant-filters">
      <input type="search" id="assistantSearch" value="${e(state.search)}" placeholder="Search notes…" aria-label="Search Assistant notes">
      ${workspaceSelect(rows)}${projectSelect()}<span class="assistant-filter-count">${rows.length} note${rows.length === 1 ? '' : 's'}</span>
    </div><section class="assistant-list assistant-list-single" aria-label="Other notes">
      ${state.notesError ? `<div class="assistant-empty">${e(state.notesError)}</div>` : rows.map(note => `<article class="assistant-list-item">
        <button type="button" class="assistant-compact-row assistant-note-row" data-assistant-note="${e(note.path)}">
          <span class="assistant-row-content"><strong>${e(note.title)}</strong><small>${e(note.path)}</small></span>
        </button></article>`).join('') || '<div class="assistant-empty">No other notes yet.</div>'}
    </section>`;
  }

  function workspaceRows() {
    return [...(state.data?.workspaces || [])].sort((left, right) =>
      String(left.name || left.id).localeCompare(String(right.name || right.id)));
  }

  function workspaceSelect(source) {
    const workspaces = workspaceRows();
    return `<select id="assistantWorkspace" aria-label="Filter by workspace">
      <option value="">All workspaces (${source.length})</option>
      ${workspaces.map(workspace => {
        const count = countWhere(source, row => row.workspace === workspace.id);
        return `<option value="${e(workspace.id)}"${state.workspace === workspace.id ? ' selected' : ''}>${e(workspace.name || workspace.id)} (${count})</option>`;
      }).join('')}
    </select>`;
  }

  function projectSelect() {
    if (state.data?.schema !== 2) return '';
    return `<select id="assistantProject" aria-label="Filter by project"><option value="">All projects</option>${(state.data.projects || []).map(row => `<option value="${e(row.id)}"${state.project === row.id ? ' selected' : ''}>${e(row.title)}</option>`).join('')}</select>`;
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
      ${workspaceSelect(isTasks ? filteredTasks({workspace: ''}) : meetings())}${projectSelect()}${advanced}
      <span class="assistant-filter-count">${rows.length} ${isTasks ? `task${rows.length === 1 ? '' : 's'}` : state.view === 'meeting_series' ? 'series' : `meeting${rows.length === 1 ? '' : 's'}`}</span>
    </div>`;
  }

  function emptyTasks() {
    return '<div class="assistant-empty">No tasks match this view.</div>';
  }

  function renderTasks(rows) {
    const workflowViews = state.data?.statuses?.includes('not_started')
      ? [['inbox', 'Not started'], ['in_progress','In progress']]
      : [['inbox', 'Inbox'], ['ready_to_review','To review'], ['waiting','Waiting']];
    const views = [['all_open', 'All open'], ['today', 'Today'], ['week', 'This week'],
      ...workflowViews,
      ['recurring', 'Recurring'], ['someday', 'Someday'], ['recent', 'Completed'], ['cancelled', 'Cancelled']];
    return `<nav class="assistant-quick-views compact" aria-label="Task views">${views.map(([id, name]) =>
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

  function pendingWork(row) {
    if (Array.isArray(row.task_items)) return row.task_items.filter(task => !['done','skipped','cancelled'].includes(task.status));
    if (!row.tracked || ['done','skipped','cancelled'].includes(row.status)) return [];
    const children = taskChildren(row);
    const pending = (item, seen = new Set()) => {
      if (item.done || ['done','skipped','cancelled'].includes(item.status) || seen.has(item)) return false;
      seen.add(item);
      const parent = item.parent && children.find(child => child.id === item.parent.id);
      return !parent || pending(parent, seen);
    };
    return [row, ...children.filter(item => pending(item))];
  }

  function seriesFor(row, all = state.data.documents) {
    return row.note_type === 'series' ? row : all.find(series => series.note_type === 'series'
      && (row.series_path ? row.series_path === series.path : row.series === series.id));
  }

  function collapseSeries(rows, all = state.data.documents) {
    const seen = new Set();
    return rows.flatMap(row => {
      const series = seriesFor(row, all);
      const key = series ? 'series:' + series.id : row.path;
      if (seen.has(key)) return [];
      seen.add(key);
      if (!series) return [{...row, displayKey:key}];
      const members = all.filter(item => item.path !== series.path && seriesFor(item, all)?.id === series.id)
        .sort((a,b) => calendarDate(b.date).localeCompare(calendarDate(a.date))
          || String(b.created || '').localeCompare(String(a.created || '')) || a.path.localeCompare(b.path));
      const latest = members[0] || series;
      return [{...latest, displayKey:key, displaySeries:series, seriesMembers:members}];
    });
  }

  function documentStarred(row) {
    const series = seriesFor(row);
    return series ? series.starred === true || state.data.documents.some(item => item.starred === true
      && (item.series_path ? item.series_path === series.path : item.series === series.id)) : row.starred === true;
  }

  function equalAttribute(a, b) {
    if (a === b) return true;
    if (!a || !b || typeof a !== 'object' || typeof b !== 'object' || Array.isArray(a) !== Array.isArray(b)) return false;
    const keys = Object.keys(a);
    return keys.length === Object.keys(b).length && keys.every(key => Object.prototype.hasOwnProperty.call(b,key) && equalAttribute(a[key],b[key]));
  }

  function matchesAttribute(row, condition) {
    const candidates = condition.scope === 'any_tab' ? [row.attributes,...(row.tab_attributes || [])] : [row.attributes];
    return candidates.some(raw => {
      const attributes = raw || {};
      const present = Object.prototype.hasOwnProperty.call(attributes,condition.name);
      if ('exists' in condition) return present === condition.exists;
      if (!present) return false;
      const value = attributes[condition.name];
      if ('equals' in condition) return equalAttribute(value,condition.equals);
      return Array.isArray(value) ? value.some(item => equalAttribute(item,condition.contains))
        : typeof value === 'string' && typeof condition.contains === 'string' && value.includes(condition.contains);
    });
  }

  function sqlLike(value, pattern) {
    const text = Array.from(value), query = Array.from(pattern);
    let i = 0, j = 0, star = -1, start = 0;
    while (i < text.length) {
      if (j < query.length && query[j] !== '%' && (query[j] === '_' || query[j] === text[i])) { i++; j++; }
      else if (query[j] === '%') { star = j++; start = i; }
      else if (star >= 0) { j = star + 1; i = ++start; }
      else return false;
    }
    while (query[j] === '%') j++;
    return j === query.length;
  }

  function matchesQuery(row, condition) {
    const field = condition.field;
    let values;
    if (field.scope === 'builtin') {
      values = field.name === 'starred' ? [documentStarred(row)]
        : field.name === 'due' ? pendingWork(row).map(item => calendarDate(item.due) || undefined)
        : field.name === 'priority' ? pendingWork(row).map(item => item.priority)
        : [row[field.name]];
    } else {
      const candidates = field.scope === 'any_tab' ? [row.attributes,...(row.tab_attributes || [])] : [row.attributes];
      values = candidates.map(item => item && Object.prototype.hasOwnProperty.call(item,field.name) ? item[field.name] : undefined);
    }
    if (!values.length) values = [undefined];
    const valueOf = operand => {
      if ('today' in operand) {
        const day = new Date(); day.setDate(day.getDate() + operand.today);
        return localToday(day);
      }
      return 'json' in operand ? operand.json : operand.literal;
    };
    const compare = (left, operand, op) => {
      const right = valueOf(operand);
      if (left === undefined || left === null && !('json' in operand) || right === null && !('json' in operand)) return null;
      if (op === 'eq') return equalAttribute(left,right);
      if (op === 'ne') return !equalAttribute(left,right);
      if (op === 'contains') return Array.isArray(left) ? left.some(item => equalAttribute(item,right))
        : typeof left === 'string' && typeof right === 'string' && left.includes(right);
      if (op === 'like') {
        return typeof left === 'string' && sqlLike(left,right);
      }
      if (!['string','number'].includes(typeof left) || typeof left !== typeof right) return false;
      return op === 'lt' ? left < right : op === 'le' ? left <= right : op === 'gt' ? left > right : left >= right;
    };
    const any = results => results.some(value => value === true) ? true : results.some(value => value === null) ? null : false;
    const all = results => results.some(value => value === false) ? false : results.some(value => value === null) ? null : true;
    let result = any(values.map(value => {
      const op = condition.op;
      if (op === 'is_missing') return value === undefined;
      if (op === 'is_not_missing') return value !== undefined;
      if (op === 'is_null') return value == null;
      if (op === 'is_not_null') return value != null;
      if (op === 'in') return any(condition.values.map(operand => compare(value,operand,'eq')));
      if (op === 'between') return all([compare(value,condition.value,'ge'),compare(value,condition.upper,'le')]);
      return compare(value,condition.value,op);
    }));
    return condition.negate && result !== null ? !result : result;
  }

  function dashboardMatches(row, section) {
    const open = pendingWork(row);
    const series = seriesFor(row);
    const starred = documentStarred(row);
    const sources = {active:row.keep_in_documents || starred || open.length > 0, all:true,
      open:open.length > 0, documents:row.keep_in_documents, starred,
      completed:row.tracked && ['done','skipped'].includes(row.status), cancelled:row.tracked && row.status === 'cancelled'};
    const matches = condition => {
      if (!condition) return false;
      if (condition.and) { const values = condition.and.map(matches); return values.includes(false) ? false : values.includes(null) ? null : true; }
      if (condition.or) { const values = condition.or.map(matches); return values.includes(true) ? true : values.includes(null) ? null : false; }
      if (condition.not) { const result = matches(condition.not); return result === null ? null : !result; }
      if ('constant' in condition) return condition.constant;
      if ('compare' in condition) return matchesQuery(row,condition.compare);
      if ('attribute' in condition) return matchesAttribute(row,condition.attribute);
      if ('source' in condition) return Boolean(sources[condition.source]);
      if ('kind' in condition) return condition.kind === 'recurring' ? Boolean(series)
        : condition.kind === 'meeting' ? row.note_type === 'meeting'
        : condition.kind === 'task' ? row.tracked : !series && row.note_type !== 'meeting' && row.type !== 'task';
      if ('status' in condition) return row.status === condition.status;
      if ('starred' in condition) return starred === condition.starred;
      if ('workspace' in condition) return row.workspace === condition.workspace;
      if ('project' in condition) return row.project === condition.project;
      if ('search' in condition) return [row.title,row.summary,row.search_text,row.series_title,series?.title].join(' ').toLowerCase().includes(condition.search.trim().toLowerCase());
      if ('priority' in condition) return open.some(item => condition.priority.includes(item.priority));
      if ('due' in condition) {
        const end = new Date(); end.setDate(end.getDate() + condition.due.within_days);
        const limit = localToday(end), today = localToday();
        return open.some(item => calendarDate(item.due) && item.due <= limit && (condition.due.include_overdue || item.due >= today));
      }
      return false;
    };
    return matches(section.filter || state.data.dashboard?.compiled_filters?.[section.id]) === true;
  }

  function dashboardSections() {
    const scope = filteredDocuments();
    return [...(state.data.dashboard?.sections || [])].sort((a,b) => a.position - b.position || a.id.localeCompare(b.id)).map(section => {
      const matches = collapseSeries(scope.filter(row => dashboardMatches(row, section)));
      const work = row => (row.seriesMembers ? [row.displaySeries,...row.seriesMembers] : [row]).flatMap(pendingWork);
      const due = row => work(row).map(item => calendarDate(item.due)).filter(Boolean).sort()[0] || '9999';
      const priority = row => work(row).map(item => item.priority || 'P2').sort()[0] || 'P9';
      const name = row => row.displaySeries?.title || row.title;
      matches.sort((a,b) => (section.sort === 'title' ? name(a).localeCompare(name(b))
        : section.sort === 'due' ? due(a).localeCompare(due(b))
        : section.sort === 'priority' ? priority(a).localeCompare(priority(b))
        : String(b.date || b.created || '').localeCompare(String(a.date || a.created || ''))) || name(a).localeCompare(name(b)));
      const rows = section.limit ? matches.slice(0,section.limit) : matches;
      return {...section,rows,total:matches.length};
    });
  }

  function renderDashboard(sections) {
    return `<div class="assistant-dashboard-tools"><p>Each section shows all matching items independently. Series appear once per section and open at the latest note.</p><button type="button" data-dashboard-add>+ Add section</button></div>
      <div class="assistant-dashboard" data-testid="assistant-list">${sections.map(section => `<section class="assistant-dashboard-section" data-dashboard-section="${e(section.id)}" aria-label="${e(section.title)}">
        <header><div><h2>${e(section.title)} <small>${section.rows.length}</small></h2></div><div class="assistant-section-actions">
          <button type="button" data-dashboard-edit="${e(section.id)}">Show filter</button></div></header>
        <div class="assistant-list assistant-list-single">${section.rows.map(row => documentCard(row,section.id)).join('') || '<div class="assistant-empty">No matching items.</div>'}</div>
        ${section.total > section.rows.length ? `<p class="assistant-section-overflow">${section.total - section.rows.length} more match. Use Show filter to change the JSON item limit.</p>` : ''}
      </section>`).join('') || '<div class="assistant-empty">Add a section and choose what you want to see here.</div>'}</div>`;
  }

  async function saveDashboard(sections, expected) {
    const response = await fetch('/api/assistant/dashboard', {method:'PUT', headers:{'Content-Type':'application/json'},body:JSON.stringify({sections,expected})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Could not save dashboard');
    ++state.request; // Ignore a poll that began before this saved layout.
    state.data.dashboard = result;
    render();
  }

  function formatSectionJson(value, depth = 0) {
    const compact = item => Array.isArray(item) ? '[' + item.map(compact).join(', ') + ']'
      : item && typeof item === 'object' ? '{ ' + Object.entries(item).map(([key,child]) => JSON.stringify(key) + ': ' + compact(child)).join(', ') + ' }'
      : JSON.stringify(item);
    const indent = '  '.repeat(depth), next = indent + '  ';
    if (!value || typeof value !== 'object') return JSON.stringify(value);
    if (Array.isArray(value)) return value.some(item => item && typeof item === 'object')
      ? '[\n' + value.map(item => next + formatSectionJson(item,depth+1)).join(',\n') + '\n' + indent + ']'
      : compact(value);
    const short = compact(value);
    if (depth > 0 && !('and' in value || 'or' in value || 'filter' in value) && short.length <= 100) return short;
    return '{\n' + Object.entries(value).map(([key,item]) => next + JSON.stringify(key) + ': ' + formatSectionJson(item,depth+1)).join(',\n') + '\n' + indent + '}';
  }

  function editDashboardSection(id = '') {
    if (document.getElementById('assistantSectionEditor')) return;
    const config = state.data.dashboard;
    if (!config?.section_template) { window.alert('Refresh to load dashboard settings.'); return; }
    const sections = structuredClone(config.sections);
    const current = id ? sections.find(row => row.id === id) : {
      ...config.section_template,
      id:'section-' + crypto.randomUUID(),
      position:Math.min(1000000,Math.max(-10,...sections.map(row => row.position)) + 10),
    };
    if (!current) return;
    const dialog = document.createElement('dialog');
    dialog.id = 'assistantSectionEditor'; dialog.className = 'assistant-section-editor';
    dialog.setAttribute('aria-labelledby', 'assistantSectionTitle');
    dialog.innerHTML = `<form><h2 id="assistantSectionTitle">${id ? e(current.title) : 'Add section'}</h2>
      <p class="assistant-json-help">Write a SQL-style condition in <code>where</code>. Use <code>AND</code>, <code>OR</code>, <code>NOT</code>, and parentheses. Lower <code>position</code> values appear first.</p>
      <details class="assistant-json-help"><summary>Filter examples</summary><p><code>starred = true</code><br><code>source = 'open' AND (priority = 'P1' OR due &lt;= TODAY + 2)</code><br><code>is_RFC = true OR is_investigation = true</code></p><p>Also supports <code>IN</code>, <code>BETWEEN</code>, <code>LIKE</code>, <code>CONTAINS</code>, <code>IS NULL</code>, and <code>IS MISSING</code>. Use <code>any_tab.is_RFC = true</code> to include subtabs. Attribute names are case-sensitive.</p></details>
      <label for="assistantSectionJson">Section JSON</label><textarea id="assistantSectionJson" name="json" spellcheck="false" autocomplete="off" autocapitalize="off" aria-describedby="assistantSectionError" required></textarea>
      <p id="assistantSectionError" class="assistant-section-error" role="alert"></p><footer>${id ? '<button type="button" data-section-remove>Remove section</button>' : ''}<span></span><button type="button" data-section-cancel>Cancel</button><button type="submit">Save JSON</button></footer></form>`;
    const textarea = dialog.querySelector('textarea');
    textarea.value = formatSectionJson(current);
    document.body.append(dialog);
    dialog.addEventListener('close', () => dialog.remove());
    dialog.querySelector('[data-section-cancel]').addEventListener('click', () => dialog.close());
    const form = dialog.querySelector('form');
    const errorMessage = dialog.querySelector('[role="alert"]');
    const save = async next => {
      errorMessage.textContent = '';
      form.querySelectorAll('button').forEach(button => { button.disabled = true; });
      try { await saveDashboard(next,config.revision); dialog.close(); }
      catch (error) { errorMessage.textContent = error.message; }
      finally { form.querySelectorAll('button').forEach(button => { button.disabled = false; }); }
    };
    dialog.querySelector('[data-section-remove]')?.addEventListener('click', () => save(sections.filter(row => row.id !== id)));
    textarea.addEventListener('input', () => { errorMessage.textContent = ''; textarea.removeAttribute('aria-invalid'); });
    form.addEventListener('submit', event => {
      event.preventDefault();
      let row;
      try {
        row = JSON.parse(textarea.value);
        if (!row || Array.isArray(row) || typeof row !== 'object') throw new Error('Use one JSON object for this section.');
      } catch (error) {
        errorMessage.textContent = 'Invalid JSON: ' + error.message;
        textarea.setAttribute('aria-invalid','true'); textarea.focus(); return;
      }
      save(id ? sections.map(item => item.id === id ? row : item) : [...sections,row]);
    });
    dialog.showModal();
  }

  function bindDashboard(host) {
    host.querySelector('[data-dashboard-add]')?.addEventListener('click', () => editDashboardSection());
    host.querySelectorAll('[data-dashboard-edit]').forEach(button => button.addEventListener('click', () => editDashboardSection(button.dataset.dashboardEdit)));
  }

  function documentIcon(row) {
    const recurring = row.displaySeries || row.note_type === 'series' || row.series || row.note_type === 'meeting' && row.recurrence === 'weekly';
    const kind = recurring ? 'recurring' : row.note_type === 'meeting' ? 'meeting' : row.type === 'task' && !row.task_format ? 'task' : 'note';
    const paths = {
      note:'<path d="M14 2H5v20h14V7l-5-5Zm0 0v6h5M8 12h8M8 16h6"/>',
      task:'<rect x="3" y="3" width="18" height="18" rx="3"/><path d="m7 12 3 3 7-7"/>',
      meeting:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 2v6M17 2v6M3 11h18M8 15h3v3H8z"/>',
      recurring:'<path d="M21 10V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M7 2v6M17 2v6M3 11h7M12 17a5 5 0 0 1 8-4l2 2m0-4v4h-4M22 18a5 5 0 0 1-8 4l-2-2m0 4v-4h4"/>',
    };
    const label = {note:'Note',task:'Task',meeting:'Meeting',recurring:'Recurring meeting'}[kind];
    return `<svg class="assistant-document-icon" data-document-icon="${kind}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" role="img" aria-label="${label}"><title>${label}</title>${paths[kind]}</svg>`;
  }

  function documentKind(row) {
    return row.kind || (['meeting','series'].includes(row.note_type) ? row.note_type : row.type === 'task' ? 'task' : 'note');
  }

  function filteredDocuments() {
    const special = ['dashboard','all','documents','starred','meetings','meeting_series','other_notes'];
    if (!special.includes(state.view)) return filteredTasks();
    const needle = state.search.trim().toLowerCase();
    return state.data.documents.filter(row => {
      if (state.workspace && row.workspace !== state.workspace || state.project && row.project !== state.project) return false;
      if (state.status && row.status !== state.status || state.priority && row.priority !== state.priority) return false;
      if (needle && ![row.title,row.summary,row.search_text,row.series_title,row.workspace_name].join(' ').toLowerCase().includes(needle)) return false;
      if (state.view === 'dashboard') return true;
      if (state.view === 'starred') return documentStarred(row);
      if (state.view === 'meetings') return row.note_type === 'meeting';
      if (state.view === 'meeting_series') return row.note_type === 'series';
      if (['documents','other_notes'].includes(state.view)) return row.keep_in_documents;
      return row.keep_in_documents || row.starred || row.tracked && !['done','skipped','cancelled'].includes(row.status);
    });
  }

  function starButton(row, label = '') {
    const target = label || (row.note_type === 'series' ? 'series' : 'document');
    return `<button type="button" class="assistant-star${row.starred ? ' is-starred' : ''}" data-star-path="${e(row.path)}" aria-pressed="${row.starred === true}" aria-label="${row.starred ? 'Unstar' : 'Star'} ${e(target)}" title="${row.starred ? 'Unstar' : 'Star'} ${e(target)}">${row.starred ? '★' : '☆'}</button>`;
  }

  function seriesStarControl(row, scope) {
    const series = row.displaySeries;
    const starredNotes = row.seriesMembers.filter(note => note.starred).length;
    const starred = series.starred === true || starredNotes > 0;
    const label = [series.starred ? 'Series starred' : '',starredNotes ? `${starredNotes} starred note${starredNotes === 1 ? '' : 's'}` : ''].filter(Boolean).join(' · ') || 'Not starred';
    const menuId = 'assistantStars-' + encodeURIComponent(JSON.stringify([scope,series.id]));
    return `<div class="assistant-series-star-control">
      <button type="button" class="assistant-star${starred ? ' is-starred' : ''}" data-series-stars="${e(series.id)}" data-group-starred="${starred}" popovertarget="${e(menuId)}" aria-haspopup="dialog" aria-expanded="false" aria-label="${e(label)}. Manage series and note stars" title="${e(label)} · Manage stars">${starred ? '★' : '☆'}</button>
      <div id="${e(menuId)}" class="assistant-star-menu" popover="auto" role="dialog" aria-label="Stars for ${e(series.title)}">
        <div class="assistant-star-choice"><span>Entire series<small>${e(series.title)}</small></span>${starButton(series,'series')}</div>
        ${row.path !== series.path ? `<div class="assistant-star-choice"><span>Latest note<small>${e(row.title)}</small></span>${starButton(row,'latest note')}</div>` : ''}
        ${starredNotes ? `<button type="button" class="assistant-star-notes" data-starred-notes="${e(series.id)}" data-latest-path="${e(row.path)}" data-latest-kind="${e(documentKind(row))}">View ${starredNotes} starred note${starredNotes === 1 ? '' : 's'}</button>` : ''}
      </div></div>`;
  }

  function bindSeriesStars(host) {
    host.querySelectorAll('[data-series-stars]').forEach(button => {
      const menu = document.getElementById(button.getAttribute('popovertarget'));
      menu.addEventListener('beforetoggle', event => {
        button.setAttribute('aria-expanded',String(event.newState === 'open'));
        if (event.newState !== 'open') return;
        const anchor = button.getBoundingClientRect();
        const width = Math.min(320,window.innerWidth - 16);
        const below = window.innerHeight - anchor.bottom - 12;
        const above = anchor.top - 12;
        const placeAbove = below < 200 && above > below;
        menu.style.width = width + 'px';
        menu.style.left = Math.max(8,Math.min(anchor.right - width,window.innerWidth - width - 8)) + 'px';
        menu.style.top = placeAbove ? 'auto' : (anchor.bottom + 4) + 'px';
        menu.style.bottom = placeAbove ? (window.innerHeight - anchor.top + 4) + 'px' : 'auto';
        menu.style.maxHeight = Math.max(80,Math.min(400,placeAbove ? above : below)) + 'px';
      });
      menu.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        event.preventDefault();event.stopPropagation();menu.hidePopover();button.focus();
      });
    });
    host.querySelectorAll('[data-starred-notes]').forEach(button => button.addEventListener('click', async () => {
      button.closest('[popover]').hidePopover();
      state.seriesFilters.set(button.dataset.starredNotes,{search:'',filter:'starred'});
      selectEntry(button.dataset.latestKind,button.dataset.latestPath,true);
      await openDocumentModal(button.dataset.latestKind,button.dataset.latestPath);
      if (state.modalRoot?.path === button.dataset.latestPath) {
        document.getElementById('assistantSeriesMenu')?.showPopover();
        document.getElementById('assistantSeriesFilter')?.focus();
      }
    }));
  }

  function externalDocument(row, compact = false) {
    if (!row?.external_url) return '';
    try {
      const url = new URL(row.external_url);
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return '';
      const label = 'Open external document for ' + (row.title || 'this document');
      return `<a class="assistant-external-doc${compact ? ' compact' : ''}" data-lab-client-external href="${e(url.href)}" target="_blank" rel="noopener noreferrer" aria-label="${e(label)}" title="${e(label)}">${compact ? '' : 'External doc '}<span aria-hidden="true">↗</span></a>`;
    } catch { return ''; }
  }

  function documentTaskBadges(summary) {
    if (!summary) return '';
    return `<span class="assistant-work-status ${summary.pending ? 'pending' : summary.total ? 'completed' : 'empty'}">${summary.pending ? summary.pending + ' pending' : summary.status === 'cancelled' ? 'Cancelled' : summary.total ? 'All tasks completed' : 'No tasks'}</span>${summary.wip ? `<span class="assistant-work-status wip">${summary.wip} WIP</span>` : ''}${summary.blocked ? `<span class="assistant-work-status blocked">${summary.blocked} blocked</span>` : ''}`;
  }

  function documentCard(row, scope = 'list') {
    const series = row.displaySeries;
    const kind = documentKind(row);
    const work = (series ? [series,...row.seriesMembers] : [row]).flatMap(pendingWork);
    const priority = work.map(item => item.priority || 'P2').sort()[0] || row.priority || 'P2';
    const due = work.map(item => calendarDate(item.due)).filter(Boolean).sort()[0] || (!series ? row.due : '');
    const taskSummary = series && row.task_format ? [series,...row.seriesMembers].reduce((total,item) => { const summary=item.task_summary || {}; for(const key of ['pending','total','wip','blocked']) total[key]+=(summary[key] || 0); return total; }, {pending:0,total:0,wip:0,blocked:0}) : row.task_summary;
    const openNotes = series ? row.seriesMembers.filter(item => pendingWork(item).length).length : 0;
    const starredNotes = series ? row.seriesMembers.filter(item => item.starred).length : 0;
    const summary = series ? (row.path !== series.path ? `Latest: ${row.title}` : '') : row.tldr || row.summary;
    return `<article class="assistant-list-item assistant-unified-item" data-assistant-entry-wrap="${e(row.path)}" data-document-key="${e(row.displayKey || row.path)}" data-terminal-document="${e(row.id)}" data-assistant-document-drag data-assistant-root="${e(state.data.root)}" draggable="true">
      <button type="button" class="assistant-compact-row assistant-document-row" data-assistant-document="${e(row.path)}" data-document-kind="${e(kind)}">
        ${documentIcon(row)}<span class="assistant-row-content"><span class="assistant-row-title">${work.length || !series && row.tracked ? `<span class="assistant-priority ${e(priority.toLowerCase())}">${e(priority)}</span>` : ''}<strong>${e(series?.title || row.title)}</strong></span>${summary ? `<span class="assistant-row-tldr">${e(summary)}</span>` : ''}</span>
        <span class="assistant-row-meta">${series ? `<small>${row.seriesMembers.length} notes</small>${starredNotes ? `<small>${starredNotes} starred note${starredNotes === 1 ? '' : 's'}</small>` : ''}${openNotes ? `<small>Open tasks in ${openNotes} note${openNotes === 1 ? '' : 's'}</small>` : ''}` : ''}${row.workspace_name ? `<span class="assistant-task-workspace-label">${e(row.workspace_name)}</span>` : ''}${row.date ? `<time>${e(row.date)}</time>` : ''}${documentTaskBadges(taskSummary)}${!taskSummary && !series && row.tracked ? `<span class="assistant-status status-${e(row.status)}">${e(labelStatus(row.status))}</span>` : ''}${due ? `<span class="assistant-task-due">Due ${e(displayDate(due))}</span>` : ''}${row.source === 'demo' || (row.tags || []).includes('demo') ? '<span class="assistant-demo">Demo</span>' : ''}</span>
      </button>${externalDocument(row)}${series ? seriesStarControl(row,scope) : starButton(row)}</article>`;
  }

  function renderDocuments(rows) {
    const sections = state.view === 'dashboard' ? dashboardSections() : null;
    const count = sections ? new Set(sections.flatMap(section => section.rows.map(row => row.displayKey))).size : rows.length;
    const views = [['dashboard','Dashboard'],['all','All'],['starred','★ Starred'],['all_open','Open tasks'],['documents','Documents'],['meetings','Meetings'],['meeting_series','Series'],['today','Today'],['week','This week'],['inbox','Not started'],['in_progress','In progress'],['recurring','Recurring'],['someday','Someday'],['recent','Completed'],['cancelled','Cancelled']];
    return `<nav class="assistant-quick-views compact" aria-label="Document views">${views.map(([id,name]) => `<button type="button" class="${state.view === id ? 'active' : ''}" data-assistant-view="${id}">${name}</button>`).join('')}</nav>
      <div class="assistant-filters"><input type="search" id="assistantSearch" value="${e(state.search)}" placeholder="Search tasks and notes…" aria-label="Search documents">${workspaceSelect(state.data.documents)}${projectSelect()}${!['dashboard','all','documents','starred','meetings','meeting_series'].includes(state.view) ? `<select id="assistantStatus" aria-label="Filter by status"><option value="">Any status</option>${(state.data.statuses || []).map(status => `<option value="${e(status)}"${state.status === status ? ' selected' : ''}>${e(labelStatus(status))}</option>`).join('')}</select><select id="assistantPriority" aria-label="Filter by priority"><option value="">Any priority</option>${(state.data.priorities || []).map(priority => `<option${state.priority === priority ? ' selected' : ''}>${e(priority)}</option>`).join('')}</select>` : ''}<span class="assistant-filter-count">${count} item${count === 1 ? '' : 's'}</span></div>
      ${sections ? renderDashboard(sections) : `<section class="assistant-list assistant-list-single" aria-label="Documents" data-testid="assistant-list">${dateGroups(rows, row => documentCard(row), row => state.view === 'meetings' ? calendarDate(row.date) : taskCreatedDate(row.created), 'document') || '<div class="assistant-empty">No items match this view.</div>'}</section>`}`;
  }

  function bindStars(host) {
    host.querySelectorAll('[data-star-path]').forEach(button => button.addEventListener('click', async event => {
      event.stopPropagation();
      button.disabled = true;
      const request = state.modalRequest;
      const value = button.getAttribute('aria-pressed') !== 'true';
      try {
        const detail = await fetchDocument('note', button.dataset.starPath);
        const response = await fetch('/api/assistant/metadata', {method:'PATCH', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({path:detail.path,field:'starred',value,expected:detail.metadata.starred ?? null})});
        const saved = await response.json();
        if (!response.ok) throw new Error(saved.detail || 'Could not save star');
        if (request === state.modalRequest && state.modalRoot?.path === saved.path) {
          state.modalRoot = saved;
          if (state.modalCurrent?.path === saved.path) state.modalCurrent = saved;
          await renderModal();
        }
        await refresh();
      } catch (error) { window.alert(error.message); }
      finally { button.disabled = false; }
    }));
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
    const unified = Array.isArray(state.data.documents);
    const rows = unified ? collapseSeries(filteredDocuments()) : isTaskSection() ? filteredTasks() : filteredMeetings();
    const title = unified ? 'Documents' : isTaskSection() ? 'Tasks' : 'Notes';
    const body = unified ? renderDocuments(rows) : isTaskSection() ? renderTasks(rows) : renderNotes(rows);
    const html = `<div class="assistant-shell assistant-minimal-shell assistant-layout-${e(state.section)}">
      <header class="assistant-head">
        <h1>${e(title)}</h1>
        <span>${unified ? '<button type="button" class="refresh-btn" data-new-record="note">+ Document</button> <button type="button" class="refresh-btn" data-new-record="task">+ Task</button> <button type="button" class="refresh-btn" data-new-record="series">+ Series</button> ' : state.data?.schema === 2 ? `<button type="button" class="refresh-btn" data-new-record="${isTaskSection() ? 'task' : 'note'}">+ ${isTaskSection() ? 'Task' : 'Note'}</button> ` : ''}${state.data?.schema === 2 ? '<button type="button" class="refresh-btn" data-new-record="project">+ Project</button> ' : ''}<button type="button" class="refresh-btn" id="assistantRefresh">Refresh</button></span>
      </header>${body}
    </div>`;
    if (state.renderedList === html && content.querySelector('.assistant-shell')) return;
    const focused = content.contains(document.activeElement) ? document.activeElement : null;
    const focusId = focused?.id;
    const selection = focused?.tagName === 'INPUT' ? [focused.selectionStart, focused.selectionEnd] : null;
    const scrollTop = content.scrollTop;
    content.innerHTML = html;
    state.renderedList = html;
    content.scrollTop = scrollTop;
    content.querySelectorAll('[data-assistant-entry-wrap]').forEach(row => row.classList.toggle('selected', row.dataset.assistantEntryWrap === state.selectedTaskPath));
    if (focusId) {
      const control = document.getElementById(focusId);
      control?.focus({preventScroll:true});
      if (selection?.[0] != null) control?.setSelectionRange?.(...selection);
    }
    content.querySelectorAll('[data-new-record]').forEach(button => button.addEventListener('click', () => createRecord(button.dataset.newRecord)));
    bindStars(content);
    bindSeriesStars(content);
    bindDashboard(content);
    content.querySelectorAll('[data-assistant-document]').forEach(button => bindDocumentLink(button, options => {
      const kind = button.dataset.documentKind, path = button.dataset.assistantDocument;
      selectEntry(kind, path, true);
      openDocumentModal(kind, path, '', options);
    }));
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
      if (state.status === 'done') state.view = 'recent';
      else if (state.status === 'cancelled') state.view = 'cancelled';
      else if (['recent','cancelled'].includes(state.view) && state.status) state.view = 'all_open';
      render();
    });
    document.getElementById('assistantPriority')?.addEventListener('change', event => {
      state.priority = event.target.value;
      render();
    });
    document.getElementById('assistantProject')?.addEventListener('change', event => { state.project = event.target.value; render(); });
    document.getElementById('assistantWorkspace')?.addEventListener('change', event => {
      selectWorkspace(event.target.value);
    });
    content.querySelectorAll('[data-assistant-task]').forEach(button => bindRow(button, 'task'));
    content.querySelectorAll('[data-assistant-meeting]').forEach(button => bindRow(button, 'meeting'));
    bindSeries(content);
    content.querySelectorAll('[data-assistant-note]').forEach(button => {
      bindDocumentLink(button, options => {
        if (state.data?.schema === 2) openDocumentModal('note', button.dataset.assistantNote, '', options);
        else window.openWorkspaceDocModal(button.dataset.assistantNote, {root: state.data.root});
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
    if (workspaceId === state.workspace) return;
    state.workspace = workspaceId;
    state.selectedTaskPath = '';
    const url = new URL(window.location);
    url.searchParams.set('view', 'assistant');
    if (workspaceId) url.searchParams.set('assistant_workspace', workspaceId);
    else url.searchParams.delete('assistant_workspace');
    url.searchParams.delete('task');
    history.pushState({nav: 'assistant', assistant_workspace: workspaceId}, '', url.pathname + url.search + url.hash);
    render();
  }

  function bindRow(button, kind) {
    const attribute = kind === 'task' ? 'assistantTask' : 'assistantMeeting';
    const path = button.dataset[attribute];
    bindDocumentLink(button, options => {
      selectEntry(kind, path, true);
      openDocumentModal(kind, path, '', options);
    });
  }

  function bindDocumentLink(button, open) {
    // Keep the chooser mounted until the second click can reach the same row.
    // Keyboard activation opens immediately; pointer clicks allow double-click.
    const openInline = () => {
      state.documentClickTimer = null;
      open({inline:button.closest('.assistant-document-overlay') ? Boolean(state.inlineHost) : true});
    };
    button.addEventListener('click', event => {
      if (event.target.closest('[data-assistant-nudge]')) return;
      clearTimeout(state.documentClickTimer);
      if (event.detail > 1) return;
      if (!event.detail) openInline();
      else state.documentClickTimer = setTimeout(openInline, 300);
    });
    button.addEventListener('dblclick', event => {
      if (event.target.closest('[data-assistant-nudge]')) return;
      event.preventDefault();
      clearTimeout(state.documentClickTimer);
      state.documentClickTimer = null;
      open({inline:false});
    });
    if (button.tagName !== 'BUTTON') button.addEventListener('keydown', event => {
      if (event.target.closest('[data-assistant-nudge]')) return;
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      clearTimeout(state.documentClickTimer);
      openInline();
    });
  }

  function selectEntry(kind, path, push) {
    state.selectedTaskPath = kind === 'task' ? path || '' : '';
    state.selectedMeetingPath = kind === 'meeting' ? path || '' : '';
    state.selectedSeriesPath = '';
    if (push) {
      const url = new URL(window.location);
      url.searchParams.set('view', 'assistant');
      url.searchParams.delete('series');
      url.searchParams.delete('note');
      if (state.data?.documents) {
        url.searchParams.set('subview','documents');
        for (const field of ['task','note','meeting','series']) url.searchParams.delete(field);
        if (path) url.searchParams.set(kind, path);
      } else if (kind === 'task') {
        url.searchParams.set('subview', 'tasks');
        if (state.workspace) url.searchParams.set('assistant_workspace', state.workspace);
        else url.searchParams.delete('assistant_workspace');
        url.searchParams.delete('meeting');
        if (path) url.searchParams.set('task', path);
      } else {
        url.searchParams.set('subview', 'notes');
        url.searchParams.delete('task');
        url.searchParams.delete('meeting');
        if (path) url.searchParams.set(kind === 'note' ? 'note' : 'meeting', path);
      }
      history.pushState({nav: 'assistant', [kind]: path}, '', url.pathname + url.search + url.hash);
    }
    document.querySelectorAll('[data-assistant-entry-wrap]').forEach(row => {
      row.classList.toggle('selected', row.dataset.assistantEntryWrap === state.selectedTaskPath);
    });
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
        <div class="assistant-modal-actions"><span id="assistantNoteStatus" class="assistant-note-status" role="status" aria-live="polite" hidden></span><button type="button" id="assistantEditNote" hidden>Edit</button><button type="button" id="assistantSaveNote" hidden>Save</button><button type="button" id="assistantRevertNote" hidden>Discard</button><details class="assistant-copy-menu"><summary>Copy <span aria-hidden="true">⌄</span></summary><div><button type="button" id="assistantCopyRich">Copy for Google Docs</button><button type="button" id="assistantCopyPlain">Copy plain text</button></div></details><button type="button" id="assistantExpandDocument" hidden>Expand</button><button type="button" class="assistant-modal-close" aria-label="Close Assistant document">×</button></div>
        <div class="assistant-modal-metadata" id="assistantModalMetadata"></div>
      </header>
      <div class="assistant-modal-body" id="assistantModalBody"><aside class="assistant-document-nav" id="assistantDocumentNav"></aside><main class="assistant-document-pane" id="assistantModalDocument"><div class="loading">Loading…</div></main></div>
      <section id="assistantDocumentTerminal" class="assistant-document-terminal" hidden aria-label="Document terminal"></section>
    </section>`;
    overlay.addEventListener('click', event => {
      const copyMenu = overlay.querySelector('.assistant-copy-menu');
      if (!event.target.closest('.assistant-copy-menu summary')) copyMenu.open = false;
      if (event.target === overlay) closeDocumentModal();
      else if (!event.target.closest('.assistant-metadata-more')) {
        const more = overlay.querySelector('.assistant-metadata-more');
        if (more) more.open = false;
      }
    });
    overlay.querySelector('.assistant-modal-close').addEventListener('click', closeDocumentModal);
    overlay.querySelector('#assistantExpandDocument').onclick = () => {
      presentDocument(overlay, false);
      window.LabDocumentTerminal?.open(state.modalCurrent, state.modalRoot, state.data.root);
    };
    document.body.appendChild(overlay);
    return overlay;
  }

  function presentDocument(overlay, inline) {
    const content = document.getElementById('content');
    inline = Boolean(inline && content);
    if (inline && !state.inlineHost) {
      state.inlineSidebarCollapsed = document.body.classList.contains('sidebar-collapsed');
      state.inlineHost = document.createElement('div');
      state.inlineHost.id = 'assistantInlineHost';
      state.inlineHost.className = 'main assistant-inline-host';
      content.after(state.inlineHost);
      state.inlineHost.append(overlay);
      document.body.classList.add('assistant-inline-document', 'sidebar-collapsed');
    } else if (!inline && state.inlineHost) {
      document.body.append(overlay);
      state.inlineHost.remove(); state.inlineHost = null;
      document.body.classList.remove('assistant-inline-document');
      document.body.classList.toggle('sidebar-collapsed', state.inlineSidebarCollapsed);
    }
    overlay.classList.toggle('assistant-document-inline', inline);
    const section = overlay.querySelector('.assistant-document-modal');
    section.setAttribute('role', inline ? 'region' : 'dialog');
    if (inline) section.removeAttribute('aria-modal'); else section.setAttribute('aria-modal', 'true');
    overlay.querySelector('#assistantExpandDocument').hidden = !inline;
  }

  function openDocumentTerminal(detail) {
    window.LabDocumentTerminal?.open(detail, state.modalRoot, state.data.root, {inline:Boolean(state.inlineHost)});
  }

  function closeDocumentModal(updateHistory = true) {
    clearTimeout(state.documentClickTimer);
    state.documentClickTimer = null;
    state.inlinePending = false;
    window.AssistantTasks?.reset();
    window.LabDocumentTerminal?.close();
    closeHeadingMenu();
    closeSeriesMenu();
    clearTimeout(state.tabActivityTimer);
    ++state.modalRequest;
    if (updateHistory) {
      const url = new URL(window.location);
      const selected = ['meeting', 'series', 'task', 'note'].some(key => url.searchParams.has(key));
      url.searchParams.delete('meeting'); url.searchParams.delete('series'); url.searchParams.delete('task'); url.searchParams.delete('note');
      if (selected) history.pushState({nav:'assistant'}, '', url.pathname + url.search + url.hash);
      state.selectedMeetingPath = ''; state.selectedSeriesPath = '';
    }
    const overlay = document.getElementById('assistantDocumentModal');
    if (overlay) { overlay.classList.remove('active'); presentDocument(overlay, false); }
    window.LabWorkspaceDocuments?.openDocument(null);
  }

  async function fetchDocument(kind, path) {
    const endpoint = kind === 'task' ? '/api/assistant/task?path='
      : kind === 'subtask' ? '/api/assistant/subtask?path='
      : kind === 'series' ? '/api/assistant/meeting-series?path='
      : kind === 'note' ? '/api/assistant/note?path='
      : kind === 'content' ? '/api/assistant/meeting-content?path=' : '/api/assistant/meeting?path=';
    const response = await fetch(endpoint + encodeURIComponent(path));
    const detail = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(detail.detail || response.statusText);
    return detail;
  }

  function documentError(message) {
    const host = document.getElementById('assistantModalDocument');
    host.querySelector('.assistant-document-error')?.remove();
    const notice = document.createElement('div');
    notice.className = 'assistant-document-error'; notice.setAttribute('role', 'status');
    notice.textContent = message;
    host.prepend(notice);
  }

  async function openDocumentModal(kind, path, focusHeading = '', options = {}) {
    closeHeadingMenu();
    closeSeriesMenu();
    window.AssistantTasks?.reset();
    const overlay = ensureModal();
    const wasOpen = overlay.classList.contains('active');
    const inline = options.inline ?? (wasOpen ? Boolean(state.inlineHost) : document.body.classList.contains('assistant-active'));
    state.inlinePending = inline;
    const request = ++state.modalRequest;
    overlay.setAttribute('aria-busy', 'true');
    try {
      let detail = await fetchDocument(kind, path);
      if (request !== state.modalRequest) return;
      let root = detail, rootKind = kind;
      if (detail.metadata?.schema === 2 && detail.root_path) {
        root = detail.root_path === detail.path ? detail : await fetchDocument(detail.root_kind, detail.root_path);
        rootKind = detail.root_kind;
      } else if (kind === 'subtask') {
        const metadata = detail.metadata || {};
        const parent = tasks().find(task => task.workspace === (metadata.parent_workspace || metadata.workspace) && task.id === metadata.parent);
        root = parent ? await fetchDocument('task', parent.path) : detail;
        rootKind = parent ? 'task' : 'subtask';
      }
      if (request !== state.modalRequest) return;
      let showIndex = !focusHeading && detail.path === root.path && Boolean(root.tree?.children?.length || root.document_tasks);
      let terminalTask = null;
      if (options.linkedTask?.task_id) {
        terminalTask = root.document_tasks?.tasks?.find(task => task.id === options.linkedTask.task_id);
        if (!terminalTask) throw new Error('The linked task no longer exists in this document.');
        const tasksById = new Map(root.document_tasks.tasks.map(task => [task.id,task]));
        let owner = terminalTask;
        const seen = new Set();
        while (owner && !owner.tab_id && !seen.has(owner.id)) {
          seen.add(owner.id); owner = tasksById.get(owner.parent_id);
        }
        const find = node => node.id === owner?.tab_id ? node : (node.children || []).map(find).find(Boolean);
        const tab = root.tree && find(root.tree);
        detail = tab && tab.path !== root.path ? await fetchDocument(tab.kind,tab.path) : root;
        showIndex = !tab;
      }
      // Explicit subtab links and heading targets always win over remembered navigation.
      if (!terminalTask && !focusHeading && !path.includes('#tab=') && detail.path === root.path && root.tree) {
        const remembered = rememberedDocumentTab(root);
        if (remembered === 'index' && (root.tree.children?.length || root.document_tasks)) showIndex = true;
        else if (remembered) {
          const find = node => node.path === remembered ? node : (node.children || []).map(find).find(Boolean);
          const tab = find(root.tree);
          if (tab) {
            if (tab.path !== root.path) detail = await fetchDocument(tab.kind, tab.path);
            showIndex = false;
          }
        }
      }
      if (request !== state.modalRequest) return;
      state.modalRoot = root; state.modalKind = rootKind;
      state.modalCurrent = detail; state.modalMeetingPart = 'summary';
      state.modalIndex = showIndex;
      presentDocument(overlay, inline);
      await renderModal(focusHeading);
      if (request === state.modalRequest) {
        overlay.classList.add('active');
        openDocumentTerminal(detail);
        window.LabWorkspaceDocuments?.openDocument({assistant_root:state.data.root,document_id:root.tree?.id || root.metadata.id});
        if (terminalTask) {
          window.AssistantTasks?.reveal(terminalTask.id);
          window.LabDocumentTerminal?.focusTask(terminalTask.id);
        } else if (options.linkedTask) window.LabDocumentTerminal?.focusTask(null);
        return true;
      }
    } catch (error) {
      if (request !== state.modalRequest) return;
      if (!wasOpen) {
        presentDocument(overlay, inline);
        document.getElementById('assistantModalDocument').replaceChildren();
        document.getElementById('assistantDocumentNav').replaceChildren();
        document.getElementById('assistantModalTitle').textContent = 'Document unavailable';
        resetCopy(); overlay.classList.add('active');
      }
      documentError(error.message || String(error));
    } finally {
      if (request === state.modalRequest) { overlay.removeAttribute('aria-busy'); state.inlinePending = false; }
    }
  }

  async function openLinkedTask(link, options = {}) {
    if (!link?.document_id || !link?.assistant_root) throw new Error('This terminal has no linked task.');
    const request = ++state.modalRequest;
    state.inlinePending = Boolean(options.inline);
    const response = await fetch('/api/assistant');
    const data = await response.json();
    if (request !== state.modalRequest) return;
    if (!response.ok) throw new Error(data.detail || 'Could not load the linked document.');
    if (data.root !== link.assistant_root) throw new Error('This terminal links to a different Assistant database.');
    const row = (data.documents || []).find(row => row.id === link.document_id);
    if (!row) throw new Error('The linked document is no longer available.');
    state.data = data;
    // Render over the current workspace without navigating its page or terminal.
    return openDocumentModal(documentKind(row),row.path,'',{linkedTask:link,inline:Boolean(options.inline)});
  }

  function localImageUrl(documentPath, src) {
    return '/api/assistant/asset?task=' + encodeURIComponent(documentPath) + '&src=' + encodeURIComponent(src);
  }

  function documentImageUrl(documentPath, src) {
    if (!src || src.startsWith('http://') || src.startsWith('https://') || src.startsWith('data:')) return src;
    return localImageUrl(documentPath, src);
  }

  function rewriteImages(host, documentPath) {
    if (state.data?.schema === 2) host.querySelectorAll('a[href]').forEach(link => {
      const src = link.getAttribute('href');
      if (!src || src.startsWith('#') && !src.startsWith('#tab=') || /^(?:[a-z]+:|\/\/)/i.test(src)) return;
      link.href = '/api/assistant/link?document=' + encodeURIComponent(documentPath) + '&src=' + encodeURIComponent(src);
    });
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

  function metadataToggle(field, label, value) {
    return `<label class="assistant-metadata-toggle"><input type="checkbox" data-metadata-field="${e(field)}" aria-label="${e(label)}"${value ? ' checked' : ''}><span>${e(label)}</span></label>`;
  }

  function editDocumentAttributes(record) {
    if (document.getElementById('assistantAttributesEditor')) return;
    const dialog = document.createElement('dialog');
    dialog.id = 'assistantAttributesEditor'; dialog.className = 'assistant-section-editor';
    dialog.setAttribute('aria-labelledby','assistantAttributesTitle');
    dialog.innerHTML = `<form><h2 id="assistantAttributesTitle">Attributes · ${e(record.metadata.title)}</h2>
      <p class="assistant-json-help">Custom attributes for this ${record.metadata.parent ? 'tab' : 'document'}. Use your own names, such as <code>is_investigation</code> or <code>is_RFC</code>, with JSON values.</p>
      <label for="assistantAttributesJson">Attributes JSON</label><textarea id="assistantAttributesJson" spellcheck="false" autocomplete="off" autocapitalize="off" aria-describedby="assistantAttributesError" required></textarea>
      <p id="assistantAttributesError" class="assistant-section-error" role="alert"></p><footer><span></span><button type="button" data-attributes-cancel>Cancel</button><button type="submit">Save attributes</button></footer></form>`;
    const textarea = dialog.querySelector('textarea');
    textarea.value = formatSectionJson(record.metadata.attributes || {});
    const errorMessage = dialog.querySelector('[role="alert"]');
    const expected = record.metadata.attributes ?? null;
    document.body.append(dialog);
    dialog.addEventListener('close', () => dialog.remove());
    dialog.addEventListener('cancel', event => { if (textarea.disabled) event.preventDefault(); });
    dialog.querySelector('[data-attributes-cancel]').addEventListener('click', () => dialog.close());
    textarea.addEventListener('input', () => { errorMessage.textContent = '';textarea.removeAttribute('aria-invalid'); });
    dialog.querySelector('form').addEventListener('submit', async event => {
      event.preventDefault();
      let value;
      try {
        value = JSON.parse(textarea.value);
        if (!value || Array.isArray(value) || typeof value !== 'object') throw new Error('Use a JSON object; {} clears all attributes.');
      } catch (error) {
        errorMessage.textContent = 'Invalid JSON: ' + error.message;
        textarea.setAttribute('aria-invalid','true');textarea.focus();return;
      }
      const buttons = dialog.querySelectorAll('button');
      buttons.forEach(button => { button.disabled = true; });textarea.disabled = true;
      errorMessage.textContent = '';
      try {
        const response = await fetch('/api/assistant/metadata', {method:'PATCH',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({path:record.path,field:'attributes',value,expected})});
        const saved = await response.json();
        if (!response.ok) throw new Error(saved.detail || 'Could not save attributes');
        if (state.modalCurrent?.path === saved.path) {
          state.modalCurrent = saved;
          if (state.modalRoot?.path === saved.path) state.modalRoot = saved;
          else if (saved.tree) state.modalRoot.tree = saved.tree;
          await renderModal();
        }
        dialog.close();await refresh();
      } catch (error) { errorMessage.textContent = error.message; }
      finally { buttons.forEach(button => { button.disabled = false; });textarea.disabled = false; }
    });
    dialog.showModal();
  }

  function renderDocumentHeader(detail, kind) {
    closeHeadingMenu();
    hideNoteControls();
    // Related documents share their meeting's properties; original notes stay read-only.
    const record = detail.metadata?.schema === 2 ? detail : ['content', 'meeting'].includes(kind) ? state.modalRoot : detail;
    const recordKind = kind === 'content' ? 'meeting' : kind;
    const metadata = record.metadata || {};
    const workspace = record.workspace || {};
    const task = !detail.document_tasks && ['task', 'subtask'].includes(recordKind);
    const subtab = Boolean(metadata.parent);
    const tracked = !detail.document_tasks && (record.progress?.tracked ?? (task || subtab || Boolean(record.progress?.derived)));
    const progress = record.path === state.modalRoot?.path ? state.modalRoot.tree?.progress || record.progress : record.progress;
    const status = progress?.status || metadata.status || 'not_started';
    const lifecycle = progress?.derived
      ? (['cancelled','skipped'].includes(status) ? [[progress.automatic_status, 'Resume · ' + labelStatus(progress.automatic_status)], [status,labelStatus(status)]]
        : [[status,labelStatus(status)], ...(subtab ? [['skipped','Skipped']] : [['cancelled','Cancelled']])])
      : [['not_started','Not started'],['in_progress','In progress'],['done','Completed'], ...(subtab ? [['skipped','Skipped']] : [['cancelled','Cancelled']])];
    const bar = document.getElementById('assistantModalMetadata');
    const heading = document.getElementById('assistantModalTitle');
    heading.textContent = kind === 'content'
      ? `${metadata.title || 'Meeting'} · ${detail.format === 'text' ? 'Raw notes' : detail.metadata?.title || 'Document'}`
      : metadata.title || metadata.id || 'Document';
    heading.title = heading.textContent;
    document.getElementById('assistantModalKind').textContent = subtab ? 'Tab' : metadata.note_type === 'series' ? 'Meeting series' : metadata.note_type === 'meeting' ? 'Meeting' : 'Document';
    const workflow = tracked ? [
      metadataSelect('status', progress?.derived ? 'Overall' : 'Status', status, metadata.schema === 2 ? lifecycle : state.data?.statuses || lifecycle),
      metadataSelect('priority', 'Priority', metadata.priority || 'P2', ['P0', 'P1', 'P2', 'P3'].map(value => [value, value])),
      metadataInput('due', 'Due', metadata.due, 'date'),
    ] : [];
    const meeting = recordKind === 'meeting' || metadata.note_type === 'meeting' ? [
      metadataInput('date', 'Date', metadata.date, 'date'),
      metadataSelect('series', 'Series', metadata.series, [['', 'Standalone'], ...(state.data?.meeting_series || [])
        .filter(row => metadata.schema === 2 || row.workspace === (metadata.workspace || workspace.id || record.path.split('/')[1]))
        .map(row => [row.id, row.title])]),
    ] : [];
    const organization = [];
    const documentFields = [metadataInput('title', 'Title', metadata.title), metadataInput('tldr', 'Summary', metadata.tldr)];
    if (metadata.schema === 2 && !record.embedded) {
      documentFields.push(
        metadataSelect('note_type', 'Label', metadata.note_type || 'plain', [['plain','None'],['meeting','Meeting'],['series','Meeting series']]),
        metadataToggle('keep_in_documents', 'Keep in Documents', metadata.keep_in_documents ?? metadata.type === 'note'),
      );
      organization.push(
        metadataSelect('project', 'Project', metadata.project, [['', 'None'], ...(state.data.projects || []).map(row => [row.id,row.title])]),
        metadataSelect('workspace', 'Workspace', metadata.workspace, [['', 'None'], ...workspaceRows().map(row => [row.id,row.name || row.id])]),
      );
    }
    const tracking = [];
    if (tracked) organization.push(metadataInput('owner', 'POC', metadata.owner));
    if (task && !subtab) tracking.push(metadataSelect('recurrence', 'Repeats', metadata.recurrence, [['', 'Once'], ['weekly', 'Weekly'], ['monthly', 'Monthly'], ['yearly', 'Yearly']]));
    let star = '', attributes = '';
    if (metadata.schema === 2) {
      documentFields.push(metadataInput('external_url', 'External document URL', metadata.external_url, 'url'));
      attributes = `<button type="button" class="assistant-attributes-button" data-edit-attributes aria-label="Edit custom attributes">Attributes${Object.keys(metadata.attributes || {}).length ? ' (' + Object.keys(metadata.attributes).length + ')' : ''}</button>`;
      if (!detail.document_tasks) tracking.unshift(metadataToggle('track_task', 'Track this tab', metadata.track_task ?? (metadata.type === 'task' || Boolean(metadata.status))));
      const owner = state.modalRoot || record;
      star = starButton({...owner.metadata,path:owner.path}, owner.metadata.note_type === 'series' ? 'series' : 'document');
    }
    const fields = task ? [
      ['group', 'Group'], ['scheduled', 'Planned', 'date'],
      ['defer_until', 'Deferred until', 'date'], ['waiting_on', 'Waiting on'], ['follow_up_at', 'Follow up', 'date'],
    ] : [];
    tracking.push(...fields.map(([field, label, type]) => metadataInput(field, label, metadata[field], type)));
    const info = [
      ['Workspace', workspace.name || metadata.workspace], ['Vault', workspace.vault],
      ['Attendees', Array.isArray(metadata.attendees) ? metadata.attendees.join(', ') : metadata.attendees],
      ['Parent', metadata.parent?.id || metadata.parent], ['Created', metadata.created], ['Updated', metadata.updated],
      ['Workspace path', workspace.workspace_path],
    ].filter(([, value]) => value);
    const group = (title, controls) => controls.length ? `<fieldset class="assistant-property-group"><legend>${title}</legend>${controls.join('')}</fieldset>` : '';
    bar.innerHTML = `${star}${workflow.length ? `<div class="assistant-header-properties" role="group" aria-label="Task progress">${workflow.join('')}</div>` : ''}${meeting.length ? `<div class="assistant-header-properties" role="group" aria-label="Meeting">${meeting.join('')}</div>` : ''}<details class="assistant-metadata-more"><summary aria-label="Document properties">Properties <span aria-hidden="true">⌄</span></summary><div class="assistant-metadata-popover">${group('Document', documentFields)}${group('Organization', organization)}${group('Tracking', tracking)}${attributes}<dl>${info.map(([label, value]) => `<div><dt>${e(label)}</dt><dd>${e(value)}</dd></div>`).join('')}</dl></div></details>${externalDocument(metadata)}<span class="assistant-metadata-message" role="status" aria-live="polite"></span>`;
    bindStars(bar);
    bar.querySelector('[data-edit-attributes]')?.addEventListener('click', () => editDocumentAttributes(record));
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
    const value = control.type === 'checkbox' ? control.checked : control.value.trim() || null;
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
      if (state.modalRoot.path === saved.path) { state.modalRoot = saved; state.modalKind = saved.root_kind || state.modalKind; }
      else if (Array.isArray(state.modalRoot.subtasks)) state.modalRoot.subtasks = state.modalRoot.subtasks.map(child => child.path === saved.path ? {...child, ...saved.metadata} : child);
      if (state.modalCurrent.path === saved.path) state.modalCurrent = saved;
      if (saved.tree && state.modalRoot.path !== saved.path) state.modalRoot.tree = saved.tree;
      await renderModal();
      if (request !== state.modalRequest) return;
      host.scrollTop = scroll;
      bar.querySelector('details').open = moreOpen;
      bar.querySelector('[role="status"]').textContent = 'Saved';
      bar.querySelector(`[data-metadata-field="${field}"]`)?.focus();
      refresh();
    } catch (error) {
      if (request !== state.modalRequest) return;
      if (control.type === 'checkbox') control.checked = previous ?? (field === 'track_task' ? record.metadata.type === 'task' || Boolean(record.metadata.status) : record.metadata.type === 'note');
      else control.value = previous || '';
      message.textContent = error.message || 'Could not save this change.';
      message.classList.add('error');
    } finally {
      controls.forEach(input => { input.disabled = false; });
    }
  }

  function noteDraftKey(path) {
    return (state.data?.root || '') + ':' + path;
  }

  function noteDraft(detail = state.modalCurrent) {
    return detail && state.noteDrafts.get(noteDraftKey(detail.path));
  }

  function dirtyDraft(draft) { return Boolean(draft && draft.body !== draft.base); }

  // Mark only added/replaced lines. Deletions get a small mark at their join.
  // Trim shared edges first and bound the LCS matrix for unusually large notes.
  function noteLineChanges(before, after) {
    const oldLines = before.split('\n'), lines = after.split('\n');
    const changed = new Set(), deleted = new Set();
    let start = 0, oldEnd = oldLines.length, end = lines.length, removed = 0;
    while (start < oldEnd && start < end && oldLines[start] === lines[start]) start++;
    while (oldEnd > start && end > start && oldLines[oldEnd - 1] === lines[end - 1]) { oldEnd--; end--; }
    const n = oldEnd - start, m = end - start;
    if (!n || !m || n * m > 1000000) {
      for (let j = start; j < end; j++) changed.add(j);
      removed = n;
      if (n) deleted.add(Math.min(start, lines.length - 1));
    } else {
      const lengths = Array.from({length:n + 1}, () => new Uint32Array(m + 1));
      for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) {
        lengths[i][j] = oldLines[start + i] === lines[start + j]
          ? 1 + lengths[i + 1][j + 1] : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
      }
      let i = 0, j = 0;
      while (i < n || j < m) {
        if (i < n && j < m && oldLines[start + i] === lines[start + j]) { i++; j++; }
        else if (j < m && (i === n || lengths[i][j + 1] >= lengths[i + 1][j])) changed.add(start + j++);
        else { removed++; deleted.add(Math.min(start + j, lines.length - 1)); i++; }
      }
    }
    return {lines, changed, deleted, removed};
  }

  function markNoteChanges(draft) {
    const diff = noteLineChanges(draft.base, draft.body);
    draft.marks.innerHTML = diff.lines.map((line, i) => `<span class="${diff.changed.has(i) ? 'note-line-changed' : ''} ${diff.deleted.has(i) ? 'note-line-deleted' : ''}">${e(line) || '&#8203;'}</span>`).join('');
    draft.summary = dirtyDraft(draft) ? 'Unsaved changes' + (diff.removed ? ` · ${diff.removed} removed line${diff.removed === 1 ? '' : 's'}` : '') : '';
  }

  function markDraftTabs() {
    document.querySelectorAll('#assistantDocumentNav [data-record-path]').forEach(button => {
      const dirty = dirtyDraft(state.noteDrafts.get(noteDraftKey(button.dataset.recordPath)));
      button.classList.toggle('assistant-note-dirty', dirty);
      const label = button.querySelector('span:last-child')?.textContent || button.textContent;
      button.setAttribute('aria-label', label + (dirty ? ' · Unsaved changes' : ''));
    });
  }

  function hideNoteControls() {
    ['assistantEditNote','assistantSaveNote','assistantRevertNote','assistantNoteStatus'].forEach(id => {
      const element = document.getElementById(id);
      if (element) element.hidden = true;
    });
  }

  function renderNoteControls(detail, kind) {
    hideNoteControls();
    if (detail.metadata?.schema !== 2 || !['task','note'].includes(detail.metadata.type) || kind === 'content' || detail.format === 'text') return;
    const edit = document.getElementById('assistantEditNote');
    const save = document.getElementById('assistantSaveNote');
    const revert = document.getElementById('assistantRevertNote');
    const status = document.getElementById('assistantNoteStatus');
    const draft = noteDraft(detail), dirty = dirtyDraft(draft);
    edit.hidden = save.hidden = false;
    edit.textContent = draft?.editing ? 'Preview' : 'Edit';
    edit.setAttribute('aria-pressed', String(Boolean(draft?.editing)));
    edit.disabled = Boolean(draft?.saving);
    save.disabled = !dirty || Boolean(draft?.saving);
    save.textContent = draft?.saving ? 'Saving…' : 'Save';
    revert.hidden = !dirty; revert.disabled = Boolean(draft?.saving);
    status.hidden = !draft || !(dirty || draft.saved || draft.error);
    status.textContent = draft?.error || (dirty ? draft.summary || 'Unsaved changes' : draft?.saved ? 'Saved' : '');
    status.classList.toggle('is-dirty', dirty); status.classList.toggle('error', Boolean(draft?.error));
    edit.onclick = async () => {
      let current = noteDraft(detail);
      if (!current) {
        current = {path:detail.path, base:detail.body || '', body:detail.body || '', editing:false, scrollTop:0};
        state.noteDrafts.set(noteDraftKey(detail.path), current);
      }
      current.editing = !current.editing;
      await renderDocumentPane(detail, kind);
      if (current.editing) current.input.focus({preventScroll:true});
    };
    save.onclick = () => saveNoteContent(detail, kind);
    revert.onclick = async () => {
      if (!window.confirm('Discard your unsaved changes to this note?')) return;
      const request = state.modalRequest;
      try {
        const latest = await fetchDocument(kind, detail.path);
        if (request !== state.modalRequest) return;
        state.noteDrafts.delete(noteDraftKey(detail.path));
        state.modalCurrent = latest;
        if (state.modalRoot.path === latest.path) state.modalRoot = latest;
        await renderModal();
      } catch (error) { documentError(error.message); }
    };
    markDraftTabs();
  }

  function mountNoteEditor(draft, detail, kind, host) {
    if (!draft.node) {
      draft.node = document.createElement('div'); draft.node.className = 'assistant-note-editor';
      draft.node.innerHTML = '<pre class="assistant-note-marks" aria-hidden="true"></pre><textarea aria-label="Note content" spellcheck="true" wrap="soft"></textarea>';
      draft.marks = draft.node.querySelector('pre'); draft.input = draft.node.querySelector('textarea');
      draft.input.value = draft.body;
      draft.input.addEventListener('input', () => {
        draft.body = draft.input.value; draft.saved = false;
        markNoteChanges(draft);
        renderNoteControls(detail, kind);
      });
      draft.input.addEventListener('keydown', event => {
        if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
          event.preventDefault(); saveNoteContent(detail, kind);
        }
      });
      markNoteChanges(draft);
    }
    if (state.currentPane && host.contains(state.currentPane.node)) state.currentPane.scrollTop = host.scrollTop;
    if (host.firstElementChild !== draft.node) {
      host.replaceChildren(draft.node); host.scrollTop = draft.scrollTop;
    }
    state.currentPane = draft;
    // Copy actions use the current rendered draft, including while typing.
    document.getElementById('assistantCopyPlain').onclick = event => {
      const node = document.createElement('div'); node.innerHTML = window.LabMarkdown.render(draft.body);
      window.LabMarkdown.copy(node, {button:event.currentTarget, plainOnly:true});
    };
    document.getElementById('assistantCopyRich').onclick = event => {
      const node = document.createElement('div'); node.innerHTML = window.LabMarkdown.render(draft.body);
      rewriteImages(node, detail.path);
      window.LabMarkdown.copy(node, {button:event.currentTarget});
    };
  }

  async function saveNoteContent(detail, kind) {
    const draft = noteDraft(detail);
    if (!dirtyDraft(draft) || draft.saving) return;
    const request = state.modalRequest, body = draft.body, key = noteDraftKey(detail.path);
    const database = state.data?.root;
    draft.saving = true; draft.error = '';
    if (draft.input) draft.input.readOnly = true;
    renderNoteControls(detail, kind);
    try {
      const response = await fetch('/api/assistant/content', {method:'PUT', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({path:detail.path, body, expected:draft.base})});
      const saved = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(saved.detail || 'Could not save. Your draft is still here.');
      // Never reopen a closed document or replace another tab after a late save.
      draft.base = body; draft.saved = true;
      if (draft.marks) markNoteChanges(draft);
      if (request === state.modalRequest && database === state.data?.root && state.modalCurrent?.path === saved.path) {
        state.modalCurrent = saved;
        if (state.modalRoot.path === saved.path) state.modalRoot = saved;
        else if (saved.tree) state.modalRoot.tree = saved.tree;
        await renderModal();
      }
      refresh();
    } catch (error) {
      draft.error = error.message || 'Could not save. Your draft is still here.';
    } finally {
      draft.saving = false;
      if (draft.input) draft.input.readOnly = false;
      if (state.noteDrafts.get(key) === draft && request === state.modalRequest && database === state.data?.root) {
        renderNoteControls(state.modalCurrent, kind);
      }
      markDraftTabs();
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
    closeHeadingMenu();
    const request = ++state.modalRequest;
    const overlay = document.getElementById('assistantDocumentModal');
    overlay.setAttribute('aria-busy', 'true');
    try {
      const detail = await fetchDocument(kind, path);
      if (request !== state.modalRequest) return;
      state.modalCurrent = detail; state.modalIndex = false;
      if (detail.tree) state.modalRoot.tree = detail.tree;
      if (detail.path === state.modalRoot.path) state.modalRoot = detail;
      await renderModal(focusHeading);
      if (request === state.modalRequest) openDocumentTerminal(detail);
    } catch (error) {
      if (request === state.modalRequest) documentError(error.message || String(error));
    } finally {
      if (request === state.modalRequest) { overlay.removeAttribute('aria-busy'); state.inlinePending = false; }
    }
  }

  async function renderModal(focusHeading = '') {
    if (state.modalRoot?.metadata?.schema === 2 && state.modalRoot.tree && (state.modalRoot.document_tasks || state.modalKind !== 'series' || state.modalRoot.tree.children?.length)) {
      await renderRecordTree(focusHeading); return;
    }
    if (['meeting', 'series'].includes(state.modalKind)) { await renderMeetingModal(); return; }
    document.getElementById('assistantDocumentNav').classList.remove('assistant-series-nav');
    const root = state.modalRoot || state.modalCurrent;
    const detail = state.modalCurrent || root;
    const rootMetadata = root.metadata || {};
    const title = document.getElementById('assistantModalTitle');
    const label = document.getElementById('assistantModalKind');
    const nav = document.getElementById('assistantDocumentNav');
    title.textContent = rootMetadata.title || rootMetadata.id || (state.modalKind === 'meeting' ? 'Meeting note' : 'Task');
    label.textContent = state.modalKind === 'meeting' ? 'Meeting note' : state.modalKind === 'subtask' ? 'Subtab' : 'Document tabs';
    if (state.modalKind === 'task' && Array.isArray(root.subtasks)) {
      nav.innerHTML = `<div class="assistant-document-nav-label">Documents</div>${modalDocumentButton(root, 'Main task', 'task')}${root.subtasks.map(child => modalDocumentButton(child, 'Subtab', 'subtask')).join('')}`;
    } else {
      nav.innerHTML = `<div class="assistant-document-nav-label">Document</div>${modalDocumentButton(root, state.modalKind === 'meeting' ? 'Meeting note' : 'Subtab', state.modalKind)}`;
    }
    nav.querySelectorAll('[data-assistant-modal-document]').forEach(button => {
      button.addEventListener('click', () => selectModalDocument(button.dataset.assistantModalKind, button.dataset.assistantModalDocument));
    });
    const detailKind = state.modalKind === 'meeting' ? 'meeting'
      : state.modalKind === 'subtask' ? 'subtask' : (detail.path === root.path ? 'task' : 'subtask');
    await renderDocumentPane(detail, detailKind, focusHeading);
  }

  async function createRecord(type, parent = null, topLevel = false, trackTask = false) {
    const title = window.prompt(type === 'series' ? 'Meeting series title' : type === 'subtab' ? (trackTask ? 'Task title' : topLevel ? 'Tab title' : 'Subtab title') : type === 'project' ? 'Project name' : type === 'task' ? 'Task title' : 'Document title');
    if (!title?.trim()) return;
    try {
      const response = await fetch('/api/assistant/record', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({type:type === 'series' ? 'note' : type, note_type:type === 'series' ? 'series' : null, track_task:trackTask, title:title.trim(), top_level:topLevel, parent:parent ? {type:parent.type,id:parent.id} : null,
          project:parent?.project || state.project || null, workspace:parent?.workspace || state.workspace || null})});
      const detail = await response.json();
      if (!response.ok) throw new Error(detail.detail || 'Could not create document');
      await refresh();
      if (type !== 'project') await openDocumentModal(type === 'task' ? 'task' : type === 'series' ? 'series' : 'note', detail.path);
    } catch (error) { window.alert(error.message); }
  }

  const TAB_RECENT_MS = 3 * 86400000;

  function tabActivityStore() {
    const key = 'lab.assistant.tab-activity.v1:' + (state.data?.root || '');
    if (state.tabActivity?.key === key) return state.tabActivity;
    let entries = {};
    try {
      const saved = JSON.parse(localStorage.getItem(key) || '{}');
      if (saved && typeof saved === 'object' && !Array.isArray(saved)) entries = saved;
    } catch (_) { /* Keep highlights usable when browser storage is unavailable. */ }
    return state.tabActivity = {key, entries, seen:new Map()};
  }

  function saveTabActivity() {
    const store = tabActivityStore();
    try { localStorage.setItem(store.key, JSON.stringify(store.entries)); } catch (_) { /* Session state still works. */ }
  }

  function tabActivityKey(row) { return JSON.stringify([row.type, row.id || row.path]); }

  function observeTabActivity(row, now) {
    const store = tabActivityStore(), key = tabActivityKey(row);
    const previous = store.entries[key];
    const revision = row.tab_revision || JSON.stringify([row.created, row.updated, row.title, row.description, row.status]);
    // An older open window must not undo a newer window's dismissal when it
    // repaints its cached tree. Observe each revision once per window.
    if (store.seen.get(key) === revision) return false;
    store.seen.set(key, revision);
    const timestamp = value => { const time = Date.parse(value); return Number.isFinite(time) ? Math.min(now, time) : 0; };
    const created = timestamp(row.created), updated = timestamp(row.updated);
    if (!previous || typeof previous !== 'object' || !Number.isFinite(previous.at) || typeof previous.revision !== 'string') {
      store.entries[key] = {revision, at:Math.max(created, updated), kind:created > now - TAB_RECENT_MS ? 'New' : 'Updated', dismissed:false};
      return true;
    }
    if (previous.revision !== revision) {
      // A changed tab revision makes the shared file mtime safe to use, even
      // for direct Markdown edits that did not advance the updated field.
      const modified = Number(row.mtime) * 1000;
      const at = Math.min(now, Math.max(created, updated, Number.isFinite(modified) ? modified : now));
      store.entries[key] = {revision, at, kind:'Updated', dismissed:false};
      return true;
    }
    return false;
  }

  function recentTabActivity(row, now) {
    const activity = tabActivityStore().entries[tabActivityKey(row)];
    return activity && !activity.dismissed && activity.at > 0 && now - activity.at < TAB_RECENT_MS ? activity : null;
  }

  function markRecentTabs() {
    clearTimeout(state.tabActivityTimer);
    const overlay = document.getElementById('assistantDocumentModal');
    if (!state.modalRoot?.tree || state.modalKind === 'series' || !overlay) return;
    const now = Date.now(), rows = new Map();
    let changed = false, expires = Infinity;
    const visit = row => {
      rows.set(row.path, row);
      changed = observeTabActivity(row, now) || changed;
      const activity = recentTabActivity(row, now);
      if (activity) expires = Math.min(expires, activity.at + TAB_RECENT_MS);
      (row.children || []).forEach(visit);
    };
    visit(state.modalRoot.tree);
    if (changed) saveTabActivity();
    overlay.querySelectorAll('[data-tab-activity]').forEach(badge => {
      const row = rows.get(badge.dataset.tabActivity);
      const activity = row && recentTabActivity(row, now);
      badge.hidden = !activity;
      badge.setAttribute('aria-label', activity?.kind || 'No recent changes');
      badge.dataset.activityKind = activity?.kind || '';
      badge.title = activity ? `${activity.kind} · ${new Date(activity.at).toLocaleString()} · Highlight clears after 3 days or when dismissed` : '';
      badge.closest('[data-record-path]')?.classList.toggle('has-recent-activity', Boolean(activity));
    });
    overlay.querySelectorAll('[data-dismiss-tab-activity]').forEach(button => {
      const row = rows.get(button.dataset.dismissTabActivity);
      button.hidden = !row || !recentTabActivity(row, now);
    });
    if (Number.isFinite(expires)) state.tabActivityTimer = setTimeout(markRecentTabs, Math.max(25, expires - now + 25));
  }

  function dismissTabActivity(row) {
    const activity = tabActivityStore().entries[tabActivityKey(row)];
    if (!activity) return;
    activity.dismissed = true;
    saveTabActivity();
    markRecentTabs();
  }

  function tabActivityBadge(row) {
    return `<small class="assistant-tab-activity" role="img" data-tab-activity="${e(row.path)}" hidden></small>`;
  }

  function documentTabs(tree) {
    const children = tree.children || [];
    return [{...tree, children:children.filter(row => !row.top_level)}, ...children.filter(row => row.top_level)];
  }

  function seriesNavigation(root, documentHtml = '') {
    const overview = state.modalKind === 'series';
    const metadata = root.metadata || {};
    const id = overview ? metadata.id : metadata.series;
    const series = overview ? {...metadata, path:root.path}
      : (state.data?.meeting_series || []).find(row => row.id === id &&
          (metadata.schema === 2 || row.workspace === metadata.workspace))
        || (root.series && (metadata.schema !== 2 || root.series.id === id) ? root.series : null);
    if (!series) return null;
    // Series membership is independent of list filters and document-tab parents.
    const indexed = state.data?.documents || [...(state.data?.meetings || []), ...(state.data?.notes || [])];
    let rows = indexed.filter(row => !row.parent && (row.series_path ? row.series_path === series.path
      : row.series === series.id && (metadata.schema === 2 || row.workspace === series.workspace)));
    if (!Array.isArray(state.data?.documents) && !Array.isArray(state.data?.meetings)) rows = series.meetings || root.meetings || [];
    if (!overview) {
      const current = rows.find(row => row.path === root.path) || {};
      rows = [...rows.filter(row => row.path !== root.path), {...current, ...metadata, path:root.path, status:root.progress?.status ?? current.status ?? metadata.status, tracked:root.progress?.tracked ?? current.tracked}];
    }
    rows = sortedMeetings(rows);
    const signature = JSON.stringify([series.path, series.title, series.starred, series.external_url, overview ? null : root.path,
      rows.map(row => [row.path,row.title,row.date,row.source,row.tags,row.note_type,row.starred,row.status,row.tracked,row.external_url])]);
    const title = `<button type="button" class="assistant-series-overview${overview ? ' active' : ''}" data-assistant-series="${e(series.path)}"${overview ? ' aria-current="page"' : ''} title="${e(series.title)}"><span aria-hidden="true">▤</span><span>${e(series.title)}</span></button>`;
    const history = rows.map(row => {
      const current = !overview && row.path === root.path;
      const kind = row.note_type && row.note_type !== 'meeting' ? 'note' : 'meeting';
      return `<li data-series-history data-series-search="${e([row.date,row.title].join(' ').toLowerCase())}" data-series-starred="${row.starred === true}" data-series-open="${row.tracked === true && !['done','skipped','cancelled'].includes(row.status)}"><button type="button" class="assistant-series-meeting${current ? ' current' : ''}" data-series-document="${e(row.path)}" data-series-kind="${kind}"${current ? ' aria-current="page"' : ''} title="${e(row.title)}"><span aria-hidden="true">${current ? '✓' : ''}</span><span><time>${e(calendarDate(row.date) || 'No date')}</time><span class="assistant-series-meeting-title">${e(row.title || 'Untitled note')}</span></span>${row.source === 'demo' || (row.tags || []).includes('demo') ? '<small class="assistant-demo">Demo</small>' : ''}</button>${externalDocument(row, true)}</li>`;
    }).join('') || '<li class="assistant-nav-empty">No notes yet.</li>';
    return {signature, html:`<div class="assistant-series-header">${title}${externalDocument(series, true)}${metadata.schema === 2 ? starButton(series, 'series') : ''}<button type="button" class="assistant-series-toggle" data-series-toggle popovertarget="assistantSeriesMenu" aria-controls="assistantSeriesMenu" aria-expanded="false">More in this series <span aria-hidden="true">⌄</span></button></div>
      <div id="assistantSeriesMenu" class="assistant-series-menu" popover="auto" data-series-root="${e(root.path)}" data-series-id="${e(series.id)}"><div class="assistant-document-nav-label">Notes in this series</div><div class="assistant-series-filters"><input type="search" id="assistantSeriesSearch" aria-label="Filter series dates or titles" placeholder="Filter dates or titles…"><select id="assistantSeriesFilter" aria-label="Filter series notes"><option value="">All dates</option><option value="starred">Starred notes</option><option value="open">Open tasks</option></select></div><p class="assistant-nav-empty" data-series-empty hidden>No dates match this filter.</p><ul class="assistant-series-meetings" aria-label="Notes in this series">${history}</ul></div>${documentHtml}`};
  }

  function closeSeriesMenu(restoreFocus = false) {
    const menu = document.getElementById('assistantSeriesMenu');
    if (!menu?.matches(':popover-open')) return;
    menu.hidePopover();
    if (restoreFocus) document.querySelector('[data-series-toggle]')?.focus({preventScroll:true});
  }

  function bindSeriesNavigation(nav) {
    bindSeries(nav);
    bindStars(nav);
    const menu = nav.querySelector('#assistantSeriesMenu');
    const toggle = nav.querySelector('[data-series-toggle]');
    const search = menu.querySelector('#assistantSeriesSearch');
    const filter = menu.querySelector('#assistantSeriesFilter');
    const previous = state.seriesFilters.get(menu.dataset.seriesId) || {search:'',filter:''};
    search.value = previous.search; filter.value = previous.filter;
    const apply = () => {
      state.seriesFilters.set(menu.dataset.seriesId, {search:search.value,filter:filter.value});
      let count = 0;
      menu.querySelectorAll('[data-series-history]').forEach(row => {
        row.hidden = !row.dataset.seriesSearch.includes(search.value.trim().toLowerCase())
          || filter.value === 'starred' && row.dataset.seriesStarred !== 'true'
          || filter.value === 'open' && row.dataset.seriesOpen !== 'true';
        if (!row.hidden) count++;
      });
      menu.querySelector('[data-series-empty]').hidden = count > 0;
    };
    search.addEventListener('input', apply); filter.addEventListener('change', apply); apply();
    menu.addEventListener('beforetoggle', event => {
      toggle.setAttribute('aria-expanded', String(event.newState === 'open'));
      if (event.newState !== 'open') return;
      const anchor = toggle.getBoundingClientRect();
      const width = Math.min(320, Math.max(240, nav.clientWidth - 18), window.innerWidth - 16);
      const below = window.innerHeight - anchor.bottom - 12;
      const above = anchor.top - 12;
      const placeAbove = below < 180 && above > below;
      menu.style.width = width + 'px';
      menu.style.left = Math.max(8, Math.min(anchor.left, window.innerWidth - width - 8)) + 'px';
      menu.style.top = placeAbove ? 'auto' : (anchor.bottom + 4) + 'px';
      menu.style.bottom = placeAbove ? (window.innerHeight - anchor.top + 4) + 'px' : 'auto';
      menu.style.maxHeight = Math.max(80, Math.min(420, placeAbove ? above : below)) + 'px';
    });
    toggle.addEventListener('keydown', event => {
      if (!['ArrowDown','ArrowUp'].includes(event.key)) return;
      event.preventDefault();
      menu.showPopover();
      const rows = [...menu.querySelectorAll('li:not([hidden]) [data-series-document]')];
      (event.key === 'ArrowUp' ? rows.at(-1) : rows[0])?.focus();
    });
    menu.addEventListener('keydown', event => {
      if (['INPUT','SELECT'].includes(event.target.tagName)) return;
      if (!['ArrowDown','ArrowUp','Home','End'].includes(event.key)) return;
      event.preventDefault();
      const rows = [...menu.querySelectorAll('li:not([hidden]) [data-series-document]')];
      const index = rows.indexOf(document.activeElement);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? rows.length - 1
        : (index + (event.key === 'ArrowDown' ? 1 : -1) + rows.length) % rows.length;
      rows[next]?.focus();
    });
    nav.querySelectorAll('[data-series-document]').forEach(button => button.addEventListener('click', async () => {
      closeSeriesMenu(true);
      selectEntry(button.dataset.seriesKind, button.dataset.seriesDocument, true);
      await openDocumentModal(button.dataset.seriesKind, button.dataset.seriesDocument);
      if (state.modalRoot?.path === button.dataset.seriesDocument) {
        nav.querySelector('[data-record-index].active, [data-record-path].active')?.focus({preventScroll:true});
      }
    }));
  }

  function replaceSeriesNavigation(nav, html) {
    const previous = nav.querySelector('#assistantSeriesMenu:popover-open');
    const current = previous?.dataset.seriesRoot;
    const scroll = previous?.scrollTop;
    const active = previous?.contains(document.activeElement) ? document.activeElement : null;
    const focused = active?.dataset.seriesDocument;
    const inputId = active?.id;
    const selection = active?.tagName === 'INPUT' ? [active.selectionStart,active.selectionEnd] : null;
    nav.innerHTML = html;
    if (!nav.querySelector('[data-series-toggle]')) return;
    bindSeriesNavigation(nav);
    const menu = nav.querySelector('#assistantSeriesMenu');
    if (current === menu.dataset.seriesRoot) {
      menu.showPopover(); menu.scrollTop = scroll;
      const next = inputId ? document.getElementById(inputId) : [...menu.querySelectorAll('[data-series-document]')].find(row => row.dataset.seriesDocument === focused);
      next?.focus({preventScroll:true});
      if (selection?.[0] != null) next?.setSelectionRange?.(...selection);
    }
  }

  function documentTabKey(root) {
    return 'lab.assistant.last-tab.v1:' + (state.data?.root || window.ASSISTANT_ROOT || '') + ':' + root.metadata.id;
  }

  function rememberedDocumentTab(root) {
    try {
      const saved=localStorage.getItem(documentTabKey(root));
      if (saved) return saved;
      const previous=JSON.parse(localStorage.getItem('lab.assistant.poc.v1:' + (state.data?.root || '') + ':' + root.metadata.id + ':tab'));
      return previous === 'dashboard' ? 'index' : previous ? root.path + '#tab=' + previous : null;
    } catch (_) { return null; }
  }

  async function renderRecordTree(focusHeading = '') {
    const root = state.modalRoot;
    const detail = state.modalCurrent;
    const request=state.modalRequest;
    if (root.document_tasks) await ensureDocumentTasks();
    if (request !== state.modalRequest) return;
    try { localStorage.setItem(documentTabKey(root), state.modalIndex ? 'index' : detail.path); } catch (_) {}
    const nav = document.getElementById('assistantDocumentNav');
    const rows = new Map();
    const node = row => {
      rows.set(row.path, row);
      return `<li><div class="assistant-record-tab-row"><button type="button" class="assistant-record-tab${detail.path === row.path ? ' active' : ''}" data-record-path="${e(row.path)}" data-record-kind="${e(row.kind)}" title="${e(row.title)}"><span aria-hidden="true">▤</span><span class="assistant-record-title">${e(row.title)}</span>${tabActivityBadge(row)}${root.document_tasks && row.task_summary?.wip ? '<small class="assistant-work-status wip">WIP</small>' : ''}</button>${externalDocument(row, true)}<details class="assistant-tab-menu"><summary aria-label="Options for ${e(row.title)}">⋮</summary><div><button type="button" data-record-subtab="${e(row.path)}">+ Add subtab</button><button type="button" data-record-task="${e(row.path)}">+ Add task</button><button type="button" data-dismiss-tab-activity="${e(row.path)}" hidden>Dismiss highlight</button></div></details></div>${row.children?.length ? `<ul>${row.children.map(node).join('')}</ul>` : ''}</li>`;
    };
    const tree = documentTabs(root.tree).map(node).join('');
    const indexTab = root.tree.children?.length || root.document_tasks ? '<button type="button" class="assistant-record-tab assistant-index-tab" data-record-index><span aria-hidden="true">☷</span><span>' + (root.document_tasks ? 'Dashboard' : 'Index') + '</span></button>' : '';
    const html = `<div class="assistant-tabs-heading"><span>Document tabs</span><button type="button" data-record-root-tab aria-label="Add tab" title="Add tab">+</button></div>${indexTab}<ul class="assistant-record-tree">${tree}</ul>
      ${root.raw ? `<button type="button" class="assistant-record-tab" data-record-raw="${e(root.raw.path)}">Original notes</button>` : ''}`;
    // Keep existing tab elements and keyboard focus when only selection changes.
    const series = seriesNavigation(root, html);
    const structure = JSON.stringify([root.tree, series?.signature]);
    nav.classList.toggle('assistant-series-nav', Boolean(series));
    if (nav.dataset.structure !== structure || !nav.querySelector('.assistant-record-tree')) {
      const scroll = nav.scrollTop;
      replaceSeriesNavigation(nav, series?.html || html);
      nav.dataset.structure = structure; nav.scrollTop = scroll;
      nav.querySelector('[data-record-root-tab]')?.addEventListener('click', () => createRecord('subtab', root.tree, true));
      nav.querySelector('[data-record-index]')?.addEventListener('click', () => {
        ++state.modalRequest; state.modalIndex = true; state.modalCurrent = state.modalRoot;
        document.getElementById('assistantDocumentModal').removeAttribute('aria-busy');
        renderRecordTree();
      });
      nav.querySelectorAll('[data-record-path]').forEach(button => button.addEventListener('click', () => selectModalDocument(button.dataset.recordKind, button.dataset.recordPath)));
      nav.querySelectorAll('[data-dismiss-tab-activity]').forEach(button => button.addEventListener('click', () => {
        const menu = button.closest('details');
        menu.open = false; menu.querySelector('summary').focus();
        dismissTabActivity(rows.get(button.dataset.dismissTabActivity));
      }));
      nav.querySelectorAll('[data-record-task]').forEach(button => button.addEventListener('click', () => {
        nav.querySelectorAll('details[open]').forEach(menu => { menu.open = false; });
        if (root.document_tasks) {
          const row=rows.get(button.dataset.recordTask);
          selectModalDocument(row.kind,row.path).then(()=>window.AssistantTasks.add());
        } else createRecord('subtab', rows.get(button.dataset.recordTask), false, true);
      }));
      nav.querySelectorAll('[data-record-subtab]').forEach(button => button.addEventListener('click', () => {
        nav.querySelectorAll('details[open]').forEach(menu => { menu.open = false; });
        createRecord('subtab', rows.get(button.dataset.recordSubtab));
      }));
    }
    nav.querySelectorAll('[data-record-path]').forEach(button => button.classList.toggle('active', !state.modalIndex && button.dataset.recordPath === detail.path));
    nav.querySelector('[data-record-index]')?.classList.toggle('active', state.modalIndex);
    markDraftTabs();
    markRecentTabs();
    const rawButton = nav.querySelector('[data-record-raw]');
    if (rawButton) rawButton.onclick = async event => {
      const request = ++state.modalRequest;
      const raw = await fetchDocument('content', event.currentTarget.dataset.recordRaw);
      if (request !== state.modalRequest) return;
      state.modalIndex = false;
      const currentHost = document.getElementById('assistantModalDocument');
      if (state.currentPane && currentHost.contains(state.currentPane.node)) state.currentPane.scrollTop = currentHost.scrollTop;
      renderDocumentHeader(root, 'meeting');
      const host = document.getElementById('assistantModalDocument');
      host.innerHTML = '<pre class="assistant-raw-notes"></pre>';
      host.querySelector('pre').textContent = raw.body;
      resetCopy(true); document.getElementById('assistantCopyRich').disabled = true;
      document.getElementById('assistantCopyPlain').onclick = async event => {
        const button = event.currentTarget;
        try { await navigator.clipboard.writeText(raw.body); button.textContent = 'Copied'; }
        catch (_) { button.textContent = 'Copy failed'; }
      };
    };
    if (state.modalIndex && (root.tree.children?.length || root.document_tasks)) { renderIndex(root); return; }
    const kind = documentKind(detail.metadata);
    await renderDocumentPane(detail, kind, focusHeading);
  }


  function renderIndex(root) {
    if (root.document_tasks) { renderTaskDashboard(root); return; }
    const host = document.getElementById('assistantModalDocument');
    renderDocumentHeader(root, documentKind(root.metadata));
    if (state.currentPane && host.contains(state.currentPane.node)) state.currentPane.scrollTop = host.scrollTop;
    const body = JSON.stringify(root.tree);
    const cacheKey = root.path + ':index';
    let pane = state.paneCache.get(cacheKey);
    if (!pane || pane.body !== body) {
      const rows = [];
      const visit = (row, depth) => {
        rows.push(`<tr data-index-path="${e(row.path)}" data-index-kind="${e(row.kind)}" tabindex="0" aria-label="Open ${e(row.title)}">
          <td><button type="button" style="padding-inline-start:${depth * 20}px" data-index-open><span aria-hidden="true">${depth ? '↳' : '▤'}</span> ${e(row.title)} ${tabActivityBadge(row)}</button><div class="assistant-index-description" style="padding-inline-start:${depth * 20}px" title="${e(row.description)}">${e(row.description || '—')}</div></td>
          <td>${row.progress?.tracked === false ? '—' : e(labelStatus(row.progress?.status || row.status || 'not_started'))}</td>
          <td>${e(displayDate(row.due) || '—')}</td><td>${e(row.priority || '—')}</td><td>${e(row.owner || '—')}</td><td>${externalDocument(row)}</td></tr>`);
        (row.children || []).forEach(child => visit(child, depth + 1));
      };
      documentTabs(root.tree).forEach(row => visit(row, 0));
      const node = document.createElement('section'); node.className = 'assistant-index';
      node.innerHTML = `<h2>Index</h2><div class="assistant-index-scroll"><table><thead><tr><th scope="col">Tab / Description</th><th scope="col">Status</th><th scope="col">Due</th><th scope="col">Priority</th><th scope="col">POC</th><th scope="col">Document</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
      node.querySelectorAll('[data-index-path]').forEach(row => {
        const open = () => selectModalDocument(row.dataset.indexKind, row.dataset.indexPath);
        row.addEventListener('click', event => { if (!event.target.closest('a')) open(); });
        row.addEventListener('keydown', event => {
          if (event.target === row && ['Enter',' '].includes(event.key)) { event.preventDefault(); open(); }
        });
      });
      pane = {node,body,scrollTop:pane?.scrollTop || 0};
      state.paneCache.set(cacheKey,pane);
    }
    host.replaceChildren(pane.node); host.scrollTop = pane.scrollTop; state.currentPane = pane;
    markRecentTabs();
    resetCopy(true);
    document.getElementById('assistantCopyPlain').onclick = event => window.LabMarkdown.copy(pane.node,{button:event.currentTarget,plainOnly:true});
    document.getElementById('assistantCopyRich').onclick = event => window.LabMarkdown.copy(pane.node,{button:event.currentTarget});
  }

  function mountDocumentTasks(host, tab) {
    const root=state.modalRoot;
    if (!root.document_tasks) return;
    window.LabDocumentTerminal?.updateRoot(root);
    let taskHost=host.querySelector(':scope > [data-document-tasks]');
    if (!taskHost) { taskHost=document.createElement('div');taskHost.dataset.documentTasks='';host.prepend(taskHost); }
    window.AssistantTasks.mount(taskHost,{database:state.data.root,root,tab,
      navigate:id=>{ const find=row=>row.id===id ? row : (row.children || []).map(find).find(Boolean); const row=find(state.modalRoot.tree); if(row) return selectModalDocument(row.kind,row.path); },
      changed:async saved=>{
        if (state.modalRoot?.path !== saved.path) return;
        const request=state.modalRequest, current=state.modalCurrent;
        const updated=await fetchDocument(state.modalKind,saved.path);
        const detail=current.path === saved.path ? updated : await fetchDocument(documentKind(current.metadata),current.path);
        if (request !== state.modalRequest || state.modalRoot?.path !== saved.path) return;
        state.modalRoot=updated;state.modalCurrent=detail;
        await renderRecordTree();
        await refresh();
      }});
  }

  function renderTaskDashboard(root) {
    const host=document.getElementById('assistantModalDocument');
    renderDocumentHeader(root,documentKind(root.metadata));
    const rows=[];
    const visit=(row,depth)=>{
      rows.push(`<li><button type="button" data-tab-dashboard-path="${e(row.path)}" data-kind="${e(row.kind)}" style="padding-left:${12+depth*18}px"><span>▤ ${e(row.title)}</span><small>${row.task_summary?.pending ? row.task_summary.pending + ' pending' : 'No pending tasks'}</small></button></li>`);
      (row.children || []).forEach(child=>visit(child,depth+1));
    };
    documentTabs(root.tree).forEach(row=>visit(row,0));
    host.innerHTML=`<section class="assistant-task-dashboard"><h2>Tabs</h2><ul class="assistant-task-dashboard-tabs">${rows.join('')}</ul></section>`;
    mountDocumentTasks(host,'dashboard');
    host.querySelectorAll('[data-tab-dashboard-path]').forEach(button=>button.onclick=()=>selectModalDocument(button.dataset.kind,button.dataset.tabDashboardPath));
    state.currentPane=null;
    resetCopy(true);
    document.getElementById('assistantCopyPlain').onclick=event=>window.LabMarkdown.copy(host,{button:event.currentTarget,plainOnly:true});
    document.getElementById('assistantCopyRich').onclick=event=>window.LabMarkdown.copy(host,{button:event.currentTarget});
  }

  async function renderDocumentPane(detail, kind, focusHeading = '') {
    const request = state.modalRequest;
    if (typeof window.ensureMarked === 'function') await window.ensureMarked().catch(() => {});
    if (request !== state.modalRequest) return;
    const draft = noteDraft(detail);
    if (draft && !dirtyDraft(draft) && !draft.saving && draft.base !== (detail.body || '')) {
      draft.base = draft.body = detail.body || ''; draft.saved = false;
      if (draft.input) { draft.input.value = draft.body; markNoteChanges(draft); }
    }
    const body = draft ? draft.body : detail.body || '';
    const host = document.getElementById('assistantModalDocument');
    renderDocumentHeader(detail, kind);
    if (draft?.editing) {
      resetCopy(true);
      mountNoteEditor(draft, detail, kind, host);
      mountDocumentTasks(host,detail.metadata.id);
      renderNoteControls(detail, kind);
      return;
    }
    if (state.currentPane && host.contains(state.currentPane.node)) state.currentPane.scrollTop = host.scrollTop;
    const cacheKey = detail.path + ':' + kind;
    let pane = state.paneCache.get(cacheKey);
    if (!pane || pane.body !== body) {
      const node = document.createElement('div');
      node.className = 'nb-markdown assistant-markdown'; node.id = 'assistantModalMarkdown';
      node.innerHTML = window.marked && window.DOMPurify ? window.LabMarkdown.render(body) : `<pre>${e(body)}</pre>`;
      rewriteImages(node, detail.path); bindHeadingCopyMenu(node);
      pane = {node, body, scrollTop:0};
    }
    state.paneCache.delete(cacheKey); state.paneCache.set(cacheKey, pane);
    while (state.paneCache.size > 20) state.paneCache.delete(state.paneCache.keys().next().value);
    if (host.firstElementChild !== pane.node || host.children.length !== 1) host.replaceChildren(pane.node);
    mountDocumentTasks(host,detail.metadata.id);
    host.scrollTop = pane.scrollTop;
    state.currentPane = pane;
    const markdownHost = pane.node;
    resetCopy(true);
    document.getElementById('assistantCopyPlain').onclick = event => window.LabMarkdown.copy(markdownHost, {button: event.currentTarget, plainOnly: true});
    document.getElementById('assistantCopyRich').onclick = event => window.LabMarkdown.copy(markdownHost, {button: event.currentTarget});
    renderNoteControls(detail, kind);
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
    hideNoteControls();
    if (!enabled) document.getElementById('assistantModalMetadata')?.replaceChildren();
    for (const id of ['assistantCopyPlain', 'assistantCopyRich']) {
      const button = document.getElementById(id);
      if (button) { button.disabled = !enabled; button.onclick = null; }
    }
    const plain = document.getElementById('assistantCopyPlain');
    if (plain) plain.textContent = 'Copy plain text';
  }

  function bindSeries(host) {
    host.querySelectorAll('[data-assistant-series]').forEach(button => bindDocumentLink(button, options => {
      const path = button.dataset.assistantSeries;
      const url = new URL(window.location);
      url.searchParams.set('view', 'assistant'); url.searchParams.set('subview', state.data?.documents ? 'documents' : 'notes');
      url.searchParams.set('series', path); url.searchParams.delete('meeting'); url.searchParams.delete('task'); url.searchParams.delete('note');
      url.searchParams.delete('assistant_workspace');
      history.pushState({nav:'assistant', series:path}, '', url.pathname + url.search + url.hash);
      state.selectedSeriesPath = path; state.selectedMeetingPath = ''; state.selectedTaskPath = '';
      openDocumentModal('series', path, '', options);
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
    if (!series) nav.classList.remove('assistant-series-nav');
    const partButton = (part, title, subtitle = '') => `<button type="button" class="assistant-document-nav-item${state.modalMeetingPart === part ? ' active' : ''}" data-meeting-part="${e(part)}"><span class="assistant-document-type">${part.endsWith('raw.txt') ? 'TXT' : 'MD'}</span><span><strong>${e(title)}</strong><small>${e(subtitle)}</small></span></button>`;
    if (series) {
      const navigation = seriesNavigation(root);
      nav.classList.add('assistant-series-nav');
      replaceSeriesNavigation(nav, navigation.html);
      delete nav.dataset.structure;
      nav.dataset.seriesStructure = navigation.signature;
      await renderDocumentPane(root, 'series');
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
      if (!series || surface !== nav) bindSeries(surface);
    }
  }

  function closeHeadingMenu(restoreFocus = false) {
    const current = state.headingMenu;
    if (!current) return;
    state.headingMenu = null;
    current.listeners.abort();
    current.menu.remove();
    if (restoreFocus && current.heading.isConnected) current.heading.focus({preventScroll:true});
  }

  function openHeadingMenu(event, host, heading) {
    event.preventDefault();
    event.stopPropagation();
    closeHeadingMenu();
    window.closeExplorerContextMenu?.();
    const menu = document.createElement('div');
    menu.className = 'explorer-context-menu open assistant-heading-menu';
    menu.setAttribute('role', 'menu');
    menu.setAttribute('aria-label', 'Section actions');
    const copy = document.createElement('button');
    copy.type = 'button';
    copy.setAttribute('role', 'menuitem');
    copy.textContent = 'Copy content';
    copy.addEventListener('click', async () => {
      const request = state.modalRequest;
      // Use the same rich clipboard payload as Copy for Google Docs. The helper
      // snapshots this exact section before any asynchronous image loading.
      const result = window.LabMarkdown.copy(host, {
        heading, includeHeading: heading.textContent.trim().toLowerCase() !== 'generate content',
      });
      closeHeadingMenu(true);
      const message = document.querySelector('#assistantModalMetadata .assistant-metadata-message');
      if (message) message.textContent = 'Copying…';
      const copied = await result;
      if (request === state.modalRequest && message?.isConnected) message.textContent = copied ? 'Copied' : 'Copy failed';
    });
    menu.appendChild(copy);
    // Keep the menu inside the dialog's accessible subtree, outside its scroller.
    document.getElementById('assistantDocumentModal').appendChild(menu);
    const keyboard = event.type === 'keydown' || (!event.clientX && !event.clientY);
    const anchor = heading.getBoundingClientRect();
    const x = keyboard ? anchor.left : event.clientX;
    const y = keyboard ? anchor.bottom : event.clientY;
    menu.style.left = Math.max(8, Math.min(x, window.innerWidth - menu.offsetWidth - 8)) + 'px';
    menu.style.top = Math.max(8, Math.min(y, window.innerHeight - menu.offsetHeight - 8)) + 'px';
    const listeners = new AbortController();
    state.headingMenu = {menu, heading, listeners};
    const outside = event => { if (!menu.contains(event.target)) closeHeadingMenu(); };
    document.addEventListener('pointerdown', outside, {capture:true, signal:listeners.signal});
    document.addEventListener('contextmenu', outside, {capture:true, signal:listeners.signal});
    document.addEventListener('scroll', () => closeHeadingMenu(), {capture:true, signal:listeners.signal});
    window.addEventListener('resize', () => closeHeadingMenu(), {signal:listeners.signal});
    menu.addEventListener('keydown', event => {
      if (['INPUT','SELECT'].includes(event.target.tagName)) return;
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); closeHeadingMenu(true); return; }
      if (event.key === 'Tab') closeHeadingMenu(true);
      if (['ArrowDown','ArrowUp','Home','End'].includes(event.key)) { event.preventDefault(); copy.focus(); }
    });
    copy.focus({preventScroll:true});
  }

  function bindHeadingCopyMenu(host) {
    host.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(heading => {
      heading.tabIndex = 0;
      heading.setAttribute('aria-haspopup', 'menu');
      heading.setAttribute('aria-keyshortcuts', 'Shift+F10');
      heading.addEventListener('contextmenu', event => openHeadingMenu(event, host, heading));
      heading.addEventListener('keydown', event => {
        if (event.key === 'ContextMenu' || event.key === 'F10' && event.shiftKey) openHeadingMenu(event, host, heading);
      });
    });
  }

  async function refreshOpenDocument() {
    const overlay = document.getElementById('assistantDocumentModal');
    const root = state.modalRoot;
    if (!overlay?.classList.contains('active') || !root || overlay.hasAttribute('aria-busy')) return;
    // Preserve drafts and their selection across background refreshes.
    const draft = noteDraft();
    if (draft && (draft.editing || dirtyDraft(draft) || draft.saving)) return;
    // Do not interrupt a property being edited or saved.
    const bar = document.getElementById('assistantModalMetadata');
    if (bar.contains(document.activeElement) || bar.querySelector('[data-metadata-field]:disabled')) return;
    if (window.AssistantTasks?.busy() || window.AssistantTasks?.editing()) return;
    if (state.modalKind === 'series' && !root.document_tasks) {
      const navigation = seriesNavigation(root);
      if (document.getElementById('assistantDocumentNav').dataset.seriesStructure !== navigation.signature) await renderMeetingModal();
      return;
    }
    if (!root.tree) return;
    const latest = (state.data.documents || [...tasks(), ...(state.data.notes || []), ...meetings()]).find(row => row.path === root.path);
    if (!latest || Number(latest.mtime) === Number(root.tree.mtime)) {
      const navigation = seriesNavigation(root);
      const signature = JSON.stringify([root.tree, navigation?.signature]);
      if (document.getElementById('assistantDocumentNav').dataset.structure !== signature) await renderRecordTree();
      return;
    }
    const request = state.modalRequest;
    const current = state.modalCurrent;
    try {
      const nextRoot = await fetchDocument(state.modalKind, root.path);
      const nextCurrent = current.path === root.path ? nextRoot : await fetchDocument(current.metadata.type === 'task' ? 'task' : 'note',current.path);
      if (request !== state.modalRequest || bar.contains(document.activeElement) || bar.querySelector('[data-metadata-field]:disabled')) return;
      state.modalRoot = nextRoot; state.modalCurrent = nextCurrent;
      await renderModal();
    } catch (_) { /* Keep the last good pane while external edits are incomplete. */ }
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
      if (section === 'notes' && data.schema !== 2 && data.exists && data.root) {
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
      }
      const available = workspaceRows();
      if (isTaskSection() && state.workspace && !available.some(workspace => workspace.id === state.workspace)) state.workspace = '';
      render();
      if (options.open && section === state.section) {
        if (isTaskSection() && state.selectedTaskPath) await openDocumentModal('task', state.selectedTaskPath);
        else if (state.selectedMeetingPath) await openDocumentModal('meeting', state.selectedMeetingPath);
        else if (state.selectedSeriesPath) await openDocumentModal('series', state.selectedSeriesPath);
        else if (new URL(window.location).searchParams.get('poc_document')) {
          const url=new URL(window.location), id=url.searchParams.get('poc_document'), tab=url.searchParams.get('poc_tab');
          const row=state.data.documents.find(item=>item.id===id);
          if(row) await openDocumentModal(documentKind(row),row.path+(tab && tab !== 'dashboard' ? '#tab='+encodeURIComponent(tab) : ''));
          url.searchParams.delete('poc_document');url.searchParams.delete('poc_tab');url.searchParams.set('subview','documents');history.replaceState(history.state,'',url.pathname+url.search+url.hash);
        }
        else if (new URL(window.location).searchParams.get('note')) await openDocumentModal('note', new URL(window.location).searchParams.get('note'));
      } else await refreshOpenDocument();
    } catch (error) {
      const content = document.getElementById('content');
      if (content && request === state.request && !state.data) content.innerHTML = `<div class="assistant-setup"><h1>Assistant</h1><p>${e(error.message || error)}</p></div>`;
    }
  }

  function init(initial = '') {
    closeDocumentModal(false);
    const options = typeof initial === 'object' && initial !== null ? initial : {task: initial};
    state.section = ['notes', 'meetings'].includes(options.section) ? 'notes' : options.section === 'tasks' ? 'tasks' : 'documents';
    state.selectedTaskPath = options.task || '';
    state.selectedSubtaskPath = '';
    state.selectedMeetingPath = options.meeting || '';
    state.selectedSeriesPath = options.series || '';
    state.view = state.section === 'documents' ? 'dashboard' : isTaskSection() ? 'all_open' : 'meetings';
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

  window.addEventListener('storage', event => {
    if (event.key === null || event.key === state.tabActivity?.key) {
      const seen = state.tabActivity?.seen;
      state.tabActivity = null;
      if (event.key !== null && seen) tabActivityStore().seen = seen;
      if (document.getElementById('assistantDocumentModal')?.classList.contains('active')) markRecentTabs();
    }
  });

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && document.getElementById('assistantDocumentModal')?.classList.contains('active')) markRecentTabs();
  });

  window.addEventListener('beforeunload', event => {
    if ([...state.noteDrafts.values()].some(dirtyDraft)) {
      event.preventDefault(); event.returnValue = '';
    }
  });

  document.addEventListener('keydown', event => {
    if (document.getElementById('assistantAttributesEditor')?.open || document.getElementById('documentTerminalSettings')?.open) return;
    if (event.target.closest?.('.assistant-terminal-screen')) return;
    const overlay = document.getElementById('assistantDocumentModal');
    if (event.key === 'Escape' && overlay && overlay.classList.contains('active')) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (state.headingMenu) { closeHeadingMenu(true); return; }
      if (document.querySelector('#assistantSeriesMenu:popover-open')) { closeSeriesMenu(true); return; }
      const copyMenu = overlay.querySelector('.assistant-copy-menu[open]');
      if (copyMenu) { copyMenu.open = false; copyMenu.querySelector('summary').focus(); return; }
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
    bindDocumentLink,
    openLinkedTask,
    closeDocument: closeDocumentModal,
    closeInlineDocument: () => { if (state.inlineHost || state.inlinePending || state.documentClickTimer) closeDocumentModal(false); },
    isInlineDocument: () => Boolean(state.inlineHost),
  };
})();
