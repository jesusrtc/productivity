# Notebook session metadata does not load execution machinery

`GET /api/nb/session` only validates the notebook path and computes its stable
session name. Importing `core.notebook_kernel` there loaded Jupyter for a read
that does not need a kernel; first responses measured about 63 ms. Use the
shared `core.notebook_identity` helpers for metadata. The kernel imports the
same calculation, preserving resolved vault identity, current workspace ID,
legacy projects directories and the existing `local-` hash format. Do not
cache identities or change the execution module's initialization/lifecycle.

A cold subprocess test denies both execution-module and Jupyter imports while
checking the full metadata response and path rejection. Real-kernel tests
cover state retention through workspace rename, execution, streaming, restart,
interrupt and cancellation. In one ordinary before/after notebook workload,
the first session response changed 62.66 → 8.55 ms and first open 156.3 →
148.3 ms; other timings varied, so this is not a universal speed guarantee.

`lab_navigation_latency.py --notebook-view --notebook-cells 200` measures
native opening/restoration, code show/hide and output fold/unfold, checks every
cell's identity/source/highlight/output, and verifies both owned files remain
byte-identical. It does not execute kernels or establish notebook execution,
rich-output, native editing or physical-display latency coverage.
