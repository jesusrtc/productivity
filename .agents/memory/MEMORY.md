# Memory index

- [Terminal console layers stay below tabs](terminal-console-layers-stay-below-tabs.md) — isolate xterm's internal layers so expanded names, scrollbar and divider own clicks over the console.

- [Terminal request history survives clears](terminal-request-history-survives-clears.md) — expandable full submitted messages and session dividers, provider-authoritative capture, durable per-terminal history and scoped access.

- [Terminal names stay open after deliberate use](terminal-names-stay-open-after-deliberate-use.md) — click or configurable 3-second hover keeps names visible until a console click; short crossings collapse.

- [Copilot autopilot follows live identity](copilot-autopilot-live-status.md) — accepted `session.task_complete` enables green without a text reply; exact PID/foreground/ownership mapping follows conversation switches.

- [Whole Objectives pass reference context](whole-objectives-pass-reference-context.md) — drag the Objective title/header/library row into a console for all active registered references, tasks/subtasks and worktrees; preserve focus-slot moves.

- [Sidebar task status menu](sidebar-task-status-menu.md) — secondary-click Completed/Undo/In progress, green check/red-framed box/yellow dot, saved states; supersedes read-only task status.

- [Terminal hover owns the expanded area](terminal-hover-owns-expanded-area.md) — full-width hover containment, including right-edge and scrollbar clicks, with a stable compact layout slot.

- [Shell DOM changes need a backend restart](shell-dom-changes-need-backend-restart.md) — fresh assets can accompany old HTML; verify the served DOM after restarting the exact server.

- [Terminal tabs reveal on hover](terminal-tabs-reveal-on-hover.md) — compact icons and status dots, temporary resizable labels, and a stable console grid.

- [Objectives live in workspace folders](objectives-live-in-workspace-folders.md) — per-folder `.objective.json` is authoritative; only UI state stays in `.lab`, with lossless legacy conversion.

- [Worktrees follow task asset buckets](worktrees-follow-task-asset-buckets.md) — only Root/Objective stay fixed; worktrees are Unassigned/task/shared assets, explorer files have no stars.

- [Task assets stay put across subtasks](task-assets-stay-put-across-subtasks.md) — reserve the largest child group so task clicks keep the asset section at a fixed position.

- [Task agent drops use scoped prompts](task-agent-drops-use-scoped-prompts.md) — Context/parent/This task labels, typed references and explicit current-task scope; unsent paste.

- [Live Objectives use task asset buckets](live-objectives-use-task-asset-buckets.md) — authorized live Unassigned/shared/Tasks/task-assets layout, stars and navigation-only task rows.
- [Live subtasks inherit Objective and parent context](live-subtasks-inherit-objective-and-parent-context.md) — complete deduplicated context bundles and sidebar-only reverse terminal drops.
- [Task status and terminal icons are separate](task-status-and-terminal-icons-are-separate.md) — left ⬜ / ✅ status; right icon appears only for an asset override, inherited by tabs and terminals.

- [Objective assets share the shell cache version](objective-assets-share-cache-version.md) — fingerprint Objective/demo files and version all sandbox dependencies for normal reloads.

- [Demo task list is navigation-only](demo-task-list-is-navigation-only.md) — middle task-mode header owns completion/editing; one parent task expands at a time.
- [Demo subtasks inherit parent context](demo-subtasks-inherit-parent-context.md) — console bundles follow Objective → parent task → subtask with exact references.
- [Demo asset stars share context](demo-asset-stars-share-context.md) — stars preserve task membership; asset drops choose task icons and Unassigned opens middle tasks.
- [Demo terminal drops target the sidebar](demo-terminal-drops-target-sidebar.md) — reverse associations accept left-column objects only; middle task rows still accept asset attachments.

- [Objective demo uses asset buckets](objective-demo-uses-asset-buckets.md) — production-like sandbox, Unassigned/Objective/Tasks/selected-task assets and recoverable Archive; complete task context bundles.

- [Objective task mode has a corner close](objective-task-mode-has-corner-close.md) — red upper-right control throughout task mode; returns to Tasks with drafts preserved.

- [Objective tasks open details and focus](objective-tasks-open-details-and-focus.md) — title hyperlinks, Off/Semi/Focus sidebar modes and asset icons inherited by current/terminal tabs.
- [Objective task assets keep original ownership](objective-task-assets-keep-original-ownership.md) — references to any sidebar asset, deduplication, icon selection/detachment and task terminal targets.
- [Task agent drops include all asset references](task-agent-drops-include-all-asset-references.md) — exact task details plus every asset reference in one unsent terminal paste bundle.

- [Objective links open editable details](objective-links-open-editable-details.md) — one click opens URL, Cmd/Ctrl-click opens editable metadata; retained drafts and conflicts.
- [Objective link sublinks reveal on hover](objective-link-sublinks-reveal-on-hover.md) — one-second parent hover, nested destinations with stable IDs and exact terminal references.

- [Servers uses global workspace tabs](global-servers-use-workspace-tabs.md) — current-workspace selection, independent scopes and removed workspace strip.
- [Resources owns reviewed cleanup](resources-owns-reviewed-cleanup.md) — Resources table, All/workspace review and exact individual/bulk targets; supersedes the separate global Cleanup button.

- [Shell templates stay with their backend process](shell-template-stays-with-backend-process.md) — avoid new Jinja context contracts in older running Python; retain asset invalidation.
- [History content is bounded before decoding](history-content-is-bounded-before-decoding.md) — non-UTF-8 companions, temporary byte spooling and aggregate 8 MiB preview limits.
- [Native browser timeouts use an explicit fallback](native-browser-timeouts-use-explicit-fallback.md) — batched URL reads, serialized probes, brief backoff and a fresh browser click.
- [Markdown preview clicks avoid measurement dispatch](markdown-preview-clicks-avoid-measure-dispatch.md) — retain click-time position mapping and capture native editor errors in regressions.

- [Objective focus uses one current tab and ordered slots](objective-focus-uses-current-tab-and-ordered-slots.md) — hover dropdown, five library slots, insertion shifts and parks the fifth; supersedes separate focus tabs and swaps.
- [Objective colors belong to focus slots](objective-colors-belong-to-focus-slots.md) — fixed slot palettes recolor moved/shifted objectives and worktrees; parked objectives are gray.
- [Inactive Objective terminals only color headers](inactive-objective-terminals-only-color-headers.md) — active group keeps worktree colors; other rails and associations are neutral.
- [Objective resource icons follow file paths](objective-resource-icons-follow-file-paths.md) — reuse Files icons for owned and generic resources, including notebook and SQL references.

- [Objective links use native service icons](objective-links-use-native-service-icons.md) — compact content-sized pills with URL-based service icons and live global domain mappings.

- [Sidebar objects paste or associate by drop target](sidebar-object-drops-paste-or-associate.md) — console drops paste source references without Enter; terminal-name and reverse drops associate any Objective sidebar object without changing its launch folder.

- [Workspace objectives use five focus tabs](workspace-objectives-use-five-focus-tabs.md) — earlier five-tab design, superseded by the current-tab dropdown and ordered library slots above.
- [Global Cleanup uses workspace tabs](global-cleanup-uses-workspace-tabs.md) — beside global Logs; per-workspace review including empty tabs, with kills limited to the selected workspace.
- [Objective Tasks and fixed gray folders](objective-tasks-and-fixed-gray-folders.md) — Tasks below selectors; gray workspace Root and changing Objective directory precede worktrees.
- [Objective documents use the native inline editor](objective-documents-use-native-inline-editor.md) — existing slash commands, left-menu tabs, idle/outgoing saves and retained drafts with sibling-safe conflicts.
- [Objective terminal groups use flat native rows](objective-terminal-groups-use-flat-native-rows.md) — small headers, one project-colored rail, spacing between worktrees and canonical checkout grouping.

- [Workspace objectives own content and reference Assistant](workspace-objectives-own-content-and-reference-assistant.md) — opt-in real workspace registry, owned Markdown/notebooks, original Assistant references and independent terminal resource mappings.
- [Objective subtabs collapse except pins](objective-subtabs-collapse-except-pins.md) — latest navigation rule replaces five-minute retention; immediate document trees, 1.5-second hover and native text sizes.
- [Large-projects is Objectives staging](large-projects-is-objectives-staging.md) — authorized simulated fixtures, dedicated shells, preserved user terminals and native latency evidence.

- [Objectives open tasks in the center](objectives-demo-tasks-open-in-center.md) — three selectors atop the sidebar, one Tasks progress item, compact task rows and mandatory document details.
- [Demo subtabs stay five minutes](objectives-demo-subtabs-stay-five-minutes.md) — 1.5-second hover, individual pinning, standalone subtab views, and browser-only expiry.

- [Local Mac links reuse browser tabs](local-mac-links-reuse-browser-tabs.md) — backend adapts Alfred's tab focus behavior for the default Mac browser, with bounded automation and visible failures.
- [Workspace link framing fallback](workspace-link-framing-fallback.md) — known public framing blockers open in the browser; origin preferences persist and reset in the compact editor.

- [Objectives demo is browser-only](objectives-demo-is-browser-only.md) — Home tab beside Admin, simulated resources and terminals, three focus slots, independent browser state and no data migration.

- [Workspace external links open in the middle panel](workspace-external-links-open-in-center.md) — keep Files and existing terminals available; ordinary clicks embed, modified clicks/browser fallback stay on the client.

- [Self-hosted link domains use client icon mappings](self-hosted-link-domains-use-client-icon-mappings.md) — configurable service/custom icons, optional subdomains, live updates, and local resized PNG uploads.

- [Link rows infer services from URLs](link-rows-infer-services-from-urls.md) — local brand icons, one-line click-to-edit metadata, automatic external types, and preserved internal document/tab targets.

- [Markdown code blocks have protected UI containers](markdown-code-blocks-have-protected-ui-containers.md) — automatic fences, None/language picker, editable highlighting, UI deletion and native undo.
- [Markdown tables align editable cells](markdown-tables-align-editable-cells.md) — forgiving separator counts, shared wrapping columns, empty cells and browser caret selection.
- [Headless macOS select uses native type-to-select](headless-macos-select-uses-native-type-to-select.md) — CDP character input selects real native dropdown options where popup arrow keys are ignored.

- [Workspace terminal folders stay fixed](workspace-terminal-folder-is-fixed.md) — every new launch asks for the workspace or a pinned checkout; cancellation starts nothing, and saved folders cannot be reassigned.

- [Copilot resume clears retained yellow](copilot-resume-clears-retained-yellow.md) — native CLI 1.0.83 fixtures verify tools, final response and shutdown; idle resume explicitly clears abandoned work without green.

- [Workspace working priority and green-dot review](workspace-working-priority-and-dot-review.md) — yellow wins across workspace terminals; direct green-dot activation reviews completed results without navigation.

- [Terminal drops match the visible document](terminal-drops-match-visible-documents.md) — series cards link the displayed series; captured roots/paths and busy-header guards prevent stale targets.

- [Command-click opens Assistant documents in the modal](assistant-document-command-click.md) — document entries and inline rendered content, with drafts preserved and pending inline clicks cancelled.

- [Recently opened documents belong above linked documents](recently-opened-documents-sidebar.md) — time-windowed, browser-local document history; successful root opens only, with existing open and drag behavior.

- [Local-main collects current edits](sidebar-comparison-collects-current-edits.md) — a separate Uncommitted snapshot can miss newer changes; compare main with the complete working tree on refresh.

- [Project sidebar ownership includes children](project-sidebar-container-ownership.md) — replace project containers during normal rendering, repair incomplete mounts, and reject moved or detached callback targets.
- [Guarded metadata lock waits cancel](guarded-metadata-lock-waits-cancel.md) — timed-out lock readers release worker capacity; shared terminal rows are copied before enrichment.

- [Error banners keep controls usable](error-banners-keep-controls-usable.md) — compact details, click-through text, page-long dismissal, and preserved diagnostics.

- [Folder drags paste their source paths](terminal-folder-drop-paths.md) — real folders across all file trees use the existing shell-safe terminal path drop.

- [Registered projects seed each browser's sidebar](registered-projects-seed-sidebar.md) — ordinary workspace opens import registered project buttons once, preserving custom settings and deliberate removals.

- [Project sidebars use disk snapshots](project-sidebar-disk-snapshots.md) — minute-old data is acceptable; shallow folders, bounded SQLite/Git work, exact uncommitted comparisons, and real six-repository evidence retain cold misses.

- [Performance goal stopped at checkpoint](performance-goal-stopped-at-checkpoint.md) — finish the stable main checkpoint and push, then stop; remaining latency gaps are not claimed complete.
- [Materialized tests wait for file snapshots](materialized-tests-wait-for-file-snapshots.md) — fixture reads wait for refreshed snapshots while production tests retain nonblocking caching behavior.
- [History fixtures exclude live vault state](history-fixtures-exclude-live-vault-state.md) — isolate Git fixtures so backend log/index writes do not change the expected working-tree state.

- [Document drags paste source paths](document-drags-paste-source-path.md) — sidebar documents paste their absolute Markdown path into terminals while retaining workspace-link drags.

- [Host resources are limited to Lab](host-resources-limited-to-lab.md) — host CPU/memory, verified Lab processes, exact stop targets, and cooperative Files-scan pause.

- [Document terminals keep independent code scopes](document-terminal-independent-code-scope.md) — draggable sidebar documents, identical shared names, and document plus folder/worktree navigation on terminal clicks.

- [Terminal indicators persist until finish or review](terminal-indicators-persist-until-finish-or-review.md) — yellow survives uncertain status; unread green clears only after the viewing delay or a real double-click, including across new work.

- [Terminal cleanup reviews inactivity](terminal-cleanup-reviewed-inactivity.md) — seven-day candidates across all scopes; exact reviewed identities, atomic tmux rechecks, and preserved conversations

- [Document startup handoff milestones](document-startup-handoff-milestones.md) — distinguish Lab launch work, trace overhead and provider bootstrap; preserve the owned workload and cold failures.

- [CLI commands load on demand](cli-commands-load-on-demand.md) — reduce fresh agent-launch imports while preserving full Click help, aliases, completion and launch context; cold UI misses remain.

- [Assistant details share request records](assistant-detail-shares-request-records.md) — one fresh library scan per modern detail request, with fresh source reads, validation, and owned-terminal browser measurements.

- [Assistant fingerprints share root resolution](assistant-fingerprint-shares-root-resolution.md) — retain fresh source/path checks and moved-root fallback while avoiding repeated root walks; native latency tails remain.

- [Assistant navigation defers background refresh](assistant-navigation-defers-background-refresh.md) — finish the clicked view and deep link, then read fresh once; preserve newer actions, retries, normal polling and remaining latency misses.

- [Assistant descendants use ordered child indexes](assistant-descendants-use-ordered-child-indexes.md) — reuse current parent groups while preserving traversal/errors; the 500-note HTTP budget passes, but native tails remain.
- [Assistant progress recursion releases trees](assistant-progress-recursive-closure-retains-rows.md) — explicit recursion removes three closure cycles and reduces collection work; native latency misses remain, with production GC unchanged.

- [Assistant index shares current records](assistant-index-shares-current-records.md) — one fresh record list serves every index projection; retain the empty-list/migration fallbacks and the larger-library latency failures.
- [Core and CLI tests have separate namespaces](core-and-cli-tests-have-separate-namespaces.md) — run their pytest suites separately to avoid a duplicate `tests.conftest` collection failure.

- [Assistant notes share a listing snapshot](assistant-notes-share-a-listing-snapshot.md) — avoid per-note filesystem scans while retaining fresh requests, complete descendant text and native Assistant latency tails.

- [Search decodes after complete pipe capture](search-decodes-after-complete-pipe-capture.md) — reduce transient allocation and unnecessary newline scans while preserving encoding, both EOFs, strict errors and timeout behavior.
- [Concurrent cProfile needs consistency checks](concurrent-cprofile-needs-consistency-checks.md) — overlapping sessions failed and guarded function costs were inconsistent; retain diagnostics and use coarse timers with unprofiled controls.

- [Literal search workers need concurrent evidence](literal-search-workers-need-concurrent-evidence.md) — smaller macOS literal-query pools reduce latency, while regex/config guards and overlapping-client failures constrain the retained policy.

- [Capped search keeps complete process output](capped-search-keeps-complete-process-output.md) — parse only consumed lines while preserving pipe EOF, strict decoding and timeout behavior; file-backed capture lost descendant output.

- [Apple Git resolution keeps its launcher environment](apple-git-resolution-retains-launcher-environment.md) — resolve once per catalog request, preserve SDK/toolchain environment and custom Git selection, retain concurrent HTTP failures

- [Repository summaries share bounded Git workers](repository-summaries-share-bounded-git-workers.md) — overlap independent fresh reads, retain order and fallbacks, and share the eight-worker bound across requests
- [Reader controls preserve actual input cadence](terminal-reader-controls-need-matched-input-cadence.md) — sleep lateness confounded the first thread comparison; corrected controls did not establish a transport fix

- [Normalize workspace history before teardown](workspace-history-normalization-precedes-teardown.md) — preserve history and notebook position without a second intermediate layout; repeated restoration falls below 200 ms
- [Notebook typing checks its visible text and draft](notebook-typing-checks-visible-highlight-and-draft.md) — native keys verify the syntax overlay, cursor, localStorage and both restored drafts while preserving notebook files
- [Direct shell launch needs a measured gain](direct-shell-launch-needs-measured-gain.md) — a terminal-only direct argv candidate did not establish a cold-start improvement and was removed

- [Cold creation separates process and render milestones](terminal-cold-start-needs-process-and-render-milestones.md) — trace-only parse/render/readiness stages and cleanup-time process timestamps retain first-use startup costs
- [Opening renderer hooks need a measured gain](terminal-opening-renderer-hook-needs-latency-gain.md) — skipping temporary DOM construction passed correctness but did not improve end-to-end latency; keep forced-GPU-failure coverage

- [Confirmed terminals attach before refresh](terminal-creation-publishes-before-refresh.md) — retain fresh metadata with atomic fallback and creation/close read ownership; avoid duplicate repaint and selection theft

- [Connect with the final renderer grid](terminal-connection-uses-final-renderer-geometry.md) — real WebGL and DOM can fit different columns; initial connections must follow final renderer setup
- [Terminal asset hints need failure and latency checks](terminal-asset-hints-need-failure-and-latency-checks.md) — failed preloads can poison later loads; the tested prefetch/parallel candidate showed no end-to-end gain

- [Batch terminal setup with failure recovery](terminal-wheel-setup-batches-idempotent-commands.md) — one tmux client on successful creation, individual retries retain later settings after an error

- [Open terminals with visible font metrics](terminal-open-needs-visible-font-metrics.md) — avoid the initial 50 ms geometry retry while retaining fitted connections and fallback
- [Terminal creation checks rendered output and identity](terminal-creation-probe-requires-render-and-identity.md) — native New/Terminal clicks, exact echoes, saved identity and owned-only exact-name cleanup

- [Producer CPU separates terminal work from waiting](terminal-source-cpu-separates-write-waiting.md) — optional whole-write CPU diagnostics expose upstream stalls; private PTY controls do not replace native rendering checks

- [Fewer terminal frames do not prove lower typing latency](terminal-frame-count-is-not-typing-latency.md) — preserve native timing failures and source/render proof; zero-yield and timed burst candidates were rejected

- [Periodic Git polling skips the cached repaint](periodic-git-poll-skips-cached-repaint.md) — refresh existing decorations once from live data, while newly mounted rows retain their fast cached paint

- [Terminal footer includes a full margin cell](terminal-footer-includes-full-margin-cell.md) — a visible terminator can occupy the cursor cell; verify the full row without waiting for the next key, preserving exact input and render checks

- [Disposable fixtures use the default tmux generation](terminal-fixtures-use-default-tmux-generation.md) — owned sessions and HTTP/browser fixtures can still share the default tmux server; keep transport controls separate and never change user sessions

- [Terminal output load has independent proof](terminal-output-load-has-independent-proof.md) — native typing during scrolling output verifies producer bytes, exact input continuity and actual rendered load, retaining every latency miss

- [Polling snapshots reuse native entries](polling-snapshots-reuse-native-entries.md) — reduce snapshot bookkeeping while preserving fresh metadata, complete event detection and normal watcher policy
- [Watcher diagnostics observe whole operations](watcher-diagnostics-observe-whole-operations.md) — bounded coarse timings distinguish concurrent watcher/worker CPU from waiting without tracing every file

- [Notebook session metadata is lightweight](notebook-session-metadata-is-lightweight.md) — share stable session identity without importing Jupyter for metadata; retain real-kernel behavior and measure complete notebook controls

- [Cold dashboard reads follow file dispatch](cold-dashboard-reads-follow-file-dispatch.md) — overlap independent I/O after dispatching files first; retain one batch, complete sidebar data, errors and navigation ownership
- [Synchronous diagnostics separate thread CPU](synchronous-diagnostics-separate-thread-cpu.md) — distinguish waiting from computation on sync workers; omit misleading async thread totals and retain the unresolved cold scan spike

- [Workspace history precedes view teardown](workspace-history-precedes-view-teardown.md) — avoid a synchronous intermediate style/layout flush while retaining history entries, exact document restoration and old terminal ownership

- [Editor keys are separate from IME setup](editor-keys-are-separate-from-ime-setup.md) — native input has its own clock/value/cursor and Save/Cancel checks; keep IME and navigation failures
- [Browser traces need time coverage checks](browser-traces-need-time-coverage-checks.md) — a saved verbose trace can stop before the failing sample and materially perturb click timings

- [File scans release recursive closures](file-scans-release-recursive-closures.md) — avoid retaining complete file lists until cyclic GC while keeping live filesystem workers and traversal semantics intact

- [Sidebar parent lookups belong to one build](sidebar-tree-lookups-belong-to-one-build.md) — reduce repeated path work while preserving fresh trees, file identity, metadata and path normalization

- [Workspace navigation defers overlapping refreshes](workspace-navigation-defers-background-refresh.md) — finish the clicked workspace first, then read fresh data once; keep scope/generation ownership and immediate later clicks

- [Background refresh respects the editor](document-refresh-respects-active-editor.md) — recheck editing after asynchronous mtime/document reads; retain the baseline so changes catch up after editing

- [Markdown skips unused disclosure searches](markdown-skips-unused-disclosure-extension.md) — bypass repeated suffix scans only when no disclosure can be consumed; preserve custom parsing and the shared safety/copy pipeline

- [Document saves publish confirmed cache content](document-saves-publish-confirmed-cache.md) — avoid stale inline paints while retaining fresh reconciliation, captured roots and newer drafts
- [Multiline IME input is not paste latency](multiline-ime-input-is-not-paste-latency.md) — distinguish CDP text setup from clicks and clipboard input; retain slow replacements and failure diagnostics

- [Document editing checks both views](document-edit-latency-checks-both-views.md) — measure saved/cancelled modal and inline content, exact files across workspaces, and restored document navigation

- [Sidebar file identity is shared](sidebar-file-identity-is-shared.md) — one captured path/root serves open, context, drag and terminal links; legacy entry rows keep their metadata

- [Native drag tests use a trusted transfer](native-drag-tests-use-trusted-transfer.md) — verify copy mode in native dragstart, cancel the owned test drag and reset pointer state before pixel comparisons

- [Named action logs avoid text layout](named-action-logs-avoid-text-layout.md) — skip unused innerText reads for named controls while preserving log labels and unnamed fallbacks

- [Terminal detach drains tty output](terminal-detach-drains-tty-output.md) — bounded worker cleanup avoids the measured tmux close stall while retaining sessions, input and pane-cache limits

- [Pin writes publish confirmed cache state](pin-writes-publish-confirmed-cache-state.md) — show saved Pin/Unpin state on warm paint, retain fresh reconciliation, and keep delayed writes in their original workspace

- [Sidebar Pin controls keep their own name](sidebar-pin-controls-keep-name-separate.md) — delegate clicks without confusing pin names and file paths; preserve native geometry and existing double-click behavior

- [Terminal probes verify text after scrolling](terminal-echo-probe-verifies-scrolled-text.md) — exact varied input, independent parse/render continuity, and explicit coverage beyond the ready marker

- [Input validation samples the current clock offset](input-validation-samples-current-clock-offset.md) — wall and monotonic clocks may drift; preserve raw measurements, queued input and strict validation limits

- [Git decorations use path indexes](sidebar-git-decorations-use-path-indexes.md) — preserve prefix and scope semantics, avoid unchanged badge mutations, and verify real Git state in latency fixtures

- [Settings latency includes the actual sidebar redraw](settings-latency-waits-for-sidebar-redraw.md) — verify inactive-workspace saves, stored preferences and restored rows; separate form setup from measured native clicks

- [Creation publishes its workspace tab immediately](workspace-creation-publishes-tab-immediately.md) — remember the confirmed row before navigation without replacing existing tab state or waiting for polling

- [Prepared sidebar groups retain containment](sidebar-preparation-retains-containment.md) — preserve auto's layout/style/paint boundaries after idle preparation, and check focused group-boundary pixels

- [Prepare sidebar layout in idle callbacks](sidebar-idle-layout-prepares-live-groups.md) — keep live preparation out of template keys, cancel stale jobs, and invalidate it before width changes

- [Empty pending state skips path resolution](notebook-empty-pending-tracker-skips-resolution.md) — avoid filesystem work when no notebook is running; preserve live identity checks when the registry is nonempty

- [All file icons share graphics](sidebar-all-icons-share-graphics.md) — one span per icon, inherited-color masks, theme-aware config fills, and native-scale pixel regression checks

- [Native Enter includes its character event](browser-native-enter-includes-character.md) — CDP button-activation checks need carriage-return text as well as keyDown/keyUp

- [Reuse pristine sidebar folder fragments](sidebar-template-fragments-reuse-pristine-folders.md) — source-range reuse avoids reparsing unchanged folders; transient identity proofs must not retain older templates

- [Separate browser and server latency](latency-probes-separate-server-and-browser-time.md) — optional isolated ASGI/handler/function timings correlate route, workspace scope, and start time without logging headers or bodies

- [Codex launch options](codex-launch-explicit-autopilot-options.md) — use explicit workspace sandbox and on-request approvals; removed `--full-auto` made terminal tabs exit immediately

- [External links use the default browser](external-links-use-default-browser.md) — local links leave the Lab PWA through the OS browser; shared handling across document views and terminal hyperlinks.

- [Notebook cell deletion](notebook-cell-delete-corner-confirmation.md) — visible upper-right trash button in output-only mode too; confirm code, text, and draft removal

- [Worktree recent files ignore the initial checkout](worktree-recent-files-ignore-initial-checkout.md) — hide untouched checkout copies from time filters while retaining new, edited, and subsequently committed files

- [Worktree discovery refreshes live](sidebar-worktree-discovery-refreshes-live.md) — refresh visible choices independently of file mtimes, preserving selection and open documents
- [Recently updated compares with local main](sidebar-local-main-comparison.md) — total working-tree comparison, workspace-scoped persistence, and retired remote/history filter migration

- [Command-click across file previews](file-previews-command-click.md) — shared word highlighting and file modal; cell outlines remain notebook-only
- [File modal sort labels and type](file-modal-sort-labels-and-type.md) — Modified/Created time desc/asc, Name A–Z/Z–A, and Type (extension)

- [Notebook click markers follow text](notebook-click-marker-follows-text.md) — green marker tracks the clicked character across text wrapping, including editable code

- [File modal sort is per file](file-modal-sort-is-per-file.md) — modified newest first by default; save name/modified/created and either direction for each file and root

- [Notebook modal centers the clicked area](notebook-modal-centers-clicked-area.md) — Command-click centers and briefly marks the clicked position within code, headers, or results

- [Assistant agents may edit Markdown metadata](assistant-agent-editable-markdown.md) — optional CLI/API, distinct task dates, and explicit recurrence history
- [Assistant meeting series and originals](assistant-meeting-series-and-originals.md) — summary-first series history, separate originals/questions/documents, and date lists

- [File context menu copies raw content](file-context-menu-copies-raw-content.md) — Copy content reads the clicked file's source from its own root, including Markdown syntax and closed disclosures

- [Native Plotly notebook output](notebook-native-plotly-mime.md) — render saved/live Plotly MIME with the vendored library; preserve typed arrays, independent views, and chart interaction state

- [Terminal copy rejoins prose](terminal-copy-reflows-prose.md) — remove display wraps and padding while preserving structured text; verify real Chrome clipboard and selections

- [Notebook cell Command-click](notebook-cell-command-click-expands.md) — replaces double-click; open the cell-focused modal from headers, editable code, or results

- [Recent terminal marker is a vertical line](terminal-recent-marker-is-vertical.md) — slim left-edge line replaces the green bullet, preserving recent timing and color settings

- [Notebook cell Expand](notebook-cell-expand-opens-modal.md) — open the same file modal at the clicked stable cell, preserving its repository root and revealing hidden code

- [Notebook cells do not scroll vertically](notebook-cells-do-not-scroll-vertically.md) — fully expand or hide code and ordinary outputs; preserve scrolling only in client-authored HTML

- [Terminal file drops and clean copy](terminal-file-drop-and-clean-copy.md) — sidebar files paste absolute paths through xterm; copying removes decorative frame rails while preserving content pipes

- [Linked terminal file identity](terminal-linked-file-name-and-icon.md) — linked tabs and headers show the file basename and shared file-type icon, including in worktrees

- [Workspace renames move folders](workspace-renames-move-folders.md) — physical folder rename, stable internal ID, independent terminal UUID index, and path migration

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

- [Terminal metadata closes SQLite connections](terminal-metadata-closes-sqlite-connections.md) — use `contextlib.closing`; SQLite transaction contexts leave handles open and can exhaust the server's descriptor limit

- [Keep client-specific work out of Lab](framework-keeps-client-domain-out.md) — framework code, defaults, skills, docs, and examples stay general-purpose; notebooks require a configured local runtime.

- [Markdown Mermaid rendering](markdown-mermaid-rendering.md) — file views render fenced Mermaid after mounting; marked alone only emits source

- [Lab UI runs as installed Chrome PWA](lab-ui-runs-as-installed-chrome-pwa.md) — same-origin `window.open` is frameless (no URL bar); prefer cross-origin/direct URLs for pop-outs
- [Cover letters: no weaknesses](feedback-cover-letter-no-weaknesses.md) — in CV workspace, keep gaps in fit.md only; close on strengths, never name missing skills
- [Console communication: be plain](console-communication-be-plain.md) — plain, short, jargon-free console messages; user dislikes dense technical recaps
- [Push changes to main by default](push-changes-to-main-by-default.md) — commit and push completed Lab work directly to `origin/main`, without PRs, unless the user explicitly requests otherwise
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
- [Terminal WS half-open after tmux attach dies](terminal-ws-half-open-after-tmux-attach-dies.md) — close promptly on PTY EOF, cancel both pumps, and expose document-terminal reconnect without restart loops
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
- [Focus mode was removed](focus-mode-removed.md) — no fullscreen/layout/zoom mode; Keep Alive still owns the browser wake lock
- [Lid Awake is a timed system control](lid-awake-is-a-timed-system-control.md) — admin-only macOS pmset timer survives page/server closure and safely resets normal sleep on cancel or expiry
- [Lid Awake named time choices](lid-awake-named-time-presets.md) — Overnight until 07:00, Working time until 17:00, and Custom time; prioritize by the local 06:00/18:00 cutoffs
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
- [Assistant uses the selected Compact design](assistant-workspace-first-document-modal.md) — one Tasks tab, planning filters, creation-date lists, workstream labels, and click-to-open modal
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

- [Vault overview prioritizes recent workspaces](vault-overview-workspaces-first.md) — Workspaces first, newest visit first, configuration below; visits persist by absolute path in browser storage

- [Workspace context menu actions](workspace-context-menu-actions.md) — Rename and Delete in both vault lists and workspace tabs; stable IDs for rename and exact-folder confirmation for deletion

- [Vaults are sections inside Home](vaults-are-home-sections.md) — vault navigation stays beneath Home alongside Overview and Admin; only workspaces open separate tabs

- [Home shares one terminal area](home-shares-one-terminal-area.md) — Overview, Admin, and all vault sections use the existing Home terminal scope, selection, connection, and settings

- [Closing workspace tabs preserves resources](workspace-close-preserves-resources.md) — close is navigation only; vault rows show live terminals, servers, and notebook kernels, independent of open tabs

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

- [Terminal tabs use folder badges](terminal-tabs-use-folder-badges.md) — replace provider text and vertical bars with colored Home/Logs or folder-alias badges and explicit worktree indicators

- [Workspace new-tab button](workspace-new-tab-button.md) — small + beside the tabs; picker selects a vault and creates or opens a workspace in that vault

- [Scoped proxy compatibility](scoped-proxy-compatibility.md) — scoped Referer rewriting, auth parsing, legacy aliases, and matching Vite/React Router base paths

- [Terminal tabs activate Home sections](terminal-tabs-activate-home-sections.md) — terminal clicks navigate to Overview/vault/Logs, preserve the exact warm session, and ignore stale navigation callbacks

- [Worktree tabs use scope names](terminal-worktree-tabs-use-scope-name.md) — agent icon plus folder alias/worktree name, no session name or generic worktree badge

- [Home terminal listing spans registries](home-terminal-list-spans-registries.md) — combine Home sessions independently of section Referers, deduplicate live names, and preserve vault isolation for real workspaces

- [Daily feature usage counters](daily-feature-usage-counters.md) — Logs shows daily feature counts sorted by use, with distinct UI interaction methods and persistent counters separate from diagnostics

- [File modal browses sibling files](file-modal-browses-sibling-files.md) — double-click selects a file; Cmd-click browses a folder in the same modal with files on the left

- [Home overview is a directory](home-overview-is-a-directory.md)

- [Assistant opens to Tasks and Notes](assistant-opens-to-tasks-and-notes.md)

- [Command+K keeps the active file scope](command-k-keeps-file-scope.md) — selected folder/worktree only; Recently updated formats first, then newest modified; opening preserves context

- [Server iframe reuse is workspace-scoped](server-iframe-reuse-is-workspace-scoped.md) — match the absolute workspace path and server name; preserve state only within the same server view

- [Assistant document metadata stays in the header](assistant-document-metadata-in-header.md) — content-only task/note panes, quiet editable properties, date calendars, and a details menu

- [Meta keeps workspace instructions visible](meta-keeps-workspace-instructions-visible.md) — show Lab context in Assistant and keep workspace instructions separate from the selected folder/worktree; live files are not terminal startup history

- [Assistant combines workspaces with neutral controls](assistant-unified-tasks-and-neutral-controls.md) — one task list, workspace filters, recurrence only in the header, and larger click targets

- [Assistant records have independent project/workspace links](assistant-independent-projects-and-workspaces.md) — schema 2 migration, flat tasks/notes/projects, typed nested tabs, aliases and verified backups

- [Migrations are agent documentation](migrations-are-agent-documentation.md) — read-only format/migration guides in lab migrations and lab agent context
- [assistant-embedded-subtabs.md](assistant-embedded-subtabs.md) — One Markdown per task/note; embedded subtabs, derived progress, generated Index, and stable navigation.
- [Assistant heading copy menu](assistant-heading-copy-menu.md) — Secondary-click headings for one rich Copy content action; no inline Slack/GDoc buttons.
- [Assistant root-level plus](assistant-root-level-plus.md) — Document tabs + creates a peer of the main tab; row-menu Add subtab creates a nested child.
- [Assistant series with document tabs](assistant-series-with-document-tabs.md) — Normal document tabs with a small More in this series button; dates appear on click, newest first, and selection closes the menu.

- [Assistant content belongs to the client](assistant-client-owned-content.md) — empty bodies, free content structure, embedded tabs, and preserved client instructions.

- [Assistant note content editing](assistant-note-content-editing.md) — explicit Save, subtle changed-line marks, retained drafts, and safe subtab body updates.
- [Current document tabs use live Markdown and idle autosave](document-live-markdown-autosave.md) — edit on open, save after 10 seconds idle, preserve concurrent typing, and restore tab-scoped saved versions.

- [Assistant recent tab highlights](assistant-tab-recent-highlights.md) — New/Updated markers in Tasks and Notes; dismiss per tab or expire after three days; later edits highlight again.

- [Assistant unified documents and stars](assistant-unified-documents-and-stars.md) — shared library, optional task tracking, independent retention, meeting labels, and separate series/note stars.

- [Assistant dashboard and single series entry](assistant-dashboard-and-single-series.md) — editable saved sections; one latest series entry; previous dates and filters inside the modal.

- [Dashboard sections use JSON only](assistant-dashboard-json-sections.md) — Show filter reveals complete editable JSON; one file per section, including position and all settings.

- [Grouped row star controls](assistant-group-star-controls.md) — filled star reflects series or member notes; separate mutation controls and starred history.
- [Explicit dashboard filter logic](assistant-explicit-filter-logic.md) — schema-2 AND/OR expressions; readable JSON, inactive filters omitted, preserved migration semantics.
- [Client-defined Assistant attributes](assistant-custom-attributes.md) — JSON metadata on notes/tasks/tabs, Attributes editor, and typed dashboard conditions with explicit scope.

- [SQL-style dashboard filters](assistant-sql-style-filters.md) — schema-3 JSON with readable WHERE conditions, custom attributes, and preserved legacy semantics.

- [Independent dashboard sections](assistant-independent-dashboard-sections.md) — items appear in every matching section; only explicit filters exclude stars; series collapse within each section.

- [Assistant document storage and external links](assistant-document-storage-and-external-links.md) — explicit per-client documents/ migration, preserved paths and client-side associated-document buttons.

- [Document terminals are resource bounded](document-terminals-are-resource-bounded.md) — saved conversations, one idle process, memory-aware startup, stale-session recovery, and protected active work.

- [Document tasks and tab memory](assistant-document-tasks.md) — production document-owned tasks, independent content tabs, migrated checklists, preserved dashboard/stars, and last-tab memory.

- [Central settings use explicit scopes](central-settings-use-explicit-scopes.md) — Cmd/Ctrl+, consolidates settings; inactive workspace edits never borrow the active scope.

- [Terminal completion uses a blinking green dot](terminal-completion-blinking-dot.md) — recency stays on the steady vertical line; completion has its own dot and configurable 20-second viewing delay.

- [Terminal browser resources are bounded](terminal-browser-resources-are-bounded.md) — cap and expire hidden views, dispose active renderers and observers, and recover graphics without restarting sessions.

- [Task terminals reuse existing sessions](task-terminals-use-existing-sessions.md) — explicit drag/drop links, preserved processes and drafts, no automatic task terminal creation.

- [Working terminals use a steady yellow dot](terminal-working-steady-yellow-dot.md) — Codex, Claude, and Copilot; only the green ready-to-review dot blinks.

- [Completion second-click dismissal](terminal-completion-second-click.md) — two separate clicks on the same selected tab dismiss early; double-click remains Rename.

- [Terminal task links open the highlighted task](terminal-task-links-open-highlighted-task.md) — clickable tab/header labels open the modal at the exact task without changing workspace or starting terminals.

- [Provider idle-event boundaries](terminal-provider-idle-events.md) — Claude local commands do not start work; Copilot shutdown preserves a verified final response.

- [Modal fonts and Obsidian-style settings](modal-font-settings-and-obsidian-layout.md) — independent document/interface sizes, live preview, browser persistence, and row controls with switches.

- [Workspace document references](workspace-document-references.md) — drag Assistant documents into workspaces, share existing terminals, choose ownership when unlinking, and remember modal placement.

- [Workspace completion indicators](workspace-completion-indicators.md) — inactive workspace tabs blink for unreviewed terminal work; shared views use one acknowledgement.

- [Linked documents open inline](linked-documents-inline-navigation.md) — sidebar navigation, terminal-driven opening and highlighting, visible Files and draft-preserving Expand.

- [Assistant documents open inline](assistant-documents-open-inline.md) — single-click and keyboard open inline; double-click opens the modal, with drafts and navigation preserved.
- [Recent tab activity uses dots](assistant-tab-activity-dots.md) — blue updates and green new tabs replace labels and rails, preserving dismissal and expiry.
- [Document controls are grouped](assistant-document-header-groups.md) — readable titles, responsive actions, Copy menu and organized Properties in inline and modal views.
- [Document tabs column resizes](document-tabs-column-resizes.md) — draggable divider, remembered width, keyboard adjustment and double-click reset in inline and modal views.
- [Document tabs reveal on hover](document-tabs-hover-drawer.md) — slim edge strip, temporary navigation drawer and persistent document/tab/heading reference.
- [Document tabs stay visible as icons](document-tabs-visible-icon-rail.md) — wider collapsed rail with clickable numbered icons, active state, activity dots and unsaved markers; full hover drawer and mobile navigation remain.

- [Document-linked terminal icon](terminal-linked-document-icon.md) — use the sidebar document glyph in terminal tabs and headers, with provider identity and status preserved.

- [Documents preserve Files visibility](documents-preserve-files-sidebar.md) — no automatic collapse or restoration; normal sidebar toggles persist while documents are open.
- [Terminal clicks open linked documents](linked-terminal-click-opens-document.md) — explicit activation opens inline and reveals the task; polling only highlights, and newer navigation cancels pending opens.

- [Document tabs need readable widths](document-tabs-readable-width.md) — 420px default drawer, wrapping titles, and more resizing room now that tabs overlay the document.

- [Filesystem polls are bounded](filesystem-polls-are-bounded.md) — cycle-safe linked folders, closed scandir handles, shared reads, cooperative cancellation, and no I/O in failure reporting.

- [Workspace files use background snapshots](workspace-files-use-background-snapshots.md) — share Files/mtime work, collect initial 202 responses, preserve complete listings, and diagnose individual stalled reads.
- [Polling watcher does not follow nested links](polling-watcher-does-not-follow-nested-links.md) — lstat prevents recursive ancestor links from consuming the index watcher; Files still browses linked folders.

- [Incremental Files and instant scope switches](workspace-files-incremental-and-instant-scope-switches.md) — native change invalidation, bounded DOM caches, and a generic under-200ms warm folder/worktree switch target.

- [Shared project and worktree folders](shared-project-and-worktree-folders.md) — editable ~/src and ~/src/.worktrees defaults, project picker, custom locations, and inherited worktree paths.

- [External project explorer access](external-project-explorer-access.md) — history and explorer actions share approved project/worktree roots; vault-user and traversal boundaries remain enforced.

- [Compact project location rows](compact-project-location-rows.md) — inline names and Default/Custom buttons; reveal paths only on click.
- [Worktrees inherit project colors](worktrees-inherit-project-colors.md) — inheritance follows project edits; per-worktree overrides are optional and resettable.
- [Recent files require Git tracking](recent-files-require-git-tracking.md) — Recently updated excludes ignored and untracked files across time and Git filters.

- [Git history loads local and recent work first](git-history-loads-local-and-recent-first.md) — independent local status, 20 commits/60 days, lazy older pages, and rename-safe pagination.
- [File scan capacity is queued](file-scan-capacity-is-queued.md) — bounded cold-first admission, quiet 202 retries, immediate cached listings, and existing FSEvents reconciliation.

- [Terminal process discovery is TTY-scoped](terminal-process-scan-is-tty-scoped.md) — query only requested panes; a whole-machine ps scan can exceed the interaction budget by itself.

- [Batch terminal ownership per vault](terminal-ownership-batched-per-vault.md) — resolve unknown UUIDs from one fresh metadata scan; retain durable recovery and legacy name handling.

- [Codex snapshots preserve timestamp ties](codex-snapshot-index-preserves-tie-order.md) — skip redundant named-thread snapshots on large windows without losing empty/untitled conversations or changing same-second ordering.

- [Workspace clicks bypass startup delay](workspace-clicks-bypass-startup-delay.md) — schedule initial URL hydration separately; early user clicks must not inherit the 750 ms quiet window.

- [Open tabs avoid redundant writes](workspace-tab-open-avoids-noop-writes.md) — read current saved state, but only write a changed open/closed flag; no-op writes trigger file-tree rebuilds.
- [Sidebar templates stay pristine and bounded](sidebar-template-cache-is-pristine-and-bounded.md) — exact markup, deterministic folder IDs, fresh clones, four scopes and 60,000 retained elements; cold rendering remains separate work.

- [File scans reuse request-local entries](workspace-file-scan-reuses-directory-entries.md) — reduce repeated stat calls while preserving fresh edits, symlink targets, and worktree annotations.
- [Sidebar refreshes keep the latest scope](sidebar-refresh-keeps-latest-scope.md) — captured paths plus generations guard delayed responses; cached paint and reconciliation share ownership.
- [Shared sidebar icons preserve baselines](sidebar-shared-icons-preserve-baselines.md) — shared graphics reduce DOM without shifting text or symlink overlays; larger and mixed trees still need work.
- [Large file lists use typed serialization](large-file-lists-use-typed-serialization.md) — generic response dictionaries retain all metadata while avoiding the Python JSON conversion walk; compare complete ASGI results.
- [Offscreen sidebar groups keep complete rows](sidebar-offscreen-groups-keep-complete-rows.md) — native search/actions remain available; flat and nested groups preserve 22px row extents and bounded template retention.
- [Sidebar actions share row metadata](sidebar-file-actions-share-row-metadata.md) — delegated file/history/modal handlers use escaped paths and roots while controls keep their separate actions.
- [Dashboard reads overlap sidebar rendering](dashboard-reads-overlap-sidebar-render.md) — earlier scheduling checkpoint; retain one batch and generation guards, with cold reads now starting after file dispatch.
- [File scans avoid unused full paths](file-scans-avoid-unused-full-paths.md) — relative prefixes and DirEntry stats remove repeated path work while preserving link, notebook, worktree, and freshness behavior.
- [Unchanged background sidebars retain live rows](sidebar-background-refresh-retains-unchanged-rows.md) — compare freshly generated markup and mounted scope/identity; preserve focus without suppressing fresh data or changed rendering.
- [Input latency includes browser queueing](input-latency-includes-browser-queueing.md) — send timestamped CDP input from outside the renderer with normal polling; keep all keys and verify their exact echoed text.
- [Browser extraction can force offscreen layout](browser-content-extraction-forces-sidebar-layout.md) — Chrome AI page-content extraction was traced forcing all content-visibility groups to lay out during typing; include blink categories before blaming a Lab timer.
- [Sidebar changes reuse equal sections](sidebar-changes-reuse-equal-sections.md) — compare pristine templates, reconcile only known tree containers, retain keyed live rows, and verify that a large fixture actually fits the bounded cache.

- [Background sidebars render fresh data once](sidebar-background-refresh-renders-fresh-once.md) — explicit background mode avoids the duplicate cached render, retaining live markers, fallback, and navigation ownership

- [Retired sidebar templates transfer unchanged folders](sidebar-retired-templates-transfer-unchanged-folders.md) — reconcile before transfer; expand placeholders on every fallback; retain complete bounded pristine caches

- [Terminal transport includes negotiation replies](typing-transport-includes-terminal-negotiation.md) — retain owned socket metadata, but distinguish xterm replies from measured native keys

- [Latency fixtures match production WebSocket settings](latency-fixture-matches-websocket-configuration.md) — explicitly disable compression by default, verify negotiation, and retain labeled legacy comparisons

- [Trace terminal latency across the PTY boundary](terminal-latency-trace-crosses-pty.md) — correlate browser, ASGI, PTY and owned echo metadata while preserving byte semantics and safe cleanup

- [tmux creation hooks preserve API errors](tmux-creation-hooks-must-preserve-api-errors.md) — session output markers can precede a failing hook; native API regression guards against masking creation errors during batching.

- [Busy notebook lookups reject unrelated regular names](busy-notebook-lookups-reject-unrelated-regular-names.md) — bounded POSIX filename filtering reduces active-notebook scan work while retaining fresh symlink resolution, locking and fallback behavior.

- [Private connection material lives in Assistant](private-connection-material-lives-in-assistant.md) — this repo is public; keep personal scripts, keys, and machine details in the ignored Assistant secrets folder.

- [Sidebar uses an active/pinned scope picker](sidebar-active-pinned-scope-picker.md)

- [Folder and worktree links support whole documents and tabs](worktree-document-and-tab-links.md)

- [Sidebar picker supports worktree and folder search words](sidebar-picker-type-search.md)

- [Sidebar scope shortcuts use one row each](sidebar-scope-shortcuts-one-per-line.md)

- [Sidebar comparison label is vs main](sidebar-main-label.md) — concise visible label; local-main API/storage semantics remain.

- [Sidebar project management lives in the picker](sidebar-project-management-lives-in-picker.md) — no duplicate workspace Settings list; file-preference saves preserve scope state.

- [Scope metadata opens on double click](scope-metadata-opens-on-double-click.md) — exact checkout metadata from shortcuts and branch labels; immediate single-click navigation.

- [Internal document links use a searchable browser](internal-document-links-use-searchable-browser.md) — document results and whole-document/tab choices, compact summaries, keyboard/mobile support.

- [Scope rows combine branch and actions](sidebar-scopes-combine-branch-and-actions.md) — folder/branch labels, distinct kinds, and active-only inline GitHub/terminal controls.

- [Cold scope switches preserve visible content](sidebar-cold-switches-preserve-visible-content.md) — loading indicator, atomic project publication, cancellation/retry, and instant cached navigation.

- [External folder links open on the client](folder-external-links-open-on-client.md) — Google and other folder links follow the clicking browser, including SSH-forwarded sessions.

- [Inline document close is red in the corner](assistant-inline-close-is-red-in-the-corner.md) — visible top-right control with reserved header space and mobile/keyboard access.

- [Terminal panel width is workspace scoped](terminal-panel-width-is-workspace-scoped.md) — independent percentages, legacy default, view restoration and captured drag ownership.

- [Expanded documents use workspace terminals](expanded-documents-use-workspace-terminals.md) — hide Files temporarily, share the active terminal panel, preserve drafts/preferences, and keep the red corner close button.

- [Regular documents open expanded](regular-documents-open-expanded.md) — single-click, keyboard, recent/linked documents, worktree links and terminal navigation share the expanded workspace layout by default.

- [Document editing reveals inline Markdown](document-editing-reveals-inline-markdown.md) — formatted document editing with local syntax, native caret/undo, selection controls and preserved tab saving.

- [Markdown editor builds use local lock entries](markdown-editor-builds-use-local-lock-entries.md) — reproducible npm ci from ordinary package records, without temporary build-directory links.

- [Checkout documents use checkout terminals](checkout-documents-use-checkout-terminals.md) — exact folder/worktree links retain native checkout controllers without importing document terminals.

- [Markdown formatting normalizes selected runs](markdown-formatting-normalizes-selected-runs.md) — full/mixed toggles, outside fragments, other styles, atomic undo, and readable toolbar themes.

- [Markdown slash menu exposes foldable content](markdown-slash-menu-exposes-foldable-content.md) — searchable block actions with native folds, keyboard/click control, and preserved save/copy behavior.

- [Markdown toolbars theme the tooltip itself](markdown-toolbars-theme-the-tooltip-itself.md) — CodeMirror places both classes on one element; theme contrast and interface type sizes need native checks.

- [Inline code uses Slack-style highlighting](inline-code-uses-slack-style-highlighting.md) — orange text, filled rounded outline, shared across live and rendered Markdown with readable light-mode colors.
