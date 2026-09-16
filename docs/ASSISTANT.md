# Assistant tasks, notes, and tabs

Assistant stores client-owned tasks and notes and displays tabs inside each
one. The client alone decides their content, structure, headings, language,
and formatting. Lab supplies storage, metadata, tab relationships, navigation,
and rendering. New document bodies are empty; there is no content template.

## Database location

Configure an absolute folder through **Home → Admin → Assistant → Use folder**,
or set `LAB_ASSISTANT_HOME` in the client checkout's untracked `.env` and restart
Lab. `lab assistant path` prints the active location. One database is shared
by the client's vaults and workspaces; it belongs outside the framework repo.

The Assistant terminal opens in that directory. Read its existing AGENTS.md
and README.md before editing. Client instructions own writing and execution
policy. Initialization and migration preserve those files when they exist.
Framework documentation is available through `lab context tasks`,
`lab context meetings`, and `lab migrations`.

## Current storage contract

For `document_format: "embedded-subtabs-v1"` in the schema-2 manifest:

```text
tasks/<id>.md             One task and all its tabs
notes/<id>.md             One note and all its tabs
projects/<id>.md          Optional independent projects
.assistant/manifest.json  Schema and document format
.assistant/workspaces.json  Symbolic workspace references
.assistant/index.json     Generated, rebuildable index
.assistant/assets/        Original captures and referenced resources
```

Each Markdown file has frontmatter and a free-form body. Its `tabs` JSON array
contains tab metadata; stable body markers delimit tab content. Typed parent
IDs and sibling positions represent nesting without imposing an editorial
structure. A tab may contain any supported Markdown, including no headings or
no content. Metadata edits preserve its body and sibling tabs.

A root task or note may reference one project and one workspace. Its tabs
inherit those associations. Projects may span workspaces; changing an
association never moves the document. IDs, unknown metadata, legacy aliases,
and original captures are preserved.

`lab migrations assistant-subtabs` documents the exact serialization contract.
Legacy layouts remain readable. Migration requires an explicit apply command,
backs up and verifies the source data, and preserves existing client
instructions. Reading a migration guide does not migrate anything.

## Tab navigation and editing

The document rail's + creates a tab beside the main tab. **Add subtab** nests
one beneath the selected tab. Names and content are the client's choice. One
tab opens directly; multiple tabs get a generated Index with their clickable
tree and metadata. The Index is not another authored file.

```bash
lab assistant ls --status open
lab assistant workspace ls
lab assistant project ls
lab assistant add "Task title"
lab assistant note add "Note title"
lab assistant subtab add "Tab title" --parent <root-id> --parent-type task --top-level
lab assistant subtab add "Nested tab" --parent <tab-id> --parent-type note
lab assistant verify
```

Agents may edit Markdown and frontmatter directly. Commands are optional
conveniences for IDs and validation. Re-read before editing, preserve sibling
content, and verify structural changes. The generated index detects direct
edits on refresh; do not maintain a second editable copy of the metadata.

The viewer renders authored content in order. Heading copy works on any
client-authored heading. Images remain in their owning repository and can be
referenced through supported relative or mapped workspace paths.

## Metadata capabilities

Properties are edited in the compact document header. Tasks support status,
priority, due date, scheduling, recurrence, and optional context fields. Notes
can use date and series metadata. None of these properties requires a body
section or writing workflow.

Leaf status is not_started, in_progress, done, or skipped. Child branches
aggregate recursively: none started → Not started; some started or completed
→ In progress; all done/skipped → Completed. Cancellation is explicit on the
root. Explicit completion also checks unchecked Markdown items when present.

`created` is the capture timestamp, `scheduled` is the planned working day,
and `due` is a deadline. Planning views use these fields without changing the
body. `lab assistant repeat <id>` explicitly creates a recurring task's next
occurrence with an empty body and history links in metadata. It does not copy
prior results or run a background scheduler.

Notes may belong to a series while keeping their own file and tabs. The rail
keeps the normal Document tabs layout. A small **More in this series** button
by the series name opens a menu of note dates, newest first. Selecting a date
closes the menu and opens that note's tabs. Optional raw captures remain
immutable assets. The legacy meeting viewer recognizes old headings
for compatibility; they are not a template for current notes.

Task and note document tabs show **New** or **Updated** for recent changes,
including in the generated Index. Highlights last three days from the change;
opening a tab does not clear them. Use the tab's **⋮ → Dismiss highlight** to
clear one early. A later change highlights that tab again. Dismissal is saved
in this browser, separately for each Assistant database; it does not change
the Markdown. Tab revisions distinguish each tab's own content and metadata
from changes elsewhere in the same file.
