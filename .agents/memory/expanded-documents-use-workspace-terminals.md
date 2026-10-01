# Expanded documents use the workspace terminals

The user wants Expand/double-click/Command-click to extend the document across
the Files sidebar area, with the active workspace (including Assistant) and its
ordinary terminal panel still visible and interactive alongside it. The expanded
document has the same red upper-right close button as the inline document.

Use the existing workspace terminal sessions and renderer. Opening, expanding,
changing content tabs and closing must not create a private document terminal,
reconnect the selected workspace terminal, or lose unsent input/editor drafts.
Terminal activation while expanded retains the expanded layout. The document is
an accessible region because the workspace terminal and navigation remain usable.

Hide Files temporarily with the expanded presentation class; never write or
change the saved sidebar-collapse preference. Closing restores the existing
choice, including a sidebar which was already collapsed. Workspace navigation
also cancels pending expanded opens and removes the expanded presentation.

This replaces the earlier standalone modal and per-document Right/Bottom display
placement preference. Retained legacy conversation support is compatibility only;
normal document presentation always reuses the workspace terminal panel.

Browser regressions in test_frontend_workspace_documents.py cover actual geometry,
interactive terminal access, drafts/selection, completion review, pending open
cancellation, terminal activation, saved Files choices, and native mobile close.
