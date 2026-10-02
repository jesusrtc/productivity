# Objective documents use the native inline editor

Objective-owned Markdown opens directly in `LabMarkdownEditor`, reusing the
existing formatted editing, slash commands and shortcuts. Subtabs live only in
the workspace's left menu. Linked Assistant documents keep their native editor
and ownership, but their Objective inline presentation hides the inner tab rail
and drawer; ordinary Assistant opens retain those controls.

Save or Cmd/Ctrl-S writes immediately. Ten seconds of idle typing autosaves;
navigation saves the outgoing draft without blocking the next view. Retain the
editor instance, draft and undo across subtab switches. Serialize saves against
the latest confirmed registry/file revisions and preserve sibling content.
Never let a late save acknowledgment erase newer typing or replace the selected
editor. A conflict retains the draft and stops automatic retries; Revert fetches
the current saved tab. Native Files/terminal links to owned Markdown reuse this
editor rather than falling back to a separate viewer.

The native-browser Objective regression holds a parent save response, edits
both parent and child, verifies idle autosave, then rejects an external-edit
conflict and recovers without changing the sibling.
