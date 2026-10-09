// Acknowledgements are browser-local and scoped to the terminal incarnation
// (and the exact conversation when provider events are used).
// They never use recent-selection timestamps: opening a running terminal must
// not acknowledge a response which has not finished yet.
(() => {
  const storageKey = 'labTerminalCompletionsSeen-v1';
  const activityKey = 'labTerminalActivity-v1';
  const quietSeconds = 40;
  let seen = {};
  let observed = {};
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
      session.agent, observed[terminalKey(session)]?.mode === 'output'
        ? observed[terminalKey(session)].outputVersion === 2 ? 'content' : 'output'
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
    const previousOutput = session && observed[terminalKey(session)];
    // Cached rows from before content verification must not revive the raw
    // I/O signals which caused false yellow/green cycles on idle SSH shells.
    if (previousOutput?.outputVersion === 2 && output && output.version !== 2) {
      return seen[key(scope, session)];
    }
    if (Number.isFinite(output?.updated_at)
        && (output.version === 2 ? output.updated_at >= 0 : output.updated_at > 0)
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
    const version = output.version === 2 ? 2 : 1;
    const same = previous?.mode === 'output' && (previous.outputVersion || 1) === version;
    const sameGeneration = same && (version !== 2 || previous.generation === output.generation);
    if (same && (output.observed_at < previous.sampledAt
        || sameGeneration && output.updated_at < previous.outputAt)) {
      return seen[key(scope, session)];
    }
    // Use server-measured age plus elapsed local time, so a remote browser's
    // clock offset cannot mark a busy terminal quiet or keep it yellow forever.
    // A new object carrying the same cached sample must not reset that age.
    const sameEvent = sameGeneration && output.updated_at === previous.outputAt;
    const deadline = Date.now() + (quietSeconds - (output.observed_at - output.updated_at)) * 1000;
    const quietAt = sameEvent && Number.isFinite(previous.quietAt)
      ? Math.min(previous.quietAt, deadline) : deadline;
    const working = output.updated_at > 0 && Date.now() < quietAt
      && (!sameEvent || previous.working);
    const hadOutput = version === 2 ? output.updated_at > 0 : working || (same
      ? previous.hadOutput || output.updated_at > previous.outputAt
      : output.updated_at > Number(session.created_at ?? session.created ?? 0));
    let completedAt = same ? previous.completedAt || 0 : 0;
    // Do not mark a terminal that has been idle since creation as newly
    // finished. A real output change or an observed active period is needed.
    if (!working && hadOutput) {
      completedAt = Math.max(completedAt, output.updated_at + quietSeconds);
    }
    if (!sameGeneration || previous.outputAt !== output.updated_at || previous.working !== working
        || previous.completedAt !== completedAt || previous.sampledAt !== output.observed_at
        || previous.quietAt !== quietAt) {
      observed[terminal] = {mode:'output', outputVersion:version, generation:output.generation,
        outputAt:output.updated_at, sampledAt:output.observed_at, quietAt,
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
  function acknowledge(scope, session) {
    if (document.hidden || !document.hasFocus()) return false;
    const previous = record(scope, session);
    if (!previous?.completed || previous.at >= previous.completed.at) return false;
    if (!see(scope, session, previous.completed.at)) return false;
    refresh();
    return true;
  }
  window.addEventListener('storage', event => {
    if (event.key !== storageKey && event.key !== activityKey) return;
    reload();
    if (typeof termRenderSessionList === 'function') termRenderSessionList();
    window.dispatchEvent?.(new Event('lab-terminal-completion-change'));
  });
  function refresh() {
    if (!document.hidden && typeof termRenderSessionList === 'function') termRenderSessionList();
  }
  window.addEventListener('focus', refresh);
  document.addEventListener('visibilitychange', refresh);
  window.LabTerminalCompletion = {meta, isWorking, acknowledge};
})();
