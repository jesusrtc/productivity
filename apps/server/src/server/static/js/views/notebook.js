import { api } from "../api.js";
import { h, render as domRender } from "../lib/dom.js";

// The notebook view is both a viewer (renders the .ipynb on disk) and an
// executor (sticky editor at the bottom that POSTs to /api/nb/exec; the
// resulting write to disk fires the watcher → WS → re-render). The same path
// is used by the UI and by Claude Code calling the endpoint directly, so a
// cell appended from anywhere shows up here automatically.

const DRAFT_PREFIX = "nb-draft:";

function fmtMtime(mtime) {
  if (!mtime && mtime !== 0) return "—";
  try {
    return new Date(mtime * 1000).toLocaleString();
  } catch {
    return String(mtime);
  }
}

function renderOutput(out) {
  const type = out && out.type;
  const content = out && out.content != null ? out.content : "";
  if (type === "image") {
    return h("div", { class: "nb-output" },
      h("img", { src: `data:image/png;base64,${content}` }),
    );
  }
  if (type === "html") {
    return h("div", { class: "nb-output nb-output-html", html: content });
  }
  if (type === "error") {
    return h("div", { class: "nb-output nb-output-error" }, content);
  }
  return h("pre", { class: "nb-output" }, content);
}

function renderCell(cell, idx) {
  const isCode = cell.cell_type === "code";
  // `lab_pending` is set by the nb_exec endpoint while a Darwin call is
  // in flight (see routes/nb_exec.py:_write_pending_cell). It survives
  // the round-trip via parse_notebook -> cell.metadata. When present,
  // we paint the cell with the same running frame the in-UI editor
  // uses for optimistic renders so the user sees consistent feedback
  // regardless of whether the run came from a curl or the Run button.
  const isPending = isCode && cell.metadata && cell.metadata.lab_pending === true;
  const execLabel = isCode
    ? (isPending ? "[*]" : `[${cell.execution_count == null ? " " : cell.execution_count}]`)
    : "";

  const header = h("div", { class: "nb-cell-header" },
    h("span", { class: "nb-cell-type" }, cell.cell_type || "cell"),
    isCode ? " " : null,
    isCode ? h("span", { class: "nb-cell-exec" }, execLabel) : null,
  );

  let body;
  if (cell.cell_type === "markdown") {
    body = h("div", { class: "nb-markdown", html: cell.html || "" });
  } else {
    body = h("pre", { class: "nb-source" },
      h("code", null, cell.source || ""),
    );
  }

  const outputs = (cell.outputs || []).map(renderOutput);
  const outputsNode = outputs.length
    ? h("div", { class: "nb-outputs" }, ...outputs)
    : null;

  return h("div", {
    class: "nb-cell" + (isPending ? " nb-cell-pending" : ""),
    "data-idx": String(idx),
  }, header, body, outputsNode);
}

// A code cell rendered before Darwin returns, so the user sees the run land
// immediately instead of waiting for the (blocking) execute call to finish.
// The watcher's WS broadcast will swap this for the real cell when the
// on-disk .ipynb gets the new outputs.
function renderPendingCell(code) {
  return h("div", { class: "nb-cell nb-cell-pending" },
    h("div", { class: "nb-cell-header" },
      h("span", { class: "nb-cell-type" }, "code"),
      " ",
      h("span", { class: "nb-cell-exec" }, "[*]"),
    ),
    h("pre", { class: "nb-source" },
      h("code", null, code || ""),
    ),
    h("div", { class: "nb-outputs" },
      h("div", { class: "nb-output nb-output-pending" },
        h("span", { class: "nb-spinner" }),
        "Running on Darwin…",
      ),
    ),
  );
}

function renderEditor(path, onRun, cellsContainer) {
  const draftKey = DRAFT_PREFIX + path;
  const initial = (() => {
    try { return localStorage.getItem(draftKey) || ""; } catch { return ""; }
  })();

  const textarea = h("textarea", {
    class: "nb-editor-input",
    placeholder: "Paste code here, then Cmd/Ctrl+Enter or click Run…",
    rows: "6",
    spellcheck: "false",
  });
  textarea.value = initial;
  textarea.addEventListener("input", () => {
    try { localStorage.setItem(draftKey, textarea.value); } catch {}
  });

  const status = h("span", { class: "nb-editor-status" }, "");
  const button = h("button", { class: "nb-run-btn", type: "button" }, "Run");

  async function run() {
    const code = (textarea.value || "").trim();
    if (!code) return;
    button.disabled = true;
    status.textContent = "Running on Darwin…";
    status.className = "nb-editor-status nb-editor-status-running";

    // Optimistic placeholder: show the code + spinner immediately so the
    // user doesn't stare at the old outputs while darwin blocks. The
    // watcher will re-render the whole view once the .ipynb is written.
    let pending = null;
    if (cellsContainer) {
      pending = renderPendingCell(code);
      cellsContainer.appendChild(pending);
      pending.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    textarea.value = "";
    try { localStorage.removeItem(draftKey); } catch {}

    try {
      await onRun(code);
      status.textContent = "";
      status.className = "nb-editor-status";
    } catch (e) {
      // Surface the error on the pending cell so the run-attempt isn't lost.
      if (pending) {
        const out = pending.querySelector(".nb-output-pending");
        if (out) {
          out.className = "nb-output nb-output-error";
          out.textContent = "Error: " + (e.message || String(e));
        }
      }
      status.textContent = "Error: " + (e.message || String(e));
      status.className = "nb-editor-status nb-editor-status-error";
    } finally {
      button.disabled = false;
    }
  }

  button.addEventListener("click", run);
  textarea.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      run();
    }
  });

  return h("div", { class: "nb-editor" },
    h("div", { class: "nb-editor-toolbar" },
      h("span", { class: "nb-editor-title" }, "New cell"),
      status,
      button,
    ),
    textarea,
  );
}

export async function render(parent, { params }) {
  const path = params.get("path");
  if (!path) {
    domRender(parent, h("p", null, "Missing ?path="));
    return;
  }

  // Fetch cells; an absent file is normal — we'll show an empty notebook
  // ready for its first cell. Session is fetched in parallel.
  let nb = { path, cells: [], mtime: null };
  let session = null;
  let notFound = false;
  try {
    const [nbResp, sessResp] = await Promise.all([
      api.notebook(path).catch((e) => {
        if (e && /^404:/.test(e.message)) { notFound = true; return null; }
        throw e;
      }),
      api.notebookSession(path).catch(() => null),
    ]);
    if (nbResp) nb = nbResp;
    if (sessResp) session = sessResp.session;
  } catch (e) {
    domRender(parent, h("p", null, "Error: " + e.message));
    return;
  }

  const cellsNodes = (nb.cells || []).map(renderCell);
  const cellsContainer = h("div", { class: "nb-cells" }, ...cellsNodes);

  async function handleRun(code) {
    await api.execCell({ path, code });
    // The .ipynb write fires index-updated → WS → re-route, which usually
    // replaces the pending cell on its own. Force a re-render here as a
    // backstop in case the WS event was deduped or dropped — render() is
    // idempotent so a double-render is harmless.
    await render(parent, { params });
  }

  domRender(parent,
    h("p", null,
      h("a", {
        href: "#",
        onclick: (e) => { e.preventDefault(); history.back(); },
      }, "← back"),
    ),
    h("h2", null, nb.path || path),
    h("div", { class: "nb-meta" },
      `Last updated: ${fmtMtime(nb.mtime)}`,
      session ? " · " : null,
      session ? h("span", { class: "nb-session-badge", title: "Darwin kernel session pinned to this file" }, "kernel: " + session) : null,
      notFound ? " · (new notebook)" : null,
    ),
    cellsContainer,
    renderEditor(path, handleRun, cellsContainer),
  );
  activateNotebookScripts(parent);
}

// Browsers ignore <script> injected via innerHTML, so DAVI/Plotly cells that
// emit <div> + <script> display_data pairs render blank. Walk the inserted
// subtree and swap each dormant <script> for a freshly-created live one.
// Also shim `require(["plotly"], fn)` (Jupyter's requirejs idiom) so Plotly
// chart init can find the Plotly global that the preceding inline bundle
// exposes on window.
function _installRequireShim() {
  if (typeof window.require === "function") return;
  window.require = function (deps, fn) {
    const resolved = (deps || []).map((d) => (d === "plotly" ? window.Plotly : window[d]));
    if (typeof fn === "function") return fn.apply(null, resolved);
    return resolved[0];
  };
}

// Plotly is preloaded via <script defer> in spa.html but might not have
// finished parsing by the time the user lands on #/nb?path=…. If any cell
// will call `require(["plotly"], fn)`, hold off activating scripts until
// window.Plotly shows up (bounded wait to avoid hangs).
function _waitForPlotly(root, timeoutMs = 5000) {
  const scripts = root.querySelectorAll(".nb-outputs script, .nb-output-html script");
  const needs = Array.from(scripts).some((s) => {
    const t = s.textContent || "";
    return t.indexOf('require(["plotly"') !== -1 || t.indexOf("require(['plotly'") !== -1;
  });
  if (!needs || window.Plotly) return Promise.resolve();
  return new Promise((resolve) => {
    const start = Date.now();
    const poll = () => {
      if (window.Plotly) return resolve();
      if (Date.now() - start > timeoutMs) return resolve();
      setTimeout(poll, 50);
    };
    poll();
  });
}

async function activateNotebookScripts(root) {
  if (!root) return;
  _installRequireShim();
  await _waitForPlotly(root);
  root.querySelectorAll(".nb-outputs script, .nb-output-html script").forEach((old) => {
    const s = document.createElement("script");
    for (const a of old.attributes) s.setAttribute(a.name, a.value);
    if (old.textContent) s.text = old.textContent;
    old.parentNode.replaceChild(s, old);
  });
}
