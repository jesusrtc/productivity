# Assistant content belongs to the client

The user clarified on September 15, 2026 that Lab must not bias the structure,
format, sections, or writing workflow of tasks and notes. The framework's role
is to support tabs inside both. This supersedes earlier body-template and
summary-first authoring guidance in Assistant memories.

Keep the technical storage contract (IDs, metadata, embedded tab markers and
relationships) separate from client-owned content. New tasks, notes, tabs,
meeting aliases, and recurrence bodies start empty unless content is supplied.
Render authored Markdown in its original order. Current note previews do not
require Summary or Action items headings. Existing content remains intact.
Migrations preserve existing AGENTS.md and README.md; only missing technical
guides are created. Writing conventions belong in client instructions.
