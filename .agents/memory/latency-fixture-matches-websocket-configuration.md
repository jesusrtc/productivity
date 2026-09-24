# Match production WebSocket settings in latency fixtures

`core.main.run()` disables permessage-deflate. A fixture that calls
`uvicorn.Config` directly must pass `ws_per_message_deflate=False`; Uvicorn's
ordinary default differs. The navigation/typing fixture also matches the 5-second
graceful shutdown timeout. Use `--websocket-deflate` only as a labeled diagnostic
comparison, and verify Chrome's actual handshake rather than assuming negotiation.
Keep all older failures, and do not claim that changing a fixture setting fixed
an unresolved production issue.
