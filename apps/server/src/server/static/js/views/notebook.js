import { api } from "../api.js";
import { h, render as domRender } from "../lib/dom.js";

// Live-follow comes for free from app.js: its global WS subscriber re-invokes
// the current view's render() on every `index-updated` event, so simply
// re-fetching on each render (including the replays) keeps the notebook in
// sync with the file on disk.

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
  const execLabel = isCode
    ? `[${cell.execution_count == null ? " " : cell.execution_count}]`
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

  return h("div", { class: "nb-cell", "data-idx": String(idx) },
    header,
    body,
    outputsNode,
  );
}

export async function render(parent, { params }) {
  const path = params.get("path");
  if (!path) {
    domRender(parent, h("p", null, "Missing ?path="));
    return;
  }

  try {
    const nb = await api.notebook(path);
    const cellsNodes = (nb.cells || []).map(renderCell);
    domRender(parent,
      h("p", null,
        h("a", {
          href: "#",
          onclick: (e) => { e.preventDefault(); history.back(); },
        }, "← back"),
      ),
      h("h2", null, nb.path || path),
      h("div", { class: "nb-meta" }, `Last updated: ${fmtMtime(nb.mtime)}`),
      h("div", { class: "nb-cells" }, ...cellsNodes),
    );
    activateNotebookScripts(parent);
  } catch (e) {
    domRender(parent, h("p", null, "Error: " + e.message));
  }
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
