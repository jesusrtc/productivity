# Settings

Press **⌘,** on macOS or **Ctrl+,** elsewhere, including while typing in a terminal.
The topbar Settings button opens the same view. Use the left column to choose
**Global**, **Home**, **Assistant**, or a workspace; search filters workspaces.
Workspace names include their vault to distinguish matching names. Unavailable
vaults are reported without blocking other settings.

- **Global → General:** default agent, default model, theme and autopilot.
  Agent availability describes the computer running Lab, even when using a
  remote browser. An agent marked “Not installed” cannot be selected as the
  global default. An existing unavailable default stays visible until changed.
- **Global → Terminal appearance:** tab orientation and recent-tab indicator.
- **Global → Projects and worktrees:** editable projects and worktrees roots,
  plus custom project locations and per-project worktree folders.
- **Global → Document terminals:** explicit resume and idle cleanup for previous
  managed document conversations. Tasks now link to existing terminal sessions;
  opening a document never creates a process. These settings do not stop or
  sleep manually linked terminals. See [Task terminal links](document-terminals.md).
- **Workspace → Agent:** agent/model overrides or inheritance. The effective
  agent is shown. The expandable vault availability section controls which
  agents are allowed across that vault; it does not install an agent.
- **Workspace → Terminal sessions:** choices in **+ New**. These checkboxes
  control the menu, not the default agent. Stop sessions is available only for
  the active workspace and retains its confirmation.
- **Workspace → File sidebar:** hidden files, recent-file filters, sorting,
  extensions, folder shortcuts, worktree folders and colors.

Home and Assistant use the global agent and have their own terminal-menu and
file-sidebar preferences. Individual terminal tabs keep their existing context
menu for names, groups and closing sessions.

## Project and worktree folders

The projects folder defaults to `~/src`. **Workspace → File sidebar → Add
project** lists its direct child folders, including projects without Git, with
a search filter and a **Use a custom folder** option. Hidden folders and the
worktrees root are excluded. Adding a project attaches a Files shortcut; it does
not clone or move the project. Workspace selections remain browser-local.

The worktrees root defaults to `~/src/.worktrees`. Each project inherits a
parent named after its project directory, for example
`~/src/.worktrees/lab/new-feature-branch`. Edit both roots under **Global →
Projects and worktrees**. Leave a project's worktree field empty to follow the
shared default, or enter a custom parent folder for that project. Custom
locations saved in the workspace form also become available throughout Lab;
manage them in the global settings. Existing explicit workspace worktree paths
continue to take precedence. Changing settings never relocates existing files.

Paths refer to the computer running Lab. `~` expands to that computer's home
folder. Missing worktree parents simply have no choices yet; discovery shows
only worktrees belonging to the selected Git repository.

The CLI uses the same defaults:

```sh
lab config set --global projectsFolder '~/src'
lab config set --global worktreesFolder '~/src/.worktrees'
lab repo ls
lab workspace add my-workspace lab --branch new-feature-branch
lab workspace add my-workspace lab --project-path /code/lab --worktree-path /scratch/lab-feature --branch another-feature
```

New catalog projects need no MP prefix. Branch names containing `/` use `-` in
the destination folder name. `--worktree-path` selects the exact destination for
one worktree. Legacy vault `repositories/` projects retain their workspace-local
layout, and existing worktrees are not migrated.

The local terminal and file-sidebar settings buttons jump to the corresponding
section for that workspace. Saving another workspace's preferences does not
switch workspace or change the active sidebar. Save changes applies the form;
navigation or closing asks before discarding unsaved edits. Failed saves retain
edits for retry. Agent changes affect future sessions, not running processes.

## Storage and compatibility

Explicit Lab-wide choices are stored using the validated settings writer in
`$LAB_HOME/settings.json`, normally `~/.lab/settings.json`. Resolution is:
workspace override → explicit Lab-wide choice → legacy vault `.agents/config.json`
→ built-in default. A vault's supported-agent policy still limits ordinary
workspace launches. Browser appearance, terminal menu choices and sidebar
preferences keep their existing browser-local storage and scope keys.

No client document migration is needed. Upgrade/restart Lab and refresh the
browser. Existing preferences are read in place; opening settings never rewrites
legacy files. Saving a global field makes that choice apply across vaults and
Assistant; fields not changed retain compatible legacy fallbacks. Existing
workspace overrides are preserved. To inherit the new default in an overridden
workspace, choose **Inherit global default** in that workspace's Agent section.

CLI equivalent: `lab config set --global defaultAgent codex`. `lab config show`
and `lab config get` report effective settings. Without `--global`, `config set`
retains legacy vault behavior and warns when a Lab-wide choice overrides it.
The authenticated admin APIs are `GET/POST /api/settings/global`; existing
`/api/settings` remains the legacy vault endpoint. File/sidebar preferences
remain specific to the browser using Lab.
