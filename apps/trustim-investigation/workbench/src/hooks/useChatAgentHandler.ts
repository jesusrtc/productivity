import { useState, useRef, useCallback } from 'react'
import { useGraphStore } from '../store/graph'
import { useSessionStore } from '../store/session'
import { miscApi } from '../api'
import { api } from '../api/client'
import { checkSevThresholds, formatSevAssessment } from '../utils/sev-checker'
import { extractCohort } from '../utils/cohort-extraction'
import { detectConvergence } from '../utils/convergence-detection'
import { getUncoveredDimensions } from '../utils/investigation-checklist'
import { v4 as uuid } from 'uuid'
import { isTrinoAuthError } from '../utils/trino-auth'
import type { AgentEvent } from '../utils/claude-adapter'
import type { InvestigationNode, InvestigationEdge } from '../types'
import type { ChatMessage, MessageRole } from '../types/session'

export interface UseChatAgentHandlerConfig {
  addNode: (data: Partial<InvestigationNode> & { node_id?: string }) => string
  addEdge: (source: string, target: string, relation: InvestigationEdge['relation']) => void
  addMessage: (role: MessageRole, content: string, extras?: Partial<ChatMessage>) => string
  setProcessingInfo: (info: { active: boolean; operation: string } | null) => void
  /** Called when agent processing ends (node_error or done) */
  onProcessingEnd: () => void
}

export function useChatAgentHandler(config: UseChatAgentHandlerConfig) {
  const { addNode, addEdge, addMessage, setProcessingInfo, onProcessingEnd } = config

  const [agentThinking, setAgentThinking] = useState('')

  // Tool-to-node mapping for parallel tool calls
  const toolNodeMapRef = useRef<Map<string, string>>(new Map())
  const toolNodeTimestamps = useRef<Map<string, number>>(new Map())
  // Fallback for adapters that don't provide toolId (SimulatedAdapter)
  const currentNodeRef = useRef<string | null>(null)
  const lastCompletedNodeRef = useRef<string | null>(null)
  const branchParentRef = useRef<string | null>(null)
  // For parallel branching: when multiple tools fire in one turn, they share this parent
  const parallelParentRef = useRef<string | null>(null)
  // Track if session has been renamed from a finding (only rename once)
  const sessionRenamedRef = useRef(false)
  // When true, the `done` handler will start auto-investigate from the latest completed node
  const pendingAutoInvestigateRef = useRef(false)
  // The root node ID for the current first-message flow (so auto-investigate skips it)
  const firstMessageRootRef = useRef<string | null>(null)
  // Track Trino auth failure so ChatPanel can show the retry banner
  const trinoAuthFailedRef = useRef<{ nodeId: string; query: string } | null>(null)
  const [trinoAuthFailed, setTrinoAuthFailed] = useState<{ nodeId: string; query: string } | null>(null)

  /** Reset all per-session refs to avoid cross-tab contamination */
  const resetRefs = useCallback(() => {
    toolNodeMapRef.current.clear()
    toolNodeTimestamps.current.clear()
    currentNodeRef.current = null
    lastCompletedNodeRef.current = null
    branchParentRef.current = null
    parallelParentRef.current = null
    sessionRenamedRef.current = false
    pendingAutoInvestigateRef.current = false
    firstMessageRootRef.current = null
    trinoAuthFailedRef.current = null
    setTrinoAuthFailed(null)
    setAgentThinking('')
  }, [])

  const handleAgentEvent = useCallback((event: AgentEvent) => {
    const { type, data } = event

    switch (type) {
      case 'node_start': {
        // Parallel branching: if this is a parallel sibling, use the same parent as the first tool
        // Cap at 3 parallel siblings per parent — after that, chain sequentially to keep tree shape
        let parentId: string | null
        const MAX_PARALLEL_FANOUT = 3

        if (data.isParallelSibling && parallelParentRef.current) {
          // Count existing children of the parallel parent
          const edges = useGraphStore.getState().edges
          const childCount = edges.filter(e => e.source === parallelParentRef.current).length
          if (childCount < MAX_PARALLEL_FANOUT) {
            parentId = parallelParentRef.current
          } else {
            // Cap reached — chain from last completed node instead of fanning
            parentId = lastCompletedNodeRef.current || parallelParentRef.current
          }
        } else {
          const currentNodes = useGraphStore.getState().nodes
          const nodeIds = Object.keys(currentNodes)
          parentId = branchParentRef.current
            || lastCompletedNodeRef.current
            || (nodeIds.length > 0 ? nodeIds[nodeIds.length - 1] : null)
          // Bug #6: Only set parallelParent if the parent actually exists in the graph
          if (parentId && currentNodes[parentId]) {
            parallelParentRef.current = parentId
          } else {
            parallelParentRef.current = null
          }
        }

        // Bug #6: Validate parent exists — don't create edges to non-existent nodes
        if (parentId && !useGraphStore.getState().nodes[parentId]) {
          parentId = null
        }

        const parentIds = parentId ? [parentId] : []
        const edgeRelation = (branchParentRef.current || data.isParallelSibling)
          ? 'branched_from' as const
          : 'led_to' as const

        const nodeId = addNode({
          node_id: uuid(),
          action_type: data.actionType || 'mcp_tool_call',
          label: data.label || '',
          query: data.query || '',
          parent_ids: parentIds,
          status: 'running',
          confidence: 0,
          skill_name: data.skillName || null,
          tool_name: data.toolName || null,
          source_tool: data.sourceTool || null,
          parameters: data.parameters || {},
          reasoning: data.reasoning || '',
        } as any)

        if (parentIds.length > 0) {
          addEdge(parentIds[0], nodeId, edgeRelation)
        }

        // Track toolId → nodeId for parallel tool completion matching
        if (data.toolId) {
          toolNodeMapRef.current.set(data.toolId, nodeId)
          toolNodeTimestamps.current.set(data.toolId, Date.now())
        }
        currentNodeRef.current = nodeId // Fallback for adapters without toolId
        // Clear branch parent after first use — but keep parallelParent for siblings
        branchParentRef.current = null

        // Show tool call preview with parameters
        const opName = data.toolName
          ? `Calling: ${data.toolName}`
          : data.skillName
            ? `Loading skill: ${data.skillName}`
            : 'Processing...'

        // Build parameter preview for observability
        let paramPreview = ''
        if (data.parameters && Object.keys(data.parameters).length > 0) {
          const params = data.parameters
          if (params.query) paramPreview = String(params.query).slice(0, 100)
          else if (params.command) paramPreview = String(params.command).slice(0, 100)
          else if (params.file_path) paramPreview = String(params.file_path)
          else if (params.pattern) paramPreview = String(params.pattern)
          else paramPreview = JSON.stringify(params).slice(0, 100)
        }
        const fullOp = opName + (paramPreview ? ` — ${paramPreview}` : '')
        setProcessingInfo({ active: true, operation: fullOp })

        // Add a system message for Trino queries for observability
        if (data.toolName?.includes('trino') || data.toolName?.includes('execute')) {
          addMessage('system', `Running query: \`${paramPreview.slice(0, 100)}...\``, { node_ids: [nodeId] })
        }
        break
      }

      case 'node_complete': {
        // Match completion to the correct node — use toolId map for parallel tools,
        // fall back to currentNodeRef for sequential/simulated flows
        let nodeId: string | null = null
        if (data.toolId && toolNodeMapRef.current.has(data.toolId)) {
          nodeId = toolNodeMapRef.current.get(data.toolId)!
          toolNodeMapRef.current.delete(data.toolId)
          toolNodeTimestamps.current.delete(data.toolId)
        } else {
          nodeId = currentNodeRef.current
        }
        if (!nodeId) break

        const { updateNode, propagateConfidence } = useGraphStore.getState()
        const isError = data.success === false || !!data.error

        updateNode(nodeId, {
          status: isError ? 'failed' : 'completed',
          duration_ms: data.durationMs || 0,
          result_summary: data.resultSummary || '',
          result_raw: data.resultRaw || '',
          confidence: data.confidence || 0,
          confidence_reasoning: data.confidenceReasoning || '',
        })

        if (!isError) {
          propagateConfidence(nodeId)

          // Auto-tag based on result content
          const raw = (data.resultRaw || '').toLowerCase()
          const { addTag } = useGraphStore.getState()
          if (/\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/.test(raw)) addTag(nodeId, 'has-ips')
          if (/sev[- ]?[12]/i.test(raw) || /critical|high.?severity/i.test(raw)) addTag(nodeId, 'high-severity')
          if (/fake|fraud|abus|malicious|spam/i.test(raw)) addTag(nodeId, 'abuse-signal')
          if (/ato|takeover|credential/i.test(raw)) addTag(nodeId, 'ato-signal')
          if (/vpn|proxy|tor|datacenter/i.test(raw)) addTag(nodeId, 'proxy-traffic')

          // Persist extracted IOCs to cross-session database
          const session = useSessionStore.getState().currentSession
          if (session && data.resultRaw) {
            const cohort = extractCohort(data.resultRaw)
            const iocs = [
              ...cohort.ips.map(v => ({ value: v, type: 'ip' })),
              ...cohort.domains.map(v => ({ value: v, type: 'domain' })),
              ...cohort.memberIds.slice(0, 20).map(v => ({ value: v, type: 'member_id' })),
            ]
            if (iocs.length > 0) {
              miscApi.addIocs(iocs, session.id).catch(() => {})
            }
          }

          // Convergence detection: check if IOCs from this node appear in other branches
          detectConvergence(nodeId, data.resultRaw || '', useGraphStore.getState().nodes)

          // Automated SEV threshold checking
          const nodeData = useGraphStore.getState().nodes[nodeId]
          if (nodeData) {
            const sevResults = checkSevThresholds(data.resultRaw || '', nodeData.label)
            const topSev = sevResults.length > 0 ? sevResults[0] : null
            if (topSev && topSev.sevLevel !== null) {
              const sev = topSev.sevLevel
              useGraphStore.getState().addTag(nodeId, `SEV-${sev}`)
              addMessage('system', `**SEV Alert:** ${formatSevAssessment(topSev)}`)
              // Auto-boost confidence for SEV-1/SEV-2
              if (sev <= 2 && nodeData.confidence < 0.8) {
                useGraphStore.getState().overrideConfidence(nodeId, sev === 1 ? 0.95 : 0.85)
              }
              // Browser notification for critical findings
              if (sev <= 2 && Notification.permission === 'granted') {
                new Notification(`SEV-${sev} Detected`, {
                  body: formatSevAssessment(topSev),
                  tag: `sev-${nodeId}`,
                })
              }
            }
          }
        }

        // Smart session rename: update name on first high-confidence finding
        if (!isError && (data.confidence || 0) > 0.5 && !sessionRenamedRef.current) {
          const session = useSessionStore.getState().currentSession
          if (session) {
            const nodeLabel = useGraphStore.getState().nodes[nodeId]?.label || ''
            const sevTag = (useGraphStore.getState().nodes[nodeId]?.tags || []).find((t: string) => t.startsWith('SEV-'))
            const shortSummary = data.resultSummary?.slice(0, 50) || nodeLabel
            const newName = sevTag
              ? `${session.name.split(':')[0]}: ${shortSummary} [${sevTag}]`
              : `${session.name.split(':')[0]}: ${shortSummary}`
            if (newName.length > session.name.length) {
              useSessionStore.getState().renameSession(newName.slice(0, 80))
              sessionRenamedRef.current = true
            }
          }
        }

        // Track this as the last completed node so the next tool call chains from it
        lastCompletedNodeRef.current = nodeId
        currentNodeRef.current = null

        const conf = data.confidence || 0
        const toolLabel = data.toolName ? `**${data.toolName}** completed.` : 'Step completed.'
        const confLabel = conf > 0.4 ? ` Confidence: **${(conf * 100).toFixed(0)}%**.` : ''

        // Proactive suggestion: after every 3rd completed node, suggest uncovered dimensions
        const completedCount = Object.values(useGraphStore.getState().nodes).filter(n => n.status === 'completed').length
        let suggestion = ''
        if (completedCount > 0 && completedCount % 3 === 0 && !isError) {
          const uncovered = getUncoveredDimensions(useGraphStore.getState().nodes)
          if (uncovered.length > 0) {
            suggestion = ` Consider checking: **${uncovered[0]}**.`
          }
        }

        addMessage('assistant',
          isError
            ? `Tool call failed: ${data.error || 'Unknown error'}`
            : `${toolLabel}${confLabel}${suggestion}`,
          { node_ids: [nodeId] }
        )

        // Detect Trino auth errors and surface retry banner
        if (isTrinoAuthError(data.resultRaw || data.error || '')) {
          const authFailure = { nodeId, query: data.query || '' }
          trinoAuthFailedRef.current = authFailure
          setTrinoAuthFailed(authFailure)
          addMessage('system', 'Trino authentication failed. Run `captain setup trino` in your terminal, then click Retry below.')
        }

        // Auto-save to investigation notebook
        const session = useSessionStore.getState().currentSession
        const nodeData2 = useGraphStore.getState().nodes[nodeId]
        if (session && nodeData2 && nodeData2.query) {
          api.post('/api/notebook/append', {
            sessionId: session.id,
            sessionName: session.name,
            nodeId,
            label: nodeData2.label,
            query: nodeData2.query,
            resultRaw: data.resultRaw,
            severity: conf > 0.6 ? 'high' : conf > 0.3 ? 'medium' : 'benign',
            confidence: conf,
            reasoning: nodeData2.reasoning,
            tags: nodeData2.tags,
            timestamp: nodeData2.timestamp,
          }).catch(() => {}) // Fire and forget
        }

        setProcessingInfo(null)
        break
      }

      case 'node_error': {
        const nodeId = currentNodeRef.current
        if (nodeId) {
          useGraphStore.getState().updateNode(nodeId, {
            status: 'failed',
            result_raw: data.error || 'Unknown error',
          })
        }
        addMessage('assistant', `Error: ${data.error || 'Unknown error'}`)
        onProcessingEnd()
        setProcessingInfo(null)
        currentNodeRef.current = null
        break
      }

      case 'message': {
        // Streaming text from the agent — accumulate for observability
        if (data.message) {
          setAgentThinking(prev => prev + data.message)
        }
        break
      }

      case 'done': {
        // Agent turn complete — flush accumulated reasoning as a single message
        setAgentThinking(prev => {
          if (prev.trim()) {
            addMessage('assistant', prev.trim())
          }
          return ''
        })

        // Finalize any nodes still stuck in 'running' — the agent died before tool_end
        const graph = useGraphStore.getState()
        for (const [nid, node] of Object.entries(graph.nodes)) {
          if (node.status === 'running') {
            graph.updateNode(nid, {
              status: 'failed',
              result_summary: 'Agent finished before this step completed',
              duration_ms: Date.now() - new Date(node.timestamp).getTime(),
            })
          }
        }

        onProcessingEnd()
        parallelParentRef.current = null
        setProcessingInfo(null)
        currentNodeRef.current = null

        // Auto-investigate: if this was the first message's agent turn, start branching
        if (pendingAutoInvestigateRef.current) {
          pendingAutoInvestigateRef.current = false
          const rootId = firstMessageRootRef.current
          firstMessageRootRef.current = null
          const graph = useGraphStore.getState()
          const completedNodes = Object.values(graph.nodes).filter(
            n => n.status === 'completed' && n.node_id !== rootId
          )
          const latest = completedNodes.sort(
            (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
          )[0]
          if (latest && !graph.autoInvestigateNodeId) {
            graph.startAutoInvestigate(latest.node_id)
            addMessage('system', `Auto-investigate started — expanding from "${latest.label.slice(0, 40)}".`)
          }
        }

        lastCompletedNodeRef.current = null
        toolNodeMapRef.current.clear()
        toolNodeTimestamps.current.clear()
        break
      }
    }
  }, [addNode, addEdge, addMessage, setProcessingInfo, onProcessingEnd])

  return {
    handleAgentEvent,
    agentThinking,
    setAgentThinking,
    lastCompletedNodeRef,
    pendingAutoInvestigateRef,
    firstMessageRootRef,
    branchParentRef,
    sessionRenamedRef,
    currentNodeRef,
    toolNodeMapRef,
    toolNodeTimestamps,
    trinoAuthFailedRef,
    trinoAuthFailed,
    setTrinoAuthFailed,
    resetRefs,
  }
}
