import { api } from "../api.js";
import { h, render as domRender, fmtDate, priorityClass, modal, activatable } from "../lib/dom.js";

let activeTab = "tasks";

export async function render(parent, { match }) {
  const pid = decodeURIComponent(match[1]);
  const [proj, tasksDoc, docs] = await Promise.all([
    api.project(pid),
    api.projectTasks(pid),
    api.projectDocs(pid),
  ]);

  const header = h("div", { class: "proj-header" },
    h("h2", null, proj.id, proj.priority ? " " : null,
      proj.priority ? h("span", { class: "chip " + priorityClass(proj.priority) }, proj.priority) : null),
    h("div", { class: "meta" }, proj.description || "(no description)"),
    h("div", { class: "meta" },
      `status: ${proj.status}`,
      proj.due ? ` · due ${proj.due}` : "",
      (proj.tags || []).length ? ` · tags: ${proj.tags.join(", ")}` : "",
      (proj.labels || []).length ? ` · labels: ${proj.labels.join(", ")}` : "",
    ),
  );

  const tabs = h("div", { class: "tabs" },
    tabButton("tasks", `Tasks (${tasksDoc.tasks.length})`, parent, match),
    tabButton("docs", `Docs (${docs.length})`, parent, match),
    tabButton("prs", `PRs (${(proj.prs || []).length})`, parent, match),
    tabButton("artifacts", `Artifacts (${(proj.artifacts || []).length})`, parent, match),
  );

  let content;
  if (activeTab === "tasks") {
    content = tasksTable(pid, tasksDoc.tasks);
  } else if (activeTab === "docs") {
    content = docsList(pid, docs);
  } else if (activeTab === "prs") {
    content = prsList(pid, proj.prs || []);
  } else {
    content = artifactsList(pid, proj.artifacts || []);
  }

  domRender(parent, header, tabs, content);
}

function tabButton(key, label, parent, match) {
  return h("button", {
    class: "tab " + (activeTab === key ? "active" : ""),
    onclick: () => { activeTab = key; render(parent, { match }); },
  }, label);
}

function tasksTable(pid, tasks) {
  const newTaskBtn = h("button", {
    class: "btn btn-primary",
    onclick: () => onNewTask(pid),
    style: "margin-bottom:12px",
  }, "+ New task");

  if (!tasks.length) {
    return h("div", null, newTaskBtn, h("p", null, "No tasks yet."));
  }

  const rows = tasks.map((t) => h("tr", { class: t.status === "done" ? "done" : "" },
    h("td", null, "#" + t.id),
    h("td", null, h("span", { class: "chip " + priorityClass(t.priority) }, t.priority)),
    h("td", null, t.title),
    h("td", null, t.status + (t.blocker ? ` (${t.blocker})` : "")),
    h("td", null, fmtDate(t.due)),
    h("td", null, taskActions(pid, t)),
  ));

  const table = h("table", { class: "tasks" },
    h("thead", null, h("tr", null,
      h("th", null, "#"),
      h("th", null, "P"),
      h("th", null, "Title"),
      h("th", null, "Status"),
      h("th", null, "Due"),
      h("th", null, "Actions"),
    )),
    h("tbody", null, ...rows),
  );

  return h("div", null, newTaskBtn, table);
}

function taskActions(pid, t) {
  const actions = [];
  if (t.status === "done") {
    actions.push(statusBtn(pid, t.id, "reopened", "reopen"));
  } else {
    actions.push(statusBtn(pid, t.id, "done", "done"));
    if (t.status !== "blocked") {
      actions.push(statusBtn(pid, t.id, "blocked", "block"));
    } else {
      actions.push(statusBtn(pid, t.id, "in_progress", "unblock"));
    }
  }
  return h("span", null, ...actions);
}

function statusBtn(pid, tid, newStatus, label) {
  return h("button", {
    class: "status-btn",
    style: "margin-right:4px",
    onclick: async () => {
      try {
        let body = { status: newStatus };
        if (newStatus === "blocked") {
          const values = await modal("Block task", [
            { name: "reason", label: "Block reason", type: "text", required: true },
          ], { submitLabel: "Block" });
          if (!values) return;
          body.reason = values.reason;
        }
        await api.setTaskStatus(pid, tid, body);
      } catch (e) {
        alert("Failed: " + e.message);
      }
    },
  }, label);
}

function docsList(pid, docs) {
  if (!docs.length) return h("p", null, "No docs, notes, or assets.");
  const items = docs.map((d) => {
    const lower = d.path.toLowerCase();
    const isMd = lower.endsWith(".md");
    const isNb = lower.endsWith(".ipynb");
    let href;
    if (isMd) {
      href = `#/md?path=${encodeURIComponent(`content/projects/${pid}/${d.path}`)}`;
    } else if (isNb) {
      href = `#/nb?path=${encodeURIComponent(`content/projects/${pid}/${d.path}`)}`;
    } else {
      href = `/api/projects/${encodeURIComponent(pid)}/file?path=${encodeURIComponent(d.path)}`;
    }
    const linkAttrs = (isMd || isNb) ? { href } : { href, target: "_blank", rel: "noopener" };
    return h("li", null,
      h("a", linkAttrs, d.path),
      h("span", { style: "color:#999; margin-left:8px; font-size:11px" }, `${d.size} bytes`),
    );
  });
  return h("ul", { class: "doc-list" }, ...items);
}

async function onNewTask(pid) {
  const values = await modal("New task", [
    { name: "title", label: "Title", type: "text", required: true },
    { name: "priority", label: "Priority", type: "select", options: ["P0", "P1", "P2", "P3"], value: "P2" },
    { name: "due", label: "Due (YYYY-MM-DD, optional)", type: "text" },
    { name: "loe", label: "LOE (days, optional)", type: "text" },
    { name: "tags", label: "Tags (comma-separated, optional)", type: "text" },
  ]);
  if (!values) return;
  try {
    const body = {
      project_id: pid,
      title: values.title.trim(),
      priority: values.priority,
      due: values.due || null,
      loe: values.loe ? parseFloat(values.loe) : null,
      tags: values.tags ? values.tags.split(",").map((s) => s.trim()).filter(Boolean) : [],
    };
    await api.createTask(body);
  } catch (e) {
    alert("Failed: " + e.message);
  }
}

function prsList(pid, prs) {
  const addBtn = h("button", {
    class: "btn btn-primary",
    style: "margin-bottom:12px",
    onclick: async () => {
      const v = await modal("Add PR", [
        { name: "url", label: "URL", type: "text", required: true },
        { name: "mp", label: "MP (optional)", type: "text" },
        { name: "title", label: "Title (optional)", type: "text" },
        { name: "status", label: "Status", type: "select", options: ["open", "draft", "merged", "closed"], value: "open" },
      ], { submitLabel: "Add" });
      if (!v) return;
      try { await api.addPR(pid, v); }
      catch (e) { alert("Failed: " + e.message); }
    },
  }, "+ Add PR");

  if (!prs.length) return h("div", null, addBtn, h("p", null, "No PRs linked."));
  const items = prs.map((p, i) => h("li", {
    style: "margin:6px 0; font-size:13px;",
  },
    h("span", { class: "chip" }, p.status || "open"),
    p.mp ? h("span", { class: "chip" }, p.mp) : null,
    h("a", { href: p.url, target: "_blank", rel: "noopener", style: "margin-left:8px" },
      p.title || p.url),
    h("button", {
      class: "status-btn",
      style: "margin-left:8px",
      onclick: async () => {
        if (!confirm("Remove PR " + (p.title || p.url) + "?")) return;
        try { await api.rmPR(pid, i); }
        catch (e) { alert("Failed: " + e.message); }
      },
    }, "rm"),
  ));
  return h("div", null, addBtn, h("ul", { style: "list-style:none; padding:0;" }, ...items));
}

function artifactsList(pid, arts) {
  const addBtn = h("button", {
    class: "btn btn-primary",
    style: "margin-bottom:12px",
    onclick: async () => {
      const v = await modal("Add artifact", [
        { name: "url", label: "URL", type: "text", required: true },
        { name: "type", label: "Type", type: "select",
          options: ["url", "google_doc", "spreadsheet", "retina_chart", "jira", "confluence", "slack", "github"],
          value: "url" },
        { name: "title", label: "Title", type: "text" },
        { name: "description", label: "Description", type: "textarea" },
      ], { submitLabel: "Add" });
      if (!v) return;
      try { await api.addArtifact(pid, v); }
      catch (e) { alert("Failed: " + e.message); }
    },
  }, "+ Add artifact");

  if (!arts.length) return h("div", null, addBtn, h("p", null, "No artifacts linked."));
  const items = arts.map((a) => h("li", {
    style: "margin:8px 0; font-size:13px; padding:6px 8px; border:1px solid #eee; border-radius:4px;",
  },
    h("div", null,
      h("span", { class: "chip" }, a.type || "url"),
      h("a", { href: a.url, target: "_blank", rel: "noopener", style: "margin-left:8px; font-weight:600;" },
        a.title || a.url),
      h("button", {
        class: "status-btn",
        style: "margin-left:8px",
        onclick: async () => {
          if (!confirm("Remove " + (a.title || a.url) + "?")) return;
          try { await api.rmArtifact(pid, a.id ?? 0); }
          catch (e) { alert("Failed: " + e.message); }
        },
      }, "rm"),
    ),
    a.description ? h("p", { style: "color:#555; margin:4px 0 0; font-size:12px;" }, a.description) : null,
  ));
  return h("div", null, addBtn, h("ul", { style: "list-style:none; padding:0;" }, ...items));
}
