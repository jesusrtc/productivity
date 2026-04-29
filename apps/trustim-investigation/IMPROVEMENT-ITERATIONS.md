# Workbench Architecture

## Overview

The Juniper workbench is a modular Trust & Safety SOAR platform: React frontend + Express/WebSocket backend with a Claude Code bridge for AI-powered investigations.

## Server Architecture

```
server/
  index.ts                  # ~80-line bootstrap: wire deps, mount routers, start server
  domains/
    alerts/                 # IRIS alert CRUD, sync, related-alert scoring
      router.ts             # 10 routes: CRUD + sync/status/start/stop + related
      service.ts            # Filtering, related-scoring (IOC + time + incident matching)
      store.ts              # File-per-alert persistence
    sessions/               # Investigation session lifecycle
      router.ts             # 5 routes: list, get, save, delete, cleanup
      service.ts            # Cascade delete (→ notebooks, IOCs, alerts, investigations), severity scoring
      store.ts              # File-per-session persistence
    automations/            # Skill-parsed + custom + DAVI automations
      router.ts             # 8 routes: CRUD + run + migrate
      service.ts            # Skill SQL parsing, 4 execution pipelines (trino, davi, python, claude)
      store.ts              # 3-way merge: skill-parsed + custom JSON + DAVI widgets (cached 30s)
    playbooks/              # DAG-based workflow definitions
      router.ts             # 8 routes: CRUD + run + execution CRUD
      service.ts            # Entry node computation, validation
      store.ts              # File-per-playbook persistence
    investigations/         # Background headless Claude investigations
      router.ts             # 4 routes: list, get, start, stop
    notebooks/              # Investigation audit trails (ipynb)
      router.ts             # 2 routes: append cells, download
      store.ts              # Notebook file management
    iocs/                   # Cross-session IOC tracking
      router.ts             # 3 routes: list, add, check
      store.ts              # Single-file JSON store
    skills/                 # Investigation skill discovery
      router.ts             # 2 routes: list, get-by-name
      store.ts              # SKILL.md frontmatter parsing, hot-reload watcher
    setup/                  # Health, prerequisites, bridge config, MCP discovery
      router.ts             # 7 routes: health, setup/check, recheck, bridge status/config, MCP tools
    misc/                   # Templates, queries, export, seed-demo
      router.ts             # 7 routes: templates CRUD, query history, bulk export, seed
  bridge/
    claude-bridge.ts        # Claude CLI subprocess: spawn, stream-json parse, abort
    event-translator.ts     # Agent events → graph node events (scaffolding detection, tool labeling, result summarization)
  ws/
    handler.ts              # WebSocket connections, broadcast, per-socket bridge management
  middleware/
    sanitize.ts             # Path traversal prevention (sanitizeId, safePath)
  background-agents.ts      # Concurrent headless investigation lifecycle + Google Doc generation
  playbook-runner.ts        # DAG executor: topological sort, input resolution, condition evaluation
  inresponse-sync.ts        # IRIS REST API poller (4 plans, dedup, severity mapping, IOC extraction)
  condition-evaluator.ts    # Pure playbook edge condition evaluation (7 operators)
```

## Frontend Architecture

```
src/
  api/                      # Typed API client (0 raw fetch calls in components/stores)
    client.ts               # Base: typed fetch wrapper, centralized error toasts
    sessions.ts, alerts.ts, automations.ts, playbooks.ts,
    investigations.ts, setup.ts, misc.ts
  types/                    # Shared TypeScript types (7 files)
    node.ts                 # InvestigationNode (30 fields), InvestigationEdge, ActionType, NodeStatus
    session.ts              # Session, SessionSummary, ChatMessage
    alert.ts                # Alert, AlertSummary, AlertFilters, AlertIOC
    automation.ts           # Automation, ParamSchema, ExecutionResult
    playbook.ts             # Playbook, PlaybookNode, PlaybookEdge, PlaybookExecution
    skill.ts                # Skill, SkillInventory, TraceEvent, ViewMode
  store/                    # 7 Zustand stores (all use API client)
    graph.ts                # Nodes, edges, selection, auto-investigate, view mode
    session.ts              # Current session, tab snapshots, chat context
    alert.ts                # Alert CRUD, IRIS sync, filtering
    automation.ts           # Automation CRUD + execution
    playbook.ts             # Playbook CRUD + execution + polling
    history.ts              # Undo/redo stack
    toast.ts                # Notification queue
  hooks/                    # 9 hooks
    useChatAgentHandler.ts  # Agent event → graph node translation (node_start, node_complete, done)
    useChatCommands.ts      # Slash command handlers (/run, /playbook, #note)
    useChatFirstMessage.ts  # First-message setup: route detection, root node, skill hints
    useTabManagement.ts     # Tab open/close/switch with snapshot/restore
    useKeyboardShortcuts.ts # 15+ keyboard shortcuts
    useBackgroundPolling.ts # Background investigation + session polling
    useAutoInvestigate.ts   # Autonomous investigation branching (real + demo modes)
    useAutoSave.ts          # Debounced session persistence
    useWebSocket.ts         # WebSocket connection with reconnect + shared singleton
  components/
    chat/                   # ChatPanel (~500) + 10 sub-components
    graph/                  # NodeDetailDrawer (~280) + GraphPanel + 14 sub-components
    alerts/                 # AlertQueue, AlertDetail, RelatedAlertsSidebar
    playbooks/              # PlaybookLibrary, PlaybookEditor, PlaybookDrawer, PlaybookProgress
    automations/            # AutomationLibrary
    home/                   # HomePage (dashboard, stats, ROI)
    setup/                  # SetupScreen (prerequisite verification)
    layout/                 # SessionBar, overlays, panels
    export/, skills/, trace/
  utils/                    # 12 utility modules
    claude-adapter.ts       # WebSocketAdapter + SimulatedAdapter + confidence inference
    export.ts               # 9 export formats (JSON, ipynb, Slack, Jira, Google Docs, timeline, tree)
    investigation-router.ts # Keyword → skill routing with confidence scoring
    sev-checker.ts          # Automated SEV threshold checking
    cohort-extraction.ts    # Regex extraction of IPs, member IDs, domains
    + layout, sql-highlight, pattern-detection, convergence-detection, etc.
  data/                     # Static data extracted from hooks
    investigation-steps.ts  # SQL templates for simulated mode
    investigation-dimensions.ts  # 8 investigation checklist dimensions
```

## Key Design Decisions

- **Domain-first vertical slices**: Each domain (alerts, sessions, automations, etc.) is self-contained with router → service → store layers. One agent can own a domain entirely.
- **Per-domain stores, NOT generic `Storage<T>`**: Each domain has different storage patterns (session deletion cascades to 4 domains, automation listing merges 3 sources, IOC storage is a single JSON file).
- **Bridge interface abstraction**: `ClaudeBridge` is in `bridge/` with a clean event-based interface. The event-translator converts raw Claude events to graph-node events. Can be swapped for LangGraph or Agent SDK.
- **Constructor injection for cross-domain deps**: Services that depend on other domains receive them as factory params. Wiring happens in `index.ts`.
- **Typed API client**: All frontend API calls go through `src/api/`. Centralized error handling shows toasts on failure. No raw `fetch('/api/...')` in components or stores.

## Cross-Domain Dependencies

```
sessions.delete → stopBackgroundInvestigation (investigations)
                → loadIocDb/saveIocDb (iocs)
                → unlink from alert files (alerts)
                → delete notebook (notebooks)

playbooks.run   → findAutomation (automations)
                → broadcast (ws)
                → writes session file (sessions)

bridge/event-translator → getAllAutomations (automations) for tool label matching
```

## WebSocket Protocol

**Client → Server**: `agent_message`, `agent_abort`, `save_session`, `node_created/updated`, `edge_created`, `chat_message`, `ping`

**Server → Client**: `connected`, `agent_init`, `agent_text`, `agent_tokens`, `agent_node_start`, `agent_node_complete`, `agent_done`, `agent_error`, `agent_aborted`, `session_saved`, `skills_changed`, `bg_node_start`, `bg_node_complete`, `bg_investigation_done`, `bg_doc_created`, `pong`

## Test Coverage

197 tests across 16 test files covering: condition evaluation, edge normalization, node defensive guards, playbook execution (topological sort, input resolution), progress tracking, session tab snapshot/restore, alert service (related scoring), session service (cascade delete, severity), event-translator (scaffolding detection, tool labeling, result summarization), API client (error handling, typed responses), investigation checklist, IOC extraction.

## Modularization Complete

All 5 phases of the strangler-fig migration are done:
- Phase 1: Server monolith (2,165 lines) → 80-line bootstrap + 10 domain routers
- Phase 2: Service + store layers for all high-value domains
- Phase 3: Typed frontend API client, 0 raw fetch calls
- Phase 4: ChatPanel 1,438→494, NodeDetailDrawer 1,187→276
- Phase 5: App.tsx 915→348, useAutoInvestigate 683→329, remaining store extractions, test coverage to 197

---

## What's Next

### Trino Auth Error Handling
When Trino queries fail with authentication errors, the system should detect the failure, pause the investigation (both foreground and background), and prompt the user to re-authenticate by running Captain MCP setup for Trino (`captain setup trino`). After authentication, a "Retry" action should re-send the failed query without restarting the entire investigation. This affects the Claude bridge event handling, background agent lifecycle, and the ChatPanel error display.

### FastAPI Backend Migration
The Express server is now modular enough to port domain-by-domain. The target is a FastAPI + Python backend that serves the identical API contract (the React frontend doesn't change). Each domain's router → service → store maps directly to a FastAPI router + Pydantic models + async file I/O. The typed API client (`src/api/`) defines the exact contract to match. The bridge needs to become `asyncio.create_subprocess_exec` instead of Node's `child_process.spawn`.

### LangChain Integration
Add LangChain chains for specific structured tasks: an investigation router chain (replace keyword matching with LLM-powered routing), a result analysis chain (replace heuristic `inferConfidenceFromResult` with structured output), and a SEV assessment chain (replace regex threshold matching with Pydantic-validated assessment). These run alongside the existing Claude bridge, not replacing it — they handle specific subtasks where structured output parsing adds value.

### LangGraph Playbook Engine
Replace `playbook-runner.ts` with a LangGraph `StateGraph`. Each playbook node type (automation, prompt, condition) maps to a LangGraph node. Conditional edges use the existing `condition-evaluator.ts` logic. Parallel entry nodes use LangGraph's `Send` API. Human approval gates use `interrupt`. Checkpointing via SQLite replaces the current file-locking approach. The `PlaybookExecution` type already matches LangGraph's state model.

### Background Agent → Agent SDK
Replace the `background-agents.ts` Claude CLI subprocess approach with Anthropic's Agent SDK. This gives direct API access (no subprocess management), native MCP server support, persistent session state, and concurrent investigations without process-level bottlenecks. The event-translator layer stays — it just receives events from the SDK instead of parsing NDJSON from stdout.

### Production Hardening (if deployed beyond localhost)
- SQLite/Postgres persistence instead of JSON files (swap the store.ts layers)
- Authentication middleware (OAuth2/JWT)
- Per-user rate limiting and session isolation
- Structured logging (replace console.log/error with pino or structlog)
- Atomic file writes (write to temp + rename) for crash safety
- Input validation on automation execution (whitelist exec_types, sanitize SQL parameters)
