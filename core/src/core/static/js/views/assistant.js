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
    project: '',
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
    renderedList: '',
    paneCache: new Map(),
    currentPane: null,
    modalIndex: false,
    headingMenu: null,
    noteDrafts: new Map(),
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

  function filteredTasks({workspace = state.workspace} = {}) {
    const needle = state.search.trim().toLowerCase();
    return tasks().filter(task => {
      if (state.view === 'recent' && !isRecentDone(task)) return false;
      if (state.view === 'cancelled' && task.status !== 'cancelled') return false;
      if (!['recent','cancelled'].includes(state.view) && ['done','skipped','cancelled'].includes(task.status)) return false;
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
      button.classList.toggle('active', button.dataset.assistantSection === state.section);
    });
  }

  function setSection(section, options = {}) {
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
    const title = isTaskSection() ? 'Tasks' : 'Notes';
    const body = isTaskSection() ? renderTasks(rows) : renderNotes(rows);
    const html = `<div class="assistant-shell assistant-minimal-shell assistant-layout-${e(state.section)}">
      <header class="assistant-head">
        <h1>${e(title)}</h1>
        <span>${state.data?.schema === 2 ? `<button type="button" class="refresh-btn" data-new-record="${isTaskSection() ? 'task' : 'note'}">+ ${isTaskSection() ? 'Task' : 'Note'}</button> <button type="button" class="refresh-btn" data-new-record="project">+ Project</button> ` : ''}<button type="button" class="refresh-btn" id="assistantRefresh">Refresh</button></span>
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
      button.addEventListener('click', () => {
        if (state.data?.schema === 2) openDocumentModal('note', button.dataset.assistantNote);
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
    state.selectedTaskPath = kind === 'task' ? path || '' : '';
    state.selectedMeetingPath = kind === 'meeting' ? path || '' : '';
    state.selectedSeriesPath = '';
    if (push) {
      const url = new URL(window.location);
      url.searchParams.set('view', 'assistant');
      url.searchParams.delete('series');
      url.searchParams.delete('note');
      if (kind === 'task') {
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
        <div class="assistant-modal-actions"><span id="assistantNoteStatus" class="assistant-note-status" role="status" aria-live="polite" hidden></span><button type="button" id="assistantEditNote" hidden>Edit</button><button type="button" id="assistantSaveNote" hidden>Save</button><button type="button" id="assistantRevertNote" hidden>Discard</button><button type="button" id="assistantCopyRich">Copy for Google Docs</button><button type="button" id="assistantCopyPlain">Copy plain text</button><button type="button" class="assistant-modal-close" aria-label="Close Assistant document">×</button></div>
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
    closeHeadingMenu();
    closeSeriesMenu();
    ++state.modalRequest;
    if (updateHistory) {
      const url = new URL(window.location);
      const selected = ['meeting', 'series', 'task', 'note'].some(key => url.searchParams.has(key));
      url.searchParams.delete('meeting'); url.searchParams.delete('series'); url.searchParams.delete('task'); url.searchParams.delete('note');
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

  async function openDocumentModal(kind, path, focusHeading = '') {
    closeHeadingMenu();
    closeSeriesMenu();
    const overlay = ensureModal();
    const wasOpen = overlay.classList.contains('active');
    const request = ++state.modalRequest;
    overlay.setAttribute('aria-busy', 'true');
    try {
      const detail = await fetchDocument(kind, path);
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
      state.modalRoot = root; state.modalKind = rootKind;
      state.modalCurrent = detail; state.modalMeetingPart = 'summary';
      state.modalIndex = !focusHeading && detail.path === root.path && Boolean(root.tree?.children?.length);
      await renderModal(focusHeading);
      if (request === state.modalRequest) overlay.classList.add('active');
    } catch (error) {
      if (request !== state.modalRequest) return;
      if (!wasOpen) {
        document.getElementById('assistantModalDocument').replaceChildren();
        document.getElementById('assistantDocumentNav').replaceChildren();
        document.getElementById('assistantModalTitle').textContent = 'Document unavailable';
        resetCopy(); overlay.classList.add('active');
      }
      documentError(error.message || String(error));
    } finally {
      if (request === state.modalRequest) overlay.removeAttribute('aria-busy');
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

  function renderDocumentHeader(detail, kind) {
    closeHeadingMenu();
    hideNoteControls();
    // Related documents share their meeting's properties; original notes stay read-only.
    const record = detail.metadata?.schema === 2 ? detail : ['content', 'meeting'].includes(kind) ? state.modalRoot : detail;
    const recordKind = kind === 'content' ? 'meeting' : kind;
    const metadata = record.metadata || {};
    const workspace = record.workspace || {};
    const task = ['task', 'subtask'].includes(recordKind);
    const subtab = Boolean(metadata.parent);
    const tracked = task || subtab || Boolean(record.progress?.derived);
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
    document.getElementById('assistantModalKind').textContent = subtab ? 'Subtab' : ({task:'Task', subtask:'Subtab', meeting:'Note', note:'Note', series:'Series', content:'Note'})[kind] || 'Document';
    const primary = tracked ? [
      metadataSelect('status', progress?.derived ? 'Overall' : 'Status', status, metadata.schema === 2 ? lifecycle : state.data?.statuses || lifecycle),
      metadataSelect('priority', 'Priority', metadata.priority || 'P2', ['P0', 'P1', 'P2', 'P3'].map(value => [value, value])),
      metadataInput('due', 'Due', metadata.due, 'date'),
      ...(task && !subtab ? [metadataSelect('recurrence', 'Repeats', metadata.recurrence, [['', 'Once'], ['weekly', 'Weekly'], ['monthly', 'Monthly'], ['yearly', 'Yearly']])] : []),
      metadataInput('owner', 'POC', metadata.owner),
    ] : recordKind === 'meeting' ? [
      metadataInput('date', 'Date', metadata.date, 'date'),
      metadataSelect('series', 'Series', metadata.series, [['', 'Standalone'], ...(state.data?.meeting_series || [])
        .filter(row => metadata.schema === 2 || row.workspace === (metadata.workspace || workspace.id || record.path.split('/')[1]))
        .map(row => [row.id, row.title])]),
    ] : [];
    if (tracked && metadata.note_type === 'meeting') primary.push(
      metadataInput('date', 'Date', metadata.date, 'date'),
      metadataSelect('series', 'Series', metadata.series, [['','Standalone'], ...(state.data?.meeting_series || []).map(row => [row.id,row.title])]),
    );
    if (metadata.schema === 2 && !record.embedded) primary.push(
      metadataSelect('project', 'Project', metadata.project, [['', 'None'], ...(state.data.projects || []).map(row => [row.id,row.title])]),
      metadataSelect('workspace', 'Workspace', metadata.workspace, [['', 'None'], ...workspaceRows().map(row => [row.id,row.name || row.id])]),
    );
    const fields = [['title', 'Title'], ['tldr', 'Summary'], ...(task ? [
      ['group', 'Group'], ['scheduled', 'Planned', 'date'],
      ['defer_until', 'Deferred until', 'date'], ['waiting_on', 'Waiting on'], ['follow_up_at', 'Follow up', 'date'],
    ] : [])];
    const info = [
      ['Workspace', workspace.name || metadata.workspace], ['Vault', workspace.vault],
      ['Attendees', Array.isArray(metadata.attendees) ? metadata.attendees.join(', ') : metadata.attendees],
      ['Parent', metadata.parent?.id || metadata.parent], ['Created', metadata.created], ['Updated', metadata.updated],
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
      control.value = previous || '';
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
    if (detail.metadata?.schema !== 2 || detail.metadata.type !== 'note' || kind === 'content' || detail.format === 'text') return;
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
    } catch (error) {
      if (request === state.modalRequest) documentError(error.message || String(error));
    } finally {
      if (request === state.modalRequest) overlay.removeAttribute('aria-busy');
    }
  }

  async function renderModal(focusHeading = '') {
    if (state.modalRoot?.metadata?.schema === 2 && state.modalRoot.tree && state.modalKind !== 'series') {
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

  async function createRecord(type, parent = null, topLevel = false) {
    const title = window.prompt(type === 'subtab' ? (topLevel ? 'Tab title' : 'Subtab title') : type === 'project' ? 'Project name' : type === 'task' ? 'Task title' : 'Note title');
    if (!title?.trim()) return;
    try {
      const response = await fetch('/api/assistant/record', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({type, title:title.trim(), top_level:topLevel, parent:parent ? {type:parent.type,id:parent.id} : null,
          project:parent?.project || state.project || null, workspace:parent?.workspace || state.workspace || null})});
      const detail = await response.json();
      if (!response.ok) throw new Error(detail.detail || 'Could not create document');
      await refresh();
      if (type !== 'project') await openDocumentModal(type === 'task' ? 'task' : 'note', detail.path);
    } catch (error) { window.alert(error.message); }
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
    const indexed = [...(state.data?.meetings || []), ...(state.data?.notes || [])];
    let rows = indexed.filter(row => !row.parent && (row.series_path ? row.series_path === series.path
      : row.series === series.id && (metadata.schema === 2 || row.workspace === series.workspace)));
    if (!Array.isArray(state.data?.meetings)) rows = series.meetings || root.meetings || [];
    if (!overview) {
      const current = rows.find(row => row.path === root.path) || {};
      rows = [...rows.filter(row => row.path !== root.path), {...current, ...metadata, path:root.path}];
    }
    rows = sortedMeetings(rows);
    const signature = JSON.stringify([series.path, series.title, overview ? null : root.path,
      rows.map(row => [row.path,row.title,row.date,row.source,row.tags,row.note_type])]);
    const title = `<button type="button" class="assistant-series-overview${overview ? ' active' : ''}" data-assistant-series="${e(series.path)}"${overview ? ' aria-current="page"' : ''} title="${e(series.title)}"><span aria-hidden="true">▤</span><span>${e(series.title)}</span></button>`;
    const history = rows.map(row => {
      const current = !overview && row.path === root.path;
      const kind = row.note_type && row.note_type !== 'meeting' ? 'note' : 'meeting';
      return `<li><button type="button" class="assistant-series-meeting${current ? ' current' : ''}" data-series-document="${e(row.path)}" data-series-kind="${kind}"${current ? ' aria-current="page"' : ''} title="${e(row.title)}"><span aria-hidden="true">${current ? '✓' : ''}</span><span><time>${e(calendarDate(row.date) || 'No date')}</time><span class="assistant-series-meeting-title">${e(row.title || 'Untitled note')}</span></span>${row.source === 'demo' || (row.tags || []).includes('demo') ? '<small class="assistant-demo">Demo</small>' : ''}</button></li>`;
    }).join('') || '<li class="assistant-nav-empty">No notes yet.</li>';
    return {signature, html:`<div class="assistant-series-header">${title}<button type="button" class="assistant-series-toggle" data-series-toggle popovertarget="assistantSeriesMenu" aria-controls="assistantSeriesMenu" aria-expanded="false">More in this series <span aria-hidden="true">⌄</span></button></div>
      <div id="assistantSeriesMenu" class="assistant-series-menu" popover="auto" data-series-root="${e(root.path)}"><div class="assistant-document-nav-label">Notes in this series</div><ul class="assistant-series-meetings" aria-label="Notes in this series">${history}</ul></div>${documentHtml}`};
  }

  function closeSeriesMenu(restoreFocus = false) {
    const menu = document.getElementById('assistantSeriesMenu');
    if (!menu?.matches(':popover-open')) return;
    menu.hidePopover();
    if (restoreFocus) document.querySelector('[data-series-toggle]')?.focus({preventScroll:true});
  }

  function bindSeriesNavigation(nav) {
    bindSeries(nav);
    const menu = nav.querySelector('#assistantSeriesMenu');
    const toggle = nav.querySelector('[data-series-toggle]');
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
      const rows = [...menu.querySelectorAll('[data-series-document]')];
      (event.key === 'ArrowUp' ? rows.at(-1) : rows[0])?.focus();
    });
    menu.addEventListener('keydown', event => {
      if (!['ArrowDown','ArrowUp','Home','End'].includes(event.key)) return;
      event.preventDefault();
      const rows = [...menu.querySelectorAll('[data-series-document]')];
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
    const focused = previous?.contains(document.activeElement) ? document.activeElement.dataset.seriesDocument : null;
    nav.innerHTML = html;
    if (!nav.querySelector('[data-series-toggle]')) return;
    bindSeriesNavigation(nav);
    const menu = nav.querySelector('#assistantSeriesMenu');
    if (current === menu.dataset.seriesRoot) {
      menu.showPopover(); menu.scrollTop = scroll;
      [...menu.querySelectorAll('[data-series-document]')].find(row => row.dataset.seriesDocument === focused)?.focus({preventScroll:true});
    }
  }

  async function renderRecordTree(focusHeading = '') {
    const root = state.modalRoot;
    const detail = state.modalCurrent;
    const nav = document.getElementById('assistantDocumentNav');
    const rows = new Map();
    const node = row => {
      rows.set(row.path, row);
      return `<li><div class="assistant-record-tab-row"><button type="button" class="assistant-record-tab${detail.path === row.path ? ' active' : ''}" data-record-path="${e(row.path)}" data-record-kind="${e(row.kind)}" title="${e(row.title)}"><span aria-hidden="true">▤</span><span>${e(row.title)}</span></button><details class="assistant-tab-menu"><summary aria-label="Options for ${e(row.title)}">⋮</summary><div><button type="button" data-record-subtab="${e(row.path)}">+ Add subtab</button></div></details></div>${row.children?.length ? `<ul>${row.children.map(node).join('')}</ul>` : ''}</li>`;
    };
    const tree = documentTabs(root.tree).map(node).join('');
    const indexTab = root.tree.children?.length ? '<button type="button" class="assistant-record-tab assistant-index-tab" data-record-index><span aria-hidden="true">☷</span><span>Index</span></button>' : '';
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
      nav.querySelectorAll('[data-record-subtab]').forEach(button => button.addEventListener('click', () => {
        nav.querySelectorAll('details[open]').forEach(menu => { menu.open = false; });
        createRecord('subtab', rows.get(button.dataset.recordSubtab));
      }));
    }
    nav.querySelectorAll('[data-record-path]').forEach(button => button.classList.toggle('active', !state.modalIndex && button.dataset.recordPath === detail.path));
    nav.querySelector('[data-record-index]')?.classList.toggle('active', state.modalIndex);
    markDraftTabs();
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
    if (state.modalIndex && root.tree.children?.length) { renderIndex(root); return; }
    const kind = detail.metadata.type === 'task' ? 'task' : detail.metadata.note_type === 'meeting' ? 'meeting' : 'note';
    await renderDocumentPane(detail, kind, focusHeading);
  }


  function renderIndex(root) {
    const host = document.getElementById('assistantModalDocument');
    renderDocumentHeader(root, root.metadata.type === 'task' ? 'task' : 'note');
    if (state.currentPane && host.contains(state.currentPane.node)) state.currentPane.scrollTop = host.scrollTop;
    const body = JSON.stringify(root.tree);
    const cacheKey = root.path + ':index';
    let pane = state.paneCache.get(cacheKey);
    if (!pane || pane.body !== body) {
      const rows = [];
      const visit = (row, depth) => {
        rows.push(`<tr data-index-path="${e(row.path)}" data-index-kind="${e(row.kind)}" tabindex="0" aria-label="Open ${e(row.title)}">
          <td><button type="button" style="padding-inline-start:${depth * 20}px" data-index-open><span aria-hidden="true">${depth ? '↳' : '▤'}</span> ${e(row.title)}</button><div class="assistant-index-description" style="padding-inline-start:${depth * 20}px" title="${e(row.description)}">${e(row.description || '—')}</div></td>
          <td>${e(labelStatus(row.progress?.status || row.status || 'not_started'))}</td>
          <td>${e(displayDate(row.due) || '—')}</td><td>${e(row.priority || '—')}</td><td>${e(row.owner || '—')}</td></tr>`);
        (row.children || []).forEach(child => visit(child, depth + 1));
      };
      documentTabs(root.tree).forEach(row => visit(row, 0));
      const node = document.createElement('section'); node.className = 'assistant-index';
      node.innerHTML = `<h2>Index</h2><div class="assistant-index-scroll"><table><thead><tr><th scope="col">Tab / Description</th><th scope="col">Status</th><th scope="col">Due</th><th scope="col">Priority</th><th scope="col">POC</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
      node.querySelectorAll('[data-index-path]').forEach(row => {
        const open = () => selectModalDocument(row.dataset.indexKind, row.dataset.indexPath);
        row.addEventListener('click', open);
        row.addEventListener('keydown', event => {
          if (event.target === row && ['Enter',' '].includes(event.key)) { event.preventDefault(); open(); }
        });
      });
      pane = {node,body,scrollTop:pane?.scrollTop || 0};
      state.paneCache.set(cacheKey,pane);
    }
    host.replaceChildren(pane.node); host.scrollTop = pane.scrollTop; state.currentPane = pane;
    resetCopy(true);
    document.getElementById('assistantCopyPlain').onclick = event => window.LabMarkdown.copy(pane.node,{button:event.currentTarget,plainOnly:true});
    document.getElementById('assistantCopyRich').onclick = event => window.LabMarkdown.copy(pane.node,{button:event.currentTarget});
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
    host.querySelectorAll('[data-assistant-series]').forEach(button => button.addEventListener('click', () => {
      const path = button.dataset.assistantSeries;
      const url = new URL(window.location);
      url.searchParams.set('view', 'assistant'); url.searchParams.set('subview', 'notes');
      url.searchParams.set('series', path); url.searchParams.delete('meeting'); url.searchParams.delete('task'); url.searchParams.delete('note');
      url.searchParams.delete('assistant_workspace');
      history.pushState({nav:'assistant', series:path}, '', url.pathname + url.search + url.hash);
      state.selectedSeriesPath = path; state.selectedMeetingPath = ''; state.selectedTaskPath = '';
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
    if (state.modalKind === 'series') {
      const navigation = seriesNavigation(root);
      if (document.getElementById('assistantDocumentNav').dataset.seriesStructure !== navigation.signature) await renderMeetingModal();
      return;
    }
    if (!root.tree) return;
    const latest = [...tasks(), ...(state.data.notes || []), ...meetings()].find(row => row.path === root.path);
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

  window.addEventListener('beforeunload', event => {
    if ([...state.noteDrafts.values()].some(dirtyDraft)) {
      event.preventDefault(); event.returnValue = '';
    }
  });

  document.addEventListener('keydown', event => {
    const overlay = document.getElementById('assistantDocumentModal');
    if (event.key === 'Escape' && overlay && overlay.classList.contains('active')) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (state.headingMenu) { closeHeadingMenu(true); return; }
      if (document.querySelector('#assistantSeriesMenu:popover-open')) { closeSeriesMenu(true); return; }
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
