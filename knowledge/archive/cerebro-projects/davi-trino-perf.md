---
scope: org
type: project
projects: [davi-trino-perf]
tags: [project-tracking]
status: active
---

# davi-trino-perf

Optimize DAVI Trino query performance by adding a persistent connection server. Currently each davi run creates a fresh TCP+SSL+OAuth connection (~23s per query). Goal: add a /api/trino/query endpoint to davi serve that holds a warm connection, auto-start the server on first query, support proxy_user. Target: match Captain MCP speed (~3-5s per query). Includes benchmarking infrastructure.

**Status:** active  
**Created:** 2026-04-07  **Updated:** 2026-04-07

## MPs
- lipy-davi

## Action Items (0/6 done)
- [ ] Write design spec for persistent Trino connection (davi serve endpoint + auto-start + proxy_user)
- [ ] Add /api/trino/query endpoint to davi serve (server.py) with persistent TrinoClient and proxy_user support
- [ ] Modify QueryExecutor to route through server when available, fallback to direct connection
- [ ] Auto-start davi serve from davi run if not already running
- [ ] Add benchmark command (davi trino benchmark) to measure and compare query times
- [ ] Test end-to-end: cold start, warm connection, token refresh, proxy_user, fallback

## One-Pager

# DAVI Persistent Trino Connection

**Date:** 2026-04-08
**Author:** Jesus Cortes
**Status:** Design

## Problem

Every `davi run` creates a fresh Python process that establishes a new TCP+SSL+OAuth2 Trino connection, runs the query, and tears everything down. Benchmarks on the same 10-row aggregation query:

| Path | Time | Why |
|------|------|-----|
| Captain MCP | ~3-5s | Long-lived MCP server, cached connection, JSON return |
| DAVI (warm token) | **23s** | New connection per invocation, DataFrame pipeline, output persistence |
| DAVI (cold SSO) | **144s** | Browser OAuth2 flow + everything above |

Both Captain and DAVI use the same Python `trino` library, same `fetchall()`, same Trino servers. The difference is process lifecycle: Captain keeps a warm connection in its MCP server. DAVI creates and destroys one per command.

## Design

### Architecture

```
davi run QueryService --query "SELECT ..."
    │
    ├── Is davi serve running on port 3284?
    │   ├── YES → POST http://localhost:3284/api/trino/query
    │   │         (server holds persistent TrinoClient, returns JSON)
    │   │         CLI converts JSON → DataFrame for service pipeline
    │   │
    │   └── NO → Auto-start davi serve in background
    │            Wait for server ready (poll /api/health, max 10s)
    │            Then POST as above
    │
    └── Server unreachable after retry?
        └── Fallback to direct connection (current behavior)
```

### Components

#### 1. Server-side: `/api/trino/query` endpoint (server.py)

New endpoint on the existing Flask server (port 3284):

```
POST /api/trino/query
Content-Type: application/json

{
  "query": "SELECT ...",
  "gateway": "holdem",       // optional, default from config
  "proxy_user": "trustim"    // optional, default from config
}

Response 200:
{
  "columns": ["datepartition", "cnt"],
  "rows": [{"datepartition": "2026-04-07-00", "cnt": 216914}, ...],
  "query_time_ms": 4200,
  "query_id": "20260408_..."
}

Response 4xx/5xx:
{
  "error": "...",
  "error_type": "AuthError|QueryError|ConnectionError",
  "query_id": "..." // if available
}
```

The server holds a persistent `TrinoClient` (similar to Captain's approach):
- Connection created lazily on first query
- Health-checked before reuse (SELECT 1)
- Auto-reconnects on stale/expired connection
- OAuth2 SSO triggered if needed (server runs in foreground-capable context)
- `proxy_user` applied via `SET SESSION li_authorization_user` once per connection
- Gateway and proxy_user loaded from `~/.davi/trino_config.json` as defaults

#### 2. Client-side: QueryExecutor server routing (query_executor.py)

Modify `_query_trino()` to try the server first:

```python
def _query_trino(self, query: str) -> pd.DataFrame:
    # Try server-accelerated path
    result = self._query_via_server(query)
    if result is not None:
        return result
    
    # Fallback: direct connection (current behavior)
    return self._query_trino_direct(query)
```

`_query_via_server()`:
- HTTP POST to `http://localhost:3284/api/trino/query`
- Timeout: 2s for connection, 300s for read (queries can be slow)
- On any connection error → return None (triggers fallback)
- On success → convert JSON rows to DataFrame
- No complex type scanning needed (server already sanitizes)

#### 3. Auto-start: server launch from query path

When `_query_via_server()` can't connect:
1. Call `_launch_serve_background(port=3284)` (already exists in main.py)
2. Poll `GET /api/health` every 500ms, max 10s
3. If server ready → retry the query through server
4. If timeout → fall back to direct connection

The auto-start only happens once per CLI session. A flag file (`~/.davi/server.pid`) tracks whether we already tried.

#### 4. Health endpoint

```
GET /api/health
Response 200: {"status": "ok", "trino_connected": true|false, "uptime_s": 123}
```

Used for auto-start readiness polling and general diagnostics.

#### 5. Benchmark command: `davi trino benchmark`

Runs a standardized query through both paths and reports:

```
$ davi trino benchmark
Running: SELECT datepartition, count(*) FROM tracking.scoreeventforregistration 
         WHERE datepartition >= '2026-04-01-00' GROUP BY datepartition LIMIT 5

Server path:  3.2s (connection reused)
Direct path: 22.8s (new connection)
Speedup:     7.1x
```

### Connection Lifecycle

```
davi serve starts
    │
    └── Flask server on :3284
        TrinoClient = None (lazy)
        
First POST /api/trino/query
    │
    ├── Create TrinoClient(gateway, proxy_user)
    │   └── OAuth2 SSO if needed (uses cached keychain token)
    │       SET SESSION li_authorization_user = 'proxy_user'
    │
    └── Execute query, return JSON
    
Subsequent queries
    │
    ├── Health check (SELECT 1)
    │   ├── OK → reuse connection
    │   └── FAIL → reconnect (may trigger SSO)
    │
    └── Execute query, return JSON

Token expires (~1hr)
    │
    └── Next query triggers reconnect
        OAuth2 uses cached keychain refresh token
        (no browser prompt if refresh token is valid)
```

### Files Changed

| File | Change |
|------|--------|
| `davi-cli/src/linkedin/davi/cli/server.py` | Add `/api/trino/query`, `/api/health` endpoints, TrinoClient management |
| `lipy-davi/src/linkedin/davi/core/query_executor.py` | Add `_query_via_server()` method, try-server-first logic |
| `davi-cli/src/linkedin/davi/cli/main.py` | Add `davi trino benchmark` command, refactor auto-start for reuse |
| `lipy-davi/src/linkedin/davi/core/trino_connection.py` | Extract shared constants (GATEWAYS, DEFAULT_GATEWAY) if needed |

### What We Don't Change

- Service pipeline (ServiceResult, Output, persistence) — untouched
- Widget layer — untouched  
- Session management — untouched
- Darwin/Jupyter path — untouched (only CLI path affected)

### Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Server process dies silently | Auto-start detects and restarts; PID file cleanup |
| OAuth2 token expires while server is running | Server reconnects on auth error, falls back to keychain refresh token |
| Port 3284 conflict | Check before auto-start; if occupied by non-DAVI process, skip server path |
| Query timeout on server blocks other requests | Flask runs with threaded=True (default); queries don't block each other |
| Proxy user mismatch across sessions | Server reads proxy_user from config on each connection setup |

### Success Criteria

- `davi run QueryService` with warm server: **< 8 seconds** for a 10-row aggregation (down from 23s)
- Second consecutive query: **< 5 seconds** (connection fully warm)
- Graceful fallback: if server is unavailable, behavior is identical to current
- `davi trino benchmark` shows measurable speedup
- Zero breaking changes to existing workflows

