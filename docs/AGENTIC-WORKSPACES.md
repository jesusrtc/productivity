# Agentic workspaces

An agentic workspace has one conversation and one coordinator, with up to five
task executors. Lab owns missions, task hierarchy, dependencies, priorities,
execution history, schedules, reminders and memory. Models are accessed only
through the user's installed Codex CLI, GitHub Copilot CLI or Claude Code.
There is no model API client or additional orchestration cloud service. The
installed CLIs still use their normal provider accounts and network connections.

## Create and operate

Create a workspace with type **Agentic**, or `lab workspace new demo --kind
agentic`. Open its Missions view and describe the desired result in the chat.
The coordinator returns a brief acknowledgement/plan and validated actions;
executors handle the longer work. Sending another message remains available
while workers run. User messages take precedence over pending automatic events.
Before each planning invocation, the launcher executes the fixed local
`lab context llm` read and includes its full output. The coordinator consumes
that context and returns a plan without tool calls; executors perform further
inspection and execution under their provider's permissions.

The center has mission selection, task hierarchy/outcomes, Schedules and Settings.
Click a task to inspect **Result**, **Assignment**, **Activity** and **Files &
sources**. The exact prompt/context/launch command remains attached to each run,
even if the task assignment later changes. Earlier activity is paginated. The
coordinator has its own inspection control. User-facing reports summarize
decisions; private provider reasoning is not a required audit artifact.

Pause requests stop the owned CLI and retain the task. Resume/retry create new
runs with previous evidence and checkpoints; they do not resume a frozen model
conversation. Agents must inspect existing effects before repeating work. Stop
cancels the task. Group tasks roll up their children; dependencies require
completed tasks, so **Review** holds follow-up work until approval. Viewing a
preview, dismissing a notification or a worker claiming approval cannot release
that gate. Chat approval is tied to the current user message and preview run.

## Providers and permissions

| Provider | Local invocation | Permission behavior |
| --- | --- | --- |
| Codex CLI | `codex exec --json --approve-for-me` | Installed automatic approval review and workspace sandbox |
| Claude Code | `claude -p --output-format stream-json --verbose --permission-mode auto` | Installed automatic permission review |
| Copilot CLI | `copilot --acp` over local stdio | Native requests displayed in the task; one-time allow/reject decisions |

Install and authenticate the provider normally before selecting it. Lab supplies
its normal launch context without changing provider homes or user instructions.
Supported flag/protocol versions are required; startup/login errors are retained
in Activity. Copilot uses ACP version 1. No direct model SDK, API key configuration,
`--allow-all` or sandbox-bypass launch flag is introduced.

Settings inherit Lab's effective workspace/global provider and model. Overrides
affect subsequent coordinator/executor invocations; existing runs keep their
provider and recorded context. The shared conversation, missions, memory and
artifacts survive a switch. Provider-native hidden subagents are prohibited by
the task contract; Copilot's task-delegation tool is also excluded.

An executor awaiting a Copilot permission keeps its process and exact pending
request while releasing idle capacity. Allowing a request reacquires a slot
atomically. Previously allowed tools still executing retain their slot. The
coordinator cannot grant tool permissions on the user's behalf. OAuth/access
questions should identify the account and actionable login command/link; never
ask users to paste credentials into chat.

## Notebook and evidence contract

Executors use `lab notebook exec` with the configured runtime. Do not invoke a
private Jupyter kernel, nbclient or nbconvert for execution. The notebook path
owns kernel state across cells. Lab writes pending metadata and checkpoints
outputs while the cell runs; task previews refresh that evidence using the
native notebook renderer. Missing runtimes are actionable blockers, not an
instruction to install dependencies without authorization.

An executor's final JSON `assets` array registers files and URLs automatically.
Use roles `input`, `support`, `source` or `output`, and origin `user`, `consulted`
or `agent`. File targets must exist inside the workspace. Lab records run identity,
size and a content hash for files up to 20 MB. Previews show the current file;
the recorded hash describes the registered version. HTML/SVG downloads do not
execute under Lab's origin. Ordinary external links open separately.

To make an existing notebook visible before a long execution, use `asset-add`
through `lab mission apply`. `lab agents files record` is a separate attribution
record for files actually changed; do not register read-only inputs as edits.
Changed/deleted/renamed file history remains attached to its run. Native file
previews, reports, CSV data, source links and notebooks remain inspectable.
Managed-run CLI mutations are limited to attaching evidence to that run's task
and saving its checkpoint; they cannot impersonate a user, approve previews or
change workspace settings. This is an application boundary, not OS isolation
from a local process with the same filesystem access as the user.

## Persistence, context and recovery

Workspace-owned state lives in `.lab/agentic/state.sqlite3` with transactional
admission and an append-only event journal. `.lab/agentic/runs/<id>/` retains the
exact prompt, runner log and provider output. Back up the workspace with normal
local backup practices. SQLite state must be copied consistently, including WAL
state when applicable. Do not hand-edit these files.

Prompts contain scoped instruction references/content, a skill catalog, relevant
mission memory and task inputs. Older summaries are bounded; full records remain
available through `lab mission ls` and `lab mission task ID`. Truncated owning
instruction files must still be read in full. Lab does not rewrite or symlink
workspace AGENTS.md, CLAUDE.md, skills or memory files to install this feature.
Durable `memory-set` records are visible in Settings and include their scope.

The supervisor runs in the local Lab backend every two seconds. One coordinator
and at most five executing task processes are admitted per workspace; idle tool
permission waits do not count as executing. Reservation, PID/start-time identity,
child launch gate and per-run lock prevent duplicate launches. Reconciliation
does not interpret unavailable process observations as termination. A lost runner's
proven child is stopped before releasing its capacity. Uncertain task failures
remain inspectable and require explicit retry.

Running work is independent of the browser. The computer and local server must
be awake for new work and schedule checks. After downtime, missed checks coalesce
to one occurrence rather than a burst. The same scheduled task reopens while old
runs/results remain in history. Pause/resume schedules in their own view; a
verified stop condition disables recurrence. Five-field numeric cron supports
lists, ranges and steps with an explicit timezone; intervals have a 60-second
minimum. Unchanged fingerprints suppress repeated outcome notifications.

Blocked/review reminders default to two hours. Snooze changes the next reminder
without approving or resuming the task. Alerts appear in the workspace and the
shared notification center, including while another workspace is selected.
Acknowledgements target the displayed alert only. The next reminder has a new
identity. Existing terminal notification behavior remains separate.

Disable admission and stop active runs before moving/deleting or changing the
kind/status of a workspace. Active runners hold the same workspace operation
lease used for notebook writes. Terminal/work status reporting in managed runs
uses the run identity and does not complete the task; only a validated final
result can do that.

## CLI and API

```bash
lab mission --workspace demo ls
lab mission --workspace demo say 'Investigate this increase' --request-id request-123
lab mission --workspace demo task task-id
lab mission --workspace demo apply --file /absolute/actions.json
lab mission --workspace demo settings --file /absolute/settings.json
lab mission --workspace demo checkpoint --run-id RUN_ID --file /absolute/checkpoint.txt
lab api routes --search agentic
lab context agentic
```

Reuse a message request ID after a timeout; a changed payload requires a new ID.
`apply` accepts an atomic array of mission/task/schedule/memory/asset actions.
UI and CLI use the same store and validation. APIs require administrator access
and validate the owning vault and agentic workspace. Permission responses allow
only an offered, one-time choice. Task approvals and notification reviews are
different operations.

## Verification

`core/tests/test_agentic.py` covers concurrent admission, gates, reminders,
recurrence, context/history, CLI reporting, permission waits, API ownership and
process recovery. `core/tests/test_agentic_browser.py` exercises the actual UI
module in Chrome. Existing workspace/notification/agent-history regressions also
cover compatibility with ordinary Lab workspaces.

Opt-in scripts use installed authenticated CLIs and isolated temporary vaults;
they install nothing and do not select or modify the user's active vault:

```bash
core/.venv/bin/python scripts/check-agentic-cli.py --provider codex --provider claude --provider copilot
core/.venv/bin/python scripts/check-agentic-workflow.py --provider codex --keep-server
core/.venv/bin/python scripts/check-agentic-workflow.py --resume /absolute/verification.json
```

The workflow script sends a mission, verifies actual two-cell shared-state
Jupyter execution, observes pending metadata, inspects CSV/notebook/report assets
and checks that review remains pending. Inspect one-time provider permissions
before allowing test operations. A timeout preserves evidence; `--resume` only
observes the existing run and never launches duplicate work. `--keep-server`
retains that isolated instance for UI verification and requires later cleanup.

### Verified on October 22, 2026

- Real installed CLIs: Codex 0.163.0, Copilot 1.0.102 and Claude Code 2.1.307.
  Each completed a delegated CSV → two-cell notebook → report workflow. The
  report stayed in Review; the shared kernel produced the expected 200% result.
- Codex and Copilot executions were observed live. Claude's persisted original
  execution was verified, and its existing second cell was rerun through Lab to
  verify live pending/output behavior. Copilot's notebook also streamed in the
  native task modal while the chat remained available.
- Copilot one-time permissions, pause/resume and backend restart reconciliation
  were exercised. All three coordinators subsequently answered a state-only
  follow-up with the complete preloaded Lab context.
- Chrome interactions covered coordinator inspection, provider choices, file
  navigation and notification → mission → task navigation without approving the
  review gate. Automated core/browser/compatibility and CLI suites passed.

External video, channel OAuth and ElevenLabs accounts were not exercised. Those
workflows use the workspace's existing skills and authorized service access.

## Acceptance contract

- Create an agentic workspace in the UI and CLI; retain ordinary workspaces.
- Inherit the existing workspace/global agent and model settings, show the
  effective provider and allow changing it without losing Lab history.
- Accept a request in the workspace chat, confirm understanding with a brief
  plan, ask necessary questions and delegate clear independent work promptly.
- Derive missions, tasks and subtasks; keep subsequent related requests in
  their mission. Preserve explicit approval gates such as preview before translation.
- Keep the chat responsive while workers run. Persist and prioritize incoming
  user messages ahead of automatic coordinator work.
- Enforce five concurrent task executors per workspace, plus one coordinator.
  Respect dependencies and priorities; support pause, resume, stop and retry.
- Present missions and all tasks in the center. A task opens a modal with
  results, exact immutable assignments/context, run history, tool activity,
  errors, checkpoints, files and source links. Keep the main chat accessible.
- Link inputs, supporting notebooks and sources to outcomes. Preview assets
  using Lab viewers; execute notebooks through `lab notebook exec`, with real
  Jupyter execution and live Lab events.
- Keep scoped user instructions and skills intact. Store durable workspace
  memory and mission context; hand each executor bounded relevant context.
- Persist interval and cron schedules locally. Avoid overlapping checks and
  duplicate notifications. Support stop conditions and blocked-task reminders
  (two hours by default), acknowledgement and snooze.
- Continue with the browser closed. After server restart or computer wake,
  inspect exact running processes before recovering; never replay work merely
  because observation timed out. Coalesce missed schedule ticks.
- Surface missing authentication/permissions as actionable task blockers while
  unrelated tasks continue. Do not weaken provider permissions or store secrets
  in prompts, memory or rendered logs.
- Verify the same workflow with the three real installed CLIs, meaningful
  persistence/concurrency/failure tests, native UI interaction, and a real
  notebook analysis with accessible evidence. Record gaps honestly.

## Design references

Only documentation was consulted; no external agent code was downloaded or
executed. The implementation is native to Lab.

- [OpenClaw automations](https://docs.openclaw.ai/automation/cron-jobs): durable
  scheduling separate from agent invocations.
- [OpenClaw subagents](https://docs.openclaw.ai/subagents): independent background
  runs, parent notification and inspectable transcripts.
- [Claude Code programmatic execution](https://code.claude.com/docs/en/headless).
- [Copilot CLI automation](https://docs.github.com/en/copilot/how-tos/copilot-cli/automate-copilot-cli/automate-with-actions).

The installed CLI help is authoritative for the commands used in local tests.
