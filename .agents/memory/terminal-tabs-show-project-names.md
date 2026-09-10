# Linked terminal tabs show project names

Use the linked project label as the default terminal tab and top-header name,
including when file linking previously saved the filename as an automatic label.
Root scopes use the project directory basename. Explicit user renames still win;
internal logical/tmux names remain stable.

Put project, worktree, folder and optional file at the top of the hover card.
Prefer displaying the card above its anchor, falling below when there is no room.
The terminal's top header exposes the same hover card. Keep the agent icon,
project/worktree colors, recent highlights, and request history.
