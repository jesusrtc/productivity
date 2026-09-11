# Markdown fences use the shared highlighter

`ensureMarked` also waits for the locally vendored syntax highlighter, and
`LabMarkdown.render` highlights explicit supported language fences before
returning HTML. This covers workspace documents, notebooks, and disclosures,
including closed ones. Keep Mermaid and unknown/unlabeled fences untouched.
Code copying must continue reading `textContent` so token spans preserve exact
SQL whitespace. The Chrome regression checks visible SQL colors and copying.
