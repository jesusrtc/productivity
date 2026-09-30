# Recently opened documents belong above linked documents

The user wants a Recently opened section in the Documents sidebar, showing
documents only and ordered by successful opening time. Use the existing time
window buttons; Git comparison modes still apply only to updated files.

History is browser-local and scoped to the Assistant/workspace and vault, with
ten deduplicated root documents. Subtab opens update the root entry. Failed or
cancelled opens and background refreshes must not change opening timestamps.
Resolve current titles and paths against fresh Assistant index data, omit deleted
documents, and preserve inline/modal opening and native document/path drags.

Keep the recent section in the pristine sidebar template so asynchronous
mounting does not invalidate sidebar child-count reconciliation.
