import { api } from "../api.js";
import { h, render as domRender, fmtDate, priorityClass, modal, activatable } from "../lib/dom.js";

let statusFilter = "active";

export async function render(parent, params) {
  const [idx, dueSoonRaw] = await Promise.all([api.index(), api.tasksDue(7)]);
  const projects = idx.projects.filter((p) => statusFilter === "all" || p.status === statusFilter);
  const dueSoon = dueSoonRaw.filter((t) => t.status !== "done");

  const filterRow = h("div", { class: "filter-row" },
    h("label", null, "Show: "),
    h("select", {
      onchange: (e) => { statusFilter = e.target.value; render(parent, params); },
    },
      ...["active", "paused", "done", "archived", "all"].map((s) =>
        h("option", { value: s, selected: s === statusFilter ? "selected" : null }, s)
      )
    ),
    h("button", {
      class: "btn btn-primary",
      onclick: () => onNewProject(),
    }, "+ New project"),
  );

  const dueStrip = h("div", { class: "due-strip" },
    ...dueSoon.slice(0, 30).map((t) => h("span", {
      class: "due-chip",
      title: `${t.project_id}  #${t.task_id}`,
      ...activatable(() => { location.hash = `#/p/${t.project_id}`; }),
    },
      h("span", { class: "chip " + priorityClass(t.priority) }, t.priority || ""),
      h("span", null, t.title),
      h("span", { class: "due-date" }, fmtDate(t.due)),
    ))
  );

  const grid = h("div", { class: "project-grid" },
    ...projects.map((p) => projectCard(p))
  );

  domRender(parent,
    filterRow,
    dueSoon.length > 0 ? dueStrip : h("span"),
    projects.length > 0 ? grid : h("p", null, "No projects. Click '+ New project' to create one."),
  );
}

function gdiffUrl(pid) {
  // Server-side /p/<id> redirects to /?project=<abs path>, so we don't have
  // to know where the monorepo lives on disk.
  return `${window.location.origin}/p/${encodeURIComponent(pid)}`;
}

function projectCard(p) {
  const counts = p.task_counts || {};
  return h("div", {
    class: "card",
    ...activatable(() => { window.open(gdiffUrl(p.id), "_blank"); }),
  },
    h("h3", null, p.id),
    p.description ? h("p", { class: "desc" }, p.description) : null,
    h("div", null,
      p.priority ? h("span", { class: "chip " + priorityClass(p.priority) }, p.priority) : null,
      p.due ? h("span", { class: "chip" }, "due " + fmtDate(p.due)) : null,
      ...(p.tags || []).map((t) => h("span", { class: "chip" }, t)),
      ...(p.labels || []).map((t) => h("span", { class: "chip" }, "@" + t)),
    ),
    h("div", { class: "counts", style: "margin-top:8px" },
      h("span", { class: "todo" }, `todo ${counts.todo || 0}`),
      h("span", { class: "in_progress" }, `in_progress ${counts.in_progress || 0}`),
      h("span", { class: "blocked" }, `blocked ${counts.blocked || 0}`),
      h("span", { class: "done" }, `done ${counts.done || 0}`),
    ),
    h("div", { class: "card-links", style: "margin-top:8px;font-size:12px" },
      h("a", {
        href: `#/p/${p.id}`,
        onclick: (e) => { e.stopPropagation(); },
        style: "color:var(--muted, #8b949e);text-decoration:none",
      }, "Tasks view \u2192"),
    ),
  );
}

async function onNewProject() {
  const values = await modal("New project", [
    { name: "id", label: "Project id (e.g. davi-vision)", type: "text", required: true },
    { name: "description", label: "Description", type: "textarea" },
    { name: "priority", label: "Priority", type: "select", options: ["", "P0", "P1", "P2", "P3"], value: "" },
    { name: "due", label: "Due (YYYY-MM-DD, optional)", type: "text" },
    { name: "tags", label: "Tags (comma-separated, optional)", type: "text" },
    { name: "labels", label: "Labels (MP names, comma-separated, optional)", type: "text" },
  ]);
  if (!values) return;
  try {
    const body = {
      id: values.id.trim(),
      description: values.description || "",
      priority: values.priority || null,
      due: values.due || null,
      tags: values.tags ? values.tags.split(",").map((s) => s.trim()).filter(Boolean) : [],
      labels: values.labels ? values.labels.split(",").map((s) => s.trim()).filter(Boolean) : [],
    };
    const p = await api.createProject(body);
    location.hash = `#/p/${p.id}`;
  } catch (e) {
    alert("Failed to create project: " + e.message);
  }
}
