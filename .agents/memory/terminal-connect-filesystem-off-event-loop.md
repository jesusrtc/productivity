# Terminal connection discovery runs off the event loop

`_term_ws_context` performs authentication, vault discovery, metadata reads,
and workspace access checks in `asyncio.to_thread` before WebSocket acceptance.
These reads can touch slow volumes; doing them on uvicorn's event loop stalls
all already-connected terminals when another terminal connects. Keep permission
checks before acceptance and socket affinity unchanged. Keep the PTY byte path
direct; only connection setup belongs in this worker.

`scripts/perf/lab_terminal_latency.py` measures authenticated local transport
with a disposable raw-echo terminal, both quiet and under metadata polling.
It does not measure browser paint or physical keyboard-to-screen latency.
