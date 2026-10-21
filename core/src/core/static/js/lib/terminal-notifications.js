// Active alerts by default; the center also includes each terminal's last alert.
(() => {
  let scopes = {}, bridge;
  const pageSize = 20;
  let historyOpen = false, visibleCount = pageSize, searchQuery = '';
  const muteStorageKey = 'labTerminalNotificationMutes-v1';
  let mutes = {}, wakeTimer;
  const opening = new Set(), saving = new Set();
  const escape = value => String(value || '').replace(/[&<>"']/g,
    ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

  function reloadMutes() {
    mutes = {};
    try {
      const value = JSON.parse(localStorage.getItem(muteStorageKey) || '{}');
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        for (const [key, mute] of Object.entries(value)) {
          // Only timed snoozes are supported; ignore legacy permanent dismissals.
          if (mute && typeof mute.report_id === 'string' && Number.isFinite(mute.until) && mute.until > 0) mutes[key] = mute;
        }
      }
    } catch {}
  }
  function muted(key, report) {
    const mute = report.kind && mutes[key];
    // Recurring automation check-ins share one launch source. A new cycle
    // cannot interrupt a full 30-minute snooze; a new launch can still alert.
    return mute && (mute.report_id === report.id || report.kind === 'automation' && mute.source === report.source)
      && mute.until > Date.now() / 1000 ? mute : null;
  }
  function scheduleWake() {
    clearTimeout(wakeTimer);
    const now = Date.now() / 1000;
    const times = [...Object.values(mutes).map(mute => mute.until),
      ...Object.values(scopes).flat().map(session => session.terminal_watch)
        .filter(watch => watch?.mode === 'remind').map(watch => watch.due_at)].filter(until => until > now);
    if (times.length) wakeTimer = setTimeout(render, Math.min(2147483647, Math.ceil(Math.min(...times) * 1000 - Date.now())));
  }
  function snoozeAlert(key, reportId) {
    // Match the displayed report and incarnation; an old control cannot mute
    // a replacement alert or alter the agent's working/attention/finished state.
    const item = findItem(key, reportId);
    if (!item?.kind || !item.active) return false;
    reloadMutes();
    mutes[key] = {report_id:reportId, ...(item.kind === 'automation' ? {source:item.source} : {}),
      until:Date.now() / 1000 + 30 * 60, updated_at:Date.now() / 1000};
    mutes = Object.fromEntries(Object.entries(mutes).sort((a, b) => b[1].updated_at - a[1].updated_at).slice(0, 2000));
    try { localStorage.setItem(muteStorageKey, JSON.stringify(mutes)); } catch {}
    render();
    return true;
  }

  function items({history = false} = {}) {
    const completion = window.LabTerminalCompletion, unique = new Map();
    if (!completion) return [];
    for (const [scope, sessions] of Object.entries(scopes)) {
      const separator = scope.indexOf('::');
      for (const session of sessions) {
        const details = completion.details(session);
        const direct = ['attention', 'finished'].includes(details.indicator) ? details.report : null;
        const watch = session.terminal_watch;
        const watching = watch && (watch.mode === 'pin' || watch.mode === 'remind' && watch.due_at <= Date.now() / 1000);
        const report = watching ? watch.report : history ? details.notification || (watch?.mode === 'closed' ? watch.report : null)
          : details.progress_alert || (direct?.state === 'attention' ? direct : null) || details.recovery_alert || direct || details.automation_alert || details.report;
        if (!report || !['attention', 'finished'].includes(report.state)
            || !history && !watching && !details.progress_alert && !details.automation_alert && !details.recovery_alert && !direct) continue;
        const closed = watch?.mode === 'closed' && watch.closed_report_id === report.id;
        if (!history && closed) continue;
        const key = completion.key(session);
        const mute = muted(key, report);
        if (!history && mute && !watching) continue;
        const owner = {workspace_id:session.workspace_id || scope.slice(separator + 2),
          vault:session.vault || scope.slice(0, separator)};
        const active = !closed && (!!watching || !mute && (details.progress_alert?.id === report.id || details.automation_alert?.id === report.id || details.recovery_alert?.id === report.id
          || details.indicator === report.state && details.report?.id === report.id));
        const age = Math.max(30, Math.floor((Date.now() / 1000 - (session.terminal_progress?.since || 0)) / 60));
        const message = !watching && active && report.kind === 'stale'
          ? `WIP · No progress update for ${age} min · Last report: ${session.terminal_progress.message || 'No report yet'}` : report.message;
        // A watch retains the last notification, not its old completion color.
        // Match the tab's live working state (including submitted input), while
        // keeping active supervisor alerts and the exact report used by close.
        const working = !!watching && details.indicator === 'working'
          && ![details.progress_alert, details.recovery_alert, details.automation_alert].some(alert => alert?.id === report.id);
        const item = {key, session, owner, report_id:report.id, state:working ? 'working' : report.state, kind:working ? null : report.kind, source:report.source, targets:report.targets,
          created_at:report.updated_at, revision:report.revision,
          active, mute:watching ? null : mute, watch:watching ? watch : null, message:message || (report.state === 'attention' ? 'Needs your input' : 'Work finished')};
        // Prefer the native row over another workspace's shared view.
        if (!unique.has(key) || scope === `${owner.vault}::${owner.workspace_id}`) unique.set(key, item);
      }
    }
    const priority = row => row.state === 'working' || ['automation','watch'].includes(row.kind) ? 1 : row.state === 'attention' ? 0 : 2;
    return [...unique.values()].sort((a, b) => (history ? 0 : priority(a) - priority(b))
      || (b.created_at || 0) - (a.created_at || 0) || b.revision - a.revision);
  }

  function findItem(key, reportId) {
    return [...items(), ...items({history:true})].find(row => row.key === key && row.report_id === reportId);
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
    const item = findItem(key, reportId);
    if (!item || opening.has(key)) return false;
    opening.add(key); render();
    try {
      const session = await bridge?.open(item);
      if (!session) return false;
      if (item.state === 'finished' && !item.watch) window.LabTerminalCompletion.acknowledge('', session, reportId);
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
    return (row.kind ? row.kind === 'reconnect' ? 'Reconnect failed' : row.kind === 'watch' ? 'Check terminal' : row.kind === 'automation' ? 'Check automation status' : row.kind === 'stale' ? 'Progress overdue' : 'Status not closed'
      : row.state === 'working' ? 'Working' : row.state === 'attention' ? 'Needs input' : 'Finished') + (historyOpen && !row.active ? ' · History' : '')
      + (row.watch ? row.watch.mode === 'pin' ? ' · Pinned' : ' · Reminder' : '')
      + (row.mute ? ' · Snoozed until ' + new Date(row.mute.until * 1000).toLocaleTimeString([], {hour:'numeric', minute:'2-digit'}) : '');
  }
  const normalize = value => String(value || '').normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
  function setSearch(value) {
    searchQuery = value; visibleCount = pageSize;
    render();
    const host = document.getElementById('termNotifications');
    if (host) host.scrollTop = 0;
  }

  function render() {
    scheduleWake();
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
      const message = (row.state === 'working' ? 'Last notification: ' : '') + row.message;
      const time = historyOpen && Number.isFinite(date.getTime())
        ? `<time class="term-notification-time" datetime="${date.toISOString()}">${escape(date.toLocaleString())}</time>` : '';
      const card = `<button type="button" class="term-notification ${row.state}${['automation','watch'].includes(row.kind) ? ' automation-reminder' : ''}${row.watch ? ' watched-notification' : ''}${row.active ? ' active-alert' : ''}" data-active="${row.active}" data-key="${escape(row.key)}" data-report-id="${escape(row.report_id)}"${opening.has(row.key) ? ' disabled' : ''} aria-label="${escape(label + ' · ' + state + ' · ' + message)}" title="${escape(label + ' · ' + state + ' · ' + message)}"><span class="term-notification-icon" aria-hidden="true">${['automation','watch'].includes(row.kind) ? '?' : row.state === 'working' ? '…' : row.state === 'attention' ? '!' : '✓'}</span><span class="term-notification-copy"><span class="term-notification-heading"><span class="term-notification-terminal-icon" aria-hidden="true">${icon}</span><span class="term-notification-context">${escape(label + ' · ' + state)}</span></span><span class="term-notification-message">${escape(message)}</span>${time}</span><span aria-hidden="true">↗</span></button>`;
      if (row.watch) return `<div class="term-notification-group term-notification-watched">${card}<button type="button" class="term-notification-dismiss" data-notification-watch-close data-key="${escape(row.key)}" data-report-id="${escape(row.report_id)}" data-watch-id="${escape(row.watch.id)}" aria-label="Close watched notification" title="Close watched notification"${saving.has(row.key) ? ' disabled' : ''}>×</button></div>`;
      if (row.kind === 'reconnect' && row.active) return `<div class="term-notification-group">${card}<div class="term-notification-actions"><button type="button" data-notification-reconnect${saving.has(row.key) ? ' disabled' : ''}>Reconnect</button></div></div>`;
      return row.kind && row.active ? `<div class="term-notification-group">${card}<div class="term-notification-actions"><button type="button" data-notification-snooze aria-label="Snooze reminder for 30 minutes">Snooze 30 min</button></div></div>` : card;
    }).join('');
    if (historyOpen && !rows.length) html += '<p class="term-notification-empty">' + (all.length ? 'No matching notifications.' : 'No notifications yet.') + '</p>';
    if (historyOpen && filtered.length > rows.length) html += '<button type="button" class="term-notification-more" data-notification-more>Load more</button>';
    const list = historyOpen ? host.querySelector('[data-notification-list]') : host;
    if (list._notificationHtml === html) return;
    const scroll = host.scrollTop;
    const expanded = new Set([...list.querySelectorAll('.term-notification-watched')]
      .filter(group => group.matches(':hover, :focus-within'))
      .map(group => group.querySelector('.term-notification')?.dataset.key));
    const focused = document.activeElement?.closest?.('.term-notification-watched');
    const focusCard = focused?.querySelector('.term-notification');
    const focus = focusCard && {key:focusCard.dataset.key, report:focusCard.dataset.reportId,
      close:document.activeElement.hasAttribute('data-notification-watch-close')};
    list._notificationHtml = html; list.innerHTML = html;
    host.querySelectorAll('.term-notification-watched').forEach(group => {
      const card = group.querySelector('.term-notification');
      if (!historyOpen && expanded.has(card.dataset.key)) group.classList.add('notification-expanded');
      group.addEventListener('pointerleave', () => group.classList.remove('notification-expanded'));
      group.addEventListener('focusout', () => queueMicrotask(() => {
        if (!group.matches(':hover, :focus-within')) group.classList.remove('notification-expanded');
      }));
      if (focus?.key === card.dataset.key) {
        const control = focus.close && focus.report === card.dataset.reportId
          ? group.querySelector('[data-notification-watch-close]') : card;
        if (!control.disabled) control.focus({preventScroll:true});
      }
    });
    host.scrollTop = scroll;
    host.querySelectorAll('.term-notification').forEach(button => {
      button.onclick = () => void open(button.dataset.key, button.dataset.reportId)
        .catch(error => bridge?.error(error.message || 'Could not open terminal.'));
    });
    host.querySelectorAll('[data-notification-watch-close]').forEach(button => {
      button.onclick = () => {
        const row = items({history:true}).find(item => item.key === button.dataset.key
          && item.report_id === button.dataset.reportId && item.watch?.id === button.dataset.watchId);
        if (row) void setWatch(row.session, 'close', {watch_id:row.watch.id, report_id:row.report_id})
          .then(() => (host.querySelector('[data-notification-search]') || document.querySelector('[data-terminal-notification-center]'))?.focus({preventScroll:true}))
          .catch(error => bridge?.error(error.message));
      };
    });
    host.querySelectorAll('[data-notification-reconnect]').forEach(button => {
      button.onclick = async () => {
        const card = button.closest('.term-notification-group').querySelector('.term-notification');
        const row = findItem(card.dataset.key, card.dataset.reportId);
        if (!row || saving.has(row.key)) return;
        saving.add(row.key); render();
        try { await bridge?.reconnect?.(row); }
        catch (error) { bridge?.error(error.message || 'Could not reconnect automation.'); }
        finally { saving.delete(row.key); render(); }
      };
    });
    host.querySelectorAll('[data-notification-snooze]').forEach(button => {
      button.onclick = () => {
        const card = button.closest('.term-notification-group').querySelector('.term-notification');
        snoozeAlert(card.dataset.key, card.dataset.reportId);
        // Muting a floating card removes its focused control. Keep keyboard
        // focus in the center when open, otherwise return to the bell.
        (host.querySelector('[data-notification-search]') || document.querySelector('[data-terminal-notification-center]'))?.focus({preventScroll:true});
      };
    });
    host.querySelector('[data-notification-more]')?.addEventListener('click', () => {
      const previous = visibleCount; visibleCount += pageSize; render();
      host.querySelectorAll('.term-notification')[previous]?.focus({preventScroll:true});
    });
  }

  function reminderTime(choice, now = new Date()) {
    if (choice === 'tomorrow') {
      const due = new Date(now); due.setDate(due.getDate() + 1); due.setHours(9, 0, 0, 0);
      return due.getTime() / 1000;
    }
    const seconds = Number(choice);
    if (![600, 1800, 3600, 7200, 21600].includes(seconds)) throw Error('Choose a reminder time.');
    return now.getTime() / 1000 + seconds;
  }
  async function setWatch(session, mode, options = {}) {
    const key = window.LabTerminalCompletion.key(session);
    if (saving.has(key)) return false;
    saving.add(key); render();
    try {
      const response = await fetch('/api/term/watch', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({name:session.name, tmux_socket:session.tmux_socket || 'default',
          tmux_id:session.tmux_id, created:session.created ?? session.created_at, mode, ...options})});
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw Error(body.detail || 'Could not save terminal watch.');
      for (const sessions of Object.values(scopes)) for (const row of sessions)
        if (window.LabTerminalCompletion.key(row) === key) row.terminal_watch = body.watch;
      session.terminal_watch = body.watch;
      await bridge?.changed?.();
      return true;
    } finally { saving.delete(key); render(); }
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
  window.addEventListener('storage', event => {
    if (event.key !== muteStorageKey && event.key !== null) return;
    reloadMutes(); render();
  });
  document.addEventListener('visibilitychange', render);
  reloadMutes();
  window.LabTerminalNotifications = {items, open, render, buttonHtml, showHistory, setWatch, reminderTime,
    snooze(key, reportId) { return snoozeAlert(key, reportId); },
    toggleHistory() { return showHistory(!historyOpen); },
    update(value) { scopes = value; render(); },
    configure(value) { bridge = value; render(); }};
})();
