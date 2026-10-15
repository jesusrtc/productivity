// Only agent reports drive terminal indicators. Output, silence and provider
// transcript guesses cannot start work, finish it, or dismiss attention.
(() => {
  const storageKey = 'labTerminalReports-v1';
  let reports = {};
  function reload() {
    try {
      const value = JSON.parse(localStorage.getItem(storageKey) || '{}');
      if (value && typeof value === 'object' && !Array.isArray(value)) reports = value;
    } catch {}
  }
  function key(session) {
    return JSON.stringify([session.name, session.tmux_socket || 'default',
      session.tmux_id || '', session.created ?? session.created_at]);
  }
  function save() {
    const entries = Object.entries(reports);
    if (entries.length > 2000) reports = Object.fromEntries(entries
      .sort((a, b) => b[1].report.revision - a[1].report.revision).slice(0, 2000));
    try { localStorage.setItem(storageKey, JSON.stringify(reports)); } catch {}
  }
  function record(session) {
    if (!session?.name) return null;
    const id = key(session), previous = reports[id], report = session.terminal_status;
    if (report?.version === 1 && ['working', 'attention', 'finished'].includes(report.state)
        && typeof report.id === 'string' && Number.isSafeInteger(report.revision)
        && report.revision > (previous?.report?.revision || 0)) {
      reload(); // Merge another window only when a report actually changes.
      if (report.revision > (reports[id]?.report?.revision || 0)) {
        reports[id] = {report};
        save();
      }
    }
    return reports[id];
  }
  function details(session) {
    const entry = record(session), report = entry?.report;
    const reviewed = !!report && report.state === 'finished' && entry.seen === report.id;
    return {report:report || null, indicator:report && !reviewed ? report.state : null,
      reviewed, reviewed_at:reviewed ? entry.seen_at || null : null,
      reason:!report ? 'no-report' : reviewed ? 'reviewed-by-click' : 'agent-report'};
  }
  function status(session) {
    const {report, indicator} = details(session);
    if (!indicator) return null;
    const label = {working:'Working', attention:'Needs your attention', finished:'Finished'}[report.state];
    return {state:report.state, label:label + (report.message ? ' · ' + report.message : '')};
  }
  function meta(scope, session) {
    const current = status(session);
    return current?.state === 'finished' ? {label:current.label + ' · Not yet viewed'} : null;
  }
  function isWorking(session) { return status(session)?.state === 'working'; }
  function acknowledge(scope, session, displayedReportId = session.terminal_status?.id) {
    if (document.hidden || !document.hasFocus()) return false;
    reload(); // A stale click must see newer reports from other windows.
    const entry = record(session);
    // A stale green click must never clear a newer working/attention report.
    if (entry?.report?.state !== 'finished' || entry.seen === entry.report.id) return false;
    if (session.terminal_status?.id !== entry.report.id) return false;
    if (displayedReportId !== entry.report.id) return false;
    reports[key(session)] = {...entry, seen:entry.report.id, seen_at:Date.now() / 1000};
    save();
    window.dispatchEvent?.(new Event('lab-terminal-completion-change'));
    refresh();
    return true;
  }
  function refresh() {
    if (!document.hidden && typeof termRenderSessionList === 'function') termRenderSessionList();
  }
  window.addEventListener('storage', event => {
    if (event.key !== storageKey && event.key !== null) return;
    reload(); refresh();
    window.dispatchEvent?.(new Event('lab-terminal-completion-change'));
  });
  window.addEventListener('focus', refresh);
  document.addEventListener('visibilitychange', refresh);
  reload();
  window.LabTerminalCompletion = {meta, status, isWorking, acknowledge, details};
})();
