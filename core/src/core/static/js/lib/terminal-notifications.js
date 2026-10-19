// Active alerts by default; the center also includes each terminal's last alert.
(() => {
  let scopes = {}, bridge;
  const pageSize = 20;
  let historyOpen = false, visibleCount = pageSize, searchQuery = '';
  const opening = new Set();
  const escape = value => String(value || '').replace(/[&<>"']/g,
    ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

  function items({history = false} = {}) {
    const completion = window.LabTerminalCompletion, unique = new Map();
    if (!completion) return [];
    for (const [scope, sessions] of Object.entries(scopes)) {
      const separator = scope.indexOf('::');
      for (const session of sessions) {
        const details = completion.details(session);
        const report = history ? details.notification : details.progress_alert || details.report;
        if (!report || !['attention', 'finished'].includes(report.state)
            || !history && !details.progress_alert && !['attention', 'finished'].includes(details.indicator)) continue;
        const key = completion.key(session);
        const owner = {workspace_id:session.workspace_id || scope.slice(separator + 2),
          vault:session.vault || scope.slice(0, separator)};
        const active = details.progress_alert?.id === report.id
          || details.indicator === report.state && details.report?.id === report.id;
        const age = Math.max(30, Math.floor((Date.now() / 1000 - (session.terminal_progress?.since || 0)) / 60));
        const message = active && report.kind === 'stale'
          ? `WIP · No progress update for ${age} min · Last report: ${session.terminal_progress.message || 'No report yet'}` : report.message;
        const item = {key, session, owner, report_id:report.id, state:report.state, kind:report.kind,
          created_at:report.updated_at, revision:report.revision,
          active, message:message || (report.state === 'attention' ? 'Needs your input' : 'Work finished')};
        // Prefer the native row over another workspace's shared view.
        if (!unique.has(key) || scope === `${owner.vault}::${owner.workspace_id}`) unique.set(key, item);
      }
    }
    return [...unique.values()].sort((a, b) => (history ? 0
      : (a.state === 'attention' ? 0 : 1) - (b.state === 'attention' ? 0 : 1))
      || (b.created_at || 0) - (a.created_at || 0) || b.revision - a.revision);
  }

  function buttonHtml() {
    return `<button type="button" class="repo-tab notification-center-toggle" data-terminal-notification-center onclick="LabTerminalNotifications.toggleHistory()" role="switch" aria-checked="${historyOpen}" aria-label="Show all notifications" aria-controls="termNotifications" aria-expanded="${historyOpen}" title="Show all notifications"><span aria-hidden="true">&#x1F514;</span><span class="keep-alive-switch" aria-hidden="true"></span></button>`;
  }
  function showHistory(value = true) {
    historyOpen = !!value; visibleCount = pageSize;
    if (!historyOpen) searchQuery = '';
    render();
    const host = document.getElementById('termNotifications');
    if (historyOpen && host) {
      host.scrollTop = 0;
      host.querySelector('[data-notification-search]')?.focus({preventScroll:true});
    }
    if (historyOpen) void window.LabWorkspaceDocuments?.poll(true);
    return {open:historyOpen};
  }

  async function open(key, reportId) {
    const item = items({history:true}).find(row => row.key === key && row.report_id === reportId);
    if (!item || opening.has(key)) return false;
    opening.add(key); render();
    try {
      const session = await bridge?.open(item);
      if (!session) return false;
      if (item.state === 'finished') window.LabTerminalCompletion.acknowledge('', session, reportId);
      // Reviewing green can rebuild the tab rail; highlight its final DOM.
      bridge?.highlight?.(session);
      return true;
    } finally { opening.delete(key); render(); }
  }

  function labelFor(row) {
    return bridge?.label?.(row) || [row.session.notification_context?.workspace || row.owner.workspace_id,
      row.session.notification_context?.objective, row.session.label || row.session.logical_name || row.session.name].filter(Boolean).join(' / ');
  }
  function stateFor(row) {
    return (row.kind ? row.kind === 'stale' ? 'Progress overdue' : 'Status not closed'
      : row.state === 'attention' ? 'Needs input' : 'Finished') + (historyOpen && !row.active ? ' · History' : '');
  }
  const normalize = value => String(value || '').normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
  function setSearch(value) {
    searchQuery = value; visibleCount = pageSize;
    render();
    const host = document.getElementById('termNotifications');
    if (host) host.scrollTop = 0;
  }

  function render() {
    document.querySelectorAll?.('[data-terminal-notification-center]').forEach(button => {
      button.setAttribute('aria-expanded', String(historyOpen));
      button.setAttribute('aria-checked', String(historyOpen));
    });
    const terms = historyOpen ? normalize(searchQuery).trim().split(/\s+/).filter(Boolean) : [];
    const all = items({history:historyOpen}).map(row => ({...row, label:labelFor(row), status:stateFor(row), date:new Date(row.created_at * 1000)}));
    // Search the complete history before paging, including owning context.
    const filtered = terms.length ? all.filter(row => {
      const text = normalize([row.label, row.status, row.state, row.message, row.date.toLocaleString(),
        row.session.logical_name, row.session.name, row.owner.workspace_id, row.owner.vault].join(' '));
      return terms.every(term => text.includes(term));
    }) : all;
    const rows = historyOpen ? filtered.slice(0, visibleCount) : filtered;
    const host = document.getElementById('termNotifications');
    if (!host) return;
    host.hidden = !historyOpen && !rows.length;
    host.classList.toggle('history-open', historyOpen);
    // Keep the search field mounted through typing, IME composition, polling
    // and review updates. Only the result list is replaced below it.
    if (host._notificationMode !== historyOpen || historyOpen && !host.querySelector('[data-notification-list]')) {
      host._notificationMode = historyOpen;
      host._notificationHtml = null;
      host.innerHTML = historyOpen ? '<div class="term-notification-toolbar"><div class="term-notification-header"><strong>Notification center</strong><button type="button" data-notification-close aria-label="Close notification center">×</button></div><div class="term-notification-search"><input type="search" data-notification-search aria-label="Search notifications" placeholder="Search notifications…" autocomplete="off"><button type="button" data-notification-clear aria-label="Clear search" hidden>×</button></div><div class="term-notification-count" data-notification-count role="status" aria-live="polite"></div></div><div class="term-notification-list" data-notification-list></div>' : '';
      host.querySelector('[data-notification-close]')?.addEventListener('click', () => {
        showHistory(false); document.querySelector('[data-terminal-notification-center]')?.focus();
      });
      host.querySelector('[data-notification-search]')?.addEventListener('input', event => setSearch(event.target.value));
      host.querySelector('[data-notification-clear]')?.addEventListener('click', () => {
        setSearch(''); host.querySelector('[data-notification-search]')?.focus({preventScroll:true});
      });
    }
    if (historyOpen) {
      const input = host.querySelector('[data-notification-search]');
      if (input.value !== searchQuery) input.value = searchQuery;
      host.querySelector('[data-notification-clear]').hidden = !searchQuery;
      const count = host.querySelector('[data-notification-count]');
      const summary = (rows.length < filtered.length ? `${rows.length} of ${filtered.length}` : String(filtered.length))
        + (terms.length ? ' matching notifications' : ' notifications');
      if (count.textContent !== summary) count.textContent = summary;
    }
    let html = rows.map(row => {
      const icon = bridge?.icon?.(row) || '💻';
      const {label, status:state, date} = row;
      const time = historyOpen && Number.isFinite(date.getTime())
        ? `<time class="term-notification-time" datetime="${date.toISOString()}">${escape(date.toLocaleString())}</time>` : '';
      return `<button type="button" class="term-notification ${row.state}${row.active ? ' active-alert' : ''}" data-active="${row.active}" data-key="${escape(row.key)}" data-report-id="${escape(row.report_id)}"${opening.has(row.key) ? ' disabled' : ''} title="${escape(label + ' · ' + state + ' · ' + row.message)}"><span class="term-notification-icon" aria-hidden="true">${row.state === 'attention' ? '!' : '✓'}</span><span class="term-notification-copy"><span class="term-notification-heading"><span class="term-notification-terminal-icon" aria-hidden="true">${icon}</span><span class="term-notification-context">${escape(label + ' · ' + state)}</span></span><span class="term-notification-message">${escape(row.message)}</span>${time}</span><span aria-hidden="true">↗</span></button>`;
    }).join('');
    if (historyOpen && !rows.length) html += '<p class="term-notification-empty">' + (all.length ? 'No matching notifications.' : 'No notifications yet.') + '</p>';
    if (historyOpen && filtered.length > rows.length) html += '<button type="button" class="term-notification-more" data-notification-more>Load more</button>';
    const list = historyOpen ? host.querySelector('[data-notification-list]') : host;
    if (list._notificationHtml === html) return;
    const scroll = host.scrollTop;
    list._notificationHtml = html; list.innerHTML = html;
    host.scrollTop = scroll;
    host.querySelectorAll('.term-notification').forEach(button => {
      button.onclick = () => void open(button.dataset.key, button.dataset.reportId)
        .catch(error => bridge?.error(error.message || 'Could not open terminal.'));
    });
    host.querySelector('[data-notification-more]')?.addEventListener('click', () => {
      const previous = visibleCount; visibleCount += pageSize; render();
      host.querySelectorAll('.term-notification')[previous]?.focus({preventScroll:true});
    });
  }
  document.addEventListener('click', event => {
    if (historyOpen && !event.target.closest?.('#termNotifications, [data-terminal-notification-center]')) showHistory(false);
  }, true);
  document.addEventListener('keydown', event => {
    if (!historyOpen || event.key !== 'Escape') return;
    event.preventDefault(); showHistory(false);
    document.querySelector('[data-terminal-notification-center]')?.focus();
  });
  window.addEventListener('lab-terminal-completion-change', render);
  document.addEventListener('visibilitychange', render);
  window.LabTerminalNotifications = {items, open, render, buttonHtml, showHistory,
    toggleHistory() { return showHistory(!historyOpen); },
    update(value) { scopes = value; render(); },
    configure(value) { bridge = value; render(); }};
})();
