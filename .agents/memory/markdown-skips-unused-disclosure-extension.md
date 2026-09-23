# Markdown skips the unused disclosure extension

Marked calls a block extension's `start` on the remaining source for each
paragraph. The disclosure extension's line-search regex therefore repeatedly
scans long documents even when there are no disclosure tags. `LabMarkdown.render`
uses a second, lazily created base parser when the entire input cannot contain
`<details>`, `<summary>`, or their closing tags. The two parser instances are
reused; no document content or rendered DOM is cached.

Keep the detection conservative and case-insensitive. Possible tags inside
fences, comments, examples and malformed HTML retain the existing extension.
Custom hooks, tokenizers and extensions also retain it because they can change
the input after detection. Both routes still sanitize, highlight, add code-copy
controls, and honor per-call renderers. Regression tests compare vendored Marked
output and exercise the real Chrome disclosure/copy behavior.

The disposable navigation probe accepts `--markdown-revision` for source-only
comparisons. Optional `LAB_PERF_REFRESH_TRACE` captures bounded call metadata for
sidebar/dashboard/document rendering; leave it off for final interaction runs.
