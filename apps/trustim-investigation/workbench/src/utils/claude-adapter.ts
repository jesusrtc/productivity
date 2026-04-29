/**
 * Claude Code Adapter — Integration bridge between the Workbench and Claude Code.
 *
 * Two adapters:
 * 1. WebSocketAdapter — Connects to the backend server which runs a real `claude`
 *    subprocess. Tool calls from the agent become graph node events in real time.
 * 2. SimulatedAdapter — Fallback for demo/development when claude CLI is not available.
 *
 * The App checks /api/bridge/status on startup and selects the appropriate adapter.
 */

import type { ActionType, InvestigationNode } from '../types'

/** Events emitted by the adapter during agent execution */
export interface AgentEvent {
  type: 'node_start' | 'node_complete' | 'node_error' | 'message' | 'tool_call' | 'skill_load' | 'done'
  nodeId?: string
  data: {
    actionType?: ActionType
    label?: string
    query?: string
    skillName?: string
    toolName?: string
    sourceTool?: string
    parameters?: Record<string, unknown>
    resultSummary?: string
    resultRaw?: string
    confidence?: number
    confidenceReasoning?: string
    reasoning?: string
    durationMs?: number
    message?: string
    error?: string
    success?: boolean
    /** True when this tool call is a parallel sibling (same parent as previous) */
    isParallelSibling?: boolean
    /** Tool call ID for matching node_start to node_complete in parallel tool calls */
    toolId?: string
  }
}

export type AgentEventHandler = (event: AgentEvent) => void

/** Interface for Claude Code adapters */
export interface ClaudeAdapter {
  sendMessage(
    content: string,
    context?: {
      nodeId?: string
      query?: string
      resultSummary?: string
      resultRaw?: string
      parentChain?: Partial<InvestigationNode>[]
    }
  ): Promise<void>
  abort(): void
  isReady(): boolean
  onEvent(handler: AgentEventHandler): void
  offEvent(handler: AgentEventHandler): void
}

// ---------------------------------------------------------------------------
// WebSocketAdapter — Real Claude Code integration via the backend bridge
// ---------------------------------------------------------------------------

/**
 * Sends user messages to the server via WebSocket, which forwards them to
 * a real `claude` subprocess. Tool calls and results stream back as events
 * that the ChatPanel translates into graph nodes.
 */
export class WebSocketAdapter implements ClaudeAdapter {
  private handlers: Set<AgentEventHandler> = new Set()
  private ws: WebSocket | null = null
  private resolveMessage: (() => void) | null = null
  private wsMessageHandler: ((event: MessageEvent) => void) | null = null
  private wsCloseHandler: (() => void) | null = null
  private listenerSocket: WebSocket | null = null

  /** Connect to the existing WebSocket (shared with useWebSocket hook) */
  setWebSocket(ws: WebSocket) {
    if (this.ws === ws) return
    this.detachListenerSocket()
    this.ws = ws
  }

  async sendMessage(
    content: string,
    context?: { nodeId?: string; query?: string; resultSummary?: string; resultRaw?: string; parentChain?: Partial<InvestigationNode>[] }
  ): Promise<void> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.emit({
        type: 'node_error',
        data: { error: 'Not connected to server. Check that the backend is running.' },
      })
      // Emit done so registered handlers (e.g., auto-investigate stepHandler) can clean up
      this.emit({ type: 'done', data: {} })
      return
    }

    // Build system prompt with FULL investigation context — all completed nodes + current branch
    let systemPrompt: string | undefined
    {
      const parts: string[] = []

      // Force-refresh from server to get ALL node data (including bg agent + playbook nodes)
      try {
        const { useGraphStore } = await import('../store/graph')
        const { useSessionStore } = await import('../store/session')
        const session = useSessionStore.getState().currentSession
        if (session?.id) {
          try {
            const { sessionsApi } = await import('../api')
            const freshData = await sessionsApi.get(session.id) as any
            if (freshData?.nodes) {
              const edges = (freshData.edges || []).map((e: any) => ({ id: e.id || `edge-${e.source}-${e.target}`, source: e.source, target: e.target, relation: e.relation || 'led_to' }))
              useGraphStore.getState().loadGraph(freshData.nodes, edges)
              if (freshData.messages) {
                // Merge server messages with local messages to preserve unsaved user input
                const localMsgs = session.messages || []
                const serverIds = new Set((freshData.messages as any[]).map((m: any) => m.id))
                const localOnly = localMsgs.filter(m => !serverIds.has(m.id))
                const merged = [...freshData.messages, ...localOnly]
                useSessionStore.setState({ currentSession: { ...session, messages: merged } })
              }
            }
          } catch { /* server may be down */ }
        }

        const nodes = useGraphStore.getState().nodes
        const allNodes = Object.values(nodes)
          .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())

        if (session?.name) {
          parts.push(`## Current Investigation: ${session.name}`)
        }

        // Include ALL node results — completed, failed, and running
        if (allNodes.length > 0) {
          parts.push(`\n## Investigation Nodes (${allNodes.length} total):`)
          for (const n of allNodes) {
            const status = n.status === 'completed' ? '✓' : n.status === 'failed' ? '✗' : n.status === 'running' ? '...' : '○'
            const source = n.source_tool === 'playbook' ? ' [playbook]' : ''
            const summary = n.result_summary || n.result_raw?.slice(0, 500) || ''
            parts.push(`${status} **${n.label}**${source}: ${summary.slice(0, 500)}`)
          }
        }

        // Include recent chat for conversational context
        const recentMessages = (useSessionStore.getState().currentSession?.messages || [])
          .filter(m => m.role !== 'system')
          .slice(-10)
        if (recentMessages.length > 0) {
          parts.push(`\n## Recent Chat:`)
          for (const m of recentMessages) {
            parts.push(`${m.role === 'user' ? 'Investigator' : 'Agent'}: ${m.content.slice(0, 300)}`)
          }
        }
      } catch { /* store import may fail in test */ }

      // Include specific branch context if continuing from a node
      if (context?.nodeId) {
        const resultData = context.resultRaw
          ? context.resultRaw.slice(0, 3000)
          : context.resultSummary || 'N/A'
        parts.push(`\n## Current Branch — Previous Step`)
        parts.push(`Query: ${context.query || 'N/A'}`)
        parts.push(`Results: ${resultData}`)
      }

      parts.push(`\n## Instructions — ACTION FIRST:`)
      parts.push(`1. You have the FULL investigation context above. Use it.`)
      parts.push(`2. Run a follow-up query using execute_trino_query. Do NOT ask clarifying questions.`)
      parts.push(`3. Always prefix with: SET SESSION li_authorization_user = 'trustim'`)
      parts.push(`4. Do not fabricate data. If results are empty, say so.`)

      if (parts.length > 2) {
        systemPrompt = parts.join('\n')
      }
    }

    // Clean up any previous listener before registering a new one
    this.cleanup()

    // Register listener BEFORE sending to avoid race condition
    return new Promise<void>((resolve) => {
      this.resolveMessage = resolve
      const socket = this.ws!
      this.listenerSocket = socket

      this.wsMessageHandler = (event: MessageEvent) => {
        try {
          const msg = JSON.parse(event.data)
          this.handleServerEvent(msg)
        } catch {
          // Ignore non-JSON messages
        }
      }

      this.wsCloseHandler = () => {
        if (!this.resolveMessage) return
        this.emit({
          type: 'node_error',
          data: { error: 'Connection to the backend was lost while Claude Code was running.' },
        })
        this.emit({ type: 'done', data: {} })
        this.cleanup()
      }

      socket.addEventListener('message', this.wsMessageHandler)
      socket.addEventListener('close', this.wsCloseHandler)

      // Now send the message to the server
      socket.send(JSON.stringify({
        type: 'agent_message',
        payload: { message: content, systemPrompt },
      }))
    })
  }

  abort(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'agent_abort' }))
    }
    this.cleanup()
  }

  isReady(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN
  }

  onEvent(handler: AgentEventHandler): void {
    this.handlers.add(handler)
  }

  offEvent(handler: AgentEventHandler): void {
    this.handlers.delete(handler)
  }

  private emit(event: AgentEvent): void {
    for (const handler of this.handlers) {
      handler(event)
    }
  }

  private detachListenerSocket() {
    if (this.listenerSocket && this.wsMessageHandler) {
      this.listenerSocket.removeEventListener('message', this.wsMessageHandler)
    }
    if (this.listenerSocket && this.wsCloseHandler) {
      this.listenerSocket.removeEventListener('close', this.wsCloseHandler)
    }
    this.listenerSocket = null
    this.wsMessageHandler = null
    this.wsCloseHandler = null
  }

  private cleanup() {
    this.detachListenerSocket()
    if (this.resolveMessage) {
      this.resolveMessage()
      this.resolveMessage = null
    }
  }

  /** Translate server events into AgentEvents for the ChatPanel */
  private handleServerEvent(msg: { type: string; payload?: Record<string, unknown> }) {
    const p = msg.payload || {}

    switch (msg.type) {
      case 'agent_text':
        this.emit({
          type: 'message',
          data: { message: String(p.text || '') },
        })
        break

      case 'agent_tokens':
        // Token consumption tracking — forward to session store
        if (typeof window !== 'undefined') {
          import('../store/session').then(({ useSessionStore }) => {
            useSessionStore.getState().addTokenUsage(
              Number(p.inputTokens || 0),
              Number(p.outputTokens || 0),
            )
          })
        }
        break

      case 'agent_node_start':
        // A tool call is starting — create a graph node
        this.emit({
          type: 'node_start',
          data: {
            actionType: (p.actionType as ActionType) || 'mcp_tool_call',
            label: String(p.label || ''),
            query: String(p.query || ''),
            toolName: String(p.toolName || ''),
            sourceTool: String(p.sourceTool || ''),
            parameters: (p.parameters as Record<string, unknown>) || {},
            reasoning: String(p.reasoning || ''),
            isParallelSibling: p.isParallelSibling === true,
            toolId: p.toolId ? String(p.toolId) : undefined,
          },
        })
        break

      case 'agent_node_complete':
        // Tool call completed — update the graph node
        // Prefer server-provided confidence; fall back to result-based inference
        this.emit({
          type: 'node_complete',
          data: {
            toolName: String(p.toolName || ''),
            resultRaw: String(p.resultRaw || ''),
            resultSummary: String(p.resultSummary || ''),
            durationMs: Number(p.durationMs || 0),
            confidence: (() => {
              if (p.error) return 0 // Failed queries have no findings — 0 confidence
              if (typeof p.confidence === 'number') return p.confidence
              return inferConfidenceFromResult(String(p.resultRaw || '')).score
            })(),
            confidenceReasoning: (() => {
              if (p.error) return 'Node failed with error'
              const inferred = inferConfidenceFromResult(String(p.resultRaw || ''))
              return inferred.reasoning
            })(),
            success: p.success !== false,
            error: p.error ? String(p.error) : undefined,
            toolId: p.toolId ? String(p.toolId) : undefined,
          },
        })
        break

      case 'agent_response':
        // Final response — show as assistant message
        this.emit({
          type: 'message',
          data: { message: String(p.text || '') },
        })
        break

      case 'agent_error':
        this.emit({
          type: 'node_error',
          data: { error: String(p.error || 'Unknown error') },
        })
        // Don't cleanup yet — wait for agent_done
        break

      case 'agent_done':
        this.emit({ type: 'done', data: {} })
        this.cleanup()
        break

      case 'agent_aborted':
        this.cleanup()
        break
    }
  }
}

// ---------------------------------------------------------------------------
// SimulatedAdapter — Fallback for demo/development
// ---------------------------------------------------------------------------

export class SimulatedAdapter implements ClaudeAdapter {
  private handlers: Set<AgentEventHandler> = new Set()
  private aborted = false
  private timer: ReturnType<typeof setTimeout> | null = null

  async sendMessage(
    content: string,
    context?: { nodeId?: string; query?: string; resultSummary?: string }
  ): Promise<void> {
    this.aborted = false

    const isQuery = content.toLowerCase().includes('query') || content.toLowerCase().includes('select')
    const isSkill = content.startsWith('/') || content.toLowerCase().includes('skill')
    const isAnnotation = content.startsWith('#note') || content.startsWith('#annotate')

    const actionType: ActionType = isAnnotation ? 'annotation'
      : isQuery ? 'query_execution'
      : isSkill ? 'skill_invocation'
      : 'mcp_tool_call'

    const label = content.slice(0, 60) + (content.length > 60 ? '...' : '')

    this.emit({
      type: 'node_start',
      data: {
        actionType,
        label,
        query: content,
        skillName: isSkill ? content.replace('/', '').split(' ')[0] : undefined,
        toolName: isQuery ? 'execute_trino_query' : undefined,
        sourceTool: isQuery ? 'captain (simulated)' : 'simulated',
        reasoning: context?.nodeId
          ? `[SIMULATED] Branching from node ${context.nodeId.slice(0, 8)}`
          : `[SIMULATED] User requested: ${label}`,
      },
    })

    if (isAnnotation) {
      this.emit({
        type: 'node_complete',
        data: { resultSummary: 'Annotation added', resultRaw: content.replace(/^#(note|annotate)\s*/i, ''), confidence: 0, durationMs: 0 },
      })
      this.emit({ type: 'done', data: {} })
      return
    }

    await this.delay(1000 + Math.random() * 2000)
    if (this.aborted) { this.emit({ type: 'done', data: {} }); return }

    // No real analysis was performed — confidence 0
    this.emit({
      type: 'node_complete',
      data: {
        resultSummary: `[Demo mode] Claude Code not connected. No real query executed.`,
        resultRaw: `Claude Code is not connected to this workbench session.\n\nTo run real investigations:\n1. Ensure the \`claude\` CLI is installed\n2. Start the backend server: npm run dev\n3. The server will spawn claude with --output-format stream-json\n\nYour input: ${content}`,
        confidence: 0,
        durationMs: 0,
      },
    })
    this.emit({ type: 'done', data: {} })
  }

  abort(): void {
    this.aborted = true
    if (this.timer) { clearTimeout(this.timer); this.timer = null }
  }

  isReady(): boolean { return true }
  onEvent(handler: AgentEventHandler): void { this.handlers.add(handler) }
  offEvent(handler: AgentEventHandler): void { this.handlers.delete(handler) }

  private emit(event: AgentEvent): void {
    for (const handler of this.handlers) handler(event)
  }

  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => { this.timer = setTimeout(resolve, ms) })
  }
}

// ---------------------------------------------------------------------------
// Adapter management
// ---------------------------------------------------------------------------

// Persist across HMR — Vite preserves module state when using this pattern
let adapterInstance: ClaudeAdapter | null = (import.meta as any).hot?.data?.adapter || null

if ((import.meta as any).hot) {
  (import.meta as any).hot.dispose((data: any) => {
    data.adapter = adapterInstance
  })
}

export function getAdapter(): ClaudeAdapter {
  if (!adapterInstance) {
    adapterInstance = new SimulatedAdapter()
  }
  return adapterInstance
}

export function setAdapter(adapter: ClaudeAdapter): void {
  adapterInstance = adapter
}

/**
 * Infer a confidence score (0-1) and reasoning from result content.
 */
function inferConfidenceFromResult(result: string): { score: number; reasoning: string } {
  if (!result) return { score: 0, reasoning: '' }
  const lower = result.toLowerCase()

  // Explicit SEV levels from agent output
  const sevMatch = lower.match(/\bsev[- ]?([1-4])\b/)
  if (sevMatch) {
    const sev = parseInt(sevMatch[1])
    const score = [0.95, 0.8, 0.6, 0.4][sev - 1] ?? 0.5
    return { score, reasoning: `Agent reported SEV-${sev} in results` }
  }

  // WoW percentage signals
  const wowMatch = lower.match(/wow[^0-9]*([+-]?\d+(?:\.\d+)?)%/)
  if (wowMatch) {
    const pct = Math.abs(parseFloat(wowMatch[1]))
    if (pct >= 40) return { score: 0.9, reasoning: `WoW metric +${pct.toFixed(1)}% — critical threshold` }
    if (pct >= 25) return { score: 0.75, reasoning: `WoW metric +${pct.toFixed(1)}% — high threshold` }
    if (pct >= 15) return { score: 0.55, reasoning: `WoW metric +${pct.toFixed(1)}% — elevated` }
    if (pct >= 10) return { score: 0.35, reasoning: `WoW metric +${pct.toFixed(1)}% — moderate` }
  }

  // TrustIM-specific abuse indicators
  if (lower.includes('confirmed automation') || lower.includes('confirmed abuse') || lower.includes('mass restriction'))
    return { score: 0.9, reasoning: 'Confirmed automation/abuse pattern in results' }
  if (lower.includes('swiftshader') || lower.includes('evilginx') || lower.includes('credential washing') || lower.includes('hosting provider ip'))
    return { score: 0.75, reasoning: 'Known abuse indicator detected (SwiftShader/evilginx/hosting IP)' }
  if (lower.includes('bcookie reuse') || lower.includes('datacenter ip') || lower.includes('disposable domain') || lower.includes('voip abuse'))
    return { score: 0.55, reasoning: 'Suspicious signal (cookie reuse/datacenter IP/disposable domain)' }

  // High count results from queries — large numbers often indicate abuse patterns
  const countMatch = result.match(/(\d{3,})\s*(registrations?|accounts?|members?|ips?|attempts)/i)
  if (countMatch) {
    const count = parseInt(countMatch[1])
    if (count > 1000) return { score: 0.7, reasoning: `High volume detected: ${count} ${countMatch[2]}` }
    if (count > 100) return { score: 0.45, reasoning: `Elevated volume: ${count} ${countMatch[2]}` }
  }

  // Zero-result queries — no findings
  if (lower.includes('0 rows') || lower.includes('no results') || lower.includes('empty'))
    return { score: 0.05, reasoning: 'Query returned no results' }

  if (lower.includes('residential ip') || lower.includes('normal pattern') || lower.includes('legitimate') || lower.includes('no restriction'))
    return { score: 0.1, reasoning: 'Results indicate normal/legitimate patterns' }

  // Default: if result has substantial content, give a mild score
  if (result.length > 200) return { score: 0.2, reasoning: 'Results returned data — manual review recommended' }

  return { score: 0, reasoning: '' }
}
