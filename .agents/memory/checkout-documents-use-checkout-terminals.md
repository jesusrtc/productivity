# Checkout documents use checkout terminals

The user wants documents brought to a folder/worktree to use that checkout's
existing terminal, rather than importing the document's original terminal. This
applies to exact-checkout metadata links and document drops onto scope rows or
the Documents section while an external folder/worktree is selected. Explicit
workspace document references retain their existing shared-terminal behavior.

Store folder/worktree documents as internal scope links (whole document or tab).
Do not create workspace document references, transfer linked_task ownership, or
change the original document terminal's conversation, cwd, label, or process.
Choose a running native terminal in the current workspace/vault whose
linked_scope.root matches the exact checkout; exclude borrowed document_source
sessions. Retain that checkout controller across document tabs and task focus.
Use the existing workspace renderer and preserve unsent input. If no checkout
terminal exists, show the attach-terminal hint instead of choosing a document
terminal or starting a process. A terminal drop within a scoped document may
select another native checkout terminal, but cannot assign a foreign terminal.

Explicit activation of a checkout terminal opens its associated scope document
or tab and restores the code scope. Delayed scope/terminal lookups must respect
newer terminal/document navigation and closing. Scope metadata writes preserve
other links and use the current revision for conflict detection.

Verified by desktop/mobile checkout-document browser regressions and existing
workspace reference, task navigation, and backend terminal ownership tests.
