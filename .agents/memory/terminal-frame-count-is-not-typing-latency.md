# Fewer terminal frames do not establish lower typing latency

The scrolling-output workload can produce different tmux repaint byte/frame
counts despite identical source batches, geometry and a single connection.
Use native input-to-render latency plus exact source hashes and independent
parse/render checks; do not select an implementation from frame count alone.

Two candidates tested against 04620e7 were removed. A single event-loop yield
reduced tiny frames but changed shared/private missed-key counts from 2/1 to
2/4 (1,200 keys per run). A one-millisecond interval between burst frames changed
counts from 0/3 to 15/0 and raised private medians. The fixed before/after orders
were not ABBA; these are insufficient grounds to claim a consistent benefit.
Neither candidate remains in production. Preserve their failures and archives
listed in docs/performance-progress.md rather than repeating them as new ideas.

Private process samples showed slow source writes overlapping tiny-frame bursts.
Aggregate select/write stacks do not identify the cause of each stall, and
sampling can perturb timings. Keep them diagnostic; do not change user tmux
settings or silently replace shared-transport runs with private ones.
