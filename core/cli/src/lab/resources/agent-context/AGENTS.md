# Lab framework capabilities

You are running inside Lab, which provides a document viewer, live notebooks,
workspace/task metadata, and managed local servers. This guide describes those
capabilities; it does not define the workspace's content, coding conventions,
workflow, skills, or memory policy. Explicit user requests and vault/workspace-owned
instructions take precedence over the defaults in this guide.

Before working, every agent—including agents assigned to an Objective or one
of its tasks—must read the owning vault's root instructions and the owning
workspace's root instructions if they have not already been loaded. Check
existing AGENTS.md (or agent.md), CLAUDE.md and .github/copilot-instructions.md
as applicable, and follow the instruction files they reference.

LAB_VAULT identifies the terminal's owning vault. Resolve the owning workspace
from the Objective/task context or workspace metadata. Read its instructions
even when the terminal starts inside an Objective folder, linked repository or
worktree; the current directory and provider discovery alone may omit them.
Read vault-wide rules first, then workspace rules, and also read applicable
instructions in the Objective/task folders and working repository. Keep each
file's scope and the user's requested task scope intact.

Vaults and workspaces own their instructions, skills and memory policy. Do not
create, rewrite, or symlink agent instruction, skill, or memory files merely to
integrate with Lab.

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
- For workspace Objective asset organization, read `lab context objectives`.
  Use `lab objective ls --workspace <id>` to inspect tasks, assets and existing
  assignment suggestions. When inferring where an asset belongs, write only a
  `suggest-assignment` action through `lab objective apply`; include the existing
  asset identifier, destination task/Objective and a short evidence-based reason.
  Suggestions remain pending for the user's Accept/Reject controls. Do not
  accept your own suggestions or use assignment, star, bucket, trash or removal
  actions to implement inferred organization unless the user explicitly requests
  that actual change. Do not re-offer an identical rejected suggestion.

- Task Markdown checklists are required action items, not minor notes. Their
  checked and pending counts affect task progress; pending items prevent task
  completion. Use concrete, well-defined actions grounded in the user's actual
  requirements. Do not invent checklist scope, add filler, delete pending items
  to claim completion, or check an item without verifying its work. Preserve
  existing wording and change requirements only with user authorization.
  For Assistant tasks, only an explicitly linked content tab owns its checklist;
  an inherited navigation tab does not assign new action items to a subtask.
  Automatic recurring tasks retain their ID, reopen before the next deadline,
  and reset their existing checklist and subtasks for the new occurrence.

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
