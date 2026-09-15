# Assistant agents may edit Markdown metadata directly

The user explicitly requested on September 14, 2026 that agents be free to
create and modify Assistant Markdown files, including task metadata. A Lab API
or CLI is a convenience; neither is a mandatory write gateway. This supersedes
older CLI-only metadata guidance. Keep the files as the source of truth, with
stable IDs and relationships, JSON-compatible frontmatter values, targeted
edits from fresh reads, and preserved unknown fields.

Agents can capture, reprioritize and defer tasks as user intent changes.
`scheduled`, `due`, and `created` have different meanings; never fabricate a
deadline to make a task appear in Today. Recurring tasks use explicit
agent-driven `lab assistant repeat` after completion, retaining each period.
There is no background scheduler. User-specific records and product research
belong in the configured Assistant directory, not framework examples/tests.
