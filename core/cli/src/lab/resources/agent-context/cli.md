# Lab CLI and UI parity

Use `lab` for managed state and user interface actions. Existing domain commands
remain available: workspace, vault, Objective, Assistant, tasks, config,
notebooks, agents, apps, links, refs, repositories and terminals.

Every public Lab HTTP endpoint is discoverable and callable through `lab api`.
This uses the same server handlers, validation, permissions and revision checks
as the UI. New endpoints appear automatically; agents do not need to hand-edit
managed JSON or duplicate UI business rules.

```bash
lab api routes
lab api routes --search terminal
lab api describe PATCH /api/term/sessions/metadata
lab api call GET /api/objectives --query workspace_id=demo --query vault=my-vault
lab api call PATCH /api/term/sessions/metadata --body-file /tmp/rename.json
```

Use `--json` for a small JSON request, or `--body-file PATH` (`-` for stdin).
Repeat `--query KEY=VALUE` for query parameters. `--output PATH` saves a response,
including binary downloads. `lab api routes --json` includes request schemas;
`describe` prints one operation and its referenced model definitions. Use the
actual owning vault/workspace/resource IDs from a read. Preserve `expected`
revision fields where the corresponding UI operation uses them. Do not retry
destructive or non-idempotent mutations blindly.

The server URL is discovered from the running port. `LAB_URL` can override it
with a local Lab origin. API access uses the owner-readable CLI credential
created by Lab, on loopback only, with an explicit owner scope. It does not
depend on a browser login password or print credentials.

## Operate an open Lab view

Client-only navigation, menus, expansion, tab layout, editing and drag/drop are
available through `lab ui`. Open/reload Lab first, then:

```bash
lab ui clients
lab ui --client VIEW_ID inspect
lab workspace open demo --vault my-vault --client VIEW_ID
lab ui --client VIEW_ID rename-tab TERMINAL_NAME 'Review'
```

With exactly one connected admin view, `--client` can be omitted. With multiple
views, select one explicitly; commands are never broadcast. `LAB_UI_CLIENT`
can hold that selection. A reconnect/reload changes the view ID; rediscover it.

`inspect` returns context, open dialogs, visible controls, labels, values and
unique selectors. Password values are excluded. Controls inside the active
modal are listed while it is open. `--offset` and `--limit` page large views.
Read the result and operate the returned selector through its existing handlers:

```bash
lab ui --client VIEW_ID contextmenu 'SELECTOR_FROM_INSPECT'
lab ui --client VIEW_ID inspect
lab ui --client VIEW_ID click 'EDIT_MENU_SELECTOR'
lab ui --client VIEW_ID fill 'URL_FIELD_SELECTOR' 'https://example.com/new'
lab ui --client VIEW_ID click 'SAVE_BUTTON_SELECTOR'
lab ui --client VIEW_ID wait '[data-link-details-status]' --text Saved
lab ui --client VIEW_ID key Escape
lab ui --client VIEW_ID drag 'TASK_OR_ASSET_SELECTOR' 'DESTINATION_SELECTOR'
```

Selectors are view-specific and can disappear after a render. Inspect again
instead of guessing if a selector is absent or ambiguous. Disabled controls
remain disabled. `click --modifier meta` offers Command-click semantics.
`hover`, `scroll`, `key --modifier meta`, and `wait --absent` cover further
interaction. A command acknowledges dispatch; use `wait` and an API read to
verify asynchronous saves and destructive operations. A timed-out action may
have run; inspect its result before retrying.

Browser-native prompts/confirmations are canceled and returned as
`native_dialogs` when unanswered, so they do not block the command channel.
Repeat the initiating action with `--prompt VALUE` or `--confirm yes|no` when
authorized. Answers apply only to that invocation. Custom Lab confirmation
modals retain their actual controls, including both task-deletion confirmations
and the exact task-name requirement. Browser/OS file pickers and permission
prompts are outside the DOM; use the underlying API or local file commands for
their data operations. Browser popup and clipboard permissions still apply.

`lab ui command ACTION --json '{...}'` also supports:

| Action | Parameters |
| --- | --- |
| `workspace-open` | `workspace`, optional `vault` |
| `document-open` | `path`, optional `root` |
| `objective-select` | `objective` |
| `task-open` | `task`, optional `objective` |
| `terminal-select` | `name` |
| `terminal-rename` | `name`, `label` |
| `terminal-input` | `text`, optional `name`, explicit `submit: true` to send Enter |
| `inspect` | optional `offset`, `limit` |
| `click`, `contextmenu`, `hover` | `selector`, optional `modifiers`, `dialogs` |
| `fill` | `selector`, `value` |
| `key` | `key`, optional `selector`, `modifiers` |
| `drag` | `selector`, `target` |
| `pointer-drag` | `selector`, `x`, `y` pixel delta, for pane resizers |
| `scroll` | `selector`, `x`, `y` |
| `wait` | `selector`, optional `text`, `absent`, `ms` |

For terminal text, prefer `lab ui paste TEXT --terminal NAME` or
`lab ui paste --file PATH --terminal NAME`. Text is pasted through the existing
terminal connection; Enter is sent only when you explicitly add `--submit`.
