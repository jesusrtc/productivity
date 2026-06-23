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
    h("button", {
      class: "btn",
      onclick: (e) => onPushProductivity(e.target),
      title: "git push the Lab framework repo (errors if dirty)",
    }, "Push productivity"),
    h("button", {
      class: "btn",
      onclick: (e) => onSyncContent(e.target),
      title: "stage, commit, push the content repo",
    }, "Sync content"),
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
  const prs = p.prs || [];
  const prCounts = p.pr_counts || {};
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
    prs.length > 0 ? prSection(prs, prCounts) : null,
    h("div", { class: "card-links", style: "margin-top:8px;font-size:12px" },
      h("a", {
        href: `#/p/${p.id}`,
        onclick: (e) => { e.stopPropagation(); },
        style: "color:var(--muted, #8b949e);text-decoration:none",
      }, "Tasks view \u2192"),
    ),
  );
}

function prSection(prs, prCounts) {
  const open = prCounts.open || 0;
  const merged = prCounts.merged || 0;
  const closed = prCounts.closed || 0;
  const header = h("div", { class: "pr-header" },
    h("span", { class: "pr-label" }, `PRs (${prs.length})`),
    open ? h("span", { class: "pr-stat pr-open" }, `${open} open`) : null,
    merged ? h("span", { class: "pr-stat pr-merged" }, `${merged} merged`) : null,
    closed ? h("span", { class: "pr-stat pr-closed" }, `${closed} closed`) : null,
  );

  const ranked = prs.slice().sort((a, b) => statusRank(a.status) - statusRank(b.status));
  const visible = ranked.slice(0, 4);
  const hidden = ranked.length - visible.length;

  return h("div", { class: "pr-section" },
    header,
    h("ul", { class: "pr-list" },
      ...visible.map((pr) => h("li", { class: "pr-item" },
        h("span", { class: "pr-status " + prStatusClass(pr.status) }, pr.status || "?"),
        pr.url
          ? h("a", {
              href: pr.url,
              target: "_blank",
              rel: "noopener",
              onclick: (e) => { e.stopPropagation(); },
              class: "pr-title",
              title: pr.title || pr.url,
            }, pr.title || pr.url)
          : h("span", { class: "pr-title" }, pr.title || "(no title)"),
      )),
      hidden > 0 ? h("li", { class: "pr-more" }, `+${hidden} more`) : null,
    ),
  );
}

function statusRank(s) {
  const v = (s || "").toLowerCase();
  if (v === "open") return 0;
  if (v === "closed") return 1;
  if (v === "merged") return 2;
  return 3;
}

function prStatusClass(s) {
  const v = (s || "").toLowerCase();
  if (v === "open") return "pr-open";
  if (v === "merged") return "pr-merged";
  if (v === "closed") return "pr-closed";
  return "pr-other";
}

async function runPush(btn, fn, label) {
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = label + "…";
  try {
    const res = await fn();
    alert(res.message || `${label} ok`);
  } catch (e) {
    alert(`${label} failed: ` + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}

function onPushProductivity(btn) {
  return runPush(btn, () => api.pushProductivity(), "Push productivity");
}

function onSyncContent(btn) {
  return runPush(btn, () => api.syncContent(), "Sync content");
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
