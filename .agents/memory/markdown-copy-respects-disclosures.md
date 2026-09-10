# Markdown copy respects disclosure state

Use native `<details><summary>Query</summary>…</details>` for foldable prompts,
code, and supporting content in Markdown, with blank lines around Markdown
inside the tags. `open` sets the initial state; a plain `> Query` is a quote.

Google Docs copy must snapshot the live rendered DOM, remove closed disclosures
including their labels, and flatten open disclosures into normal content.
Filter before fetching images. Rich HTML, plain text, legacy clipboard fallback,
section copy, and Assistant copy share `LabMarkdown.copy` in
`static/js/lib/markdown-content.js`; do not reparse raw Markdown for copying,
which loses the reader's current open/closed choices. Main Markdown rendering
uses locally vendored DOMPurify through `LabMarkdown.render`.
