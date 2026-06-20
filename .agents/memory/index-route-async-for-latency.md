# Index route stays async for latency

The `/` HTML route in `core/src/core/main.py` must stay `async def`.
It serves cached bytes on the hot path and should not run in FastAPI's sync
thread pool, because terminal polling endpoints intentionally use sync `def`
for blocking tmux subprocess work. If `/` is sync too, page loads can queue
behind `tmux capture-pane`/status polling and show 50ms+ spikes even though
the cached response itself is sub-millisecond.
