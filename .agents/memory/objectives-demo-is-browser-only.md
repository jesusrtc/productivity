# Objectives demo is a simulation

The user requested an interactive Objectives demo tab beside Home's Admin tab
before implementing workspace objectives. Its documents, notebooks, files,
tasks, worktrees and terminals are simulated. It owns only the browser-local
`labObjectivesDemo:v1` state, with an explicit Reset demo action. Do not treat
the prototype as authorization to migrate workspace or Assistant data.

Keep the demo sandboxed and its network connections disabled. The real Home
terminal remains mounted but hidden while the demo is selected; opening the
demo must not launch a real terminal. Up to three simulated objectives occupy
the focus slots; replacing a slot retains hidden simulation state.
