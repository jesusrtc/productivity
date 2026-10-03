# Objectives asset cases — 2026-10-02

The authorized `large-projects` staging workspace now has **56 additional named
items** across phone recovery, repository navigation, release verification and
documentation review. These supplement the existing six Objective fixtures;
focus order and original resources/content were preserved.

| Added cases | Count | Purpose |
| --- | ---: | --- |
| Markdown evidence documents | 4 | Native inline editing, folded supporting context, Baseline → Edge cases and Results subtabs |
| Native notebooks | 4 | Three synthetic verification rates, HTML table/chart and streamed text output |
| Existing notebook file references | 4 | Valid `kind: file` records use `.ipynb` icons and open the native notebook view |
| SQL file references | 4 | Extension-based icons without running a database query |
| External links | 24 | Google Docs, Slack, Jira, Grafana, GitHub and a generic unknown service |
| Tasks and subtasks | 16 | Required details, attached evidence, chosen notebook icons and due/completion states |

Each Google Docs fixture has Investigation → Malformed values and Recovery
sublinks, with its own title, TLDR and properties. Each evidence document has
three subtabs. Parent tasks reference documents, notebooks, SQL, links and a
worktree where available. Child tasks reference the exact document and link
children. Documentation review is complete; repository navigation is at risk;
release verification is overdue; phone recovery is on track. URLs labeled as
staging are simulated destinations and were not visited.

## Live verification

The real native workspace UI displayed service-aware link icons, notebook/SQL
icons, five ordered library slots, task status colors and two gray fixed roots.
The narrow sidebar had no horizontal overflow. Cmd-click opened the exact
sublink metadata. Focus displayed the selected task's assets; Semi restored
the ordinary order with highlights, and Off cleared them. A generic existing
notebook reference showed the notebook icon and opened its three native cells
with the synthetic output. All four new notebooks executed through
`lab notebook exec`, preserving live UI output.

Scrolling a task notebook revealed a bug: the red close button could move
behind the fixed workspace tabs/notebook toolbar. It now follows the working
area's viewport, reserves toolbar space and remains clickable. Native input
confirmed closing returns to Tasks. The regression covers a scrolled center,
overlapping fixed headers, center replacement and outgoing draft saving.

Normal reloads initially reused an old Objective asset version. The shell's
fingerprint now includes the Objective library and demo files. The sandbox
document propagates that version to all seven scripts/styles, including the
immutable Markdown editor. A normal reload after restarting the backend loaded
the new version without cache bypass. The real sandbox iframe mounted the
native editor, task header/completion and red close; Unassigned opened the
middle Tasks view. The bucket experiment remains demo-only.

The resource/task seeder ran through the Lab CLI. Reruns reused the same named
items. Assertions retained focus order, terminal associations, workspace/task
metadata, existing resource metadata and existing document bodies/subtabs.
All **11 terminal identities and saved associations** matched the pre-restart
snapshot. This audit sent no terminal input, opened no external site and edited
no original Assistant document. The isolated audit pages raised no JavaScript
exceptions. User terminal contents are excluded from this report.

## Checks and reproduction

**137 tests passed** across the Objective backend/native browser suites,
browser-only demo, terminal UI/completion and index/template cache tests.
JavaScript syntax, Python compilation and whitespace checks passed. The native
demo regression covers navigation-only sidebar rows, completion in task mode,
one expanded parent, asset stars/icon drops, left-column terminal associations,
Unassigned attachments and Objective → task → subtask reference bundles.
These functional checks make no new latency claim; earlier measurements and
their first-use misses remain in the main staging report.

The initial staging fixtures must already exist. Select the authorized vault:

```bash
LAB_VAULT="<staging-vault>" core/.venv/bin/python \
  scripts/perf/seed_objective_asset_cases.py --workspace large-projects --execute-notebooks
```

The script resolves the current server through `scripts/lab-url.sh`. Notebook
reruns reuse the marked cell instead of appending copies. Omitting
`--execute-notebooks` leaves outputs unchanged. Existing named fixture content,
manual icon choices, focus order and terminal links are retained.
