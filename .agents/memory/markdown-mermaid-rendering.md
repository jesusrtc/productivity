# Markdown Mermaid rendering

Project Markdown documents and shared/repository Markdown file views call
`renderMermaidBlocks` after inserting their rendered HTML. It converts fenced
`mermaid` blocks to SVG with an on-demand, locally vendored Mermaid bundle.
Keep strict security enabled and preserve source when parsing fails. New
Markdown surfaces need an explicit call after mounting; `marked.parse` alone
only emits a code block.
