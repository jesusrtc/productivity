// Backend API wrapper + WebSocket client.

const BASE = ""; // same origin

async function request(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(BASE + path, opts);
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const j = await r.json();
      detail = j.detail || detail;
    } catch {}
    throw new Error(`${r.status}: ${detail}`);
  }
  const ct = r.headers.get("content-type") || "";
  if (ct.includes("application/json")) return r.json();
  return r.text();
}

export const api = {
  // Reads
  index: () => request("GET", "/api/index"),
  workspaces: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request("GET", "/api/workspaces" + (qs ? "?" + qs : ""));
  },
  workspace: (id) => request("GET", `/api/workspaces/${encodeURIComponent(id)}`),
  workspaceTasks: (id) => request("GET", `/api/workspaces/${encodeURIComponent(id)}/tasks`),
  workspaceDocs: (id) => request("GET", `/api/workspaces/${encodeURIComponent(id)}/docs`),
  workspaceFile: (id, path) =>
    request("GET", `/api/workspaces/${encodeURIComponent(id)}/file?path=${encodeURIComponent(path)}`),
  tasks: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request("GET", "/api/tasks" + (qs ? "?" + qs : ""));
  },
  tasksDue: (days) => request("GET", `/api/tasks/due?days=${days}`),
  markdown: (path) => request("GET", `/api/markdown?path=${encodeURIComponent(path)}`),
  notebook: (path) => request("GET", `/api/nb?path=${encodeURIComponent(path)}`),
  notebookSession: (path) =>
    request("GET", `/api/nb/session?path=${encodeURIComponent(path)}`),
  execCell: (body) => request("POST", "/api/nb/exec", body),
  search: (q) => request("GET", "/api/search?q=" + encodeURIComponent(q)),
  logFiles: () => request("GET", "/api/log/files"),
  logTail: (file, tail) => {
    const qs = new URLSearchParams({ file, tail: String(tail) });
    return request("GET", "/api/log/tail?" + qs.toString());
  },

  // Writes
  createWorkspace: (body) => request("POST", "/api/workspaces", body),
  createTask: (body) => request("POST", "/api/tasks", body),
  setTaskStatus: (workspaceId, taskId, body) =>
    request("POST", `/api/tasks/${encodeURIComponent(workspaceId)}/${taskId}/status`, body),
  updateTaskField: (workspaceId, taskId, body) =>
    request("POST", `/api/tasks/${encodeURIComponent(workspaceId)}/${taskId}/update`, body),
  addPR: (pid, body) => request("POST", `/api/workspaces/${encodeURIComponent(pid)}/prs`, body),
  rmPR: (pid, idx) => request("DELETE", `/api/workspaces/${encodeURIComponent(pid)}/prs/${idx}`),
  addArtifact: (pid, body) => request("POST", `/api/workspaces/${encodeURIComponent(pid)}/artifacts`, body),
  rmArtifact: (pid, idx) => request("DELETE", `/api/workspaces/${encodeURIComponent(pid)}/artifacts/${idx}`),

  // Git push (dashboard buttons)
  pushProductivity: () => request("POST", "/api/git/push-productivity"),
  syncContent: () => request("POST", "/api/git/sync-content"),
};

export function subscribeWS(onEvent) {
  let ws = null;
  let delay = 1000;
  const MAX_DELAY = 30000;
  let stopped = false;

  function connect() {
    if (stopped) return;
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws`);
    ws.onopen = () => {
      delay = 1000;
      try { ws.send("hello"); } catch {}
    };
    ws.onmessage = (ev) => {
      try {
        onEvent(JSON.parse(ev.data));
      } catch (e) {
        console.error("bad ws message", ev.data, e);
      }
    };
    ws.onclose = () => {
      if (stopped) return;
      setTimeout(connect, delay);
      delay = Math.min(delay * 2, MAX_DELAY);
    };
    ws.onerror = () => {
      try { ws.close(); } catch {}
    };
  }

  connect();

  return {
    close: () => {
      stopped = true;
      try { ws && ws.close(); } catch {}
    },
  };
}
