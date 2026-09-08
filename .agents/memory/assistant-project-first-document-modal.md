# Assistant uses the selected Compact design

The user selected Compact (proposal 2) on September 8, 2026. The comparison is
complete. This supersedes the earlier five-proposal instructions.

- Keep one Tasks tab beside Overview and Meeting notes. Remove proposal tabs and
  the modal sizing switcher after selection.
- Preserve the original project selector, grouped task list, and single-click
  document modal. The user explicitly likes the modal interaction.
- Use Compact proportions: 48px task-row minimum height, 5px vertical row padding,
  16px task titles, 12px summaries, a 270px document navigation rail, 5px document
  card padding, 15px card task titles, 22px document icons, and compact metadata.
- Do not replace this with a board, outline, focus queue, adjacent detail pane,
  notebook layout, or another redesign without a new explicit request.
- Cross-project subtask data support remains available independently of layout:
  `lab assistant subtask add "Title" --parent <task-id> --project <child-project>`.
  `parent_project` identifies the parent’s project; legacy children default it to
  their own project. Parent completion includes cross-project children.
