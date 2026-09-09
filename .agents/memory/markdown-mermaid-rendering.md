# Markdown Mermaid rendering

Workspace Markdown documents and shared/repository Markdown file views call
`renderMermaidBlocks` after inserting their rendered HTML. It converts fenced
`mermaid` blocks to SVG with an on-demand, locally vendored Mermaid bundle.
Keep strict security enabled and preserve source when parsing fails. New
Markdown surfaces need an explicit call after mounting; `marked.parse` alone
only emits a code block.

The Mermaid standalone bundle needs a lexical `define` shadow: bundled
FastDOM detects Lab's AMD-ish loader even though `define.amd` is absent, then
fails with `Wae.default.extend is not a function`. Use `mermaid.lab.min.js`;
never temporarily delete the page's loader while a script loads. Regression
checks must include the real `installLabAmdShim`, not just a blank HTML page.
