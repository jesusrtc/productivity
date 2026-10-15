// A view of current terminal reports, not a separate notification history.
(() => {
  let scopes = {}, bridge;
  const opening = new Set();
  const escape = value => String(value || '').replace(/[&<>"']/g,
    ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

  function items() {
    const completion = window.LabTerminalCompletion, unique = new Map();
    if (!completion) return [];
    for (const [scope, sessions] of Object.entries(scopes)) {
      const separator = scope.indexOf('::');
      for (const session of sessions) {
        const {report, indicator} = completion.details(session);
        if (!report || !['attention', 'finished'].includes(indicator)) continue;
        const key = completion.key(session);
        const owner = {workspace_id:session.workspace_id || scope.slice(separator + 2),
          vault:session.vault || scope.slice(0, separator)};
        const item = {key, session, owner, report_id:report.id, state:indicator,
          message:report.message || (indicator === 'attention' ? 'Needs your input' : 'Work finished')};
        // Prefer the native row over another workspace's shared view.
        if (!unique.has(key) || scope === `${owner.vault}::${owner.workspace_id}`) unique.set(key, item);
      }
    }
    return [...unique.values()].sort((a, b) => (a.state === 'attention' ? 0 : 1) - (b.state === 'attention' ? 0 : 1)
      || (b.session.terminal_status?.revision || 0) - (a.session.terminal_status?.revision || 0));
  }

  async function open(key, reportId) {
    const item = items().find(row => row.key === key && row.report_id === reportId);
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

  function render() {
    const rows = items(), host = document.getElementById('termNotifications');
    if (!host) return;
    host.hidden = !rows.length;
    const html = rows.map(row => {
      const label = bridge?.label(row) || `${row.owner.workspace_id} / ${row.session.label || row.session.logical_name || row.session.name}`;
      const state = row.state === 'attention' ? 'Needs input' : 'Finished';
      return `<button type="button" class="term-notification ${row.state}" data-key="${escape(row.key)}" data-report-id="${escape(row.report_id)}"${opening.has(row.key) ? ' disabled' : ''} title="${escape(state + ' · ' + label + ' · ' + row.message)}"><span class="term-notification-icon" aria-hidden="true">${row.state === 'attention' ? '!' : '✓'}</span><span class="term-notification-copy"><span class="term-notification-context">${escape(state + ' · ' + label)}</span><span class="term-notification-message">${escape(row.message)}</span></span><span aria-hidden="true">↗</span></button>`;
    }).join('');
    if (host._notificationHtml === html) return;
    host._notificationHtml = html; host.innerHTML = html;
    host.querySelectorAll('button').forEach(button => {
      button.onclick = () => void open(button.dataset.key, button.dataset.reportId)
        .catch(error => bridge?.error(error.message || 'Could not open terminal.'));
    });
  }
  window.addEventListener('lab-terminal-completion-change', render);
  document.addEventListener('visibilitychange', render);
  window.LabTerminalNotifications = {items, open, render,
    update(value) { scopes = value; render(); },
    configure(value) { bridge = value; render(); }};
})();
