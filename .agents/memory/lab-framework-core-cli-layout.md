# Lab framework CLI layout

The installable `lab` CLI lives as its own Python package under `core/cli/`.
The FastAPI backend/UI lives in `core/` as package `core`.

Do not put the CLI under `core/src/core`; the server imports `lab` as a sibling
dependency so CLI/state code stays separate from backend code. Do not put
framework internals under root `apps/`; that name is reserved for
workspace/client apps.
