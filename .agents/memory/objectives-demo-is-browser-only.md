# Objectives demo is a simulation

The user requested an interactive Objectives demo tab beside Home's Admin tab
before implementing workspace objectives. Its documents, notebooks, files,
tasks, worktrees and terminals are simulated. It owns only the browser-local
`labObjectivesDemo:v1` state, with an explicit Reset demo action. Do not treat
the prototype as authorization to migrate workspace or Assistant data.

Keep the demo sandboxed and its network connections disabled. The real Home
terminal remains mounted but hidden while the demo is selected; opening the
demo must not launch a real terminal. It now mirrors the production shell:
Objectives/current-task tabs, five ordered focus slots and hover switching,
flat terminal groups, native inline Markdown editing and left-menu subtabs.
Slot insertion shifts later objectives down and parks the fifth; colors belong
to positions. The new asset bucket flow is experimental in this demo only.
