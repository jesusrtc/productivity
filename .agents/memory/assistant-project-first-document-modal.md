# Keep the original Assistant layout; adjust sizing only

The user rejected all five task redesigns on September 8, 2026. This supersedes
the five-proposal UI instructions.

- Keep the original Overview / Tasks / Meeting notes navigation, project selector,
  grouped task list, and single-click task document modal.
- The user likes opening the modal on click. Do not replace it with an adjacent
  detail pane, board, outline, focus queue, notebook, or extra Tasks 1–5 tabs.
- Improve the existing design through box sizes, padding, and typography:
  compact task rows and document cards, readable actual task titles, and smaller
  metadata boxes. Preserve the existing composition and controls.
- Cross-project subtask data support remains available independently of the UI:
  `lab assistant subtask add "Title" --parent <task-id> --project <child-project>`.
  `parent_project` identifies the parent’s project; legacy children default it
  to their own project. Parent completion includes cross-project children.
