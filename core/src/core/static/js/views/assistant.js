(function () {
  'use strict';

  const state = {
    data: null,
    files: [],
    section: 'overview',
    selectedTaskPath: '',
    selectedSubtaskPath: '',
    selectedMeetingPath: '',
    view: 'all_open',
    status: '',
    priority: '',
    project: '',
    search: '',
    expandedGroups: new Set(),
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
        const haystack = [task.title, task.tldr, task.summary, task.group, task.project_name, task.project, task.workspace]
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
    state.section = ['overview', 'tasks', 'meetings'].includes(section) ? section : 'overview';
    state.view = isTaskSection() ? 'all_open' : state.section === 'meetings' ? 'meetings' : 'overview';
    state.status = '';
    state.priority = '';
    if (isTaskSection() && !projectRows().some(project => project.id === state.project)) {
      const available = projectRows();
      state.project = available.length ? available[0].id : '';
    }
    if (!options.history) {
      const url = new URL(window.location);
      url.searchParams.set('view', 'assistant');
      if (state.section === 'meetings') url.searchParams.set('subview', 'meetings');
      else if (state.section === 'tasks') {
        url.searchParams.set('subview', 'tasks');
        if (state.project) url.searchParams.set('assistant_project', state.project);
      } else {
        url.searchParams.delete('subview');
        url.searchParams.delete('assistant_project');
      }
      if (state.section !== 'tasks') url.searchParams.delete('task');
      if (state.section !== 'meetings') url.searchParams.delete('meeting');
      history.pushState({nav: 'assistant', subview: state.section}, '', url.pathname + url.search + url.hash);
    }
    if (window.assistantSectionShell) window.assistantSectionShell(state.section);
    syncSectionTabs();
    render();
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
        <span class="assistant-task-branch" aria-hidden="true"></span>
        <span class="assistant-row-content">
          <span class="assistant-row-title"><span class="assistant-priority ${e(String(task.priority || '').toLowerCase())}">${e(task.priority || 'P2')}</span><strong>${e(task.title)}</strong></span>
          <span class="assistant-row-tldr"><b>TLDR</b>${e(tldr)}</span>
        </span>
        <span class="assistant-row-meta">${reviews ? `<span class="assistant-review-count">${reviews} to review</span>` : ''}${progress ? `<span class="assistant-progress-label">${e(progress)}</span>` : ''}<span class="assistant-status status-${e(task.status || 'inbox')}">${e(labelStatus(task.status))}</span>${task.status === 'waiting' ? `<button type="button" class="assistant-nudge" data-assistant-nudge="${e(task.path)}">Nudge</button>` : ''}${due}</span>
      </div>
    </article>`;
  }

  function meetingCard(meeting) {
    const actionProgress = progressLabel(meeting.action_items_done, meeting.action_items_total, 'actions');
    return `<article class="assistant-list-item${meeting.path === state.selectedMeetingPath ? ' selected' : ''}" data-assistant-entry-wrap="${e(meeting.path)}">
      <button type="button" class="assistant-compact-row" data-assistant-meeting="${e(meeting.path)}" data-testid="assistant-meeting-row">
        <span class="assistant-row-main"><span class="assistant-meeting-date">${e(displayDate(meeting.date))}</span><strong>${e(meeting.title)}</strong></span>
        <span class="assistant-row-meta">${actionProgress ? `<span class="assistant-progress-label">${e(actionProgress)}</span>` : ''}<span class="assistant-task-project">${e(meeting.project_name || meeting.project)}</span></span>
      </button>
    </article>`;
  }

  function renderSetup(content) {
    const root = state.data && state.data.root;
    const message = !state.data || !state.data.configured
      ? 'Choose the Assistant folder from Home → Admin.'
      : 'Open Home → Admin and choose an available Assistant folder.';
    content.innerHTML = `<div class="assistant-setup">
      <span class="assistant-kicker">Global workspace</span>
      <h1>Assistant needs a database</h1>
      <p>${e(message)}</p>
      ${root ? `<code>${e(root)}</code>` : '<code>Home → Admin → Assistant</code>'}
    </div>`;
  }

  function openTaskCount() {
    return countWhere(tasks(), task => task.status !== 'done');
  }

  function recentFiles() {
    return [...state.files]
      .filter(file => file && file.type !== 'dir' && file.path && !file.path.startsWith('.lab/'))
      .sort((left, right) => Number(right.mtime || 0) - Number(left.mtime || 0))
      .slice(0, 10);
  }

  function updatedLabel(seconds) {
    const time = Number(seconds || 0) * 1000;
    if (!Number.isFinite(time) || time <= 0) return '';
    const elapsed = Math.max(0, Date.now() - time);
    if (elapsed < 60000) return 'just now';
    if (elapsed < 3600000) return `${Math.floor(elapsed / 60000)}m ago`;
    if (elapsed < 86400000) return `${Math.floor(elapsed / 3600000)}h ago`;
    if (elapsed < 7 * 86400000) return `${Math.floor(elapsed / 86400000)}d ago`;
    return displayDate(new Date(time).toISOString());
  }

  function renderOverview(content) {
    const open = openTaskCount();
    const active = countWhere(tasks(), task => task.status === 'in_progress');
    const review = countWhere(tasks(), hasReview);
    const urgent = countWhere(tasks(), task => task.status !== 'done' && task.priority === 'P0');
    const recent = recentFiles();
    const projects = projectRows();
    content.innerHTML = `<div class="assistant-shell assistant-overview-shell">
      <header class="assistant-overview-hero">
        <div><span class="assistant-kicker">Client-global project</span><h1>Assistant</h1><p>Tasks, notes, and agent-ready context across every Lab workspace.</p></div>
        <button type="button" class="refresh-btn" id="assistantOverviewTasks">Open tasks</button>
      </header>
      <div class="assistant-overview-stats">
        <div><strong>${open}</strong><span>Open tasks</span></div>
        <div><strong>${active}</strong><span>In progress</span></div>
        <div><strong>${review}</strong><span>Ready to review</span></div>
        <div><strong>${urgent}</strong><span>P0</span></div>
      </div>
      <div class="assistant-overview-grid">
        <section class="assistant-overview-card">
          <header><h2>Recently updated</h2><span>${recent.length}</span></header>
          <div class="assistant-recent-files">${recent.length ? recent.map(file => `<button type="button" data-assistant-file="${e(file.path)}"><span><b>${e(file.path.split('/').pop())}</b><small>${e(file.path.includes('/') ? file.path.slice(0, file.path.lastIndexOf('/')) : 'Assistant root')}</small></span><time>${e(updatedLabel(file.mtime))}</time></button>`).join('') : '<p class="assistant-overview-empty">No files yet.</p>'}</div>
        </section>
        <section class="assistant-overview-card">
          <header><h2>Projects</h2><span>${projects.length}</span></header>
          <div class="assistant-overview-projects">${projects.length ? projects.map(project => {
            const rows = tasks().filter(task => task.project === project.id);
            const pending = countWhere(rows, task => task.status !== 'done');
            return `<button type="button" data-assistant-overview-project="${e(project.id)}"><span><b>${e(project.name || project.id)}</b><small>${e(project.workspace || 'Unmapped workspace')}</small></span><strong>${pending} open</strong></button>`;
          }).join('') : '<p class="assistant-overview-empty">No mapped projects yet.</p>'}</div>
        </section>
      </div>
      <section class="assistant-root-card"><span>Assistant folder</span><code>${e(state.data.root || '')}</code><small>Managed from Home → Admin. New terminals and all file views use this location.</small></section>
    </div>`;
    document.getElementById('assistantOverviewTasks')?.addEventListener('click', () => setSection('tasks'));
    content.querySelectorAll('[data-assistant-file]').forEach(button => {
      button.addEventListener('click', () => {
        if (window.openProjectDocFromFileClick) {
          window.openProjectDocFromFileClick(button.dataset.assistantFile, {root: state.data.root});
        }
      });
    });
    content.querySelectorAll('[data-assistant-overview-project]').forEach(button => {
      button.addEventListener('click', () => {
        state.project = button.dataset.assistantOverviewProject;
        setSection('tasks');
      });
    });
  }

  function projectRows() {
    const projects = [...((state.data && state.data.projects) || [])];
    return projects.sort((left, right) => {
      const leftCount = countWhere(tasks(), task => task.project === left.id && needsAttention(task));
      const rightCount = countWhere(tasks(), task => task.project === right.id && needsAttention(task));
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

  function labProjectNav() {
    return `<nav class="assistant-lab-projects" aria-label="Lab projects">${projectRows().map(project => {
      const rows = tasks().filter(task => task.project === project.id);
      const count = countWhere(rows, needsAttention);
      return `<button type="button" class="${state.project === project.id ? 'active' : ''}" data-assistant-project="${e(project.id)}" title="${e(attentionBreakdown(rows))}">
        <span class="assistant-lab-project-name">${e(project.name || project.id)}</span><small>${count}</small>
      </button>`;
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
      ${isTasks ? '' : projectSelect(meetings())}${advanced}
      <span class="assistant-filter-count">${rows.length} ${isTasks ? 'task' : 'note'}${rows.length === 1 ? '' : 's'}</span>
    </div>`;
  }

  function emptyTasks() {
    return '<div class="assistant-empty">No tasks match this view.</div>';
  }

  function internalGroup(task) {
    return String(task.group || 'Ungrouped');
  }

  function internalGroupKey(name) {
    return `${state.project}:${name}`;
  }

  function renderTasks(rows) {
    const names = [...new Set(rows.map(internalGroup))].sort((left, right) => left.localeCompare(right));
    const groups = names.map(name => {
      const items = rows.filter(task => internalGroup(task) === name);
      const key = internalGroupKey(name);
      const expanded = state.expandedGroups.has(key);
      const attention = countWhere(items, needsAttention);
      return `<section class="assistant-internal-project${expanded ? ' expanded' : ''}" data-assistant-group-wrap="${e(key)}">
        <button type="button" class="assistant-group-header" data-assistant-group="${e(key)}" aria-expanded="${expanded}">
          <span class="assistant-group-badge">PROJECT</span>
          <span class="assistant-group-name"><strong>${e(name)}</strong><small>${items.length} task${items.length === 1 ? '' : 's'}${attention ? ` · ${attention} attention` : ''}</small></span>
          <span class="assistant-group-summary">${e(attentionBreakdown(items))}</span>
          <span class="assistant-group-chevron" aria-hidden="true">›</span>
        </button>
        ${expanded ? `<div class="assistant-group-tasks">${items.map(taskCard).join('')}</div>` : ''}
      </section>`;
    }).join('');
    return `${labProjectNav()}${filterBar(rows)}<div class="assistant-internal-projects" data-testid="assistant-list">${groups || emptyTasks()}</div>`;
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
    if (window.LAB_ASSISTANT_DOCUMENT_OPEN) return;
    syncSectionTabs();
    const content = document.getElementById('content');
    if (!content) return;
    if (!state.data || !state.data.configured || !state.data.exists) {
      renderSetup(content);
      return;
    }
    if (state.section === 'overview') {
      renderOverview(content);
      return;
    }
    const rows = isTaskSection() ? filteredTasks() : filteredMeetings();
    const project = projectRows().find(item => item.id === state.project);
    const proposal = isTaskSection()
      ? `Lab project · ${project ? project.name || project.id : 'Tasks'}`
      : 'Global Assistant';
    const title = isTaskSection() ? 'Tasks' : 'Meeting notes';
    const body = isTaskSection() ? renderTasks(rows) : renderMeetings(rows);
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
    content.querySelectorAll('[data-assistant-project]').forEach(button => {
      button.addEventListener('click', () => selectProject(button.dataset.assistantProject));
    });
    content.querySelectorAll('[data-assistant-group]').forEach(button => {
      button.addEventListener('click', () => {
        const key = button.dataset.assistantGroup;
        if (state.expandedGroups.has(key)) state.expandedGroups.delete(key);
        else state.expandedGroups.add(key);
        render();
      });
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
    document.getElementById('assistantProject')?.addEventListener('change', event => {
      state.project = event.target.value;
      render();
    });
    content.querySelectorAll('[data-assistant-task]').forEach(button => bindRow(button, 'task'));
    content.querySelectorAll('[data-assistant-meeting]').forEach(button => bindRow(button, 'meeting'));
    content.querySelectorAll('[data-assistant-nudge]').forEach(button => {
      button.addEventListener('click', event => {
        event.stopPropagation();
        const task = tasks().find(item => item.path === button.dataset.assistantNudge);
        openDocumentModal('task', button.dataset.assistantNudge, task && task.has_generated_content ? 'Generate content' : '');
      });
    });
  }

  function selectProject(projectId) {
    if (!projectId || projectId === state.project) return;
    state.project = projectId;
    state.selectedTaskPath = '';
    state.expandedGroups.clear();
    const url = new URL(window.location);
    url.searchParams.set('view', 'assistant');
    url.searchParams.set('assistant_project', projectId);
    url.searchParams.delete('task');
    history.pushState({nav: 'assistant', assistant_project: projectId}, '', url.pathname + url.search + url.hash);
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
      if (kind === 'task') {
        url.searchParams.set('subview', 'tasks');
        if (state.project) url.searchParams.set('assistant_project', state.project);
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
      <header class="assistant-modal-header">
        <div class="assistant-modal-heading"><span class="assistant-kicker" id="assistantModalKind">Assistant</span><h2 id="assistantModalTitle">Loading…</h2></div>
        <div class="assistant-modal-actions"><button type="button" id="assistantCopyRich">Copy for Google Docs</button><button type="button" id="assistantCopyPlain">Copy plain text</button><button type="button" class="assistant-modal-close" aria-label="Close Assistant document">×</button></div>
      </header>
      <div class="assistant-modal-body" id="assistantModalBody"><aside class="assistant-document-nav" id="assistantDocumentNav"></aside><main class="assistant-document-pane" id="assistantModalDocument"><div class="loading">Loading…</div></main></div>
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

  async function fetchDocument(kind, path) {
    const endpoint = kind === 'task' ? '/api/assistant/task?path='
      : kind === 'subtask' ? '/api/assistant/subtask?path=' : '/api/assistant/meeting?path=';
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
    host.innerHTML = '<div class="loading">Loading document…</div>';
    nav.innerHTML = '';
    overlay.classList.add('active');
    const request = ++state.modalRequest;
    try {
      const detail = await fetchDocument(kind, path);
      if (request !== state.modalRequest || !overlay.classList.contains('active')) return;
      if (kind === 'subtask') {
        const metadata = detail.metadata || {};
        const parent = tasks().find(task => task.project === metadata.project && task.id === metadata.parent);
        state.modalRoot = parent ? await fetchDocument('task', parent.path) : detail;
        state.modalKind = parent ? 'task' : 'subtask';
      } else {
        state.modalRoot = detail;
        state.modalKind = kind === 'meeting' ? 'meeting' : 'task';
      }
      if (request !== state.modalRequest || !overlay.classList.contains('active')) return;
      state.modalCurrent = detail;
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

  function documentMeta(detail, kind) {
    const metadata = detail.metadata || {};
    const project = detail.project || {};
    const rows = kind !== 'meeting' ? [
      ['Status', labelStatus(metadata.status)], ['Priority', metadata.priority],
      ['Lab project', project.name || metadata.project], ['Group', metadata.group], ['Workspace', project.workspace],
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
    if (typeof window.ensureMarked === 'function') await window.ensureMarked().catch(() => {});
    const body = detail.body || '';
    const markdown = window.marked ? window.marked.parse(body) : `<pre>${e(body)}</pre>`;
    const metadata = detail.metadata || {};
    const project = detail.project || {};
    const host = document.getElementById('assistantModalDocument');
    const badges = kind !== 'meeting'
      ? `<div class="assistant-detail-badges"><span class="assistant-priority ${e(String(metadata.priority || '').toLowerCase())}">${e(metadata.priority || 'P2')}</span><span class="assistant-status status-${e(metadata.status || 'inbox')}">${e(labelStatus(metadata.status))}</span></div>`
      : `<div class="assistant-detail-badges"><span class="assistant-meeting-date full">${e(displayDate(metadata.date))}</span></div>`;
    const tldr = detail.tldr || metadata.tldr || '';
    const isMainTask = kind === 'task' && state.modalRoot && detail.path === state.modalRoot.path;
    const progress = isMainTask && Array.isArray(state.modalRoot.subtasks)
      ? progressLabel(countWhere(state.modalRoot.subtasks, item => item.status === 'done'), state.modalRoot.subtasks.length)
      : '';
    host.innerHTML = `<div class="assistant-document-title">
      <div>${badges}<h1>${e(metadata.title || metadata.id || 'Document')}</h1>${tldr ? `<p><b>TLDR</b>${e(tldr)}</p>` : ''}</div>${progress ? `<span>${e(progress)}</span>` : ''}
    </div>
    <div class="assistant-meta">${documentMeta(detail, kind)}</div>
    ${project.project_path ? `<div class="assistant-path"><span>Project path</span><code>${e(project.project_path)}</code></div>` : ''}
    <div class="nb-markdown assistant-markdown" id="assistantModalMarkdown">${markdown}</div>`;
    const markdownHost = document.getElementById('assistantModalMarkdown');
    rewriteImages(markdownHost, detail.path);
    addCopyButtons(markdownHost, body, detail.path);
    document.getElementById('assistantCopyPlain').onclick = event => copyPlain(body, event.currentTarget);
    document.getElementById('assistantCopyRich').onclick = event => copyRich(body, detail.path, event.currentTarget);
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
      if (data.exists && data.root) {
        const filesResponse = await fetch('/api/project-files?path=' + encodeURIComponent(data.root));
        state.files = filesResponse.ok ? await filesResponse.json() : [];
      } else {
        state.files = [];
      }
      if (request !== state.request || !document.body.classList.contains('assistant-active')) return;
      if (options.task !== undefined) state.selectedTaskPath = options.task || '';
      if (options.meeting !== undefined) state.selectedMeetingPath = options.meeting || '';
      if (options.project !== undefined) state.project = options.project || '';
      const selected = tasks().find(task => task.path === state.selectedTaskPath);
      if (selected) {
        state.project = selected.project;
        state.expandedGroups.add(`${selected.project}:${internalGroup(selected)}`);
      }
      const available = projectRows();
      if (!available.some(project => project.id === state.project)) {
        state.project = available.length ? available[0].id : '';
      }
      render();
    } catch (error) {
      const content = document.getElementById('content');
      if (content && request === state.request) content.innerHTML = `<div class="assistant-setup"><h1>Assistant</h1><p>${e(error.message || error)}</p></div>`;
    }
  }

  function init(initial = '') {
    const options = typeof initial === 'object' && initial !== null ? initial : {task: initial};
    state.section = ['overview', 'tasks', 'meetings'].includes(options.section) ? options.section : 'overview';
    state.selectedTaskPath = options.task || '';
    state.selectedSubtaskPath = '';
    state.selectedMeetingPath = options.meeting || '';
    state.view = isTaskSection() ? 'all_open' : state.section === 'meetings' ? 'meetings' : 'overview';
    state.status = '';
    state.priority = '';
    state.project = options.project || new URL(window.location).searchParams.get('assistant_project') || '';
    state.search = '';
    state.expandedGroups.clear();
    refresh({task: state.selectedTaskPath, meeting: state.selectedMeetingPath, project: state.project});
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
