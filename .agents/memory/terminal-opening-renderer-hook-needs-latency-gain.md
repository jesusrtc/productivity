# Skipping a temporary DOM renderer did not establish a latency gain

Vendored xterm 5.3 fires its internal onWillOpen hook before selecting a
renderer; a guarded WebGL activation there can skip the temporary DOM renderer.
A candidate preserved final geometry, Unicode, focus, GPU-failure fallback and
listener disposal in real Chrome, but its native 20-creation comparison did not
establish an end-to-end gain: median 165.2 vs 168.6 ms, p95 183.5 vs 179.9 ms,
first 319.4 vs 287.9 ms, one miss in each run. It was fully removed. Do not
retain it solely because a renderer-factory count fell to zero.

The onWillOpen member is a getter. Test instrumentation must use a property
override; ordinary assignment silently leaves it unchanged. The retained
native lifecycle test now also forces WebGL context creation to fail and
checks that DOM fallback remains fitted, focused, usable and latched.
The rejected patch and measurements are recorded in performance-progress.md.
