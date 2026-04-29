import { api } from "../api.js";
import { h, render as domRender } from "../lib/dom.js";

export async function render(parent, { params }) {
  const initialQuery = params.get("q") || "";

  const input = h("input", {
    type: "text",
    placeholder: "Search projects, tasks, and docs…",
    value: initialQuery,
    style: "width:100%; padding:8px; font-size:14px; border:1px solid #ccc; border-radius:4px;",
    onkeydown: (e) => {
      if (e.key === "Enter") runSearch(e.target.value);
    },
  });

  const status = h("p", { style: "color:#888; font-size:12px;" },
    initialQuery ? "" : "Type a query and press Enter.");
  const results = h("div");

  domRender(parent,
    h("h2", null, "Search"),
    input,
    status,
    results,
  );

  if (initialQuery) {
    await runSearch(initialQuery);
  }

  async function runSearch(q) {
    if (!q) return;
    location.hash = "#/search?q=" + encodeURIComponent(q);
    status.textContent = "searching…";
    try {
      const r = await api.search(q);
      renderResults(r);
    } catch (e) {
      status.textContent = "Error: " + e.message;
    }
  }

  function renderResults(r) {
    const total = r.projects.length + r.tasks.length + r.docs.length;
    status.textContent = `${total} result${total === 1 ? "" : "s"} for “${r.query}”`;
    const sections = [];
    if (r.projects.length) {
      sections.push(h("section", null,
        h("h3", null, `Projects (${r.projects.length})`),
        h("ul", { style: "list-style:none; padding:0;" },
          ...r.projects.map((p) => h("li", { style: "margin:6px 0; font-size:13px;" },
            h("a", { href: `#/p/${p.id}` }, p.id),
            h("span", { style: "color:#888; margin-left:8px" }, `[${p.status}]`),
            p.description ? h("span", { style: "color:#555; margin-left:8px" }, p.description.slice(0, 80)) : null,
          )),
        ),
      ));
    }
    if (r.tasks.length) {
      sections.push(h("section", null,
        h("h3", null, `Tasks (${r.tasks.length})`),
        h("ul", { style: "list-style:none; padding:0;" },
          ...r.tasks.map((t) => h("li", { style: "margin:6px 0; font-size:13px;" },
            h("a", { href: `#/p/${t.project_id}` }, `${t.project_id}#${t.task_id}`),
            h("span", { style: "color:#888; margin-left:8px" }, `[${t.status}] ${t.priority}`),
            h("span", { style: "margin-left:8px" }, t.title),
          )),
        ),
      ));
    }
    if (r.docs.length) {
      sections.push(h("section", null,
        h("h3", null, `Docs (${r.docs.length})`),
        h("ul", { style: "list-style:none; padding:0;" },
          ...r.docs.map((d) => h("li", { style: "margin:6px 0; font-size:13px;" },
            h("a", { href: `#/md?path=${encodeURIComponent(d.path)}` }, d.path),
            h("div", { style: "color:#666; font-size:12px; margin-top:2px;" }, d.snippet),
          )),
        ),
      ));
    }
    if (!sections.length) {
      sections.push(h("p", null, "No matches."));
    }
    domRender(results, ...sections);
  }
}
