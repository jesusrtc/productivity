# Memory index

- [Workspace creation needs only a name](workspace-creation-needs-only-name.md) — single name field in the selected vault; automatic folder IDs; picker clicks survive replacing menu contents

- [Terminal multi-selection](terminal-multi-selection.md) — Cmd/Ctrl-click toggles tabs; secondary-click groups, associates, unlinks, or closes the captured selection

- [Workspace tabs stay in place](workspace-tabs-stay-in-place.md) — activation and polling preserve saved positions; only drag-and-drop reorders, with absolute paths identifying tabs across vaults

- [Assistant terminals retain their scope ID](assistant-terminal-scope-keeps-reserved-id.md) — register the Assistant pseudo-vault before active-root fallback; explicit cwd must not turn it into a basename vault

- [Markdown fence highlighting](markdown-fence-highlighting.md) — shared rendering colors supported language fences, including SQL in disclosures; copy preserves exact source

- [Markdown fences and code copy](markdown-fences-and-code-copy.md) — disclosures parse fenced SQL without blank-line requirements; every code block has an upper-right copy action preserving source whitespace

- [Terminal hover stays left](terminal-hover-left-latest-request.md) — prepend earlier requests until 50 characters; colored project → worktree → file headers; never cover the terminal

- [Workspaces own their agent context](workspaces-own-agent-context.md) — inject packaged Lab capabilities at launch; no workspace instruction seeding or symlinks; preserve provider and workspace rules

- [Markdown copy respects disclosure state](markdown-copy-respects-disclosures.md) — native details/summary folds; copy excludes closed blocks and flattens open blocks from the live view for every clipboard format

- [Terminal labels follow rail width](terminal-tabs-resize-labels-automatically.md) — drag the tabs/console separator between compact icons and full labels; persist width and adapt labels automatically

- [Keep client-specific work out of Lab](framework-keeps-client-domain-out.md) — framework code, defaults, skills, docs, and examples stay general-purpose; notebooks require a configured local runtime.

- [Markdown Mermaid rendering](markdown-mermaid-rendering.md) — file views render fenced Mermaid after mounting; marked alone only emits source

- [Lab UI runs as installed Chrome PWA](lab-ui-runs-as-installed-chrome-pwa.md) — same-origin `window.open` is frameless (no URL bar); prefer cross-origin/direct URLs for pop-outs
- [Cover letters: no weaknesses](feedback-cover-letter-no-weaknesses.md) — in CV workspace, keep gaps in fit.md only; close on strengths, never name missing skills
- [Console communication: be plain](console-communication-be-plain.md) — plain, short, jargon-free console messages; user dislikes dense technical recaps
- [Push changes to main by default](push-changes-to-main-by-default.md) — completed Lab work goes to `origin/main` unless the user explicitly requests otherwise
- [Terminal latency invariants](terminal-latency-invariants.md) — term.py endpoints stay sync `def`; UI libs vendored (no CDN); WebGL on active terminal only
- [Index route stays async for latency](index-route-async-for-latency.md) — cached `/` must avoid the sync worker pool so tmux polling cannot delay page loads
- [Lab proxy injects base href](lab-proxy-injects-base-href.md) — static sites viewed via `/api/proxy/...` need `<base target="_self">` in every page or subdirectory links/assets break
- [Remotion: render-only, no Studio](remotion-render-only-no-studio.md) — user removed Remotion Studio (2026-06-10); videos are reviewed by rendering mp4/stills to `out/`, don't reintroduce the Studio or proxy hacks
- [ElevenLabs expressive settings gotcha](elevenlabs-expressive-settings-gotcha.md) — don't force stability/style on designed/cloned voices; check sidecar pacing (words >1s, gaps >0.8s) before building beats
- [Claude memory uses repo path](claude-memory-auto-directory.md) — prefer `autoMemoryDirectory` in ignored `.claude/settings.local.json`; keep `~/.claude/projects/.../memory` symlink only as fallback
- [Lab framework CLI layout](lab-framework-core-cli-layout.md) — keep the installable `lab` CLI as its own package under `core/cli/`; reserve framework `apps/` for vault/client apps, not core internals
- [Core tests: unset LAB_VAULT](core-tests-unset-lab-vault.md) — a shell-exported `LAB_VAULT` overrides test fixtures' `LAB_ROOT`; run `env -u LAB_VAULT .venv/bin/python -m pytest`; the watcher debounce test flakes under load
- [Vault workspaces use the Makefile dev-server standard](workspace-servers-make-standard.md) — `make server-start`/`server-stop` + `SERVER_PORT` (+ `/healthz` where ours); port map so far; `remotion-manim` has no server on purpose; Vite needs `server.host: "127.0.0.1"` or the default IPv4 health check fails
- [Terminal wheel scrolling routes to the app](lab-terminal-wheel-scroll-routing.md) — WheelUpPane must pass through when `mouse_any_flag` (claude scrolls its own transcript); copy-mode `-e` line-scroll otherwise; never arrow keys, never unconditional copy-mode
- [Terminal WS half-open after tmux attach dies](terminal-ws-half-open-after-tmux-attach-dies.md) — server doesn't close the WS on PTY EOF; frontend's 8s poll + auto-restore covers it (detection lag ≤8s)
- [Sidebar file rows have five render sites](sidebar-file-rows-have-five-render-sites.md) — icons/decorations must be applied at all five (workspace sidebar, meta rows, shared tree, self view, repo-tab tree); git-status containment = vault ∪ registered repos ∪ framework root
- [Notebook paths use the active vault root](notebook-paths-use-active-vault-root.md) — keep framework/self-view and active-vault roots separate; notebook APIs only accept vault-relative paths, and cached shells must vary by vault root
- [Headless UI check misses launch-agent server](check-ui-launch-agent-process-detection.md) — `scripts/check-ui.sh`'s relative Python `pgrep` pattern does not match the Homebrew-Python launch-agent command; it may try to start a duplicate server
- [Lab navigation is cross-vault](lab-navigation-cross-vault.md) — Home is the permanent framework home; vault/workspace tabs carry vault identity and must not change the globally active vault
- [Terminal tmux names hide vault identity](terminal-tmux-names-hide-vault.md) — current names are `neurona-<workspace>-<tab>-<hash6>`; ownership stays in hash/runtime metadata and old names remain discoverable
- [Terminal tab dividers are browser-local](terminal-tab-groups-are-browser-local.md) — draggable colored lines are locally persisted navigation chrome scoped to each terminal surface
- [Terminal bar settings and context actions](terminal-bar-settings-and-context-actions.md) — one settings modal, New after the tabs, context-menu groups/dividers/close, and confirmed Kill all in a Danger zone
- [Terminal drag previews before drop](terminal-drag-previews-before-drop.md) — visible insertion space and group highlight before release; hover never persists a move, and cancel restores the rail
- [Terminal New menu options are workspace-scoped](terminal-new-menu-options-are-workspace-scoped.md) — settings checkboxes narrow the New menu per vault/workspace, including plain Terminal and Attach
- [Terminal tabs avoid stale provider titles](terminal-tabs-use-agent-session-names.md) — manual labels win; provider titles yield to the logical name once a conversation has follow-ups
- [Terminal session metadata stays off the global poll](terminal-session-metadata-hot-path.md) — unscoped/attach scans skip agent details; Codex cache coverage includes unresolved TTYs
- [Terminal context uses bounded scrollable request history](terminal-task-summary-is-multiline.md) — show three two-line requests in the header or five in hover, with full history available by scrolling
- [Terminal sessions prefer real recaps over request history](terminal-session-requests-and-copilot-objective.md) — prefer current provider recaps; otherwise show post-clear requests and detect empty Codex `/clear` threads
- [Workspace names are display aliases](workspace-names-are-display-aliases.md) — keep `workspace.json.id` and the directory stable; render/edit `workspace.json.name` as the human-facing tab label
- [Server config is agent-authored](server-config-is-agent-authored.md) — create a plain `servers.json` template and let agents fill it; do not infer server entries from Makefiles
- [Focus mode and Keep Alive](focus-mode-is-presentation-mode.md) — Focus requests fullscreen plus a wake lock; the adjacent persistent Keep Alive switch can own the wake lock independently
- [Focus mode keeps navigation tabs](focus-mode-keeps-navigation-tabs.md) — Home and open vault/workspace tabs remain visible above the Overview strip in Focus mode
- [Lid Awake is a timed system control](lid-awake-is-a-timed-system-control.md) — admin-only macOS pmset timer survives page/server closure and safely resets normal sleep on cancel or expiry
- [Focus mode trackpad pinch zoom](focus-mode-trackpad-pinch-zoom.md) — reproduce Chrome's suppressed fullscreen pinch gesture with Focus-only CSS zoom, including same-origin iframes
- [Sidebar tree indentation must recurse](sidebar-tree-indentation-recurses.md) — indent nested `.sidebar-folder-children` containers; never hard-code selectors for a finite number of depths
- [Sidebar shortcuts preserve the file tree](sidebar-shortcuts-preserve-file-tree.md) — pinned/recent sections duplicate file shortcuts; shared browser-local settings control hidden files, freshness, and extension filters
- [Sidebar file scopes can follow worktrees](sidebar-worktree-file-scopes.md) — a browser-local parent folder discovers direct child worktrees; each sidebar surface remembers its selected root and color
- [Sidebar workspace folders scope the complete file view](sidebar-workspace-folder-scopes.md) — colored Root/workspace buttons switch Files and Recently updated together; every workspace folder may own a worktree parent
- [Sidebar file settings are workspace-scoped](sidebar-file-settings-are-workspace-scoped.md) — browser-local hidden/recent/folder/worktree preferences are keyed by active workspace path; never share one config across workspaces or vaults
- [Recent files use a compact folder tree](sidebar-recent-files-use-compact-tree.md) — collapse single-child directory chains, preserve real branch levels, and persist folder open state
- [Recent files use one quick-selector scope](sidebar-recent-quick-selectors.md) — one active mtime/Git scope, active-click clears to None, and File view settings live in the Overview cog
- [Sidebar file history uses one three-pane modal](sidebar-file-history-review.md) — repository and file history share files-left/diff-center/revisions-right; file history orders the clicked path first and includes commit companions
- [Notebook review diff granularity](notebook-review-diff-granularity.md) — source changes are line-level red/green; changed outputs use one whole-block red/green rail
- [Recent-file diagnostics and consolidated log controls](sidebar-recent-diagnostics-and-log-controls.md) — settings Save logs per-README inclusion reasons; Admin Logs can copy or flush the selected consolidated log
- [Nested repository sidebar scans and new-file history](nested-repo-sidebar-scan-and-unborn-history.md) — reset bounded scan depth at nested Git roots; history/diff supports untracked files before the first commit
- [Workspace mtime polling is single-flight](workspace-mtime-polling-is-single-flight.md) — never overlap recursive mtime walks; back off exponentially after HTTP failures to prevent 503 storms
- [Sidebar sections have horizontal dividers](sidebar-sections-have-dividers.md) — separate top-level Recently updated, Servers, Files, Pinned, and Meta sections visually
- [Terminal recent activity is selection-local](terminal-recent-tab-activity.md) — mark tabs when selected or left; persist the scope, preset window, and user-selected marker color in browser storage
- [Backend Python changes require a server restart](backend-python-changes-require-server-restart.md) — static assets update from disk, but the always-on process keeps imported routes until `make restart`
- [Client server port comes from .env](client-server-port-config.md) — `make run/start` uses checkout-local `.env`, then vault `lab.toml`; ambient inherited `LAB_PORT` must not override the next start
- [Assistant tasks are client-global Markdown](assistant-task-database-is-client-global.md) — one `LAB_ASSISTANT_HOME` per Lab client, outside framework/vaults; Lab renders it and Assistant terminals manage Markdown through `lab assistant`
- [Assistant progressive disclosure and meetings](assistant-progressive-disclosure-and-meetings.md) — compact rows expand on click, full documents open on double-click, subtasks gate completion, and meeting notes are first-class
- [Assistant workspace artifacts and copy-ready content](assistant-workspace-artifacts-and-copy-content.md) — map exact Lab workspaces without direct navigation; preview workspace-owned images and copy prepared communications manually
- [Assistant uses the selected Compact design](assistant-workspace-first-document-modal.md) — one Tasks tab, compact original workspace groups and cards, and click-to-open modal; proposal comparison is complete
- [Framework updates restart in place](framework-update-restarts-in-place.md) — admin update pulls `origin/main` serially, exec-restarts, and reloads only after a new boot ID
- [Notebook runtimes preserve venv Python paths](notebook-runtime-preserve-venv-python-path.md) — make interpreter paths absolute without resolving venv symlinks, or kernels lose the venv's ipykernel and client packages
- [Quiet Jupyter polls are not execution timeouts](notebook-kernel-quiet-polls-are-not-timeouts.md) — `get_iopub_msg` may be empty for many one-second polls while client CLIs run; enforce only the overall monotonic deadline
- [Repository notebooks render read-only](repository-notebooks-render-read-only.md) — Home/framework/repository `.ipynb` files are inspectable through `/api/notebook`; only active-vault notebooks get kernel controls
- [Repository notebooks own their kernel by path](repository-notebooks-own-kernel-by-path.md) — create valid `.ipynb` files at a user-selected active-vault repository path; same path shares one human/agent kernel, different paths get different sessions
- [Built-in Jupyter tab needs no server config](built-in-jupyter-tab-needs-no-server-config.md) — every workspace gets a first-class Jupyter tab backed by Lab's shared notebook runtime; never self-proxy Lab's port through `servers.json`
- [Live notebook agent/human contract](live-notebook-agent-human-contract.md) — agent cell edits and Jupyter outputs are visible live; humans share the kernel and can edit, rerun, and interrupt
- [Notebook reruns hide stale output before scrolling](notebook-reruns-hide-stale-output-before-scrolling.md) — on idle→running, hide the prior rich output immediately and focus the code/header; centering a tall stale chart makes live execution look already finished
- [Notebook hide-code uses fixed pin slots](notebook-hide-code-pin-slots.md) — pinned and running code stays visible; pins are fixed slots plus one accordion-style transient cell
- [Notebook reading position uses stable cell IDs](notebook-reading-position-navigation.md) — restore large notebooks to the last-read stable cell, with vault-scoped storage, index fallback, running-cell priority, and floating Start/End controls
- [Notebook actions use the docked navigation toolbar](notebook-actions-use-fixed-toolbar.md) — use immediate custom labels and visible pressed states for icons in the full-width, always-visible top toolbar; leave All notebooks in the header
- [Notebook tabs follow their owning vault](notebook-tabs-follow-owning-vault.md) — cross-vault notebook paths, APIs, replay state, events, and deep links must use the workspace tab's vault identity
- [Live notebook streaming requires Lab's executor](live-notebook-streaming-requires-lab-executor.md) — raw Jupyter execution bypasses actor/timer/output events; agents must use `lab notebook exec`
- [Local notebook CLI uses a bearer capability](local-notebook-cli-auth.md) — owner-only token, loopback `/api/nb` scope, and normal vault resolution; never add header-only cookie bypasses
- [Client issues can use diagnostic scripts](client-issue-diagnostic-scripts.md) — for issues occurring in the user's client environment, provide a focused script they can run there and bring back its output for evidence-based diagnosis
- [Lab terminals use bounded rolling tmux sockets](lab-terminal-rolling-tmux-sockets.md) — active + at most one drain; exact socket affinity for old sessions; no background watcher or PTY byte-path discovery
- [Existing tmux attachment uses a grouped alias](lab-terminal-attach-uses-grouped-alias.md) — + New imports by session name without nesting; closing the Lab alias leaves the original session running
- [Terminal attach picker groups live sessions](terminal-attach-picker-groups-sessions.md) — modal groups by workspace/client state, pins current-workspace unattached sessions first, and captures the target scope
- [Linked file terminals separate links from sync](linked-file-terminals-separate-links-from-sync.md) — secondary-click creates durable file/session links; the browser-local Sync linked switch alone controls bidirectional navigation
- [Files section exposes file creation](files-section-exposes-create-action.md) — every Files header has a visible ＋ File action at its current root; secondary-click still creates within specific folders
- [Sidebar sections sort independently](sidebar-section-sort-modes-are-independent.md) — Recently updated and Files persist separate Updated/Name/Type sort modes; keep folders first and make narrow controls readable

- [Vault → Workspace → Terminal](vault-workspace-terminal-naming.md) — consistent entity names throughout UI, CLI, APIs, code, configuration, and docs; old names only at compatibility boundaries.

- [Vaults are sections inside Home](vaults-are-home-sections.md) — vault navigation stays beneath Home alongside Overview and Admin; only workspaces open separate tabs

- [Home shares one terminal area](home-shares-one-terminal-area.md) — Overview, Admin, and all vault sections use the existing Home terminal scope, selection, connection, and settings

- [Closing workspace tabs preserves resources](workspace-close-preserves-resources.md) — close is navigation only; vault rows show live terminals, servers, and notebook kernels, independent of open tabs

- [Terminal metadata closes SQLite connections](terminal-metadata-closes-sqlite-connections.md) — use `contextlib.closing`; SQLite transaction contexts leave handles open and can exhaust the server's descriptor limit

- [Terminal polling preserves unchanged DOM](terminal-polling-preserves-dom.md) — skip unchanged tab/header DOM replacement while preserving updates and focus

- [Terminal connect filesystem work stays off the event loop](terminal-connect-filesystem-off-event-loop.md) — authentication/discovery/access checks run in a worker; local authenticated echo benchmark covers polling load

- [Terminal latency needs a browser frame baseline](terminal-browser-latency-baseline.md) — browser input-to-render probe includes an empty-page frame control; endpoint budgets exclude test-only index rebuilds

- [Terminal project/worktree links](terminal-project-worktree-links.md) — new terminals inherit the selected folder and cwd; file links cascade, unlink preserves scope, and colors coexist with recent highlights

- [Meta is agent context, not skills](meta-is-agent-context-not-skills.md) — show the launch guide and local instructions; keep workspace skills and settings in Files

- [Terminal tabs show project names](terminal-tabs-show-project-names.md) — default linked labels use the project; worktree/file details appear at the top of hover cards on tabs and the header

- [Terminal drag links](terminal-drag-links.md) — drag tabs onto files/folders/worktrees; one-to-one file ownership, shared folder ownership, independent context-menu unlink

- [Terminal startup and disposal](terminal-startup-and-disposal.md) — dispatch views after state initialization; guard xterm 5.3 viewport callbacks when disposing terminals

- [Logs is a Home section](logs-are-a-home-section.md) — before Admin, with a full-page source selector and live, copy, and clear controls

- [Home terminal section associations](home-terminal-section-associations.md) — Logs keeps the terminal visible; Home/vault/Logs labels select each section's latest terminal from the shared pool

- [Workspace new-tab button](workspace-new-tab-button.md) — small + beside the tabs; picker selects a vault and creates or opens a workspace in that vault

- [Terminal tabs use folder badges](terminal-tabs-use-folder-badges.md) — replace provider text and vertical bars with colored Home/Logs or folder-alias badges and explicit worktree indicators

- [Scoped proxy compatibility](scoped-proxy-compatibility.md) — scoped Referer rewriting, auth parsing, legacy aliases, and matching Vite/React Router base paths

- [Terminal tabs activate Home sections](terminal-tabs-activate-home-sections.md) — terminal clicks navigate to Overview/vault/Logs, preserve the exact warm session, and ignore stale navigation callbacks

- [Worktree tabs use scope names](terminal-worktree-tabs-use-scope-name.md) — agent icon plus folder alias/worktree name, no session name or generic worktree badge
