import { api } from "../api.js";
import { h, render as domRender, fmtDate, priorityClass, activatable } from "../lib/dom.js";

let mode = "list";

export async function render(parent, params) {
  const idx = await api.index();

  const toggle = h("div", { class: "view-toggle" },
    h("button", {
      class: "pill " + (mode === "list" ? "active" : ""),
      onclick: () => { mode = "list"; render(parent, params); },
    }, "List"),
    h("button", {
      class: "pill " + (mode === "gantt" ? "active" : ""),
      onclick: () => { mode = "gantt"; render(parent, params); },
    }, "Gantt"),
  );

  const body = mode === "list" ? renderList(idx) : renderGantt(idx);

  domRender(parent,
    h("h2", null, "Timeline"),
    toggle,
    body,
  );
}

function renderList(idx) {
  const tasks = [...idx.tasks].filter((t) => t.status !== "done");
  tasks.sort((a, b) => {
    if (a.due && b.due) return a.due.localeCompare(b.due);
    if (a.due) return -1;
    if (b.due) return 1;
    return 0;
  });

  const today = new Date().toISOString().slice(0, 10);
  const inDays = (n) => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10);
  const buckets = {
    "Overdue": [],
    "Today / this week": [],
    "Next week": [],
    "This month": [],
    "Later": [],
    "No due date": [],
  };
  const thisWeek = inDays(7);
  const nextWeek = inDays(14);
  const thisMonth = inDays(30);

  for (const t of tasks) {
    if (!t.due) { buckets["No due date"].push(t); continue; }
    if (t.due < today) { buckets["Overdue"].push(t); continue; }
    if (t.due <= thisWeek) { buckets["Today / this week"].push(t); continue; }
    if (t.due <= nextWeek) { buckets["Next week"].push(t); continue; }
    if (t.due <= thisMonth) { buckets["This month"].push(t); continue; }
    buckets["Later"].push(t);
  }

  return h("div", null,
    ...Object.entries(buckets)
      .filter(([, rows]) => rows.length > 0)
      .map(([name, rows]) => bucket(name, rows))
  );
}

function bucket(name, rows) {
  return h("div", { class: "bucket" },
    h("h3", null, `${name} (${rows.length})`),
    h("table", null,
      h("thead", null, h("tr", null,
        h("th", null, "Due"),
        h("th", null, "P"),
        h("th", null, "Project"),
        h("th", null, "Title"),
      )),
      h("tbody", null, ...rows.map((t) => h("tr", null,
        h("td", null, fmtDate(t.due)),
        h("td", null, h("span", { class: "chip " + priorityClass(t.priority) }, t.priority)),
        h("td", null, h("a", { href: `#/p/${t.project_id}` }, t.project_id)),
        h("td", null, t.title),
      ))),
    ),
  );
}

function renderGantt(idx) {
  const projects = idx.projects.filter((p) => p.status === "active");
  if (!projects.length) return h("p", null, "No active projects.");

  const today = new Date();
  const minD = projects.reduce((m, p) => {
    const d = p.created ? new Date(p.created) : today;
    return d < m ? d : m;
  }, today);
  const maxD = projects.reduce((m, p) => {
    const candidate = p.due ? new Date(p.due) : (p.earliest_task_due ? new Date(p.earliest_task_due) : today);
    return candidate > m ? candidate : m;
  }, new Date(today.getTime() + 14 * 86400000));

  const spanMs = Math.max(maxD - minD, 86400000);
  const pct = (d) => ((new Date(d) - minD) / spanMs) * 100;

  return h("div", { class: "gantt" },
    ...projects.map((p) => {
      const startD = p.created || today.toISOString().slice(0, 10);
      const endD = p.due || p.earliest_task_due || new Date(today.getTime() + 7 * 86400000).toISOString().slice(0, 10);
      const left = Math.max(0, pct(startD));
      const width = Math.max(1, pct(endD) - left);
      return h("div", { class: "gantt-row" },
        h("div", { class: "gantt-label" }, h("a", { href: `#/p/${p.id}` }, p.id)),
        h("div", { class: "gantt-lane" },
          h("div", {
            class: "gantt-bar " + priorityClass(p.priority) + (p.status === "archived" ? " archived" : ""),
            style: `left:${left}%; width:${width}%`,
            title: `${startD} → ${endD}`,
            ...activatable(() => { location.hash = `#/p/${p.id}`; }),
          }),
        ),
      );
    }),
    h("p", { style: "color:#999; font-size:12px; margin-top:8px" },
      `${fmtDate(minD.toISOString())} → ${fmtDate(maxD.toISOString())}`),
  );
}
