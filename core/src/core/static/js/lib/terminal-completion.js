// Agent reports drive terminal indicators. A submitted LLM message gives immediate
// working feedback until the next report; output/silence never imply completion.
(() => {
  const storageKey = 'labTerminalReports-v1';
  let reports = {};
  const drafts = new Map(); // Unsent text stays in memory, never browser storage.
  function isLLM(session) {
    return session?.llm_controlled ?? ['claude', 'codex', 'copilot'].includes(session?.agent);
  }
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
      .sort((a, b) => (b[1].report?.revision || 0) - (a[1].report?.revision || 0)).slice(0, 2000));
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
    if (session.llm_controlled === false && reports[id]?.pending) {
      delete reports[id].pending;
      drafts.delete(id);
      save();
    }
    return reports[id];
  }
  function details(session) {
    const entry = record(session), report = entry?.report;
    const pending = isLLM(session) ? entry?.pending : null;
    const reviewed = !pending && !!report && report.state === 'finished' && entry.seen === report.id;
    return {report:report || null, pending:pending || null, llm_controlled:!!isLLM(session),
      indicator:pending ? 'working' : report && !reviewed ? report.state : null,
      reviewed, reviewed_at:reviewed ? entry.seen_at || null : null,
      reason:pending ? 'user-submission' : !report ? 'no-report' : reviewed ? 'reviewed-by-click' : 'agent-report'};
  }
  function status(session) {
    const {report, indicator, pending} = details(session);
    if (!indicator) return null;
    if (pending) return {state:'working', label:pending.label};
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
    if (entry?.pending || entry?.report?.state !== 'finished' || entry.seen === entry.report.id) return false;
    if (session.terminal_status?.id !== entry.report.id) return false;
    if (displayedReportId !== entry.report.id) return false;
    reports[key(session)] = {...entry, seen:entry.report.id, seen_at:Date.now() / 1000};
    save();
    window.dispatchEvent?.(new Event('lab-terminal-completion-change'));
    refresh();
    return true;
  }
  function submitted(session, text) {
    reload();
    const previous = details(session), entry = record(session) || {};
    const action = previous.indicator === 'attention' ? 'responded' : 'submitted';
    reports[key(session)] = {...entry, pending:{
      label:'Working - ' + action + (text ? ' ' + text.replace(/\s+/g, ' ').trim().slice(0, 500) : ''),
      submitted_at:Date.now() / 1000}};
    save();
    window.dispatchEvent?.(new Event('lab-terminal-completion-change'));
    refresh();
  }
  // Observe only bytes actually sent to the terminal. Recognize Enter outside
  // bracketed paste, and keep ordinary editing for the short hover preview.
  // History/completion/unknown edits deliberately produce a generic preview.
  function input(session, data) {
    if (!session?.name || !isLLM(session)) return;
    const id = key(session);
    const fresh = () => ({text:'', cursor:0, known:true, paste:false, escape:''});
    let draft = drafts.get(id) || fresh();
    const insert = value => {
      if (draft.text.length + value.length > 2000) { draft.known = false; return; }
      draft.text = draft.text.slice(0, draft.cursor) + value + draft.text.slice(draft.cursor);
      draft.cursor += value.length;
    };
    for (const ch of data) {
      if (draft.escape) {
        draft.escape += ch;
        if (draft.escape === '\x1b[' || draft.escape === '\x1bO') continue;
        if (draft.escape.startsWith('\x1b[') && !/[\x40-\x7e]/.test(ch)) {
          if (draft.escape.length > 80) draft.escape = '';
          continue;
        }
        const sequence = draft.escape; draft.escape = '';
        if (sequence === '\x1b[200~') draft.paste = true;
        else if (sequence === '\x1b[201~') draft.paste = false;
        else if (draft.paste) insert(sequence);
        else if (sequence === '\x1b[D') draft.cursor = Math.max(0, draft.cursor - 1);
        else if (sequence === '\x1b[C') draft.cursor = Math.min(draft.text.length, draft.cursor + 1);
        else if (['\x1b[H', '\x1bOH', '\x1b[1~'].includes(sequence)) draft.cursor = 0;
        else if (['\x1b[F', '\x1bOF', '\x1b[4~'].includes(sequence)) draft.cursor = draft.text.length;
        else if (sequence === '\x1b[3~') draft.text = draft.text.slice(0,draft.cursor) + draft.text.slice(draft.cursor+1);
        else if (sequence === '\x1b\r' || sequence === '\x1b[13;2u') insert('\n');
        else if (!/^\x1b\[(?:[IO]|[<?>=].*|[\d;]*[Rcn])$/.test(sequence)) draft.known = false;
        continue;
      }
      if (ch === '\x1b') { draft.escape = ch; continue; }
      if (draft.paste) { insert(ch); continue; }
      if (ch === '\r') {
        const text = draft.known ? draft.text.trim() : '';
        if (!/^\/(?:clear|new)(?:\s|$)/.test(text)
            && (text || !draft.known || details(session).indicator === 'attention')) submitted(session, text);
        draft = fresh();
      } else if (ch === '\x7f' || ch === '\b') {
        if (draft.cursor) { draft.text = draft.text.slice(0,draft.cursor-1) + draft.text.slice(draft.cursor); draft.cursor--; }
      } else if (ch === '\x01') draft.cursor = 0;
      else if (ch === '\x05') draft.cursor = draft.text.length;
      else if (ch === '\x15') { draft.text = draft.text.slice(draft.cursor); draft.cursor = 0; draft.known = !draft.text; }
      else if (ch === '\x0b') draft.text = draft.text.slice(0,draft.cursor);
      else if (ch === '\x03') draft = fresh();
      else if (ch === '\n' || ch >= ' ') insert(ch);
      else draft.known = false;
    }
    drafts.set(id, draft);
    if (drafts.size > 100) drafts.delete(drafts.keys().next().value);
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
  window.LabTerminalCompletion = {meta, status, isWorking, acknowledge, details, input, isLLM};
})();
