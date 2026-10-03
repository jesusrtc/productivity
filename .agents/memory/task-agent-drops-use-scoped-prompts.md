# Task agent drops use scoped prompts

The user wants a task console drop to read like an agent prompt. Label Context:
with Objective shared assets and each parent task, then This task: with the
selected task specification and assets. Include source titles, semantic types
and exact paths, URLs, document tabs and sublinks. Repeated references use one
[R#] definition and keep their role in each group; Archive stays excluded.

Instruct the agent to work only on This task. Inherited Objective/parent assets
are background context and read-only unless also attached to the current task.
Limit changes to current references and explicitly linked worktrees/folders;
preserve parent/sibling tasks and ask before expanding scope.

Live and demo producers use js/lib/task-context.js with a versioned drag MIME.
The terminal validates its references against the ordinary exact-source array.
Use xterm's public bracketedPasteMode for readable multiline agent-editor
paste; flatten line breaks for consoles without bracketed paste. Do not send
Enter. Ordinary asset drops keep shell-quoted paths. Terminal-name association
and Assistant ownership remain unchanged. This supersedes the older flat,
shell-quoted task bundle presentation.
