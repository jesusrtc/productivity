import { useCallback } from 'react'
import { useGraphStore } from '../store/graph'
import { useSessionStore } from '../store/session'
import { automationsApi, playbooksApi, setupApi } from '../api'
import { v4 as uuid } from 'uuid'
import type { InvestigationNode, InvestigationEdge } from '../types'
import type { ChatMessage, MessageRole } from '../types/session'
import type { ChatContext } from '../store/session'

interface UseChatCommandsConfig {
  addNode: (data: Partial<InvestigationNode> & { node_id?: string }) => string
  addEdge: (source: string, target: string, relation: InvestigationEdge['relation']) => void
  addMessage: (role: MessageRole, content: string, extras?: Partial<ChatMessage>) => string
  chatContext: ChatContext | null
  setChatContext: (ctx: ChatContext | null) => void
  nodes: Record<string, InvestigationNode>
  lastCompletedNodeRef: React.MutableRefObject<string | null>
  currentNodeRef: React.MutableRefObject<string | null>
}

export function useChatCommands(config: UseChatCommandsConfig) {
  const { addNode, addEdge, addMessage, chatContext, setChatContext, nodes, lastCompletedNodeRef, currentNodeRef } = config

  const handleNote = useCallback((content: string): boolean => {
    const trimmed = content.trim()
    if (!/^#(note|annotate)\s+/i.test(trimmed)) return false

    const noteText = trimmed.replace(/^#(note|annotate)\s+/i, '').trim()
    if (!noteText) return true // Handled but empty

    const ts = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    const parentId = chatContext?.nodeId
      || lastCompletedNodeRef.current
      || Object.keys(nodes).pop()
      || null
    const nodeId = addNode({
      node_id: uuid(),
      action_type: 'annotation',
      label: noteText.slice(0, 60),
      query: noteText,
      parent_ids: parentId ? [parentId] : [],
      status: 'completed',
      result_summary: `Investigator annotation at ${ts}`,
      result_raw: noteText,
      reasoning: 'Annotation added by investigator via #note command',
      confidence: 0,
      investigator_notes: `[${ts}] ${noteText}`,
    } as any)
    if (parentId) addEdge(parentId, nodeId, 'supports')
    addMessage('user', content)
    addMessage('system', `Annotation added to graph: "${noteText.slice(0, 50)}"`)
    if (chatContext) setChatContext(null)
    return true
  }, [addNode, addEdge, addMessage, chatContext, setChatContext, nodes, lastCompletedNodeRef])

  const handleRunAutomation = useCallback(async (content: string): Promise<boolean> => {
    const trimmed = content.trim()
    if (!/^\/run\s+/i.test(trimmed)) return false

    const parts = trimmed.replace(/^\/run\s+/i, '').trim()
    const paramRegex = /\b([A-Z_]+)=(\S+)/g
    const inlineInputs: Record<string, string> = {}
    let match: RegExpExecArray | null
    while ((match = paramRegex.exec(parts)) !== null) inlineInputs[match[1]] = match[2]
    const autoQuery = parts.replace(/\b[A-Z_]+=\S+/g, '').trim()

    addMessage('user', trimmed)
    addMessage('system', `Searching automations for "${autoQuery}"...`)
    try {
      const automations = await automationsApi.list({ search: autoQuery }) as any[]
      if (automations.length === 0) {
        addMessage('system', `No automations found matching "${autoQuery}". Try /run with a different name.`)
        return true
      }
      const auto = automations[0]
      const detail = await automationsApi.get(auto.id) as any
      const requiredInputs = (detail.inputs || []).filter((i: any) => i.required)
      const missingInputs = requiredInputs.filter((i: any) => !inlineInputs[i.name])
      if (missingInputs.length > 0) {
        addMessage('system', `**${auto.name}** requires inputs: ${requiredInputs.map((i: any) => `\`${i.name}\` (${i.type}${i.default ? `, default: ${i.default}` : ''})`).join(', ')}\n\nUsage: \`/run ${autoQuery} ${missingInputs.map((i: any) => `${i.name}=${i.default || '...'}`).join(' ')}\``)
        return true
      }

      addMessage('system', `Running automation: **${auto.name}** (${auto.exec_type})${Object.keys(inlineInputs).length > 0 ? ` with ${JSON.stringify(inlineInputs)}` : ''}`)
      const parentId = lastCompletedNodeRef.current || Object.keys(nodes).pop() || null
      const nodeId = addNode({
        node_id: uuid(),
        action_type: 'skill_invocation',
        label: auto.name,
        query: `Automation: ${auto.id}`,
        skill_name: auto.id,
        tool_name: auto.id,
        source_tool: 'automation',
        status: 'running',
        confidence: 0,
        parent_ids: parentId ? [parentId] : [],
      } as any)
      if (parentId) addEdge(parentId, nodeId, 'led_to')
      currentNodeRef.current = nodeId
      const result = await automationsApi.run(auto.id, inlineInputs) as any
      useGraphStore.getState().updateNode(nodeId, {
        status: result.success ? 'completed' : 'failed',
        result_raw: JSON.stringify(result.output),
        result_summary: result.error || JSON.stringify(result.output).slice(0, 200),
        confidence: result.success ? 0.5 : 0,
        duration_ms: result.duration_ms,
      })
      lastCompletedNodeRef.current = nodeId
      addMessage('assistant', `**${auto.name}** — ${result.success ? 'Completed' : `Failed: ${result.error}`}`)
    } catch (err) {
      addMessage('system', `Error running automation: ${err}`)
    }
    return true
  }, [addNode, addEdge, addMessage, nodes, lastCompletedNodeRef, currentNodeRef])

  const handleRunPlaybook = useCallback(async (content: string): Promise<boolean> => {
    const trimmed = content.trim()
    if (!/^\/playbook\s+/i.test(trimmed)) return false

    const pbQuery = trimmed.replace(/^\/playbook\s+/i, '').trim()
    addMessage('user', trimmed)
    try {
      const bridgeStatus = await setupApi.bridgeStatus().catch(() => ({ available: false }))
      if (!(bridgeStatus as any).available) {
        addMessage('system', 'Playbooks require the Claude CLI to execute prompt steps. Install `claude` and restart the server.')
        return true
      }
      const playbooks = await playbooksApi.list() as any[]
      const found = playbooks.find((p: any) => p.name.toLowerCase().includes(pbQuery.toLowerCase()))
      if (!found) {
        addMessage('system', `No playbook found matching "${pbQuery}". Available: ${playbooks.map((p: any) => p.name).join(', ')}`)
        return true
      }
      const sessionId = useSessionStore.getState().currentSession?.id
      if (!sessionId) { addMessage('system', 'No active session'); return true }
      addMessage('system', `Running playbook: **${found.name}** (${found.nodes?.length || 0} steps)`)
      await playbooksApi.run(found.id, {}, sessionId)
      addMessage('system', `Playbook "${found.name}" started. Watch the playbook drawer for progress.`)
    } catch (err) {
      addMessage('system', `Error starting playbook: ${err}`)
    }
    return true
  }, [addMessage])

  return { handleNote, handleRunAutomation, handleRunPlaybook }
}
