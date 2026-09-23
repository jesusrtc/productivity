# Terminal typing during output needs independent load and input proof

The disposable native typing probe has `--typing-output` for a scrolling TUI:
40 colored log lines every 50 ms, with a fixed input footer. It retains the same
25 ms key cadence, native timestamp checks, exact input and 50 ms limit. Use
`--server-timings` to retain the producer's input hash, byte/line totals and batch
write times; `--trace-terminal` additionally records input receipt/footer writes.

The footer retains 64 characters and a source offset. Separate parse/render
readers verify the exact suffix and continuity of every prefix before it leaves
the footer; partial transport frames remain pending. Actual xterm render ranges
must show progressing, valid load lines in both phases. Neither buffer parsing
alone nor producer output alone establishes rendered load coverage.

Keep this workload distinct from quiet typing. At the initial large run, all
2,400 characters survived but 15 keys missed 50 ms (maximum 58.1 ms). Diagnostics
found both browser stalls and tiny-frame bursts with slow producer writes.
Do not discard those failures or attribute all misses to one mechanism.
