# Assistant tasks, notes, and tabs

Current task/note storage is `documents/<id>.md` after an explicit per-client
migration. Read `lab migrations assistant-documents` for the backup, conversion,
verification, client-instruction updates and restart sequence. Existing clients
continue using tasks/notes until migrated. `external_url` optionally associates
an external document with any root or subtab; its **External doc** button opens
in the clicking client's browser from dashboards, lists and document views.


Assistant stores client-owned tasks and notes and displays tabs inside each
one. The client alone decides their content, structure, headings, language,
and formatting. Lab supplies storage, metadata, tab relationships, navigation,
and rendering. New document bodies are empty; there is no content template.

## Shared Documents library

Tasks and notes share the **Documents** entry, opening at Dashboard, with All, Open tasks, Documents,
Starred, Meetings, Series, and task history views. Existing `tasks/` and `notes/`
paths are compatibility storage; this change does not move or duplicate files.
All existing content, IDs, tabs, aliases, original captures, and series links stay
in place. The labels and filters do not change a record's storage type.

`track_task: true|false` controls whether a tab has its own task lifecycle.
New ordinary tabs are untracked; **Add task** (CLI `subtab add --task`) creates a
tracked tab. **Track this tab** can change an existing tab in either direction,
preserving its content and stored status. A direct status edit enables tracking.
For older records without the field, task records and tabs with a stored status
retain their existing tracking. Only tracked child branches contribute to
progress; untracked content with no tracked descendants has no status. A
containing document appears in Open tasks whenever its overall work is pending.
Completing or reopening a tracked child updates that document's progress.

`keep_in_documents: true|false` belongs to the root. It defaults to true for
notes and false for transient tasks. Completion never changes this preference:
retained documents stay in Documents; completed transient tasks stay in Completed
history and leave All/Open tasks. History has no seven-day cutoff. **Keep in
Documents** retains the result of a task in the same Markdown file.

`starred: true|false` is independent of tracking, completion, and retention.
Use the star beside an item or in its header. A series and each of its notes
have separate stars; starring a series adds just the series to Starred. Its
existing dates menu provides access to the member notes.

Use **Label → Meeting** to include a document in Meetings, then optionally set
its date and series. **+ Series** creates a meeting series with an empty body.
A series with members cannot be relabeled until those memberships are removed.

```bash
lab assistant document ls
lab assistant document ls --starred
lab assistant document ls --kind meeting
lab assistant document ls --status open
lab assistant document add "Reference"
lab assistant document add "Weekly sync" --kind meeting
lab assistant document set <id> starred true
lab assistant document set <id> note_type meeting
lab assistant document set <id> keep_in_documents true
lab assistant document set <id> track_task false
lab assistant subtab add "Review" --parent <id> --parent-type note --task
```

Document edits use the same Save workflow for tasks and notes, with conflict
checks and preservation of sibling tabs. Unchecked Markdown items still block
explicit completion of a tracked leaf; ordinary prose and headings never become
tasks automatically.

## Dashboard and series lists

**Add section** starts a complete section JSON object. **Show filter** is the
only action in each section header and opens its editable JSON. Every section
setting is explicit in that object: title, position, filters, sort, and limit.
There are no separate filter forms, summaries, or reorder buttons. Edit
`position` to reorder sections (lower numbers first; ties sort by ID), or remove
a section from the JSON editor.
The initial sections are Priority, Starred, and Documents. Priority matches open
P1 work **or** deadlines within two local calendar days, including overdue work.
Tracked subtabs contribute their priorities and deadlines; completed, skipped,
and cancelled branches do not. Other section filters combine with this rule.
Filters include source, document type, priority, deadline window, status, star,
workspace, project, and text; order and item limits are configurable.

Dashboard sections match independently. An item appears in every section whose
filter matches it; starring it adds it to Starred while it remains in Documents
and other matching sections. Each series appears once within each section and
once in each list view. A series row shows its
name and opens the latest dated note (newest creation time breaks date ties;
undated notes follow dated notes). A grouped row shows a filled star if either the series or a member note is
starred. Clicking it opens separate Entire series and Latest note controls;
View starred notes opens the existing modal history filtered to starred notes.
A star in the document header belongs to that individual note. A starred older note
or older unfinished task can match a section without changing which note opens.
Rows identify notes, meetings, and recurring meeting series with distinct icons.

Inside the document modal, **More in this series** contains every member,
regardless of list filters. Search dates or titles, or select Starred notes or
Open tasks, to find a previous meeting. The modal preserves its date filter,
focus, and current document tabs during background refreshes.

Each section is a complete schema-3 JSON file at
`.assistant/dashboard/<id>.json`, separate from document Markdown and generated
indexes. Filenames match section IDs. Packaged JSON files define initial
sections and the new-section template. **Show filter** edits the complete JSON,
with a SQL-style condition in `where`:

```json
{
  "schema": 3,
  "id": "priority",
  "title": "Priority",
  "position": 10,
  "where": "source = 'open' AND (priority = 'P0' OR due <= TODAY + 2)",
  "sort": "due",
  "limit": 20
}
```

`NOT` binds before `AND`, and `AND` before `OR`; parentheses make grouping
explicit. Keywords are case-insensitive. Quote text with single quotes; double
an apostrophe inside text (`'Won''t do'`). Use `true` and `false` for flags.
The supported expression language is a WHERE condition, without SELECT/FROM,
joins or executable statements. An optional leading `WHERE` is accepted.

| Condition | Example |
| --- | --- |
| Equality / comparison | `is_RFC = true`, `score >= 2`, `status != 'done'` |
| One of several values | `priority IN ('P0', 'P1')` |
| Date window, including today | `due BETWEEN TODAY AND TODAY + 2` |
| Due soon, including overdue | `due <= TODAY + 2` |
| Text pattern | `title LIKE '%review%'` (`%` is any text; `_` is one character) |
| Text or array membership | `tags CONTAINS 'research'` |
| Empty value | `outcome IS NULL` or `outcome IS NOT NULL` |
| Attribute presence | `is_RFC IS MISSING` or `is_RFC IS NOT MISSING` |

`NOT IN`, `NOT BETWEEN`, `NOT LIKE` and `NOT CONTAINS` are also supported.
`TODAY` uses the viewer's local date, with optional plus/minus integer days;
`CURRENT_DATE` and `CURRENT_DATE()` are aliases. Absolute dates are quoted
`'YYYY-MM-DD'` strings. Comparisons preserve JSON types and case. Missing/null
values do not satisfy ordinary comparisons, even under NOT; use IS NULL or
IS MISSING explicitly. `IS NULL` includes both null and missing values.

Built-in fields include `source`, `kind`, `status`, `priority`, `due`, `starred`,
`workspace`, `project`, `title`, `summary`, `tldr`, `owner`, `date`, `created`,
`updated`, `tracked`, `keep_in_documents`, `note_type` and `type`.
`source` supports active, all, open, documents, starred, completed and cancelled;
`kind` supports note, meeting, recurring and task. These two fields support
`=`, `!=` and `IN`. `search CONTAINS 'text'` searches titles, summaries and
content without case sensitivity. Priority and due check pending work, including
tracked subtabs. BETWEEN checks both bounds on the same pending task.
`starred` reflects stars on either the series or its member notes.

`sort` is newest, due, priority or title. `limit` is 0 (all), 5, 10, 20, 50 or 100.
Positions are integers from -1000000 to 1000000; lower positions appear first.
Section order only changes placement; it does not change membership. Limits and
counts are independent for each section. The dashboard total counts unique items
across the displayed sections. To hide starred items from Documents, explicitly
use `source = 'active' AND starred = false` in that section. No settings are
stored outside the section JSON except the separate document metadata.

`GET /api/assistant` returns sections, the new-section template, a revision, and
server-parsed filters for matching. Parsed filters are generated, never another
editable copy. `PUT /api/assistant/dashboard` validates JSON and query syntax,
checks the revision, then writes changed section files under the database lock.
Errors include the query character position and retain the editor draft. Direct
file edits are picked up on refresh; an empty directory is an empty dashboard.
Queries allow up to 100 conditions and 16 nesting levels. The parser never
executes SQL or code.

Older single-file settings, schema-1 flat sections and schema-2 JSON expressions
remain readable. Migration preserves grouping, custom filters, section order,
limits and sort settings, and backs up original section bytes under
`.assistant/backups/`. The legacy `.assistant/dashboard.json` remains intact.

## Custom attributes

Open any task, note, or subtab and choose **Attributes** to edit its JSON object.
Names and values are client-defined; nothing is assigned automatically. For example:

```json
{
  "is_investigation": true,
  "is_RFC": false,
  "stage": "Review",
  "tags": ["research", "draft"]
}
```

Attributes live in the record's `attributes` metadata, alongside its content in
the same Markdown file. Subtabs own their attributes in their existing tab
metadata; they do not inherit them. Saving preserves document IDs, content,
other properties and sibling tabs. Concurrent edits keep the draft and report a
conflict. `{}` clears the object; CLI `null` also clears it.

Use **Show filter** to combine custom attributes with any other conditions:

```sql
source = 'open' AND (is_investigation = true OR is_RFC = true)
```

Put that expression in the section's `where` string. Unqualified custom names
check the document's attributes. `attributes.is_RFC` is the explicit form;
use it when a custom name also names a built-in field, such as `attributes.title`.
For names with spaces, use double quotes: `attributes."My flag" = true` (escape
those quotes when inside a JSON string). Attribute names and text values keep
their case. A missing attribute differs from false, zero, or explicit null.

Use `any_tab.is_RFC = true` to check the root and every embedded subtab. Any
matching tab includes the document. `any_tab.flag IS MISSING` matches if at
least one tab lacks the attribute. Each condition searches independently;
conditions in an AND can match different tabs. Series still appear once and
open the latest note, even when an older note matched.

For exact structured JSON values use `data = JSON '{"approved":true}'`.
`outcome = JSON 'null'` matches only explicit null, preserving the older JSON
filter's equality semantics. Use `tags CONTAINS JSON 'null'` for null array items.

Values can be booleans, strings, finite numbers, null, arrays, or objects.
Validation allows up to 100 entries per object/list, names up to 100 characters,
text values up to 4096 characters, nesting depth 8, and 32 KB per attributes object.

```bash
lab assistant set <task-id> attributes '{"is_RFC":true}'
lab assistant note set <note-id> attributes '{"is_investigation":true}'
lab assistant subtab set <tab-id> attributes '{"stage":"Review"}'
```

These commands replace the selected record's whole attributes object; read its
current value and preserve unrelated attributes when making a targeted edit.

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

## Document terminals

Opening a schema-2 document opens one terminal with the Lab-wide default
agent. All tabs inside the same Markdown file share that terminal. The agent
receives the document path and selected tab as context; opening a document does
not send a task or change its content. Dashboard rendering and refreshes never
start terminals.

The defaults are **60 minutes to sleep**, **36 hours to expire**, and **3 running
document terminals**. Change them in the document terminal's **Settings** button
or **⌘, → Global → Document terminals**. The validated settings
are stored under `documentTerminals` in `$LAB_HOME/settings.json` (normally
`~/.lab/settings.json`). **Global → General** selects the default agent and shows
which agents are installed on the computer running Lab. Legacy Assistant
`.agents/config.json` values remain a fallback until explicitly changed. See
[Settings](SETTINGS.md) for scope and migration details.
Turning off **Open automatically** prevents future automatic starts; existing
agents still follow cleanup rules.

Sleep stops the tmux session and agent process, releasing their memory. Reopening
before expiry resumes the exact saved agent conversation where the installed
provider supports it. Expiry removes the managed association and context file;
opening it again starts a fresh conversation. Documents and the provider's
ordinary saved chat history are preserved. A provider's missing, changed, or
unreadable activity format is treated conservatively: an agent that might be
working stays alive rather than being interrupted.

Keyboard/mouse interaction and confirmed work completion count as activity;
status polling and merely leaving a document visible do not. A submitted task,
a tool call, and waiting for an approval remain busy until an explicit provider
turn-completion event. Cleanup checks once a minute, including while the browser
is closed. It can run late while the computer is asleep or Lab is stopped and
catches up after restart. At the running limit, a safely idle older terminal may
sleep early. When no safe slot is available, the new document offers **Try again**
instead of launching another agent. Ordinary manually opened terminals are
outside these limits.

Only the visible document has an xterm renderer and WebSocket. Closing, switching,
or hiding the document releases those browser resources. Terminal input updates
activity in RAM; the byte path does not scan files, query databases, or spawn
processes. The single cleanup worker scans only the bounded live set and at most
512 KiB of each provider's recent activity trace.

The runtime registry is `.lab/state/document-terminals.json`; selected-document
context lives in `.lab/state/document-context/`. They are generated state, not
client-authored document metadata. No document migration is required for this
feature. Update and restart Lab on each client; existing schema-2 tasks/notes and
migrated `documents/` libraries both work. Older record formats still need their
existing explicit Assistant migration.

## Current storage contract

For `document_format: "embedded-subtabs-v1"` in the schema-2 manifest:

```text
tasks/<id>.md             One task and all its tabs
notes/<id>.md             One note and all its tabs
projects/<id>.md          Optional independent projects
.assistant/manifest.json  Schema and document format
.assistant/workspaces.json  Symbolic workspace references
.assistant/index.json     Generated, rebuildable index
.assistant/dashboard/<id>.json  One complete JSON per dashboard section
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
