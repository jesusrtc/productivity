---
name: html-proposal
description: >-
  Generate a self-contained, dark-themed HTML response for big requests —
  multi-step plans, refactor proposals, investigation summaries, architecture
  / design docs, cleanup plans, or any answer that would otherwise be a wall
  of markdown in the terminal. Saves to `tmp/YYYY-MM-DD-<slug>.html` in the
  current project; updated in place across follow-up turns. Supports
  embedded Plotly charts and Mermaid flowcharts via CDN. Use when the user
  asks for a plan / proposal / summary / investigation / architecture doc /
  cleanup approach. DO NOT use for small chat answers (yes/no, single
  command, brief clarification) — those stay in the terminal.
---

# HTML proposal skill

## When to use

Trigger on requests that meet **both**:

1. The answer benefits from structure (sections, diagrams, code blocks, decisions tables) — not just a one-line reply.
2. The answer would scroll past the visible terminal as plain markdown.

Concrete triggers: "draft a plan", "propose an approach", "summarize the
investigation", "give me the cleanup steps", "explain the architecture",
"compare options A and B", "what's the migration", "write up what we
just did".

**Do not** use for: single-command answers, quick clarifications, status
checks, yes/no questions, file content the user can just `cat`.

## File location

- `<project-root>/tmp/YYYY-MM-DD-<slug>.html`
  - Example: `tmp/2026-05-13-folder-cleanup-plan.html`
- `<slug>`: lowercase kebab-case, ≤ 6 words, describes the requirement.
- `tmp/` is gitignored — don't commit. Add `tmp/` to the project's
  `.gitignore` if it isn't already.
- **One file per big requirement.** Follow-up turns update the same file
  in place; never spawn a new HTML per turn.

After saving, tell the user where it lives and how to open it:

```
Plan rendered at:
  tmp/YYYY-MM-DD-<slug>.html

Open in lab UI:
  http://localhost:3333/?project=<absolute project path>
  Sidebar → tmp/<filename>.html  (renders inline; toggle to Code if needed)
```

## Document structure

Three sections, top to bottom:

1. **Summary** — current snapshot of decisions + work done. Refreshed
   every turn. This is the first thing a reader sees; it should stand
   alone if they read nothing else.
2. **Conversation log** — each user request + assistant response, in
   chronological order. Lets the reader audit the reasoning behind the
   summary.
3. **Specs & decisions** — concrete artifacts: file paths, command
   blocks, diffs, decision tables. The bash the user would copy.

## Standard template

Always start from this skeleton. The styling is intentionally
self-contained (inline `<style>`, no external CSS) so the file renders
identically in the lab UI iframe and in any browser.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="color-scheme" content="dark">
<title>{title}</title>
<style>
  /* Dark theme — matches the lab UI's --bg-primary / --text-primary etc.
     Background lives on BOTH html and a dedicated `.page` wrapper so the
     full viewport stays dark even if the host iframe or a default UA
     stylesheet paints something behind the centered .content column. */
  :root {
    --bg: #0d1117;
    --bg-card: #161b22;
    --bg-code: #1c2128;
    --bg-zebra: #11161d;
    --text: #e6edf3;
    --text-muted: #8b949e;
    --border: #30363d;
    --accent: #58a6ff;
    --success: #3fb950;
    --warning: #d29922;
    --danger: #f85149;
  }
  html, body {
    margin: 0; padding: 0;
    background: #0d1117;
    color: #e6edf3;
    color-scheme: dark;             /* form controls + scrollbars go dark */
  }
  body { font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; }
  /* `.page` paints the full viewport; `.content` centers the readable
     960px column. This split is what makes the dark background survive
     the lab UI's iframe host and any browser default. */
  .page {
    background: #0d1117;
    color: #e6edf3;
    min-height: 100vh;
    width: 100%;
    box-sizing: border-box;
    padding: 32px 28px 80px;
  }
  .content { max-width: 960px; margin: 0 auto; }
  /* Headings use pure white for top-level so contrast survives even if a
     downstream stylesheet wins the background cascade. */
  h1, h2, h4 { color: #ffffff; font-weight: 600; }
  h3 { color: #f0f6fc; font-weight: 600; }
  h1 { font-size: 28px; border-bottom: 1px solid var(--border); padding-bottom: 8px; margin-bottom: 8px; }
  h2 { font-size: 20px; margin-top: 32px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
  h3 { font-size: 16px; margin-top: 24px; }
  p, li { color: var(--text); }
  .meta { color: var(--text-muted); font-size: 13px; margin-top: 0; }
  code, pre, kbd { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  code { background: var(--bg-code); color: var(--text); padding: 2px 6px; border-radius: 4px; font-size: 13px; }
  pre { background: var(--bg-code); padding: 14px 16px; border-radius: 6px; overflow-x: auto; font-size: 13px; line-height: 1.5; border: 1px solid var(--border); }
  pre code { background: transparent; padding: 0; }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .callout { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 16px 20px; margin: 16px 0; }
  .callout.summary { border-color: #1f3a5f; background: #0d1b2a; }
  .callout h3 { margin-top: 0; }
  .badge { display: inline-block; font-family: ui-monospace, monospace; font-size: 12px; padding: 1px 8px; border-radius: 4px; background: var(--bg-code); color: var(--text); border: 1px solid var(--border); }
  .badge.success { color: var(--success); border-color: var(--success); background: rgba(63,185,80,0.08); }
  .badge.warning { color: var(--warning); border-color: var(--warning); background: rgba(210,153,34,0.08); }
  .badge.danger  { color: var(--danger);  border-color: var(--danger);  background: rgba(248,81,73,0.08); }
  ul, ol { padding-left: 28px; }
  li { margin: 4px 0; }
  .turn { margin: 16px 0; padding: 14px 18px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; }
  .turn .who { font-weight: 600; color: var(--text-muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
  .turn.user .who { color: var(--accent); }
  /* Tables paint every cell explicitly so a stray light background from
     the host can't bleed through transparent td defaults. */
  table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 14px; background: #0d1117; }
  th, td { border: 1px solid var(--border); padding: 8px 12px; text-align: left; vertical-align: top; }
  th { background: var(--bg-card); color: #ffffff; }
  td { background: #0d1117; color: var(--text); }
  tr:nth-child(even) td { background: var(--bg-zebra); }
  hr { border: none; border-top: 1px solid var(--border); margin: 32px 0; }
</style>
</head>
<body>
<div class="page">
  <div class="content">

    <h1>{title}</h1>
    <p class="meta">Drafted {YYYY-MM-DD} · project <code>{project-id}</code></p>

    <div class="callout summary">
      <h3>Summary</h3>
      <p>{1–3 sentence current snapshot of decisions and work done.}</p>
      <p><span class="badge success">RECOMMENDED</span> {one-line recommendation or current direction}</p>
    </div>

    <h2>Conversation</h2>
    <div class="turn user">
      <div class="who">User · {timestamp or turn #}</div>
      <p>{paraphrased user request}</p>
    </div>
    <div class="turn assistant">
      <div class="who">Assistant</div>
      <p>{response highlights — what was decided, what was done}</p>
    </div>

    <h2>Specs &amp; decisions</h2>

    <h3>File paths</h3>
    <ul>
      <li><code>{path}</code> — {what changes / why}</li>
    </ul>

    <h3>Commands</h3>
    <pre><code>{bash blocks the user would copy}</code></pre>

  </div>
</div>
</body>
</html>
```

## Embedded Plotly charts (when data is involved)

For investigations, metric breakdowns, before/after comparisons — embed
Plotly inline. Always set the dark-theme colors so the chart blends with
the page.

```html
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<div id="chart-1" style="height:380px;margin:16px 0"></div>
<script>
  Plotly.newPlot('chart-1', [{
    x: ['Jan','Feb','Mar','Apr'],
    y: [120, 145, 132, 168],
    type: 'bar',
    marker: { color: '#58a6ff' }
  }], {
    paper_bgcolor: '#0d1117',
    plot_bgcolor:  '#0d1117',
    font: { color: '#e6edf3', family: 'ui-sans-serif' },
    margin: { t: 24, r: 16, b: 40, l: 48 },
    xaxis: { gridcolor: '#30363d', zerolinecolor: '#30363d' },
    yaxis: { gridcolor: '#30363d', zerolinecolor: '#30363d' }
  }, {displayModeBar: false, responsive: true});
</script>
```

## Embedded Mermaid flowcharts (for process / architecture diagrams)

```html
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>mermaid.initialize({ startOnLoad: true, theme: 'dark', themeVariables: { background: '#0d1117', primaryColor: '#161b22', primaryTextColor: '#e6edf3', primaryBorderColor: '#30363d', lineColor: '#8b949e' } });</script>
<pre class="mermaid">
flowchart LR
  A[Raw event] --> B{Suspicious?}
  B -->|yes| C[Quarantine queue]
  B -->|no|  D[Pass through]
  C --> E[Manual review]
</pre>
```

Other CDNs worth knowing about — use them when the content genuinely
benefits, not for decoration:

- **highlight.js** for prettier code blocks:
  `https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js`
  + `…/styles/github-dark.min.css`
- **DataTables** for sortable/filterable tables when the table is large:
  `https://cdn.datatables.net/2.0.8/js/dataTables.min.js`

## Update pattern (follow-up turns)

When a follow-up message extends the same requirement:

1. **Read** the existing HTML from `tmp/YYYY-MM-DD-<slug>.html`.
2. **Refresh** the Summary callout at the top with the latest snapshot.
3. **Append** a new `<div class="turn user">…</div>` and matching
   `<div class="turn assistant">…</div>` to the Conversation section.
4. **Extend** Specs & decisions with any new file paths, commands, or
   decision rows.
5. **Save** back to the same file. The lab UI auto-refreshes within 2s.

Never create a second HTML for the same requirement. If the answer has
truly diverged into a new topic, start a new file with a new date/slug.

## Anti-patterns

- ❌ Light-mode HTML (white background — clashes with the lab UI).
- ❌ External CSS files or shared stylesheets — keep it self-contained.
- ❌ Pulling in jQuery / Bootstrap / Tailwind just for layout — the
  template above is enough.
- ❌ Animations, transitions, hover bling for the sake of looking fancy.
  This is a *document*, not a landing page.
- ❌ A new HTML per turn. One file per requirement; update in place.
- ❌ Using HTML for a 3-line reply that fits in the terminal.
- ❌ Putting the dark background only on `html`/`body` when `body` has a
  `max-width` — the area outside the column may not get painted dark by
  the host iframe. Use the `.page` wrapper with `min-height: 100vh`.
- ❌ Using `color: var(--text)` (= `#e6edf3`) for `h1`/`h2`. If the
  wrapper's background fails to cascade, those headings disappear
  against white. Use `#ffffff` for top-level headings as a contrast
  floor.
- ❌ Shipping without `<meta name="color-scheme" content="dark">` in
  `<head>` and a matching `color-scheme: dark` declaration on `html`.
  Some renderers honor only one; declaring both costs nothing.
- ❌ Relying on `th` background alone to make a table look dark. Paint
  `td` explicitly too, or zebra-striped rows will show through white.

## File-naming examples

| Request | Slug | Final path |
|---|---|---|
| "draft a cleanup plan for test-davi-vision" | `folder-cleanup-plan` | `tmp/2026-05-13-folder-cleanup-plan.html` |
| "investigate the reaction 4xx spike" | `reaction-4xx-investigation` | `tmp/2026-05-13-reaction-4xx-investigation.html` |
| "compare ingest options A vs B" | `ingest-options-comparison` | `tmp/2026-05-13-ingest-options-comparison.html` |
| "what's the migration plan for the auth middleware" | `auth-middleware-migration` | `tmp/2026-05-13-auth-middleware-migration.html` |

## Sanity checks before saving

- Summary callout reflects the CURRENT state (not just the first turn).
- Conversation log has every turn, in order, with both user + assistant.
- Specs section has at least one of: file paths, commands, decisions.
- No external CSS/JS imports other than approved CDNs (Plotly, Mermaid,
  highlight.js, DataTables).
- File opens correctly in the lab UI iframe and renders dark.
- **Open the file in the actual lab UI iframe** (not just a standalone
  browser tab) — the host wrapper is where rendering bugs hide.
- **Squint at the page.** If you have to squint to read `h1`, the
  contrast is too low. Raise heading color toward `#ffffff`.
- **Resize the window** narrower than 960px and wider than 1600px. The
  dark background should fill the viewport at both extremes; nothing
  should be white outside the centered column.
