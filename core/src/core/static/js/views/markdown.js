import { api } from "../api.js";
import { h, render as domRender } from "../lib/dom.js";

export async function render(parent, { params }) {
  const path = params.get("path");
  if (!path) {
    domRender(parent, h("p", null, "Missing ?path="));
    return;
  }

  try {
    const { frontmatter, html } = await api.markdown(path);
    const fmNode = Object.keys(frontmatter || {}).length
      ? h("div", { class: "md-frontmatter" },
          JSON.stringify(frontmatter, null, 2),
        )
      : null;
    const body = h("div", { class: "md-content", html });
    domRender(parent,
      h("p", null, h("a", { href: "#", onclick: (e) => { e.preventDefault(); history.back(); } }, "← back")),
      h("h2", null, path),
      fmNode,
      body,
    );
  } catch (e) {
    domRender(parent, h("p", null, "Error: " + e.message));
  }
}
