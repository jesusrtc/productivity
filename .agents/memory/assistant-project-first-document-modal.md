# Assistant task layouts are global (September 8, 2026)

This supersedes the earlier project-first restriction at the user’s request.

- Overview, Tasks 1–5, and Meeting notes must appear in Lab’s native Assistant
  navigation. A separate conversation preview does not fulfill this request.
- The five layouts are Compact list, Living outline, Focus queue, Flow board,
  and Task notebook. They share real data and default to all projects.
- Project ownership is a label and optional filter, not a mandatory folder/group.
- Use prominent task titles, compact rows, expandable subtasks, and adjacent
  details. The document browser uses task titles as its primary navigation text.
- A subtask may belong to another mapped project. Create it with
  `lab assistant subtask add "Title" --parent <task-id> --project <child-project>`.
  `parent_project` identifies the parent’s project independently of the child’s
  owning `project`; legacy children default the parent project to their own.
- Parent progress and completion include cross-project children. Source assets
  stay in the workspace/project that owns each document.
