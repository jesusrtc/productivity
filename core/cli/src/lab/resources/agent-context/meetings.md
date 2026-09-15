# Meetings in Lab

Read `lab assistant path`, that database's existing AGENTS.md and README.md,
and `lab assistant workspace ls` before writing. Resolve the exact mapped
workspace. Client policies about ownership, research, and writing stay in
client instructions. Do not rewrite them to adopt a framework capability.

## Storage and navigation

Paths are relative to the Assistant database:

```text
workspaces/<workspace>/workspace.md
workspaces/<workspace>/meeting-series/<series-id>.md
workspaces/<workspace>/meetings/<meeting-id>.md
workspaces/<workspace>/meetings/<meeting-id>/raw.txt
workspaces/<workspace>/meetings/<meeting-id>/questions/<content-id>.md
workspaces/<workspace>/meetings/<meeting-id>/documents/<content-id>.md
```

Legacy `projects/<id>/project.md` mappings remain readable without migration.
The main meeting file has frontmatter `id`, `title`, `workspace`, `date`,
`attendees`, `created`, `updated`, `tags`, and optional `series` and `tldr`.
Use JSON-compatible values. IDs match filenames. A series ID is workspace-local;
similar titles alone do not establish a recurring relationship.

Meetings open on Summary. The overview contains `# Summary`, `# Highlights`,
and `# Action items`. Only checkboxes under Action items count as follow-ups.
Other sections, including legacy `# Notes`, appear as Supporting notes.
Questions and documents are separate records in the rail. Lists and histories
have newest-first `yyyy-mm-dd` headers; invalid/missing dates appear last as
Undated. Rows show the series name, or the standalone meeting title.

Series files have `id`, `title`, `workspace`, `created`, `updated` and a free
Markdown body describing purpose. Histories derive from meeting references.
Content files have `id`, `title`, `kind` (`question` or `document`), `meeting`,
`workspace`, `created`, `updated`; bodies are free Markdown. Keep each question
and its answer together. Keep each requested document separate. External
documents can be descriptive links; Lab does not fetch or send them.

## Commands

```bash
lab assistant meeting series add weekly --workspace demo --title "Weekly review"
lab assistant meeting series ls --workspace demo
lab assistant meeting series show weekly --workspace demo
lab assistant meeting add "Review" --workspace demo --date 2026-09-14 --series weekly --raw-file notes.txt
lab assistant meeting add "Unknown date" --workspace demo --undated
lab assistant meeting ls --workspace demo
lab assistant meeting show <meeting-id>
lab assistant meeting set <meeting-id> series weekly
lab assistant meeting set <meeting-id> date none
lab assistant meeting raw add <meeting-id> --file notes.txt
lab assistant meeting raw show <meeting-id>
lab assistant meeting content add "Why?" --meeting <meeting-id> --kind question
lab assistant meeting content add "Draft" --meeting <meeting-id> --kind document --file draft.md
lab assistant meeting content add "Shared brief" --meeting <meeting-id> --kind document --url https://example.org/brief
lab assistant meeting content ls --meeting <meeting-id>
lab assistant meeting content show <content-id> --meeting <meeting-id>
```

Omitting date options means today. Use `--undated` when the actual date is
unknown, even if the capture date is known. Never infer an old meeting's date
from its creation timestamp. `date none` clears an incorrectly inferred date.

Original raw notes are an optional create-only UTF-8 snapshot: preserve bytes,
line endings, whitespace, and Markdown-looking text. Save only the original
content, not the user's surrounding instructions. Raw import never overwrites.
The viewer treats originals as plain text; Copy raw notes copies that text.
Do not relabel old supporting notes or generated summaries as originals.
Corrections, questions and analysis belong in separate Markdown content.
Generated demo notes must be labeled as fictional; no fabricated transcript
may be represented as an actual original.

Agents may create and modify Markdown files directly, including frontmatter.
The CLI supplies convenient IDs and relationship validation. Keep metadata
ownership consistent with paths, preserve unknown fields, and re-read before
editing. Filesystem writes appear in the next Assistant refresh. General
read APIs: `/api/assistant`, `/meeting`, `/meeting-series`, `/meeting-content`
(the last three are below `/api/assistant` and take a relative `path`).
