import { api } from "../api.js";
import { h, render as domRender } from "../lib/dom.js";

const DEFAULT_FILE = "errors.log";
const DEFAULT_TAIL = 500;

function readTail(params) {
  const raw = Number(params && params.get("tail"));
  if (!Number.isFinite(raw) || raw <= 0) return DEFAULT_TAIL;
  return Math.min(Math.floor(raw), 5000);
}

function readFile(params) {
  return (params && params.get("file")) || DEFAULT_FILE;
}

function updateUrl(file, tail) {
  const qs = new URLSearchParams({ file, tail: String(tail) }).toString();
  if (location.pathname === "/logs") {
    history.replaceState(null, "", `/logs?${qs}`);
  } else {
    location.hash = `#/logs?${qs}`;
  }
}

function fmtTs(ts) {
  if (!ts) return "";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return String(ts);
  }
}

function compactMeta(entry) {
  const bits = [];
  if (entry.source) bits.push(entry.source);
  if (entry.logger) bits.push(entry.logger);
  if (entry.method || entry.status_code) {
    bits.push([entry.method, entry.status_code].filter(Boolean).join(" "));
  }
  if (entry.duration_ms != null) bits.push(`${entry.duration_ms}ms`);
  if (entry.action) bits.push(entry.action);
  if (entry.event_type) bits.push(entry.event_type);
  return bits.join(" · ");
}

function logLine(entry, index) {
  const level = String(entry.level || (entry.raw ? "RAW" : "")).toUpperCase();
  const msg = entry.msg || entry.raw || "";
  const path = entry.path || entry.href || entry.source_url || "";
  const detail = entry.exc || entry.raw || "";

  return h("div", { class: `log-line log-level-${level.toLowerCase()}` },
    h("div", { class: "log-row" },
      h("span", { class: "log-level" }, level || String(index + 1)),
      h("span", { class: "log-time" }, fmtTs(entry.ts)),
      h("span", { class: "log-path", title: path }, path),
    ),
    h("pre", { class: "log-message" }, msg),
    compactMeta(entry) ? h("div", { class: "log-meta" }, compactMeta(entry)) : null,
    detail && detail !== msg ? h("details", { class: "log-detail" },
      h("summary", null, "Details"),
      h("pre", null, detail),
    ) : null,
  );
}

function renderEntries(container, data) {
  const entries = data.entries || [];
  domRender(container,
    h("div", { class: "log-summary" },
      h("strong", null, data.file || DEFAULT_FILE),
      h("span", null, ` last ${data.line_count || 0} lines`),
    ),
    entries.length
      ? h("div", { class: "log-list" }, entries.map(logLine))
      : h("p", { class: "empty" }, "No log lines found."),
  );
}

export async function render(parent, { params } = {}) {
  const selectedFile = readFile(params);
  const selectedTail = readTail(params || new URLSearchParams());

  const controls = h("form", { class: "log-controls", novalidate: "novalidate" },
    h("label", null, "File",
      h("select", { name: "file" },
        h("option", { value: selectedFile }, selectedFile),
      ),
    ),
    h("label", null, "Tail",
      h("input", {
        name: "tail",
        type: "text",
        inputmode: "numeric",
        value: String(selectedTail),
      }),
    ),
    h("button", { class: "btn btn-primary", type: "submit" }, "Apply"),
    h("button", { class: "btn", type: "button", name: "refresh" }, "Refresh"),
  );
  const status = h("div", { class: "log-status" }, "Loading logs...");
  const list = h("div", { class: "log-results" });

  domRender(parent,
    h("section", { class: "log-view" },
      h("div", { class: "log-heading" },
        h("h2", null, "Error Logs"),
        h("p", null, "Use the file and tail controls, or edit the URL query by hand."),
      ),
      controls,
      status,
      list,
    ),
  );

  const fileSelect = controls.elements.file;
  const tailInput = controls.elements.tail;
  const refreshButton = controls.elements.refresh;

  async function load() {
    const file = fileSelect.value || DEFAULT_FILE;
    const tail = readTail(new URLSearchParams({ tail: tailInput.value }));
    tailInput.value = String(tail);
    status.textContent = `Loading ${file}...`;
    refreshButton.disabled = true;
    try {
      const data = await api.logTail(file, tail);
      status.textContent = "";
      renderEntries(list, data);
      if (file === DEFAULT_FILE && window.labLogAlertMarkSeen) {
        window.labLogAlertMarkSeen(data.state);
      }
    } catch (e) {
      status.textContent = `Failed to load logs: ${e.message}`;
      domRender(list);
    } finally {
      refreshButton.disabled = false;
    }
  }

  controls.addEventListener("submit", (e) => {
    e.preventDefault();
    const tail = readTail(new URLSearchParams({ tail: tailInput.value }));
    updateUrl(fileSelect.value || DEFAULT_FILE, tail);
    load();
  });
  refreshButton.addEventListener("click", load);

  try {
    const files = await api.logFiles();
    const names = (files.files || []).map((f) => f.name);
    domRender(fileSelect,
      ...names.map((name) => h("option", {
        value: name,
        selected: name === selectedFile ? "selected" : null,
      }, name)),
    );
    if (!names.includes(selectedFile)) {
      fileSelect.insertBefore(h("option", { value: selectedFile }, selectedFile), fileSelect.firstChild);
      fileSelect.value = selectedFile;
    }
  } catch {
    fileSelect.value = selectedFile;
  }

  await load();
}
