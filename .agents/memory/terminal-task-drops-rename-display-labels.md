# Terminal task drops rename display labels

Dragging a terminal onto a task or subtask renames the terminal's saved display
label to that task's current name, replacing an earlier custom label. This
supersedes label preservation for that gesture in sidebar-object-drops-paste-or-associate.md.
Other resource/folder associations keep their existing labels.

Live Objective drops explicitly request rename_to_task, resolve the canonical
task title after association validation, and use the terminal metadata writer
on the original owning workspace/vault, including borrowed Assistant terminals.
Assistant task links also request the canonical name; checkout-scoped task
drops update only the label. The Home demo keeps its simulated name in sync.
Allow full task titles (up to 512 characters) in saved terminal labels; visual
rows still use ellipsis. Keep the same logical/tmux identity, launch folder,
agent conversation, ownership and unsent input. Do not send terminal commands.
