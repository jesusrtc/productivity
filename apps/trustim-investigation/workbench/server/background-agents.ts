/**
 * Background Investigation Agents — Run multiple Claude investigations concurrently.
 *
 * Each background investigation gets its own ClaudeBridge instance and writes results
 * to its session file. The foreground UI can monitor progress via WebSocket broadcasts.
 * Cross-investigation context is shared: each new investigation receives summaries
 * from all other active/recent investigations.
 */

import fs from 'fs'
import path from 'path'
import { ClaudeBridge, type BridgeEvent } from './bridge/claude-bridge.js'
import { isTrinoAuthError } from './bridge/event-translator.js'
import { sanitizeId, safePath } from './middleware/sanitize.js'
import type { ActionType, InvestigationNode, InvestigationEdge } from '../src/types/node.js'
import type { ChatMessage } from '../src/types/session.js'

type StoredActionType = ActionType
type StoredNode = InvestigationNode & { children_ids: string[] }
type StoredEdge = InvestigationEdge
type StoredMessage = ChatMessage

export interface BackgroundInvestigation {
  id: string
  sessionId: string
  alertId?: string
  prompt: string
  status: 'running' | 'completed' | 'failed' | 'aborted' | 'paused_auth'
  startedAt: string
  finishedAt?: string
  nodeCount: number
  lastActivity: string
  error?: string
}

interface ActiveAgent {
  bridge: ClaudeBridge
  investigation: BackgroundInvestigation
  /** Accumulated nodes for the session file */
  nodes: Record<string, StoredNode>
  edges: StoredEdge[]
  messages: StoredMessage[]
  /** Last node ID for edge linking */
  lastNodeId: string | null
  /** Text buffer for reasoning between tool calls */
  textBuffer: string
  /** Maps toolId → nodeId for parallel tool call matching */
  toolNodeMap: Map<string, string>
  summaryAdded?: boolean
  /** Saved context when paused for auth */
  pausedContext?: { failedQuery: string; nodeId: string }
  /** Session name for save/resume */
  sessionName?: string
}

let sessionsDir = ''
let projectDir = ''
const agents = new Map<string, ActiveAgent>()
/** Callback to broadcast WS messages to all connected clients */
let broadcastFn: ((msg: object) => void) | null = null

/** Generate conclusion message + Google Doc for a completed/stopped investigation */
async function finalizeInvestigation(agent: ActiveAgent, sessionName: string | undefined) {
  const allNodes = Object.values(agent.nodes) as any[]
  const completedNodes = allNodes.filter(n => n.status === 'completed' && n.result_summary)
  const failedNodes = allNodes.filter(n => n.status === 'failed')

  // Extract actual findings from assistant messages (Claude's analysis, not raw tool output)
  const assistantFindings = agent.messages
    .filter(m => m.role === 'assistant' && m.content.length > 80)
    .filter(m => !m.content.startsWith('Running:') && !m.content.startsWith('**Investigation progress**'))
    .map(m => m.content)

  // The final result text is the most important — it's Claude's conclusion
  const finalResult = assistantFindings.length > 0 ? assistantFindings[assistantFindings.length - 1] : ''

  // Add conclusion message if not already present
  const alreadyHasConclusion = agent.messages.some(m => m.content.includes('Investigation complete') || m.content.includes('Investigation stopped'))
  if (!alreadyHasConclusion) {
    const lines = [`**Investigation ${agent.investigation.status === 'aborted' ? 'stopped' : 'complete'}**`]
    if (finalResult) {
      lines.push('', finalResult.slice(0, 2000))
    } else if (completedNodes.length > 0) {
      lines.push('', '**Key findings:**')
      for (const n of completedNodes.slice(-8)) {
        lines.push(`- **${n.label}**: ${(n.result_summary || '').slice(0, 200)}`)
      }
    }
    agent.messages.push({
      id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      role: 'assistant',
      content: lines.join('\n'),
      timestamp: new Date().toISOString(),
      node_ids: [],
    })
  }

  // Create Google Doc — give Claude the raw data and let it synthesize a professional report
  const hasFindings = assistantFindings.length > 0 || completedNodes.length > 0
  if (hasFindings) {
    const docTitle = `🔍 Investigation: ${sessionName || 'Alert Investigation'} (${new Date().toISOString().split('T')[0]})`

    // Collect all raw data for Claude to synthesize
    const rawData: string[] = []

    // Include raw query results (the actual data tables)
    for (const n of completedNodes) {
      const raw = (n.result_raw || '').trim()
      const summary = (n.result_summary || '').trim()
      if (raw || summary) {
        rawData.push(`### Query: ${n.label || 'Unknown'}\n${summary}\n${raw ? `Raw output (first 3000 chars):\n${raw.slice(0, 3000)}` : ''}`)
      }
    }

    // Include Claude's analysis messages
    for (const msg of assistantFindings) {
      rawData.push(`### Agent Analysis:\n${msg}`)
    }

    const investigationData = rawData.join('\n\n---\n\n')

    const sessionId = agent.investigation.sessionId
    ;(async () => {
      const docBridge = new ClaudeBridge(projectDir)
      docBridge.maxTurns = 8
      let docUrl = ''
      let docId = ''
      docBridge.onEvent(ev => {
        if (ev.type === 'tool_end' && ev.data.toolResult) {
          const result = String(ev.data.toolResult)
          const urlMatch = result.match(/https:\/\/docs\.google\.com\/document\/d\/([^\s"\/]+)/)
          if (urlMatch) {
            docUrl = urlMatch[0]
            if (!docId) docId = urlMatch[1]
          }
          const idMatch = result.match(/"document_id"\s*:\s*"([^"]+)"/)
          if (idMatch && !docId) docId = idMatch[1]
        }
      })
      try {
        const prompt = `You are writing an investigation report for a Trust & Safety team. Create a Google Doc and write a professional, data-rich investigation report.

TITLE: "${docTitle}"

STEPS:
1. First, call create_google_docs_document with just the title (no content).
2. Then call write_to_google_docs_document with the document_id and structured elements.

REPORT FORMAT — follow this exact structure using structured elements with paragraph_style named_style_type for headings:

**Executive Summary** (HEADING_1)
- 2-3 sentence overview: what was investigated, key finding, primary concern
- Include specific numbers (volumes, percentages, comparisons to baseline)

**Numbered sections** (HEADING_2) for each major finding area:
- Historical Baseline — include data tables using the "table" element type with table_info
- Identified campaigns/patterns with specific IOCs (email patterns, IPs, user agents)
- Registration/activity breakdown tables
- Model & challenge performance tables

**SEV Assessment** (HEADING_2)
- Table comparing each threshold check with values and whether it triggers SEV
- Clear recommendation (SEV-N or No SEV) with reasoning

**Recommended Actions** (HEADING_2)
- 🔴 Immediate actions (restrict accounts, block IPs)
- 🟠 Short-term (rule changes, pattern detection)
- 🟡 Medium-term (model improvements, feature gaps)
- 🟢 Monitoring (what to watch)

FORMATTING RULES:
- Use tables (element type "table" with table_info: {data: [[headers], [row1], ...], header_style: {bold: true}}) for ALL tabular data
- Use HEADING_1 for title, HEADING_2 for sections, HEADING_3 for subsections
- Include specific numbers, percentages, and comparisons throughout
- Flag defense gaps with ⚠️
- Be specific about IOCs: email patterns, IP ranges, user agents, device fingerprints
- Do NOT include metadata about the investigation process (node counts, query counts, etc.)
- Write for a Trust & Safety analyst audience

RAW INVESTIGATION DATA:

${investigationData}

Now create the doc and write the report. Use multiple write_to_google_docs_document calls if needed (the elements array for a single call can be large). Return the document URL when done.`
        await docBridge.send(prompt)
      } catch {} finally { docBridge.abort() }
      if (docUrl) {
        agent.messages.push({
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          role: 'assistant',
          content: `**Investigation report published:** [Google Doc](${docUrl})`,
          timestamp: new Date().toISOString(),
          node_ids: [],
        })
        saveSession(agent, sessionName)
        broadcast({ type: 'bg_doc_created', payload: { sessionId, docUrl } })
      }
    })()
  }
}

export function initBackgroundAgents(sessDir: string, projDir: string, broadcast: (msg: object) => void) {
  sessionsDir = sessDir
  projectDir = projDir
  broadcastFn = broadcast
}

export function getActiveInvestigations(): BackgroundInvestigation[] {
  return Array.from(agents.values()).map(a => a.investigation)
}

export function getInvestigation(sessionId: string): BackgroundInvestigation | null {
  return agents.get(sessionId)?.investigation || null
}

/**
 * Build cross-investigation context from all active + recent sessions.
 * Gives each new investigation awareness of what others have found.
 */
function buildSharedContext(): string {
  const lines: string[] = []

  // Active investigations
  for (const [, agent] of agents) {
    if (agent.investigation.status !== 'running') continue
    const nodeSummaries = Object.values(agent.nodes)
      .filter((n: any) => n.status === 'completed' && n.result_summary)
      .map((n: any) => `  - ${n.label}: ${n.result_summary}`)
      .slice(-5) // Last 5 findings
    if (nodeSummaries.length > 0) {
      lines.push(`[Active investigation: ${agent.investigation.prompt.slice(0, 80)}]`)
      lines.push(...nodeSummaries)
    }
  }

  // Recent completed sessions (last 5)
  try {
    const files = fs.readdirSync(sessionsDir)
      .filter(f => f.endsWith('.json'))
      .map(f => {
        const stat = fs.statSync(path.join(sessionsDir, f))
        return { name: f, mtime: stat.mtimeMs }
      })
      .sort((a, b) => b.mtime - a.mtime)
      .slice(0, 5)

    for (const file of files) {
      try {
        const data = JSON.parse(fs.readFileSync(path.join(sessionsDir, file.name), 'utf-8'))
        if (!data.nodes || Object.keys(data.nodes).length === 0) continue
        // Skip if this session is currently active
        if (agents.has(data.id)) continue

        const findings = Object.values(data.nodes as Record<string, any>)
          .filter((n: any) => n.status === 'completed' && n.result_summary)
          .map((n: any) => `  - ${n.label}: ${n.result_summary}`)
          .slice(-3)
        if (findings.length > 0) {
          lines.push(`[Recent session: ${data.name || data.id}]`)
          lines.push(...findings)
        }
      } catch { /* skip corrupt files */ }
    }
  } catch { /* sessionsDir may not exist yet */ }

  if (lines.length === 0) return ''
  return [
    '',
    'CROSS-INVESTIGATION CONTEXT — Findings from other active and recent investigations:',
    ...lines,
    '',
    'Use this context to avoid duplicate work and cross-reference findings.',
  ].join('\n')
}

/**
 * Start a background investigation. Returns immediately.
 */
export function startBackgroundInvestigation(
  sessionId: string,
  prompt: string,
  alertId?: string,
  sessionName?: string,
): BackgroundInvestigation {
  // If already running for this session, abort old one first
  if (agents.has(sessionId)) {
    stopBackgroundInvestigation(sessionId)
  }

  const bridge = new ClaudeBridge(projectDir)
  bridge.maxTurns = 30 // Allow agent to run many skills — same as CLI

  const investigation: BackgroundInvestigation = {
    id: `bg-${sessionId}`,
    sessionId,
    alertId,
    prompt,
    status: 'running',
    startedAt: new Date().toISOString(),
    nodeCount: 0,
    lastActivity: new Date().toISOString(),
  }

  const agent: ActiveAgent = {
    bridge,
    investigation,
    nodes: {},
    edges: [],
    messages: [
      { id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, role: 'system', content: `Background investigation started.\n\n${prompt}`, timestamp: new Date().toISOString(), node_ids: [] },
    ],
    lastNodeId: null,
    textBuffer: '',
    toolNodeMap: new Map(),
    sessionName,
  }

  agents.set(sessionId, agent)

  // Create session file immediately so the frontend can find it
  saveSession(agent, sessionName)

  // Wire up bridge events
  const handler = (event: BridgeEvent) => {
    agent.investigation.lastActivity = new Date().toISOString()

    switch (event.type) {
      case 'text':
        if (event.data.text) {
          agent.textBuffer += event.data.text
          // Broadcast thinking status so the UI can show activity
          broadcast({ type: 'bg_agent_thinking', payload: { sessionId, text: event.data.text.slice(0, 100) } })
        }
        break

      case 'tool_start': {
        const nodeId = `node-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
        const toolName = event.data.toolName || 'unknown'
        const toolInput = event.data.toolInput || {}

        agent.nodes[nodeId] = {
          node_id: nodeId,
          parent_ids: agent.lastNodeId ? [agent.lastNodeId] : [],
          children_ids: [],
          label: buildLabel(toolName, toolInput),
          query: extractQuery(toolName, toolInput),
          status: 'running',
          action_type: toolName.includes('trino') ? 'query_execution' : 'mcp_tool_call',
          skill_name: null,
          tool_name: toolName.replace(/^mcp__captain__/, ''),
          source_tool: event.data.serverName || null,
          parameters: toolInput,
          confidence: 0,
          confidence_reasoning: '',
          confidence_override: false,
          result_summary: '',
          result_raw: '',
          displays: [],
          timestamp: new Date().toISOString(),
          duration_ms: 0,
          tags: [],
          reasoning: agent.textBuffer.trim() || '',
          investigator_notes: '',
          ipynb_cell_ref: null,
          input_prompt: null,
          input_choices: null,
          is_dead_end: false,
          subtree_collapsed: false,
          pinned: false,
        }

        // Update parent's children_ids
        if (agent.lastNodeId && agent.nodes[agent.lastNodeId]) {
          const parent = agent.nodes[agent.lastNodeId] as any
          if (!parent.children_ids) parent.children_ids = []
          parent.children_ids.push(nodeId)
        }

        if (agent.lastNodeId) {
          agent.edges.push({
            id: `edge-${agent.lastNodeId}-${nodeId}`,
            source: agent.lastNodeId,
            target: nodeId,
            relation: 'led_to',
          })
        }

        agent.investigation.nodeCount++

        // Add reasoning as assistant message if present
        if (agent.textBuffer.trim()) {
          agent.messages.push({
            id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}-r`,
            role: 'assistant',
            content: agent.textBuffer.trim(),
            timestamp: new Date().toISOString(),
            node_ids: [nodeId],
          })
        }
        // Add "running" message for the tool call
        const label = (agent.nodes[nodeId] as any).label || toolName
        agent.messages.push({
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}-s`,
          role: 'system',
          content: `Running: ${label}`,
          timestamp: new Date().toISOString(),
          node_ids: [nodeId],
        })

        agent.textBuffer = ''

        // Save immediately so the poll picks up new messages
        saveSession(agent, sessionName)

        // Broadcast to all clients so they can see progress
        broadcast({ type: 'bg_node_start', payload: { sessionId, nodeId, node: agent.nodes[nodeId] } })

        // Map toolId → nodeId for parallel tool matching
        const toolId = event.data.toolId || `auto-${Date.now()}`
        agent.toolNodeMap.set(toolId, nodeId)
        break
      }

      case 'tool_end': {
        // Match tool_end to the correct node via toolId
        const endToolId = event.data.toolId || ''
        const nodeId = agent.toolNodeMap.get(endToolId) || agent.toolNodeMap.values().next().value
        if (endToolId) agent.toolNodeMap.delete(endToolId)
        if (nodeId && agent.nodes[nodeId]) {
          const result = event.data.toolResult || event.data.error || ''
          const startTime = new Date((agent.nodes[nodeId] as any).timestamp).getTime()
          agent.nodes[nodeId] = {
            ...agent.nodes[nodeId],
            status: event.data.error ? 'failed' : 'completed',
            result_raw: result,
            result_summary: summarize(result),
            confidence: event.data.error ? 0 : 0.5,
            duration_ms: Date.now() - startTime,
          }
          agent.lastNodeId = nodeId

          // Add result message to chat
          const summary = (agent.nodes[nodeId] as any).result_summary || ''
          const nodeLabel = (agent.nodes[nodeId] as any).label || ''
          agent.messages.push({
            id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}-c`,
            role: 'assistant',
            content: `**${nodeLabel}** — ${event.data.error ? `Failed: ${event.data.error}` : summary || 'Completed'}`,
            timestamp: new Date().toISOString(),
            node_ids: [nodeId],
          })

          broadcast({ type: 'bg_node_complete', payload: { sessionId, nodeId, node: agent.nodes[nodeId] } })

          // Persist session after each node completes
          saveSession(agent, sessionName)

          // Detect Trino auth errors — pause investigation so user can re-auth
          const toolName = (agent.nodes[nodeId] as any).tool_name || ''
          if (toolName.includes('trino') && isTrinoAuthError(result)) {
            agent.investigation.status = 'paused_auth'
            agent.investigation.lastActivity = new Date().toISOString()
            const failedQuery = (agent.nodes[nodeId] as any).query || ''
            agent.pausedContext = { failedQuery, nodeId }
            agent.bridge.abort()
            saveSession(agent, sessionName)
            broadcast({
              type: 'bg_auth_required',
              payload: {
                sessionId,
                failedQuery,
                error: result.slice(0, 300),
                fixCommand: 'captain setup trino',
              },
            })
            break
          }

          // Check if all nodes are done — add mid-investigation summary if so
          const allNodes = Object.values(agent.nodes)
          const runningCount = allNodes.filter((n: any) => n.status === 'running').length
          const completedCount = allNodes.filter((n: any) => n.status === 'completed').length
          if (runningCount === 0 && completedCount >= 3 && !agent.summaryAdded) {
            agent.summaryAdded = true
            const findings = (allNodes.filter((n: any) => n.status === 'completed' && n.result_summary) as any[]).slice(-6)
            agent.messages.push({
              id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
              role: 'assistant',
              content: `**Investigation progress** — ${completedCount} queries completed.\n\n**Findings so far:**\n${findings.map((n: any) => `- **${n.label}**: ${(n.result_summary || '').slice(0, 150)}`).join('\n')}\n\n_Agent is still analyzing results..._`,
              timestamp: new Date().toISOString(),
              node_ids: [],
            })
            saveSession(agent, sessionName)
          }
        }
        break
      }

      case 'result':
        // Final text — add as assistant message
        if (event.data.text) {
          agent.messages.push({
            id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            role: 'assistant',
            content: event.data.text,
            timestamp: new Date().toISOString(),
            node_ids: [],
          })
        }
        break

      case 'error':
        if (event.data.error) {
          agent.investigation.error = event.data.error
        }
        break

      case 'done':
        agent.investigation.status = agent.investigation.error ? 'failed' : 'completed'
        agent.investigation.finishedAt = new Date().toISOString()
        bridge.offEvent(handler)

        // Finalize any nodes still in 'running' status (tool_end may not have fired)
        for (const nid of Object.keys(agent.nodes)) {
          const n = agent.nodes[nid] as any
          if (n.status === 'running') {
            n.status = agent.investigation.error ? 'failed' : 'completed'
            n.result_summary = n.result_summary || 'Agent finished'
            n.duration_ms = Date.now() - new Date(n.timestamp).getTime()
          }
        }

        // Finalize: conclusion + Google Doc (fire-and-forget from sync handler)
        finalizeInvestigation(agent, sessionName).then(() => {
          saveSession(agent, sessionName)
          broadcast({
            type: 'bg_investigation_done',
            payload: { sessionId, status: agent.investigation.status, nodeCount: agent.investigation.nodeCount, error: agent.investigation.error },
          })
        }).catch(() => {
          saveSession(agent, sessionName)
          broadcast({
            type: 'bg_investigation_done',
            payload: { sessionId, status: agent.investigation.status, nodeCount: agent.investigation.nodeCount, error: agent.investigation.error },
          })
        })

        // Remove from active agents after a delay — check identity to avoid deleting a newer agent
        const thisAgent = agent
        setTimeout(() => { if (agents.get(sessionId) === thisAgent) agents.delete(sessionId) }, 600000)
        break
    }
  }

  bridge.onEvent(handler)

  // Build shared context from other investigations
  const sharedContext = buildSharedContext()
  const systemPrompt = sharedContext
    ? `\n\nCROSS-INVESTIGATION CONTEXT:\n${sharedContext}`
    : undefined

  // Fire and forget — the bridge runs in the background
  bridge.send(prompt, systemPrompt).catch(err => {
    agent.investigation.status = 'failed'
    agent.investigation.error = String(err)
    agent.investigation.finishedAt = new Date().toISOString()
    saveSession(agent, sessionName)
    broadcast({
      type: 'bg_investigation_done',
      payload: { sessionId, status: 'failed', nodeCount: 0, error: String(err) },
    })
  })

  // Broadcast start
  broadcast({ type: 'bg_investigation_started', payload: { sessionId, prompt, alertId } })

  return investigation
}

export function stopBackgroundInvestigation(sessionId: string): boolean {
  const agent = agents.get(sessionId)
  if (!agent) return false

  agent.bridge.abort()
  agent.investigation.status = 'aborted'
  agent.investigation.finishedAt = new Date().toISOString()

  // Finalize any running nodes — bridge.abort() kills the process before 'done' fires
  for (const nid of Object.keys(agent.nodes)) {
    const n = agent.nodes[nid] as any
    if (n.status === 'running') {
      n.status = 'failed'
      n.result_summary = 'Manually terminated by investigator'
      n.duration_ms = Date.now() - new Date(n.timestamp).getTime()
    }
  }

  // Also finalize in the session file on disk (may have been written by saveSession earlier)
  try {
    const sanitized = sessionId.replace(/[^a-zA-Z0-9_-]/g, '')
    const sessionPath = path.resolve(sessionsDir, `${sanitized}.json`)
    if (!sessionPath.startsWith(path.resolve(sessionsDir))) throw new Error('Path traversal')
    if (fs.existsSync(sessionPath)) {
      const session = JSON.parse(fs.readFileSync(sessionPath, 'utf-8'))
      let changed = false
      for (const nid of Object.keys(session.nodes || {})) {
        if (session.nodes[nid].status === 'running') {
          session.nodes[nid].status = 'failed'
          session.nodes[nid].result_summary = 'Manually terminated by investigator'
          changed = true
        }
      }
      if (changed) fs.writeFileSync(sessionPath, JSON.stringify(session, null, 2))
    }
  } catch { /* ignore disk errors */ }

  // Finalize: add conclusion + Google Doc even when manually stopped
  finalizeInvestigation(agent, undefined).then(() => {
    saveSession(agent)
    broadcast({ type: 'bg_investigation_done', payload: { sessionId, status: 'aborted', nodeCount: agent.investigation.nodeCount } })
  }).catch(() => {
    saveSession(agent)
    broadcast({ type: 'bg_investigation_done', payload: { sessionId, status: 'aborted', nodeCount: agent.investigation.nodeCount } })
  })

  agents.delete(sessionId)
  return true
}

/**
 * Resume a background investigation that was paused due to Trino auth error.
 * Creates a new bridge and re-runs the failed query.
 */
export function resumeBackgroundInvestigation(sessionId: string): boolean {
  const agent = agents.get(sessionId)
  if (!agent || agent.investigation.status !== 'paused_auth') return false
  const { failedQuery } = agent.pausedContext || {}
  if (!failedQuery) return false

  agent.investigation.status = 'running'
  agent.investigation.lastActivity = new Date().toISOString()
  agent.pausedContext = undefined

  // Add resume message to chat
  agent.messages.push({
    id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    role: 'system',
    content: 'Trino authentication refreshed. Resuming investigation...',
    timestamp: new Date().toISOString(),
    node_ids: [],
  })

  const prompt = `The previous Trino query failed with an authentication error. Auth has been refreshed via \`captain setup trino\`. Re-run this query and continue the investigation:\n\`\`\`sql\n${failedQuery}\n\`\`\``

  // Create a new bridge to continue
  const bridge = new ClaudeBridge(projectDir)
  bridge.maxTurns = agent.bridge.maxTurns
  agent.bridge = bridge

  saveSession(agent, agent.sessionName)
  broadcast({ type: 'bg_investigation_resumed', payload: { sessionId } })

  // Re-use the same startBackgroundInvestigation event wiring by calling send
  // We need to wire up the same handler. Re-start via the existing mechanism:
  // Re-wire event handler on the new bridge (same logic as startBackgroundInvestigation)
  const sessionName = agent.sessionName
  const handler = (event: BridgeEvent) => {
    agent.investigation.lastActivity = new Date().toISOString()

    switch (event.type) {
      case 'text':
        if (event.data.text) {
          agent.textBuffer += event.data.text
          broadcast({ type: 'bg_agent_thinking', payload: { sessionId, text: event.data.text.slice(0, 100) } })
        }
        break

      case 'tool_start': {
        const nodeId = `node-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
        const toolName = event.data.toolName || 'unknown'
        const toolInput = event.data.toolInput || {}

        agent.nodes[nodeId] = {
          node_id: nodeId,
          parent_ids: agent.lastNodeId ? [agent.lastNodeId] : [],
          children_ids: [],
          label: buildLabel(toolName, toolInput),
          query: extractQuery(toolName, toolInput),
          status: 'running',
          action_type: toolName.includes('trino') ? 'query_execution' : 'mcp_tool_call',
          skill_name: null,
          tool_name: toolName.replace(/^mcp__captain__/, ''),
          source_tool: event.data.serverName || null,
          parameters: toolInput,
          confidence: 0,
          confidence_reasoning: '',
          confidence_override: false,
          result_summary: '',
          result_raw: '',
          displays: [],
          timestamp: new Date().toISOString(),
          duration_ms: 0,
          tags: [],
          reasoning: agent.textBuffer.trim() || '',
          investigator_notes: '',
          ipynb_cell_ref: null,
          input_prompt: null,
          input_choices: null,
          is_dead_end: false,
          subtree_collapsed: false,
          pinned: false,
        }

        if (agent.lastNodeId && agent.nodes[agent.lastNodeId]) {
          const parent = agent.nodes[agent.lastNodeId] as any
          if (!parent.children_ids) parent.children_ids = []
          parent.children_ids.push(nodeId)
        }

        if (agent.lastNodeId) {
          agent.edges.push({
            id: `edge-${agent.lastNodeId}-${nodeId}`,
            source: agent.lastNodeId,
            target: nodeId,
            relation: 'led_to',
          })
        }

        agent.investigation.nodeCount++

        if (agent.textBuffer.trim()) {
          agent.messages.push({
            id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}-r`,
            role: 'assistant',
            content: agent.textBuffer.trim(),
            timestamp: new Date().toISOString(),
            node_ids: [nodeId],
          })
        }
        const label = (agent.nodes[nodeId] as any).label || toolName
        agent.messages.push({
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}-s`,
          role: 'system',
          content: `Running: ${label}`,
          timestamp: new Date().toISOString(),
          node_ids: [nodeId],
        })

        agent.textBuffer = ''
        saveSession(agent, sessionName)
        broadcast({ type: 'bg_node_start', payload: { sessionId, nodeId, node: agent.nodes[nodeId] } })

        const toolId = event.data.toolId || `auto-${Date.now()}`
        agent.toolNodeMap.set(toolId, nodeId)
        break
      }

      case 'tool_end': {
        const endToolId = event.data.toolId || ''
        const nodeId = agent.toolNodeMap.get(endToolId) || agent.toolNodeMap.values().next().value
        if (endToolId) agent.toolNodeMap.delete(endToolId)
        if (nodeId && agent.nodes[nodeId]) {
          const result = event.data.toolResult || event.data.error || ''
          const startTime = new Date((agent.nodes[nodeId] as any).timestamp).getTime()
          agent.nodes[nodeId] = {
            ...agent.nodes[nodeId],
            status: event.data.error ? 'failed' : 'completed',
            result_raw: result,
            result_summary: summarize(result),
            confidence: event.data.error ? 0 : 0.5,
            duration_ms: Date.now() - startTime,
          }
          agent.lastNodeId = nodeId

          const summary = (agent.nodes[nodeId] as any).result_summary || ''
          const nodeLabel = (agent.nodes[nodeId] as any).label || ''
          agent.messages.push({
            id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}-c`,
            role: 'assistant',
            content: `**${nodeLabel}** — ${event.data.error ? `Failed: ${event.data.error}` : summary || 'Completed'}`,
            timestamp: new Date().toISOString(),
            node_ids: [nodeId],
          })

          broadcast({ type: 'bg_node_complete', payload: { sessionId, nodeId, node: agent.nodes[nodeId] } })
          saveSession(agent, sessionName)

          // Detect Trino auth errors again — pause if auth expired mid-resume
          const tn = (agent.nodes[nodeId] as any).tool_name || ''
          if (tn.includes('trino') && isTrinoAuthError(result)) {
            agent.investigation.status = 'paused_auth'
            agent.investigation.lastActivity = new Date().toISOString()
            const fq = (agent.nodes[nodeId] as any).query || ''
            agent.pausedContext = { failedQuery: fq, nodeId }
            agent.bridge.abort()
            saveSession(agent, sessionName)
            broadcast({
              type: 'bg_auth_required',
              payload: { sessionId, failedQuery: fq, error: result.slice(0, 300), fixCommand: 'captain setup trino' },
            })
            break
          }
        }
        break
      }

      case 'result':
        if (event.data.text) {
          agent.messages.push({
            id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            role: 'assistant',
            content: event.data.text,
            timestamp: new Date().toISOString(),
            node_ids: [],
          })
        }
        break

      case 'error':
        if (event.data.error) {
          agent.investigation.error = event.data.error
        }
        break

      case 'done':
        agent.investigation.status = agent.investigation.error ? 'failed' : 'completed'
        agent.investigation.finishedAt = new Date().toISOString()
        bridge.offEvent(handler)

        for (const nid of Object.keys(agent.nodes)) {
          const n = agent.nodes[nid] as any
          if (n.status === 'running') {
            n.status = agent.investigation.error ? 'failed' : 'completed'
            n.result_summary = n.result_summary || 'Agent finished'
            n.duration_ms = Date.now() - new Date(n.timestamp).getTime()
          }
        }

        finalizeInvestigation(agent, sessionName).then(() => {
          saveSession(agent, sessionName)
          broadcast({
            type: 'bg_investigation_done',
            payload: { sessionId, status: agent.investigation.status, nodeCount: agent.investigation.nodeCount, error: agent.investigation.error },
          })
        }).catch(() => {
          saveSession(agent, sessionName)
          broadcast({
            type: 'bg_investigation_done',
            payload: { sessionId, status: agent.investigation.status, nodeCount: agent.investigation.nodeCount, error: agent.investigation.error },
          })
        })

        const thisAgent2 = agent
        setTimeout(() => { if (agents.get(sessionId) === thisAgent2) agents.delete(sessionId) }, 600000)
        break
    }
  }

  bridge.onEvent(handler)

  const sharedContext = buildSharedContext()
  const systemPrompt = sharedContext
    ? `\n\nCROSS-INVESTIGATION CONTEXT:\n${sharedContext}`
    : undefined

  bridge.send(prompt, systemPrompt).catch(err => {
    agent.investigation.status = 'failed'
    agent.investigation.error = String(err)
    agent.investigation.finishedAt = new Date().toISOString()
    saveSession(agent, sessionName)
    broadcast({
      type: 'bg_investigation_done',
      payload: { sessionId, status: 'failed', nodeCount: agent.investigation.nodeCount, error: String(err) },
    })
  })

  return true
}

function saveSession(agent: ActiveAgent, sessionName?: string) {
  if (!sessionsDir) return
  const session = {
    id: agent.investigation.sessionId,
    name: sessionName || `Alert Investigation`,
    created_at: agent.investigation.startedAt,
    updated_at: new Date().toISOString(),
    starting_input: agent.investigation.prompt,
    nodes: agent.nodes,
    edges: agent.edges,
    messages: agent.messages,
    skills_used: [],
    tools_used: [],
    linked_sessions: [],
  }
  try {
    const sessionPath = safePath(sessionsDir, `${sanitizeId(agent.investigation.sessionId)}.json`)
    if (!sessionPath) return
    fs.writeFileSync(sessionPath, JSON.stringify(session, null, 2))
  } catch { /* ignore write errors */ }
}

function broadcast(msg: object) {
  if (broadcastFn) broadcastFn(msg)
}

let _autoLabelCache: { name: string; table: string }[] | null = null
let _autoLabelCacheTime = 0

function matchAutomationLabel(query: string): string | null {
  // Cache automation labels for 60s
  if (!_autoLabelCache || Date.now() - _autoLabelCacheTime > 60000) {
    _autoLabelCache = []
    try {
      const dir = path.join(sessionsDir, '..', '.automations')
      const files = fs.readdirSync(dir).filter(f => f.endsWith('.json'))
      for (const f of files) {
        try {
          const data = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf-8'))
          if (data.exec_type !== 'trino_query' || !data.exec_body) continue
          const fromMatch = data.exec_body.match(/FROM\s+(\S+)/i)
          if (fromMatch) _autoLabelCache.push({ name: data.name, table: fromMatch[1].toLowerCase() })
        } catch { /* skip */ }
      }
    } catch { /* dir may not exist */ }
    _autoLabelCacheTime = Date.now()
  }
  const ql = query.toLowerCase()
  for (const { name, table } of _autoLabelCache) {
    if (ql.includes(table)) return name
  }
  return null
}

function buildLabel(toolName: string, input: Record<string, unknown>): string {
  const clean = toolName.replace(/^mcp__captain__/, '')
  if (clean === 'execute_trino_query') {
    const q = String(input.query || '')
    const autoName = matchAutomationLabel(q)
    if (autoName) return autoName
    const ql = q.toLowerCase()
    if (ql.includes('registrationevent')) return 'Query: Registration Events'
    if (ql.includes('scoreevent')) return 'Query: Score Events'
    if (ql.includes('challengeevent')) return 'Query: Challenge Events'
    if (ql.includes('denialevent')) return 'Query: Denial Events'
    if (ql.includes('describe')) return 'Describe Table'
    const tableMatch = q.match(/FROM\s+(\S+)/i)
    return tableMatch ? `Query: ${tableMatch[1].split('.').pop()}` : `Query: ${clean}`
  }
  return clean
}

function extractQuery(toolName: string, input: Record<string, unknown>): string {
  if (toolName.includes('trino') && input.query) return String(input.query)
  if (input.query) return String(input.query)
  if (input.jql) return String(input.jql)
  return JSON.stringify(input).slice(0, 200)
}

function summarize(result: string): string {
  if (!result) return 'No results'
  const lines = result.split('\n').filter(l => l.trim())
  if (lines.length <= 3) return lines.join(' ').slice(0, 200)
  return `${lines.length} rows returned. ${lines[0].slice(0, 100)}...`
}
