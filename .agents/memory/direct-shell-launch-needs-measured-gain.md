# Direct tmux shell execution did not resolve cold creation

tmux supports multiple command arguments without an intermediate shell. A
terminal-only candidate passed `[shell, '-l']` directly while retaining agent
launching and saved command metadata. Four untraced 20-creation runs did not
establish a cold-start gain: original first/median 317.0/168.1 ms, candidate
281.1/167.8 and 267.3/168.3 ms, restored control 269.7/170.8 ms. Every run kept
its cold miss. The candidate was removed; no shell launch behavior changed.

Do not infer an end-to-end improvement from one fewer shell process. Keep the
configured echo workload, first sample, rendered/native-key checks and owned
cleanup intact. Detailed runs and rejected patch are in performance-progress.md.
