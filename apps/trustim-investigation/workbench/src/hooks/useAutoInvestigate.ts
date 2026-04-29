import { useEffect, useRef, useCallback } from 'react'
import { useGraphStore } from '../store/graph'
import { useSessionStore } from '../store/session'
import { getAdapter, type AgentEvent } from '../utils/claude-adapter'
import { v4 as uuid } from 'uuid'
import type { ActionType } from '../types'
import { INVESTIGATION_STEPS } from '../data/investigation-steps'
import { buildContinuationPrompt } from '../utils/continuation-prompt'
import { handleAutoInvestigateComplete } from '../utils/auto-investigate-summary'

const AUTO_INVESTIGATE_CONFIG = {
  maxNodes: 15,
  delayBetweenMs: 1500,
}

/**
 * Hook that drives auto-investigate mode.
 *
 * Two modes:
 * 1. **Real mode** (Claude Code connected): Sends a continuation prompt to the
 *    Claude bridge, which runs real queries via MCP tools. The agent decides
 *    what to investigate next based on previous findings.
 * 2. **Demo mode** (no Claude Code): Uses hardcoded investigation step templates
 *    with simulated results.
 *
 * Both modes respect maxAutoDepth and maxNodes from the graph store.
 */
export function useAutoInvestigate() {
  const autoNodeId = useGraphStore((s) => s.autoInvestigateNodeId)
  const stopAutoInvestigate = useGraphStore((s) => s.stopAutoInvestigate)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()
  const nodesCreatedRef = useRef(0)
  const activeRef = useRef(false)
  const prevAutoNodeId = useRef<string | null>(null)
  const consecutiveMissesRef = useRef(0)

  // Generate summary when auto-investigate stops
  useEffect(() => {
    if (prevAutoNodeId.current && !autoNodeId) {
      handleAutoInvestigateComplete()
    }
    prevAutoNodeId.current = autoNodeId
  }, [autoNodeId])

  // Callback for real Claude bridge auto-investigate step
  const runRealStep = useCallback(async (parentId: string, depth: number) => {
    if (!activeRef.current) return
    const graph = useGraphStore.getState()
    if (!graph.autoInvestigateNodeId) return

    const parent = graph.nodes[parentId]
    if (!parent || parent.is_dead_end) return

    const maxDepth = graph.maxAutoDepth
    if (depth >= maxDepth || nodesCreatedRef.current >= AUTO_INVESTIGATE_CONFIG.maxNodes) {
      useSessionStore.getState().addMessage('system',
        `Auto-investigate reached ${depth >= maxDepth ? `depth limit (${maxDepth})` : `node budget (${AUTO_INVESTIGATE_CONFIG.maxNodes})`}. Stopping.`
      )
      stopAutoInvestigate()
      return
    }

    const adapter = getAdapter()
    if (!adapter.isReady()) {
      runDemoStep(parentId, depth)
      return
    }

    useGraphStore.getState().setAutoInvestigateCurrent(parentId)

    const prompt = buildContinuationPrompt(parent)

    useSessionStore.getState().addMessage('system',
      `Auto-investigating: ${prompt.slice(0, 80)}...`
    )

    nodesCreatedRef.current++

    const nodesBefore = new Set(Object.keys(useGraphStore.getState().nodes))

    let currentAutoNodeId: string | null = null
    let stepDone = false
    let handlerActive = true

    const stepHandler = (event: AgentEvent) => {
      if (!handlerActive || !activeRef.current) return
      const { type, data } = event

      if (type === 'node_start') {
        const nodeId = useGraphStore.getState().addNode({
          node_id: uuid(),
          action_type: (data.actionType as ActionType) || 'mcp_tool_call',
          label: data.label || '',
          query: data.query || '',
          parent_ids: [parentId],
          status: 'running',
          confidence: 0,
          skill_name: data.skillName || null,
          tool_name: data.toolName || null,
          source_tool: data.sourceTool || null,
          parameters: data.parameters || {},
          reasoning: data.reasoning || '',
        })
        useGraphStore.getState().addEdge(parentId, nodeId, 'led_to')
        currentAutoNodeId = nodeId
        useSessionStore.getState().setProcessingInfo({ active: true, operation: `Auto: ${data.toolName || data.label || 'Processing'}` })
        return
      }

      if (type === 'node_complete' && currentAutoNodeId) {
        const isError = data.success === false || !!data.error
        useGraphStore.getState().updateNode(currentAutoNodeId, {
          status: isError ? 'failed' : 'completed',
          duration_ms: data.durationMs || 0,
          result_summary: data.resultSummary || '',
          result_raw: data.resultRaw || '',
          confidence: data.confidence || 0,
          confidence_reasoning: data.confidenceReasoning || '',
        })
        if (!isError) {
          useGraphStore.getState().propagateConfidence(currentAutoNodeId)
          const raw = (data.resultRaw || '').toLowerCase()
          if (/\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/.test(raw)) useGraphStore.getState().addTag(currentAutoNodeId, 'has-ips')
          if (/sev[- ]?[12]/i.test(raw) || /critical|high.?severity/i.test(raw)) useGraphStore.getState().addTag(currentAutoNodeId, 'high-severity')
          if (/fake|fraud|abus|malicious|spam/i.test(raw)) useGraphStore.getState().addTag(currentAutoNodeId, 'abuse-signal')
        }
        const session = useSessionStore.getState().currentSession
        const nodeData = useGraphStore.getState().nodes[currentAutoNodeId]
        if (session && nodeData?.query) {
          import('../api').then(({ api }) => {
            api.post('/api/notebook/append', {
              sessionId: session.id, sessionName: session.name, nodeId: currentAutoNodeId,
              label: nodeData.label, query: nodeData.query, resultRaw: data.resultRaw,
              confidence: data.confidence || 0, tags: nodeData.tags, timestamp: nodeData.timestamp,
            }).catch(() => {})
          })
        }
        useSessionStore.getState().setProcessingInfo(null)
        currentAutoNodeId = null
        return
      }

      if (type === 'message' && data.message) {
        return
      }

      if (type === 'done') {
        stepDone = true
        handlerActive = false
        adapter.offEvent(stepHandler)

        if (!activeRef.current) return

        const currentNodes = useGraphStore.getState().nodes
        const newNodeIds = Object.keys(currentNodes).filter(id => !nodesBefore.has(id))

        const completedNewNodes = newNodeIds
          .map(id => currentNodes[id])
          .filter(n => n.status === 'completed' && n.confidence > 0.2 && !n.is_dead_end)
          .sort((a, b) => b.confidence - a.confidence)

        if (completedNewNodes.length > 0) {
          consecutiveMissesRef.current = 0
          const maxBranches = useGraphStore.getState().maxConcurrentBranches
          const branchTargets = completedNewNodes.slice(0, maxBranches)

          if (branchTargets.length > 1) {
            useSessionStore.getState().addMessage('system',
              `Branching into ${branchTargets.length} directions from depth ${depth + 1}.`
            )
          }

          const runBranchesSequentially = async () => {
            for (const target of branchTargets) {
              if (!activeRef.current || !useGraphStore.getState().autoInvestigateNodeId) break
              await new Promise(r => setTimeout(r, AUTO_INVESTIGATE_CONFIG.delayBetweenMs))
              await runRealStep(target.node_id, depth + 1)
            }
            if (activeRef.current && useGraphStore.getState().autoInvestigateNodeId) {
              stopAutoInvestigate()
            }
          }
          runBranchesSequentially()
        } else if (newNodeIds.length > 0) {
          if (depth < useGraphStore.getState().maxAutoDepth - 1) {
            timerRef.current = setTimeout(() => runRealStep(parentId, depth + 1), AUTO_INVESTIGATE_CONFIG.delayBetweenMs)
          } else {
            stopAutoInvestigate()
          }
        } else {
          consecutiveMissesRef.current++
          if (consecutiveMissesRef.current >= 3) {
            useSessionStore.getState().addMessage('system', 'Auto-investigate: 3 consecutive steps without queries. Stopping.')
            stopAutoInvestigate()
          } else if (depth < useGraphStore.getState().maxAutoDepth - 1) {
            timerRef.current = setTimeout(() => runRealStep(parentId, depth + 1), AUTO_INVESTIGATE_CONFIG.delayBetweenMs)
          } else {
            useSessionStore.getState().addMessage('system', 'Auto-investigate: reached depth limit without new queries. Stopping.')
            stopAutoInvestigate()
          }
        }
      }
    }

    adapter.onEvent(stepHandler)

    try {
      await adapter.sendMessage(prompt, {
        nodeId: parentId,
        query: parent.query,
        resultSummary: parent.result_summary,
        resultRaw: parent.result_raw,
      })
    } catch {
      handlerActive = false
      adapter.offEvent(stepHandler)
      if (!stepDone) {
        useSessionStore.getState().addMessage('system', 'Auto-investigate step failed. Stopping.')
        stopAutoInvestigate()
      }
    }
  }, [stopAutoInvestigate])

  // Demo mode fallback (original behavior)
  const runDemoStep = useCallback((parentId: string, depth: number) => {
    if (!useGraphStore.getState().autoInvestigateNodeId) return

    const parent = useGraphStore.getState().nodes[parentId]
    if (!parent || parent.is_dead_end) return

    const maxDepth = useGraphStore.getState().maxAutoDepth
    if (depth >= maxDepth || nodesCreatedRef.current >= AUTO_INVESTIGATE_CONFIG.maxNodes) {
      useSessionStore.getState().addMessage('system',
        `Auto-investigate reached ${depth >= maxDepth ? `depth limit (${maxDepth})` : `node budget (${AUTO_INVESTIGATE_CONFIG.maxNodes})`}. Stopping.`
      )
      stopAutoInvestigate()
      return
    }

    timerRef.current = setTimeout(() => {
      const graph = useGraphStore.getState()
      if (!graph.autoInvestigateNodeId) return

      const step = INVESTIGATION_STEPS[nodesCreatedRef.current % INVESTIGATION_STEPS.length]

      const today = new Date().toISOString().split('T')[0]
      const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString().split('T')[0]
      const resolvedQuery = step.queryTemplate
        .replace(/\{DATE\}/g, today)
        .replace(/\{START_DATE\}/g, weekAgo)
        .replace(/\{END_DATE\}/g, today)
        .replace(/\{COHORT_MEMBER_IDS\}/g, '123456789, 987654321, 555555555')

      const nodeId = graph.addNode({
        node_id: uuid(),
        action_type: step.actionType,
        label: step.label,
        query: `-- Auto-investigate step ${nodesCreatedRef.current + 1}\n${resolvedQuery}`,
        parent_ids: [parentId],
        status: 'running',
        reasoning: `Auto-investigate step ${nodesCreatedRef.current + 1}: Following up on ${parent.label} with ${step.label}.`,
      })

      graph.addEdge(parentId, nodeId, depth === 0 ? 'branched_from' : 'led_to')
      nodesCreatedRef.current++

      setTimeout(() => {
        const g = useGraphStore.getState()
        if (!g.autoInvestigateNodeId) return

        const parentConf = parent.confidence
        const confidence = Math.max(0, parentConf - 0.2)
        const sevLabel = confidence > 0.6 ? 'high' : confidence > 0.3 ? 'medium' : 'benign'

        g.updateNode(nodeId, {
          status: 'completed',
          duration_ms: 0,
          result_summary: `[Demo] ${step.resultTemplate(sevLabel)}`,
          result_raw: `[Demo — connect Claude Code for real queries]\n\n${step.resultTemplate(sevLabel)}`,
          confidence,
        })
        g.propagateConfidence(nodeId)

        const { addTag } = g
        if (confidence > 0.5) addTag(nodeId, 'high-severity')
        if (step.label.includes('IP')) addTag(nodeId, 'has-ips')

        if (confidence > 0.3) {
          runDemoStep(nodeId, depth + 1)
        } else if (depth < 2) {
          runDemoStep(parentId, depth + 1)
        } else {
          useSessionStore.getState().addMessage('system',
            `Auto-investigate completed branch at depth ${depth + 1}. Connect Claude Code for real investigation.`
          )
          stopAutoInvestigate()
        }
      }, 1000 + Math.random() * 1500)
    }, AUTO_INVESTIGATE_CONFIG.delayBetweenMs)
  }, [stopAutoInvestigate])

  useEffect(() => {
    if (!autoNodeId) {
      nodesCreatedRef.current = 0
      activeRef.current = false
      return
    }

    activeRef.current = true
    nodesCreatedRef.current = 0
    consecutiveMissesRef.current = 0

    const rootNode = useGraphStore.getState().nodes[autoNodeId]
    const skillInfo = rootNode?.skill_name ? ` (skill: ${rootNode.skill_name})` : ''
    const adapter = getAdapter()
    if (adapter.isReady()) {
      useSessionStore.getState().addMessage('system', `Auto-investigate started with Claude Code${skillInfo}. Depth limit: ${useGraphStore.getState().maxAutoDepth}.`)
      runRealStep(autoNodeId, 0)
    } else {
      useSessionStore.getState().addMessage('system', `Auto-investigate started in demo mode${skillInfo}. Connect Claude Code for real queries.`)
      runDemoStep(autoNodeId, 0)
    }

    return () => {
      activeRef.current = false
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [autoNodeId, stopAutoInvestigate, runRealStep, runDemoStep])
}
