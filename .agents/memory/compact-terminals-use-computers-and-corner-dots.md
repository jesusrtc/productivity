# Compact terminals use computers and corner dots

The user's October 8, 2026 screenshot correction requests a centered 💻 icon
for every terminal in the compact rail, including task, inherited, worktree,
automation, display-main and dormant launch rows. Keep existing status/worktree
dots small in a corner, rather than using a dot as the entire terminal icon.
Automation dots remain white (theme primary text color) in the corner. Preserve
active selection, working/completion indicators and explicit recovery controls.

Show compact terminal rows without hierarchy indentation, guide lines or
subtab carets. Restore names, worktree colors and hierarchy when expanded.
Implement this as presentation only: retain the live DOM, parent relationships,
hover disclosure, selected-family visibility, keyboard navigation, session
identity and process ownership. Apply the same compact presentation in both
vertical and horizontal orientations.

This supersedes the centered compact markers in
[Automation terminals show white bullets when folded](automation-terminal-folded-white-bullets.md)
and the compact dot-only presentation in
[Terminal names keep existing colored bullets](terminal-names-keep-existing-colored-bullets.md).
