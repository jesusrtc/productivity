# Document terminals keep independent code scopes

Assistant Linked documents and workspace Documents rows are drag sources using
the same Assistant root/document ID payload as the document chooser.

A shared document terminal keeps the same display name as in Assistant. Do not
fill an absent custom `label` with the logical session name in task-terminal
listings: that hides the document title only in the workspace view.

Document/task links and folder/worktree links are independent. Linking a code
scope through a workspace updates the shared terminal's canonical owner without
clearing its document, label, conversation, or cwd. Explicit document-terminal
clicks open the document and restore the linked code scope even with file Sync
linked off. Start these independently so slow file discovery cannot delay or
reopen a document after newer navigation. Regular file linking still assigns
its containing scope; unlink actions preserve the other associations.
