# Markdown disclosures support fences and code copy

`LabMarkdown.render` uses a local Marked block extension to consume disclosure
tags separately, so fenced SQL and other Markdown inside `<details>` work even
without blank lines after `</summary>`. Keep this at tokenization time: rewriting
raw Markdown with a global tag regex can corrupt literal tags in code samples.

Every rendered `pre > code` receives an upper-right Copy button through the
shared renderer. Copy only `code.textContent`, preserving whitespace, and reuse
the plain clipboard fallback. Mermaid keeps its original `pre` hidden after
rendering so its button can still copy the source. Whole-document copying strips
buttons and hidden source along with closed disclosures.

The browser regression uses the repo's real-time Chrome DevTools driver because
virtual-time `--dump-dom` can finish before FileReader/Blob clipboard I/O.
