# Git history loads local and recent work first

The shared history modal must render uncommitted work independently of Git log.
Use status-only reads, 20-commit pages with an initial 60-day cutoff, and an
explicit older-history expansion. Keep base comparisons lazy. Preserve selected
diffs and list scroll when pages arrive, and cancel stale browser requests.

Pin the Git revision and cutoff for pagination. Git --skip combined with --follow
can skip rename processing and lose earlier history; file pages must replay the
bounded prefix before slicing, while directory pages can use --skip directly.
Real-Git rename/new-HEAD tests and delayed-request Chrome tests cover this.
See docs/HISTORY_LOADING.md.
