# Task and note tabs show recent activity

For both Tasks and Notes, show small New/Updated labels and a subtle rail mark
on document tabs and subtabs, mirrored in the Index. Opening a tab does not
dismiss its highlight. It lasts three days from the change or until the user
chooses ⋮ → Dismiss highlight. A later change highlights the tab again.

Store dismissal in browser localStorage scoped to the Assistant database and
stable typed record ID. Keep Markdown untouched. Backend tab revisions hash
the tab's own body and metadata, excluding shared file mtime/root updated and
inherited child workspace/project values, so edits do not flag every sibling.
Use authored created/updated dates for initial recency; a changed known revision
can use file mtime to recognize direct Markdown edits. Polls, expiry, and
dismissal update badges without replacing the tab tree or current pane.
