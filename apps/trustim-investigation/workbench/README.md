# Investigation Workbench

Visual decision graph interface for agentic trust and safety investigations. Connects to Claude Code and a repository of investigation skills through a conversational chat panel (left) while simultaneously visualizing agent reasoning as an interactive decision graph (right).

## Quick Start

```bash
cd workbench
npm install
npm run dev
```

This starts both the backend server (port 3100) and the Vite dev server (port 5173). Open http://localhost:5173.

## Architecture

```
workbench/
  src/
    types/           # Core data models (node, session, skill)
    store/           # Zustand state (graph, session)
    components/
      chat/          # Chat panel (graph-aware, skill autocomplete)
      graph/         # Decision graph (React Flow, custom nodes, search)
      layout/        # Session bar, MCP status, stats, keyboard help
      skills/        # Skill browser
      trace/         # Trace log view
      export/        # Export dialog (4 formats)
    hooks/           # WebSocket, auto-save, auto-investigate
    utils/           # Layout engine, export formats, Claude adapter
  server/            # Express + WebSocket server
```

## Features

### Decision Graph
- DAG visualization with 6 node types and 3 edge types
- Severity color coding (benign/low/medium/high/critical) with upward propagation
- Real-time node creation as the agent acts
- Heatmap view for instant severity scanning
- Collapse/expand subtrees, mark dead ends, flag for review
- Node search, manual repositioning, stable auto-layout
- Context menu with severity override, branch export, convergence node creation

### Chat Panel
- Graph-aware: click a node to branch from it
- Skill autocomplete: type `/` for skill suggestions
- Annotation nodes via `#note`
- Enhanced markdown (tables, code blocks, lists)
- Tool/skill metadata badges
- Activity indicator with operation name

### Sessions
- Auto-save on every change
- Create, load, close, delete, rename
- Import previously exported investigations (read-only)
- Quick-start templates (Alert Triage, IOC Lookup, etc.)
- Drag-and-drop JSON import
- Multi-session via WebSocket sync

### Export (4 formats)
- **Full JSON**: Complete graph + chat + metadata
- **Notebook**: Jupyter-compatible ipynb trace
- **Summary**: Human-readable markdown
- **Playbook**: Decision path contribution with critical path extraction

### Skills Integration
- Reads from the `skills/` directory on the filesystem
- Organized by attack vector (investigation vs. action skills)
- Hot-reload: edit SKILL.md files and changes are available immediately
- Tool requirements checker warns about missing MCP connections

### Auto-Investigate (R24)
- Autonomous node spawning from any node
- Configurable depth limit (5) and node budget (15)
- Follows high-severity branches deeper
- Stop button in the graph panel

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `?` | Toggle keyboard help |
| `Esc` | Close detail drawer |
| `Cmd+Shift+S` | Toggle Skills browser |
| `Cmd+Shift+M` | Toggle MCP status |
| `/` in chat | Skill autocomplete |
| `#note` in chat | Create annotation node |
| Right-click node | Context menu |
| Double-click session name | Rename |

## Claude Code Integration

The Workbench uses a pluggable adapter pattern (`src/utils/claude-adapter.ts`). The current `SimulatedAdapter` generates demo data. To connect a real Claude Code instance:

```typescript
import { setAdapter } from './utils/claude-adapter'
import { RealClaudeAdapter } from './your-adapter'

setAdapter(new RealClaudeAdapter({ /* config */ }))
```

The `ClaudeAdapter` interface requires:
- `sendMessage(content, context?)` - Send to agent, events fire as it processes
- `abort()` - Cancel in-progress execution
- `onEvent(handler)` / `offEvent(handler)` - Subscribe to agent events

## MCP Tool Discovery

The server reads MCP configuration from `~/.claude/settings.json` and `settings.local.json`. If no config is found, it falls back to known Captain MCP tools. The MCP status panel shows connection health and warns when a skill requires tools that aren't connected.

## Tech Stack

- React 18 + TypeScript + Vite (code-split chunks)
- @xyflow/react (React Flow v12) + dagre for graph layout
- Zustand for state management
- Tailwind CSS for styling
- Express + WebSocket for the backend
- JSON file persistence for sessions
