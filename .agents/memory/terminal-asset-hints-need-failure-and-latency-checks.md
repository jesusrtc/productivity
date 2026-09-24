# Terminal asset hints require failure and end-to-end checks

A Chrome preload hint that received a non-cacheable 503 was reused as a failed
response by the later normal script load. Keeping it out of Lab's JavaScript
promise cache was not sufficient. A real browser/server failure fixture is
needed before adding intent-based asset hints.

Prefetch recovered from that failure and reused successful downloads. Combined
with parallel ordered script loading, it passed 104 focused checks but did not
show an end-to-end creation gain: median 189.3 vs 186.0 ms in an unchanged
control; first 351.1 vs 274.1 ms; misses 7/20 vs 3/20. API time also varied, so
do not attribute the whole difference to hints. The combined candidate was
removed, not adopted on the strength of faster asset requests alone. This does
not separately prove the effect of parallel loading on every other entry path.
See performance-progress.md for paired patches/tests and trace artifacts.
