// Acknowledgements are browser-local and scoped to the exact conversation.
// They never use recent-selection timestamps: opening a running terminal must
// not acknowledge a response which has not finished yet.
(() => {
  const storageKey = 'labTerminalCompletionsSeen-v1';
  let seen = {};
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
  function see(scope, session) {
    reload(); // Merge acknowledgements from other Lab windows.
    const previous = record(scope, session);
    if (!previous?.completed || previous.at >= previous.completed.at) return false;
    const id = key(scope, session);
    seen[id] = {...previous, at: previous.completed.at};
    save();
    return true;
  }
  window.addEventListener('storage', event => {
    if (event.key !== storageKey) return;
    reload();
    if (typeof termRenderSessionList === 'function') termRenderSessionList();
  });
  const refresh = () => {
    if (!document.hidden && typeof termRenderSessionList === 'function') termRenderSessionList();
  };
  window.addEventListener('focus', refresh);
  document.addEventListener('visibilitychange', refresh);
  window.LabTerminalCompletion = {meta, see};
})();
