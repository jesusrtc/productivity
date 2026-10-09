# Lab user guide

Lab is a local workspace for documents, tasks, Objectives, notebooks, terminals
and local applications. This guide explains how users and agents operate Lab.
Vault and workspace instructions own project conventions, content, terminology,
skills and memory policy. Explicit user requests and those instructions take
precedence over framework defaults.

## Find your context before working

A vault contains workspaces and their content. The Lab framework installation
can live outside the vault. `LAB_VAULT` pins a Lab terminal to its owning vault;
use `lab vault --help` to inspect or select vaults. A selected Files folder or
worktree may be outside the owning workspace, so its path alone does not
identify all instructions that apply.

Every agent, including agents assigned to an Objective or a task, must read:

1. This user guide and the Lab changelog, unless already loaded.
2. The owning vault's root instructions.
3. The owning workspace's root instructions.
4. Applicable Objective, task and working repository instructions and the
   additional files they reference.

Check existing `AGENTS.md` (or `agent.md`), `CLAUDE.md` and
`.github/copilot-instructions.md`. Read vault-wide rules first and preserve each
file's scope. Provider discovery in an Objective or linked checkout can miss
the vault and workspace roots; read those roots even if your terminal starts
elsewhere. Lab does not create or link client instruction, skill or memory files.

The sidebar's **META** section lists **Lab agent context**, **Lab user guide**,
**Lab changelog**, and existing Vault, Workspace, Objective and selected-folder
instruction files. Click a document to read it. Documentation and instruction
shortcuts expose their absolute paths in their tooltips; the context reader
lists absolute paths in its text. Switching Objectives updates the Objective
instruction shortcuts while retaining the owning vault and workspace.

Click **Lab agent context** to inspect the context for the selected scope. Drag
it, or the reader's **Drag context to terminal** button, onto a terminal to paste
the full context without submitting it. The context keeps the scope captured
when opened or dragged, even if you select another folder while it loads.
Switching terminals while a drag loads cancels its paste. The context and files
show current information; they do not report what an already running agent has
loaded.

## Read the installed documentation

These commands print documentation and do not create files in a workspace:

```bash
lab --help
lab context
lab context user-guide
lab context changelog
lab context user-guide --path
lab context changelog --path
lab agents doctor
```

In a source or editable installation, the user guide and changelog resolve to
the framework checkout's `docs/USER-GUIDE.md` and `docs/CHANGELOG.md`. In an
installed wheel or source distribution, they resolve to the installed Lab
package's `resources/docs/` directory. The context always supplies the actual
absolute paths for that installation. The package ships both documents, so a
client does not need access to the original source checkout.

Use the detailed topics for the work you are doing:

| Command | Coverage |
| --- | --- |
| `lab context markdown` | Documents, disclosures, links and copy behavior |
| `lab context notebooks` | Live execution, output and kernels |
| `lab context servers` | Local applications and lifecycle commands |
| `lab context tasks` | Assistant tasks, checklist ownership and recurrence |
| `lab context meetings` | Assistant meetings and document ownership |
| `lab context objectives` | Workspace Objectives, tasks, assets and terminals |
| `lab context migrations` | Data formats and migration procedures |

`lab agent context` and `lab agents context` are aliases. Add `--path` to a
topic to print its installed absolute file path.

## Launch agents and use terminals

Lab's New agent controls launch the selected provider with Lab context. From
an ordinary shell, use:

```bash
lab agents run codex
lab agents run claude
lab agents run copilot
lab agents run codex -- resume --last
lab agents run --vault /absolute/vault/path copilot
lab agents run --vault /absolute/vault/path --workspace <id> --objective <id> codex
```

Arguments after `--` belong to the provider. A bare provider command in a plain
shell bypasses Lab's launcher. Existing agents are not interrupted or sent
unsolicited messages when the guide changes; ask them to read `lab context`
and `lab context user-guide`, or start a new session.

Lab terminal launches also pin the owning workspace and, when associated, the
Objective. For a manual launch in an external worktree, pass `--workspace` and
`--objective` before the provider name. `LAB_CONTEXT_WORKSPACE` and
`LAB_CONTEXT_OBJECTIVE` retain those identities, so `lab context` can list the
owning instructions even outside their folders. Without explicit ownership,
Lab discovers workspace and Objective roots from the current directory.

Codex receives the guide and absolute references through a process-local
developer instruction override combined with its existing trusted instructions.
Claude receives them through an appended system prompt, retaining user append
prompts and files. Supported Claude resumes refresh their system prompt unless
the user explicitly retains a snapshot. Copilot loads Lab's packaged bootstrap
instructions alongside existing custom instruction directories; those
instructions require reading `LAB_AGENT_CONTEXT` for the launch's absolute
references. Repository discovery, provider homes and authentication remain
provider-owned. See `lab context` for the context of the current terminal.

Opening a terminal does not itself authorize an agent to modify content. Work
within the user's request and follow the owning instructions.

Objective task terminal tabs appear by default only while the task is **In
progress**. Paused, Not started, Completed and Won’t do tasks stay hidden even
when selected, including child terminals that inherit their status. Selecting
one of those tasks opens its details without creating or activating a terminal.
Changing it back to In progress makes its terminal available again. Hidden
sessions keep running. Use **Show all** on an Objective or **Show all terminals**
in the terminal menu to inspect them explicitly; **Show WIP** restores the
In progress filter. Workflow and current Objective main terminals remain available.

## Change metadata through Lab

Discover the relevant CLI with `lab --help` and each command's `--help`. Use
`lab` to change workspace and task metadata. Never hand-edit `workspace.json`,
`tasks.json` or `.index.json`. Markdown documents are content and may be edited
directly when the user authorizes that work.

For workspace Objectives, read `lab context objectives` and inspect the current
state with `lab objective ls --workspace <id>`. Mutations use
`lab objective apply`; consult its help for supported actions.

When inferring where an existing asset belongs, write only a
`suggest-assignment` action. Include the existing asset identifier, destination
task/Objective and an evidence-based reason. Suggestions remain pending for
the user's Accept/Reject controls. Do not accept your own suggestions, repeat
an identical rejected suggestion, or use assignment, star, bucket, trash or
removal actions to implement inferred organization without an explicit user
request for the actual change.

## Tasks, subtasks and action items

Task Markdown checklists represent required work. Checked and pending counts
affect progress, and pending items prevent task completion. Use concrete
actions grounded in the user's actual requirements. Preserve existing wording;
change requirements only when authorized. Do not invent scope, add filler,
delete pending items to claim completion or check an item without verifying
its work.

The Objective Tasks sidebar shows unfinished task and subtask navigation.
Unchecked Markdown actions appear in the main task dashboard and their source
document, without adding rows or blank space to the left sidebar. Completed and
discarded branches are excluded. The dashboard highlights overdue actions and
actions due within the next two days. Write an action's deadline at the beginning of its text:

```markdown
- [ ] [2026-10-12 09:30] Review the alert proposal
- [ ] [2026-10-12] Send the revised document
- [ ] Prepare the agenda
- [x] Review the previous draft
```

Use `YYYY-MM-DD HH:mm` in local time, with a 24-hour clock. Date-only deadlines
use the end of that day. Undated actions remain pending. Click an action to
open its owning Markdown tab, reveal folded content and highlight the exact
action; entering Edit selects its source line.

Recurring tasks keep their ID across occurrences. A completed occurrence
stays hidden until its **show again** time. At that time Lab reopens it and
resets its existing checklist and subtasks, so the new occurrence appears
unchecked. The show-again lead can be configured; the default is one day before
the next deadline. Overdue unfinished occurrences stay obligations rather than
being skipped.

For Assistant tasks and meetings, read `lab context tasks` and
`lab context meetings` before editing their source documents. Only an explicitly
linked content tab owns an Assistant task's checklist; inheriting a navigation
tab does not create checklist requirements for a subtask. Follow client rules
for ownership, research and writing.

When `LAB_DOCUMENT_CONTEXT` is set, read that JSON file for the current absolute
Markdown path and tab ID before working on an Assistant document. This context
does not authorize edits. Preserve sibling documents and tabs. If present,
`LAB_ASSISTANT_HOME` selects the owning Assistant database.

## Documents and foldable supporting material

Lab reads Markdown documents and supports HTML disclosures:

```markdown
<details><summary>Supporting calculation</summary>

An explanation, code, a table, an image or a note goes here.

</details>
```

Keep blank lines around the inner Markdown. Closed disclosures, including
their labels, are excluded from Google Docs copy. Open disclosures are copied
as ordinary content. Use this for supporting material the user wants folded.
See `lab context markdown` for examples and other document behavior.

## Run notebooks live

When notebook work should appear live in Lab, use Lab's executor so the cell
appears as execution starts and its timer and outputs stream to open views:

```bash
lab notebook exec workspaces/<id>/notebooks/<name>.ipynb --code 'print(1+1)'
lab notebook exec workspaces/<id>/notebooks/<name>.ipynb --cell-id <id> --file /tmp/cell.py
```

The kernel is pinned to the notebook path, so consecutive cells share state.
Direct kernel execution bypasses the live UI. Read `lab context notebooks`
for constraints, interruption and execution details.

## Expose local applications

Configure workspace server tabs and proxies in `servers.json`, with `make`
commands for their lifecycle. Do not add proxy declarations to `workspace.json`.
Read `lab context servers` for the supported format.

In a framework source checkout, resolve the running Lab URL with
`scripts/lab-url.sh`. Its configured port may differ between installations and
from the default. The active vault records the running port at
`.lab/state/server.port`; do not hardcode a localhost port in tooling or links.

## Migrate existing data

Read `lab migrations` or `lab context migrations` before migrating. Individual
guides include `assistant-document-tasks`, `assistant-documents`,
`assistant-subtabs`, `assistant-records-v2`, `workspace-agent-context` and
`vault-workspace-names`, for example:

```bash
lab migrations assistant-records-v2
```

These commands print documentation only. Inspect the current format and local
instructions, preserve IDs, content and references, and migrate only within
the user's authorized scope. `lab agents sync` is a read-only compatibility
check. `lab agents detach --dry-run` previews removal of recognized legacy
integration links without altering their targets; see the migration guide
before applying it.

## Keep Lab documentation current

ALWAYS update this user guide with every Lab change the user requests,
including changes to operational guidance. Update `docs/CHANGELOG.md` and any
relevant topic in the same change; documentation is required work. Explain the
resulting behavior and how to use it, including migration or compatibility implications
when applicable. Record dated changes without claiming an exhaustive history
for versions that predate the changelog.

The source checkout's `docs/USER-GUIDE.md` and `docs/CHANGELOG.md` are canonical.
Package builds include those exact documents; do not maintain separate manual
copies for installed clients. Keep domain-specific instructions in their
owning vault or workspace.
