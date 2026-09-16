# Notes and meeting metadata in Lab

The client decides the content, structure, headings, language, and formatting
of every note and tab. Lab does not require summaries, highlights, action
items, questions, or any other section. Creation commands leave bodies empty
unless content is explicitly supplied. Read the database's client-owned
instructions before editing; preserve existing content and instructions.

## Documents and tabs

With `document_format: "embedded-subtabs-v1"`, each independent note lives in
`notes/<id>.md`. All of its tabs, including nested tabs, live inside that same
file. The frontmatter `tabs` array stores their stable IDs and relationships;
body markers delimit their free Markdown content. A task supports the same
tabs in `tasks/<id>.md`. Read `lab migrations assistant-subtabs` for the exact
serialization contract. It describes storage, not a document template.

The rail's + adds a tab beside the main tab. Add subtab nests a tab beneath the
selected one. Tab names, purpose, and content are the client's choice. A
single tab opens directly; multiple tabs have a generated Index. Agents may
edit Markdown and frontmatter directly; commands provide IDs and validation.
Re-read before editing and preserve sibling tabs. Run `lab assistant verify`
after structural changes.

## Optional meeting and series metadata

A note may use `note_type: "meeting"`, `date`, `attendees`, and `series`.
A series is an independent note with `note_type: "series"`. Membership links
notes through metadata; it does not turn them into tabs of the series file.
The sidebar can show the series history and the current note's tabs together.
Lists sort known dates newest first and put undated notes last.

```bash
lab assistant note add "Note title"
lab assistant subtab add "Tab title" --parent <note-id> --parent-type note --top-level
lab assistant meeting series add weekly --workspace demo --title "Weekly"
lab assistant meeting add "Meeting" --workspace demo --series weekly --date 2026-09-14
lab assistant meeting add "Undated note" --workspace demo --undated
lab assistant meeting set <note-id> date none
lab assistant meeting raw add <note-id> --file original.txt
lab assistant verify
```

The meeting command defaults to today's date; `--undated` leaves the date
unset. `created` records capture time, independently of the meeting date.
Do not infer an unknown historical date from the capture timestamp.

Original raw captures are optional create-only UTF-8 assets. Preserve their
bytes, line endings, whitespace, and Markdown-looking text. Imported content
is preserved; linked external documents remain references. Lab does not fetch
or send those links. Existing `meeting content add` aliases can create tabs,
including importing a supplied Markdown file with `--file`.

## Legacy compatibility

Older databases may store meetings, series, and related documents in separate
workspace folders. Their legacy viewer recognizes Summary, Highlights, and
Action items headings for old overview and follow-up displays. These are
compatibility conventions, not requirements for new content. Current embedded
documents render the full body in its authored order through the shared tab
viewer. Do not restructure a client's note to match legacy headings.

Migration is explicit and preserves original bodies, IDs, aliases, captures,
and existing client instructions. Read `lab migrations` and inspect the
manifest before an authorized migration; reading documentation changes no data.
