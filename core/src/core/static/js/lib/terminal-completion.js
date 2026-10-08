// Acknowledgements are browser-local and scoped to the terminal incarnation
// (and the exact conversation when provider events are used).
// They never use recent-selection timestamps: opening a running terminal must
// not acknowledge a response which has not finished yet.
(() => {
  const storageKey = 'labTerminalCompletionsSeen-v1';
  const activityKey = 'labTerminalActivity-v1';
  const delayKey = 'labTerminalCompletionReadSeconds';
  const quietSeconds = 40;
  const outputSamples = new WeakMap();
  let seen = {};
  let observed = {};
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
      const activity = JSON.parse(localStorage.getItem(activityKey) || '{}');
      if (activity && typeof activity === 'object' && !Array.isArray(activity)) observed = activity;
    } catch {}
  }
  reload();
  function terminalKey(session) {
    return JSON.stringify([session.name, session.created_at ?? session.created, session.agent]);
  }
  function key(scope, session) {
    // A shared terminal has one acknowledgement across workspace/document views.
    return JSON.stringify(['session', session.name, session.created_at ?? session.created,
      session.agent, observed[terminalKey(session)]?.mode === 'output' ? 'output'
        : session.agent_session_id || observed[terminalKey(session)]?.conversation]);
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
    const output = session?.output_activity;
    if (Number.isFinite(output?.updated_at) && output.updated_at > 0
        && Number.isFinite(output.observed_at) && output.observed_at >= output.updated_at) {
      return recordOutput(scope, session, output);
    }
    // An unavailable/stale listing is not evidence that output has stopped.
    if (session && observed[terminalKey(session)]?.mode === 'output') return seen[key(scope, session)];
    if (!session || !['codex', 'claude', 'copilot'].includes(session.agent)) return null;
    const terminal = terminalKey(session);
    const previous = observed[terminal];
    const conversation = session.agent_session_id || previous?.conversation;
    if (!conversation) return null;
    const state = session.agent_activity?.state;
    const activity = completion(session);
    const updatedAt = Number(session.agent_activity?.updated_at) || 0;
    let stateAt = previous?.conversation === conversation ? previous.stateAt || 0 : 0;
    let completedAt = previous?.conversation === conversation ? previous.completedAt || 0 : 0;
    let working = previous?.conversation === conversation && previous.working === true;
    if (session.agent_session_id && (!updatedAt || updatedAt > stateAt
        || activity && updatedAt === stateAt && activity.completed_at > completedAt)) {
      if (state === 'working' || state === 'waiting') working = true;
      else if (state === 'interrupted' || state === 'error') working = false;
      else if (activity && activity.completed_at > completedAt) {
        // A cached row from another view must not replay an old completion
        // and clear the yellow dot for newer work in the same conversation.
        completedAt = activity.completed_at;
        working = false;
      }
      if (['working', 'waiting', 'interrupted', 'error'].includes(state) || activity) stateAt = updatedAt;
    }
    if (previous?.conversation !== conversation || previous.working !== working
        || previous.completedAt !== completedAt || previous.stateAt !== stateAt) {
      observed[terminal] = {conversation, working, completedAt, stateAt, updated: Date.now()};
      saveObserved();
    }
    const id = key(scope, session);
    const legacy = JSON.stringify([scope, session.name, session.created_at, session.agent, session.agent_session_id]);
    if (!seen[id] && seen[legacy]) { seen[id] = seen[legacy]; save(); }
    if (activity && !(seen[id]?.completed?.at >= activity.completed_at)) {
      reload();
      if (!(seen[id]?.completed?.at >= activity.completed_at)) {
        seen[id] = {...seen[id], completed: {at: activity.completed_at}};
        save();
      }
    }
    return seen[id];
  }
  function recordOutput(scope, session, output) {
    const terminal = terminalKey(session), previous = observed[terminal];
    const same = previous?.mode === 'output';
    if (same && (output.updated_at < previous.outputAt
        || output.updated_at === previous.outputAt && output.observed_at < previous.sampledAt)) {
      return seen[key(scope, session)];
    }
    if (!outputSamples.has(output)) outputSamples.set(output, Date.now());
    // Use server-measured age plus elapsed local time, so a remote browser's
    // clock offset cannot mark a busy terminal quiet or keep it yellow forever.
    const idle = output.observed_at - output.updated_at
      + Math.max(0, Date.now() - outputSamples.get(output)) / 1000;
    const working = idle < quietSeconds;
    const hadOutput = working || (same ? previous.hadOutput || output.updated_at > previous.outputAt
      : output.updated_at > Number(session.created_at ?? session.created ?? 0));
    let completedAt = same ? previous.completedAt || 0 : 0;
    // Do not mark a terminal that has been idle since creation as newly
    // finished. A real output change or an observed active period is needed.
    if (!working && hadOutput) {
      completedAt = Math.max(completedAt, output.updated_at + quietSeconds);
    }
    if (!same || previous.outputAt !== output.updated_at || previous.working !== working
        || previous.completedAt !== completedAt) {
      observed[terminal] = {mode:'output', outputAt:output.updated_at, sampledAt:output.observed_at,
        hadOutput, working, completedAt, updated:Date.now()};
      saveObserved();
    }
    const id = key(scope, session);
    if (completedAt && !(seen[id]?.completed?.at >= completedAt)) {
      reload();
      if (!(seen[id]?.completed?.at >= completedAt)) {
        seen[id] = {...seen[id], completed:{at:completedAt, source:'output'}};
        save();
      }
    }
    return seen[id];
  }
  function saveObserved() {
    const entries = Object.entries(observed);
    if (entries.length > 2000) observed = Object.fromEntries(entries
      .sort((a, b) => b[1].updated - a[1].updated).slice(0, 2000));
    try { localStorage.setItem(activityKey, JSON.stringify(observed)); } catch {}
  }
  function isWorking(session) {
    record('', session);
    return !!session && observed[terminalKey(session)]?.working === true;
  }
  function meta(scope, session, now = Date.now()) {
    const previous = record(scope, session);
    if (!previous?.completed || previous.at >= previous.completed.at) return null;
    const minutes = Math.max(0, Math.floor((now - previous.completed.at * 1000) / 60000));
    const age = minutes < 1 ? 'just now' : minutes < 60 ? `${minutes} minutes ago`
      : minutes < 1440 ? `${Math.floor(minutes / 60)} hours ago` : `${Math.floor(minutes / 1440)} days ago`;
    return {label: previous.completed.source === 'output'
      ? 'Output quiet for 40 seconds · Ready to review · Not yet viewed'
      : `Finished · ${age} · Not yet viewed`};
  }
  function see(scope, session, completedAt) {
    reload(); // Merge acknowledgements from other Lab windows.
    const previous = record(scope, session);
    if (!previous?.completed || previous.at >= previous.completed.at) return false;
    if (previous.completed.at !== completedAt) return false;
    const id = key(scope, session);
    seen[id] = {...previous, at: previous.completed.at};
    save();
    window.dispatchEvent?.(new Event('lab-terminal-completion-change'));
    return true;
  }
  function watch(scope, session) {
    const previous = record(scope, session);
    if (isWorking(session) || !previous?.completed || previous.at >= previous.completed.at) {
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
  function acknowledge(scope, session) {
    if (document.hidden || !document.hasFocus()) return false;
    const previous = record(scope, session);
    if (!previous?.completed || previous.at >= previous.completed.at) return false;
    if (!see(scope, session, previous.completed.at)) return false;
    stopViewing();
    refresh();
    return true;
  }
  window.addEventListener('storage', event => {
    if (event.key === delayKey) {
      stopViewing();
      refresh();
      return;
    }
    if (event.key !== storageKey && event.key !== activityKey) return;
    reload();
    if (typeof termRenderSessionList === 'function') termRenderSessionList();
    window.dispatchEvent?.(new Event('lab-terminal-completion-change'));
  });
  function refresh() {
    if (!document.hidden && typeof termRenderSessionList === 'function') termRenderSessionList();
    else if (!document.hidden) window.LabDocumentTerminal?.watchCompletion();
  }
  window.addEventListener('blur', stopViewing);
  window.addEventListener('pagehide', stopViewing);
  window.addEventListener('focus', refresh);
  document.addEventListener('visibilitychange', () => document.hidden ? stopViewing() : refresh());
  window.LabTerminalCompletion = {meta, isWorking, watch, stopViewing, acknowledge, getDelaySeconds, setDelaySeconds};
})();
