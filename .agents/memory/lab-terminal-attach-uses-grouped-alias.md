# Existing tmux attachment uses a grouped alias

The Lab terminal **+ New → Attach tmux session** flow must create a Lab-named
tmux grouped-session alias (`new-session -t <source> -s <alias>`), not a nested
tmux client or byte-forwarding process. The alias shares the source panes while
remaining independently removable, so closing the Lab tab never kills the
original session. Persist attached entries with `kind: attached` and never
auto-restore a missing attached entry as a normal shell.
