# Terminal links use drag-and-drop and direct context actions

Drag a terminal tab onto a file, folder row, folder selector, or the selected
worktree picker to link it. Divider drags remain reorder-only. File/folder
context menus offer Link to active terminal and Unlink from terminal; terminal
menus unlink the file and folder/worktree associations separately.

A file has one terminal owner. Assigning it to another terminal transfers the
link, including across workspace tabs and available registered vaults, with
access checks before any transfer writes. A terminal has one file link and one
folder/worktree link. Multiple terminals may share a folder/worktree. Unlinking
one association preserves the other and never stops processes or deletes files.
File linking still assigns its containing project/worktree. Browser Sync linked
remains separate and opt-in.
