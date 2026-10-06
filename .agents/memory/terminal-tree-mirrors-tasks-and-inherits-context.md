# Terminal tree mirrors tasks and inherits context

The October 6, 2026 terminal request supersedes the multiple-primary rule in
`task-clicks-activate-linked-terminal.md`. Each Objective task/subtask owns one
primary terminal. Reassigning that primary keeps the former session alive and
removes only its task ownership. Recommend one global terminal per Objective
and one per task through explicit open/create rows; never launch a process just
because a task was added or a task row was opened. Existing primary sessions are
reused and repeated create clicks are deduplicated.

Primary terminal rows mirror task names, left status boxes and optional right
asset icons. Subtask terminals nest under their task's terminal, including a
recommended parent row when no primary has been opened. Task focus and hover
reveal children. Deliberate moves override the default task hierarchy through
browser-local `tabRoots`, `tabParents` and `tabAfter` state.

Extra subterminals need no task ownership. Resolve their effective context from
the nearest ancestor that owns a task; clicking them opens that task while
selecting the child session. An explicit task of their own takes precedence.
New subterminal preserves the parent's launch scope and Objective association
without claiming its task. Paste task context uses the inherited full bundle
without sending Enter. Preserve cwd, session IDs, conversations and drafts.
