# Terminal tmux names hide workspace identity

Current Lab-owned tmux names are human-facing
`neurona-<project>-<tab>-<hash6>` names. Do not restore a visible workspace
segment: workspace ownership remains in the deterministic hash and runtime
registry. Continue discovering the previous `neurona-<workspace>-...` and
older `lab-...` forms so live sessions survive framework upgrades.
