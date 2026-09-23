# Document editing latency checks both views

Run `scripts/perf/lab_navigation_latency.py --document-edit` only with its
disposable fixture. Alternate Alpha and Beta, which have identically named
documents, and verify all four files after Save, Cancel and Close. A Save is
complete only after both the modal and inline pane show all expected headings
and paragraphs. Editor readiness includes the loaded sibling list, disabled
file navigation, exact source and textarea focus. Keep cancelled text out of
every persisted file.

Returning to a visited workspace restores its last document; only first visits
expect a dashboard. Text insertion prepares the native Save/Cancel clicks and
is not an editor typing latency measurement. `--document-sections` controls
document size without changing the default 30-section navigation fixture.
