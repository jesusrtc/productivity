// Acknowledgements are browser-local and scoped to the exact conversation.
// They never use recent-selection timestamps: opening a running terminal must
// not acknowledge a response which has not finished yet.
(() => {
  const storageKey = 'labTerminalCompletionsSeen-v1';
  const delayKey = 'labTerminalCompletionReadSeconds';
  let seen = {};
  let viewing = null;
  let timer = null;
  function getDelaySeconds() {
    try {
      const value = Number(localStorage.getItem(delayKey));
      if (Number.isFinite(value) && value >= 1 && value <= 3600) return Math.round(value);
    } catch {}
    return 20;
  }
  function stopViewing() {
    if (timer !== null) clearTimeout(timer);
    timer = null;
    viewing = null;
  }
  function setDelaySeconds(value) {
    const number = Number(value);
    const seconds = Number.isFinite(number) && number >= 1 && number <= 3600 ? Math.round(number) : 20;
    try { localStorage.setItem(delayKey, String(seconds)); } catch {}
    stopViewing();
    refresh();
  }
  function reload() {
    try {
      const value = JSON.parse(localStorage.getItem(storageKey) || '{}');
      if (value && typeof value === 'object' && !Array.isArray(value)) seen = value;
    } catch {}
  }
  reload();
  function key(scope, session) {
    return JSON.stringify([scope, session.name, session.created_at,
      session.agent, session.agent_session_id]);
  }
  function completion(session) {
    const activity = session?.agent_activity;
    return activity?.state === 'completed' && activity.completion_id
      && Number.isFinite(activity.completed_at) && activity.completed_at > 0
      && session.agent_session_id ? activity : null;
  }
  function save() {
    const entries = Object.entries(seen);
    if (entries.length > 2000) seen = Object.fromEntries(entries
      .sort((a, b) => Math.max(b[1].at || 0, b[1].completed?.at || 0)
        - Math.max(a[1].at || 0, a[1].completed?.at || 0)).slice(0, 2000));
    try { localStorage.setItem(storageKey, JSON.stringify(seen)); } catch {}
  }
  function record(scope, session) {
    if (!session?.agent_session_id) return null;
    const id = key(scope, session);
    const activity = completion(session);
    if (activity && !(seen[id]?.completed?.at >= activity.completed_at)) {
      reload();
      if (!(seen[id]?.completed?.at >= activity.completed_at)) {
        seen[id] = {...seen[id], completed: {at: activity.completed_at}};
        save();
      }
    }
    return seen[id];
  }
  function meta(scope, session, now = Date.now()) {
    const previous = record(scope, session);
    if (!previous?.completed || previous.at >= previous.completed.at) return null;
    const minutes = Math.max(0, Math.floor((now - previous.completed.at * 1000) / 60000));
    const age = minutes < 1 ? 'just now' : minutes < 60 ? `${minutes} minutes ago`
      : minutes < 1440 ? `${Math.floor(minutes / 60)} hours ago` : `${Math.floor(minutes / 1440)} days ago`;
    return {label: `Finished · ${age} · Not yet viewed`};
  }
  function see(scope, session, completedAt) {
    reload(); // Merge acknowledgements from other Lab windows.
    const previous = record(scope, session);
    if (!previous?.completed || previous.at >= previous.completed.at) return false;
    if (previous.completed.at !== completedAt) return false;
    const id = key(scope, session);
    seen[id] = {...previous, at: previous.completed.at};
    save();
    return true;
  }
  function watch(scope, session) {
    const previous = record(scope, session);
    if (!previous?.completed || previous.at >= previous.completed.at) {
      stopViewing();
      return;
    }
    // Each response needs its own continuous viewing interval, even when
    // this terminal has been selected throughout the agent's work.
    const id = JSON.stringify([key(scope, session), previous.completed.at]);
    const now = performance.now();
    if (viewing?.id !== id) {
      stopViewing();
      viewing = {id, started: now};
    }
    const remaining = getDelaySeconds() * 1000 - (now - viewing.started);
    if (remaining <= 0) {
      see(scope, session, previous.completed.at);
      stopViewing();
    } else if (timer === null) {
      timer = setTimeout(() => {
        timer = null;
        // The render rechecks visibility, focus, connection, current tab,
        // and latest response before watch can acknowledge anything.
        refresh();
      }, remaining);
    }
  }
  window.addEventListener('storage', event => {
    if (event.key === delayKey) {
      stopViewing();
      refresh();
      return;
    }
    if (event.key !== storageKey) return;
    reload();
    if (typeof termRenderSessionList === 'function') termRenderSessionList();
  });
  function refresh() {
    if (!document.hidden && typeof termRenderSessionList === 'function') termRenderSessionList();
  }
  window.addEventListener('blur', stopViewing);
  window.addEventListener('pagehide', stopViewing);
  window.addEventListener('focus', refresh);
  document.addEventListener('visibilitychange', () => document.hidden ? stopViewing() : refresh());
  window.LabTerminalCompletion = {meta, watch, stopViewing, getDelaySeconds, setDelaySeconds};
})();
