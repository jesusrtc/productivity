# Lab framework capabilities

You are running inside Lab, which provides a document viewer, live notebooks,
workspace/task metadata, and managed local servers. This guide describes those
capabilities; it does not define the workspace's content, coding conventions,
workflow, skills, or memory policy. Explicit user requests and workspace-owned
instructions take precedence over the defaults in this guide.

Read the applicable instructions in the working repository, including existing
AGENTS.md or CLAUDE.md files if your agent has not already loaded them. Each
workspace owns its instructions and skills. Do not create, rewrite, or symlink
agent instruction, skill, or memory files merely to integrate with Lab.

- Discover commands with `lab --help`. Use `lab` to change Lab workspace/task
  metadata; do not hand-edit workspace.json, tasks.json, or .index.json.
- Markdown supports HTML <details><summary>Query</summary>…</details> blocks
  containing prompts, code, tables, images, or notes. Keep blank lines around
  inner Markdown. Closed blocks (including their labels) are excluded from
  Google Docs copy; open blocks are copied as ordinary content. Use this for
  supporting material the user wants folded. Examples: `lab context markdown`.
- For notebook work that should appear live in Lab, use `lab notebook exec`
  so cell execution and output stream to the UI. Examples and constraints:
  `lab context notebooks`.
- To expose a workspace's local server in Lab, use servers.json with Makefile
  lifecycle commands. See `lab context servers`.
- Run `lab context` to reread this guide. These commands read documentation
  shipped with Lab and do not create any files in the workspace.
- For Assistant tasks and meetings, read `lab context tasks` and
  `lab context meetings`. Markdown files are the source of truth; agents may
  create and edit them directly. Read client instructions for ownership,
  terminology, research, and writing rules. Lab does not rewrite those rules.

- For migration instructions and expected data formats, read `lab migrations`
  or `lab agent context migrations`. Detailed guides include
  `lab migrations assistant-document-tasks` (document-owned tasks, independent content tabs),
  `lab migrations assistant-documents` (unified document storage),
  `lab migrations assistant-subtabs` (one Markdown per task/note, embedded subtabs),
  `lab migrations assistant-records-v2`, `lab migrations workspace-agent-context`,
  and `lab migrations vault-workspace-names`. These commands only print
  documentation. Inspect the current format and local instructions, preserve
  IDs/content/references, and migrate only within the user's authorized task.

- When `LAB_DOCUMENT_CONTEXT` is set, this terminal belongs to an Assistant
  document. Read that JSON file for its current absolute Markdown path and tab
  ID before working on a document request; it is context, not authorization to
  modify the document. Follow the client's instructions and preserve siblings.
  Opening the terminal alone does not request an agent task. If present,
  `LAB_ASSISTANT_HOME` selects the owning Assistant database.
