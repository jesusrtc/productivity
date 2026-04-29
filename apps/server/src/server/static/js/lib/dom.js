// Tiny DOM helpers — no framework, no build step.
// h("div", {class: "row", onclick: fn}, "text", h("span", null, "nested"))

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k.startsWith("on") && typeof v === "function") {
        el.addEventListener(k.slice(2).toLowerCase(), v);
      } else if (k === "class") {
        el.className = v;
      } else if (k === "html") {
        el.innerHTML = v;
      } else if (k === "style" && typeof v === "object") {
        Object.assign(el.style, v);
      } else {
        el.setAttribute(k, v);
      }
    }
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
}

export function render(parent, ...nodes) {
  clear(parent);
  for (const node of nodes) parent.appendChild(node);
}

export function fmtDate(iso) {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

export function priorityClass(p) {
  return p ? `p-${p.toLowerCase()}` : "";
}


// Open a modal form. `fields` is an array of:
//   { name: "id", label: "Project id", type: "text", required: true, value: "" }
//   { name: "priority", label: "Priority", type: "select", options: ["P0","P1","P2","P3"], value: "P2" }
//   { name: "description", label: "Description", type: "textarea" }
// onSubmit(values) is called with an object of the filled-in values.
// Returns a promise that resolves when the user submits or cancels (null on cancel).
export function modal(title, fields, { submitLabel = "Create", cancelLabel = "Cancel" } = {}) {
  return new Promise((resolve) => {
    const inputs = {};
    const fieldEls = fields.map((f) => {
      let input;
      if (f.type === "select") {
        input = h("select", { name: f.name },
          ...(f.options || []).map((o) =>
            h("option", { value: o, selected: o === f.value ? "selected" : null }, o)
          )
        );
      } else if (f.type === "textarea") {
        input = h("textarea", { name: f.name, rows: 3 }, f.value || "");
      } else {
        input = h("input", { type: f.type || "text", name: f.name, value: f.value || "" });
      }
      inputs[f.name] = input;
      return h("label", null, f.label, input);
    });

    const form = h("form", {
      onsubmit: (e) => {
        e.preventDefault();
        const values = {};
        for (const [name, el] of Object.entries(inputs)) {
          values[name] = el.value;
        }
        for (const f of fields) {
          if (f.required && !values[f.name]) {
            inputs[f.name].focus();
            return;
          }
        }
        document.body.removeChild(backdrop);
        resolve(values);
      },
    },
      ...fieldEls,
      h("div", { class: "modal-actions" },
        h("button", {
          type: "button",
          class: "btn",
          onclick: () => {
            document.body.removeChild(backdrop);
            resolve(null);
          },
        }, cancelLabel),
        h("button", { type: "submit", class: "btn btn-primary" }, submitLabel),
      ),
    );

    const box = h("div", { class: "modal" },
      h("h3", null, title),
      form,
    );
    const backdrop = h("div", {
      class: "modal-backdrop",
      onclick: (e) => {
        if (e.target === backdrop) {
          document.body.removeChild(backdrop);
          resolve(null);
        }
      },
    }, box);

    document.body.appendChild(backdrop);
    // Focus first input
    const firstInput = box.querySelector("input, select, textarea");
    if (firstInput) firstInput.focus();
  });
}


// Make a non-button element keyboard-activatable.
// Usage: h("div", { class: "card", ...activatable(() => nav()) }, ...)
export function activatable(onActivate) {
  return {
    role: "button",
    tabindex: "0",
    onclick: onActivate,
    onkeydown: (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onActivate(e);
      }
    },
  };
}
