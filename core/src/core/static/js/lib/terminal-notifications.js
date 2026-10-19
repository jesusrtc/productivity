// Active alerts by default; the center also includes each terminal's last alert.
(() => {
  let scopes = {}, bridge;
  const pageSize = 20;
  let historyOpen = false, visibleCount = pageSize, historyGeneration = 0;
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
        const report = history ? details.notification : details.report;
        if (!report || !['attention', 'finished'].includes(report.state)
            || !history && !['attention', 'finished'].includes(details.indicator)) continue;
        const key = completion.key(session);
        const owner = {workspace_id:session.workspace_id || scope.slice(separator + 2),
          vault:session.vault || scope.slice(0, separator)};
        const item = {key, session, owner, report_id:report.id, state:report.state,
          created_at:report.updated_at, revision:report.revision,
          active:details.indicator === report.state && details.report?.id === report.id,
          message:report.message || (report.state === 'attention' ? 'Needs your input' : 'Work finished')};
        // Prefer the native row over another workspace's shared view.
        if (!unique.has(key) || scope === `${owner.vault}::${owner.workspace_id}`) unique.set(key, item);
      }
    }
    return [...unique.values()].sort((a, b) => (history ? 0
      : (a.state === 'attention' ? 0 : 1) - (b.state === 'attention' ? 0 : 1))
      || (b.created_at || 0) - (a.created_at || 0) || b.revision - a.revision);
  }

  function buttonHtml() {
    return `<button type="button" class="repo-tab notification-center-toggle" data-terminal-notification-center onclick="LabTerminalNotifications.toggleHistory()" aria-controls="termNotifications" aria-expanded="${historyOpen}" title="Latest notification per terminal, newest first"><span aria-hidden="true">&#x1F514;</span> Notifications</button>`;
  }
  function showHistory(value = true) {
    historyOpen = !!value; visibleCount = pageSize; historyGeneration++;
    render();
    const host = document.getElementById('termNotifications');
    if (historyOpen && host) host.scrollTop = 0;
    if (historyOpen) void window.LabWorkspaceDocuments?.poll(true);
    return {open:historyOpen};
  }

  async function open(key, reportId) {
    const item = items({history:true}).find(row => row.key === key && row.report_id === reportId);
    if (!item || opening.has(key)) return false;
    const generation = historyGeneration;
    opening.add(key); render();
    try {
      const session = await bridge?.open(item);
      if (!session) return false;
      if (item.state === 'finished') window.LabTerminalCompletion.acknowledge('', session, reportId);
      // Reviewing green can rebuild the tab rail; highlight its final DOM.
      bridge?.highlight?.(session);
      if (historyOpen && historyGeneration === generation) showHistory(false);
      return true;
    } finally { opening.delete(key); render(); }
  }

  function render() {
    document.querySelectorAll?.('[data-terminal-notification-center]').forEach(button =>
      button.setAttribute('aria-expanded', String(historyOpen)));
    const all = items({history:historyOpen}), rows = historyOpen ? all.slice(0, visibleCount) : all;
    const host = document.getElementById('termNotifications');
    if (!host) return;
    host.hidden = !historyOpen && !rows.length;
    host.classList.toggle('history-open', historyOpen);
    let html = historyOpen ? '<div class="term-notification-header"><strong>Notification center</strong><button type="button" data-notification-close aria-label="Close notification center">×</button></div>' : '';
    html += rows.map(row => {
      const label = bridge?.label?.(row) || `${row.owner.workspace_id} / ${row.session.label || row.session.logical_name || row.session.name}`;
      const state = (row.state === 'attention' ? 'Needs input' : 'Finished') + (historyOpen && !row.active ? ' · History' : '');
      const date = new Date(row.created_at * 1000);
      const time = historyOpen && Number.isFinite(date.getTime())
        ? `<time class="term-notification-time" datetime="${date.toISOString()}">${escape(date.toLocaleString())}</time>` : '';
      return `<button type="button" class="term-notification ${row.state}" data-key="${escape(row.key)}" data-report-id="${escape(row.report_id)}"${opening.has(row.key) ? ' disabled' : ''} title="${escape(state + ' · ' + label + ' · ' + row.message)}"><span class="term-notification-icon" aria-hidden="true">${row.state === 'attention' ? '!' : '✓'}</span><span class="term-notification-copy"><span class="term-notification-context">${escape(state + ' · ' + label)}</span><span class="term-notification-message">${escape(row.message)}</span>${time}</span><span aria-hidden="true">↗</span></button>`;
    }).join('');
    if (historyOpen && !rows.length) html += '<p class="term-notification-empty">No notifications yet.</p>';
    if (historyOpen && all.length > rows.length) html += '<button type="button" class="term-notification-more" data-notification-more>Load more</button>';
    if (host._notificationHtml === html) return;
    const scroll = host.scrollTop;
    host._notificationHtml = html; host.innerHTML = html;
    host.scrollTop = scroll;
    host.querySelectorAll('.term-notification').forEach(button => {
      button.onclick = () => void open(button.dataset.key, button.dataset.reportId)
        .catch(error => bridge?.error(error.message || 'Could not open terminal.'));
    });
    host.querySelector('[data-notification-close]')?.addEventListener('click', () => {
      showHistory(false); document.querySelector('[data-terminal-notification-center]')?.focus();
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
