import { useState, useRef, useEffect, useCallback } from 'react'
import { useSessionStore } from '../../store/session'
import { useGraphStore } from '../../store/graph'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { getAdapter, WebSocketAdapter } from '../../utils/claude-adapter'
import { waitForSharedWebSocket } from '../../hooks/useWebSocket'
import { routeInvestigation } from '../../utils/investigation-router'
import { useChatAgentHandler } from '../../hooks/useChatAgentHandler'
import { useChatCommands } from '../../hooks/useChatCommands'
import { useChatFirstMessage } from '../../hooks/useChatFirstMessage'
import { InvestigationMaturityBanner } from './InvestigationMaturityBanner'
import { ChatFilter } from './ChatFilter'
import { InvestigationMiniStats } from './InvestigationMiniStats'
import { ContextBreadcrumb } from './ContextBreadcrumb'
import { RecentInvestigations } from './RecentInvestigations'
import { LiveElapsed } from './LiveElapsed'
import { AutoInvestigateBanner } from './AutoInvestigateBanner'
import { AgentStepProgress } from './AgentStepProgress'
import { PlaybookChatProgress } from './PlaybookChatProgress'

export function ChatPanel() {
  const currentSession = useSessionStore((s) => s.currentSession)
  const messages = currentSession?.messages || []
  const addMessage = useSessionStore((s) => s.addMessage)
  const chatContext = useSessionStore((s) => s.chatContext)
  const setChatContext = useSessionStore((s) => s.setChatContext)
  const processingInfo = useSessionStore((s) => s.processingInfo)
  const setProcessingInfo = useSessionStore((s) => s.setProcessingInfo)
  const readOnly = useSessionStore((s) => s.readOnly)
  const addNode = useGraphStore((s) => s.addNode)
  const addEdge = useGraphStore((s) => s.addEdge)
  const nodes = useGraphStore((s) => s.nodes)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [processingSessionId, setProcessingSessionId] = useState<string | null>(null)
  const [chatFilter, setChatFilter] = useState<'all' | 'findings'>('all')
  const isProcessing = processingSessionId === currentSession?.id && processingSessionId !== null
  const setIsProcessing = useCallback((v: boolean) => setProcessingSessionId(v ? (currentSession?.id || null) : null), [currentSession?.id])

  // Agent event handler hook — owns all per-session refs
  const onProcessingEnd = useCallback(() => setIsProcessing(false), [setIsProcessing])
  const agentHandler = useChatAgentHandler({ addNode, addEdge, addMessage, setProcessingInfo, onProcessingEnd })
  const {
    handleAgentEvent, agentThinking, setAgentThinking,
    lastCompletedNodeRef, pendingAutoInvestigateRef, firstMessageRootRef,
    branchParentRef, currentNodeRef, toolNodeMapRef, toolNodeTimestamps,
    trinoAuthFailed, setTrinoAuthFailed,
    resetRefs,
  } = agentHandler

  // Command handlers hook
  const commands = useChatCommands({ addNode, addEdge, addMessage, chatContext, setChatContext, nodes, lastCompletedNodeRef, currentNodeRef })

  // First-message setup hook
  const { handleFirstMessage } = useChatFirstMessage({ addNode, addMessage, lastCompletedNodeRef, firstMessageRootRef, pendingAutoInvestigateRef })

  // Track which session the refs belong to — reset when session changes
  const activeSessionRef = useRef<string | null>(null)
  useEffect(() => {
    if (currentSession?.id !== activeSessionRef.current) {
      activeSessionRef.current = currentSession?.id || null
      resetRefs()
      setProcessingSessionId(null)
    }
  }, [currentSession?.id, resetRefs])

  // Clean up abandoned tool nodes — if a tool_start fired but node_complete never arrived
  // (network drop, process crash), mark the node as failed after 30s
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now()
      for (const [toolId, startTime] of toolNodeTimestamps.current) {
        if (now - startTime > 30000) {
          const nodeId = toolNodeMapRef.current.get(toolId)
          if (nodeId) {
            const node = useGraphStore.getState().nodes[nodeId]
            if (node && node.status === 'running') {
              useGraphStore.getState().updateNode(nodeId, {
                status: 'failed',
                result_summary: 'Tool call timed out — no response after 60s',
              })
            }
          }
          toolNodeMapRef.current.delete(toolId)
          toolNodeTimestamps.current.delete(toolId)
        }
      }
    }, 15000)
    return () => clearInterval(interval)
  }, [toolNodeMapRef, toolNodeTimestamps])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages.length])

  // Auto-focus the chat input when branching context is set
  useEffect(() => {
    if (chatContext) {
      const textarea = document.querySelector('textarea') as HTMLTextAreaElement
      if (textarea) textarea.focus()
    }
  }, [chatContext])

  const handleSend = async (content: string) => {
    if (!content.trim() || readOnly || isProcessing) return

    const trimmed = content.trim()

    // Slash commands — handled entirely by the hooks
    if (commands.handleNote(content)) return
    if (await commands.handleRunAutomation(content)) return
    if (await commands.handleRunPlaybook(content)) return

    // Auto-detect pasted SQL queries and wrap them for Claude
    const looksLikeSQL = /^(SELECT|WITH|SET\s+SESSION|DESCRIBE|SHOW)\s/i.test(trimmed) && !trimmed.includes('investigate') && !trimmed.includes('check')
    if (looksLikeSQL && !trimmed.startsWith('[')) {
      content = `Run this SQL query using execute_trino_query:\n\`\`\`sql\n${trimmed}\n\`\`\``
    }

    // If this is the first message, rename the session, detect type, create root node
    const isFirstMessage = Object.keys(nodes).length === 0
    if (isFirstMessage) {
      handleFirstMessage(content)
    }

    const contextPrefix = chatContext
      ? `[Branching from: ${chatContext.label}]\n\n`
      : ''
    addMessage('user', contextPrefix + content)

    setIsProcessing(true)
    setAgentThinking('')

    // Save context before clearing — need it for the adapter call
    const savedContext = chatContext ? { ...chatContext } : null

    // Set the branch parent if we have graph context
    if (chatContext) {
      branchParentRef.current = chatContext.nodeId
      setChatContext(null)
    }

    const adapter = getAdapter()

    // If the adapter isn't ready, try to reconnect it before giving up
    if (!adapter.isReady() && adapter instanceof WebSocketAdapter) {
      const ws = await waitForSharedWebSocket(2000)
      if (ws) {
        adapter.setWebSocket(ws)
      }
    }

    adapter.onEvent(handleAgentEvent)

    // Pass full node context including result_raw for rich system prompts
    const adapterContext = savedContext ? {
      nodeId: savedContext.nodeId,
      query: savedContext.query,
      resultSummary: savedContext.result_summary,
      resultRaw: savedContext.result_raw,
    } : undefined

    // For first messages, enhance the prompt with skill guidance
    let enhancedContent = content
    if (isFirstMessage) {
      const isHeadless = /\bheadless\b/i.test(content)
      const route = routeInvestigation(content)
      if (isHeadless) {
        enhancedContent = `${content}\n\n[Read the file skills/headless-investigation/SKILL.md for the full investigation flow. This is HEADLESS MODE — run autonomously without asking questions. Gather context from InResponse first, then route to the appropriate investigation skill. Trino account: ${route?.trino_account || 'trustim'}.]`
      } else if (route) {
        const alertId = content.match(/\balert\s*#?\s*(\d{6,})/i)?.[1]
        const irHint = alertId ? ` First run: ir alert view ${alertId} --json to get context from InResponse.` : ''
        const yesterday = new Date(Date.now() - 86400000).toISOString().split('T')[0]
        enhancedContent = `${content}\n\n[Read skills/${route.skill}/SKILL.md then IMMEDIATELY start running queries. Do NOT ask clarifying questions — the user's prompt is your scope. Default date: ${yesterday}. Trino account: ${route.trino_account}. Run 2-3 queries IN PARALLEL in this response to start branching the investigation tree immediately (e.g., email domains AND IP clustering at the same time).${irHint}]`
      } else {
        const alertId = content.match(/\balert\s*#?\s*(\d{6,})/i)?.[1]
        if (alertId) {
          enhancedContent = `${content}\n\n[Run ir alert view ${alertId} --json to get context, then IMMEDIATELY start investigation queries. Do NOT ask questions.]`
        }
      }
    }

    try {
      await adapter.sendMessage(enhancedContent, adapterContext)
    } catch {
      setIsProcessing(false)
      setProcessingInfo(null)
    } finally {
      adapter.offEvent(handleAgentEvent)
    }
  }

  // Ref to always call the latest handleSend (avoids stale closure in event handlers)
  const handleSendRef = useRef(handleSend)
  handleSendRef.current = handleSend

  // Direct execution from node — auto-sends a query without manual chat input
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { query: string; parentNodeId: string; label: string }
      if (!detail?.query) return
      // Set branch context and auto-send
      const parentNode = useGraphStore.getState().nodes[detail.parentNodeId]
      if (parentNode) {
        branchParentRef.current = detail.parentNodeId
      }
      handleSendRef.current(detail.query)
    }
    window.addEventListener('executeFromNode', handler)
    return () => window.removeEventListener('executeFromNode', handler)
  }, [branchParentRef])

  // Auto-send from URL params (?alert=ID, ?investigate=PROMPT)
  useEffect(() => {
    const handler = (e: Event) => {
      const text = (e as CustomEvent).detail?.text
      if (text) handleSendRef.current(text)
    }
    window.addEventListener('autoSendChat', handler)
    return () => window.removeEventListener('autoSendChat', handler)
  }, [])

  // Drag-drop file handling
  const [dragOver, setDragOver] = useState(false)
  const [droppedFileContent, setDroppedFileContent] = useState<string | null>(null)

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (!file) return
    if (file.size > 100000) {
      import('../../store/toast').then(({ useToastStore }) =>
        useToastStore.getState().addToast('File too large (max 100KB)', 'warning', 3000))
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      const content = reader.result as string
      setDroppedFileContent(content)
      import('../../store/toast').then(({ useToastStore }) =>
        useToastStore.getState().addToast(`File "${file.name}" loaded — type your prompt to include it`, 'success', 3000))
    }
    reader.readAsText(file)
  }

  // If file content is pending, prepend it to the next message
  const originalHandleSend = handleSend
  const wrappedHandleSend = async (content: string) => {
    if (droppedFileContent) {
      const enriched = `${content}\n\n--- Attached file content ---\n${droppedFileContent.slice(0, 5000)}`
      setDroppedFileContent(null)
      return originalHandleSend(enriched)
    }
    return originalHandleSend(content)
  }

  const handleTrinoRetry = useCallback(() => {
    const query = trinoAuthFailed?.query
    setTrinoAuthFailed(null)
    if (query) {
      handleSendRef.current(query)
    }
  }, [trinoAuthFailed, setTrinoAuthFailed])

  if (!currentSession) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500 text-sm">
        <p>Start or open an investigation to begin</p>
      </div>
    )
  }

  return (
    <div
      className={`h-full flex flex-col bg-surface-0 ${dragOver ? 'ring-2 ring-accent-blue ring-inset' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      <div className="px-4 py-2 border-b border-surface-3 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-medium text-gray-300">Chat</h2>
          <div className="flex bg-surface-2 rounded-md p-0.5">
            {(['all', 'findings'] as const).map(f => (
              <button
                key={f}
                onClick={() => setChatFilter(f)}
                className={`px-2 py-0.5 text-[10px] rounded transition-colors ${
                  chatFilter === f ? 'bg-surface-4 text-gray-200' : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                {f === 'all' ? 'All' : 'Findings'}
              </button>
            ))}
          </div>
        </div>
        {/* Compact investigation progress */}
        {Object.keys(nodes).length > 1 && (
          <InvestigationMiniStats nodes={nodes} />
        )}
        <div className="flex items-center gap-2">
          {messages.length > 10 && (
            <ChatFilter messages={messages} onJumpTo={(msgId) => {
              const el = document.querySelector(`[data-msg-id="${msgId}"]`)
              if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
            }} />
          )}
          {readOnly && (
            <span className="text-[10px] bg-yellow-900/30 text-yellow-400 px-2 py-0.5 rounded">READ-ONLY</span>
          )}
        </div>
      </div>

      {chatContext && (
        <div className="px-4 py-2.5 bg-accent-blue/[0.07] border-b border-accent-blue/15 flex-shrink-0">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-1.5 h-1.5 bg-accent-blue rounded-full animate-pulse" />
            <span className="text-[13px] text-accent-blue font-medium">
              Branching from: {chatContext.label}
            </span>
            <button onClick={() => setChatContext(null)} className="ml-auto text-[11px] text-gray-400 hover:text-gray-200 transition-colors">
              Cancel
            </button>
          </div>
          {/* Breadcrumb trail: root → ... → parent → current */}
          <ContextBreadcrumb nodeId={chatContext.nodeId} nodes={nodes} onNavigate={(id) => {
            const n = nodes[id]
            if (n) setChatContext({ nodeId: id, label: n.label, query: n.input_prompt || '', result_summary: n.result_summary || '', result_raw: n.result_raw })
          }} />
          {chatContext.result_summary && (
            <p className="text-[11px] text-gray-400 ml-3.5 leading-relaxed line-clamp-2">
              {chatContext.result_summary}
            </p>
          )}
          <p className="text-[10px] text-accent-blue/60 ml-3.5 mt-1">
            Your next message will create a new branch from this node.
          </p>
        </div>
      )}

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-500 px-8">
            <div className="text-4xl mb-4 opacity-30">{'\u{1F50D}'}</div>
            <p className="text-[17px] font-medium text-gray-300 mb-2">What would you like to investigate?</p>
            <p className="text-[14px] text-center max-w-[380px] leading-relaxed text-gray-500 mb-6">
              Type anything to start — an alert ID, member IDs, an IP address, or describe what you're seeing.
              Your message becomes the root of the investigation tree.
            </p>
            <div className="flex flex-wrap gap-2 justify-center max-w-[400px]">
              {[
                'Investigate fake account registrations from yesterday',
                'Alert 249973199',
                'Check ATO signals for member 12345678',
                'Registration spike from .xyz domains',
                'Scraping denial events in the last 7 days',
                'SEV assessment for messaging spam spike',
              ].map((example) => (
                <button
                  key={example}
                  onClick={() => handleSend(example)}
                  className="text-[12px] bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] text-gray-400 hover:text-gray-200 px-3 py-1.5 rounded-lg transition-all"
                >
                  {example}
                </button>
              ))}
            </div>
            {/* Skills, Guide, Templates — quick access to investigation tools */}
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => window.dispatchEvent(new Event('showInvestigationGuide'))}
                className="text-[12px] bg-accent-blue/10 hover:bg-accent-blue/20 text-accent-blue/80 hover:text-accent-blue px-4 py-2 rounded-lg transition-colors"
              >
                Investigation guide
              </button>
              <button
                onClick={() => window.dispatchEvent(new Event('showTemplateGallery'))}
                className="text-[12px] bg-accent-purple/10 hover:bg-accent-purple/20 text-accent-purple/80 hover:text-accent-purple px-4 py-2 rounded-lg transition-colors"
              >
                Templates
              </button>
            </div>
            <p className="text-[10px] text-gray-600 mt-3 max-w-[360px] text-center leading-relaxed">
              20 investigation skills + 13 action skills loaded. Type / to browse. Your prompt auto-routes to the best skill.
            </p>
            <div className="flex gap-4 mt-3 text-[10px] text-gray-600">
              <span>Cmd+K quick open</span>
              <span>Cmd+Shift+F global search</span>
              <span>/ for skills</span>
              <span>? for help</span>
            </div>
            {/* Recent investigations */}
            <RecentInvestigations />
          </div>
        )}
        {(() => {
          const isFinding = (msg: typeof messages[0]) => {
            if (msg.role === 'user') return true
            const c = msg.content.toLowerCase()
            if (c.includes('investigation complete') || c.includes('investigation progress') || c.includes('investigation stopped')) return true
            if (c.includes('key findings') || c.includes('findings so far')) return true
            if (c.includes('google doc') || c.includes('docs.google.com')) return true
            if (c.includes('sev-')) return true
            const nids = msg.node_ids || []
            if (nids.length > 0 && msg.role === 'assistant') {
              const node = nodes[nids[0]]
              if (node && node.status === 'completed' && node.confidence > 0.3) return true
            }
            return false
          }
          const visible = chatFilter === 'findings' ? messages.filter(isFinding) : messages
          return visible
        })().map((msg, idx, visible) => {
          const prevMsg = idx > 0 ? visible[idx - 1] : null
          const showDivider = (msg.node_ids || []).length > 0 && (!prevMsg || (prevMsg.node_ids || [])[0] !== (msg.node_ids || [])[0])
          const linkedNode = (msg.node_ids || [])[0] ? useGraphStore.getState().nodes[(msg.node_ids || [])[0]] : null

          return (
            <div key={msg.id} data-msg-id={msg.id}>
              {showDivider && linkedNode && (
                <div className="flex items-center gap-2 py-1 my-1">
                  <div className="flex-1 h-px bg-white/[0.04]" />
                  <span className="text-[10px] text-gray-500 flex-shrink-0">
                    Step: {linkedNode.label?.slice(0, 40)}
                  </span>
                  <div className="flex-1 h-px bg-white/[0.04]" />
                </div>
              )}
              <ChatMessage message={msg} />
            </div>
          )
        })}
        {/* Real-time observability: show agent progress with step tracking */}
        {isProcessing && (
          <div className="bg-surface-2/50 border border-white/[0.04] rounded-xl p-3 animate-[fadeIn_0.2s_ease-out]">
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2 text-[13px] text-gray-300">
                <div className="w-2 h-2 bg-accent-blue rounded-full animate-pulse" />
                <span className="font-medium">{processingInfo?.operation || 'Agent is working...'}</span>
              </div>
              <div className="flex items-center gap-2">
                <LiveElapsed />
                <button
                  onClick={() => {
                    const adapter = getAdapter()
                    adapter.abort()
                    setIsProcessing(false)
                    setProcessingInfo(null)
                    setAgentThinking('')
                    // Mark all running nodes as terminated
                    const graph = useGraphStore.getState()
                    const runningNodes = Object.values(graph.nodes).filter(n => n.status === 'running')
                    for (const n of runningNodes) {
                      graph.updateNode(n.node_id, { status: 'failed', result_summary: 'Manually terminated by investigator' })
                    }
                    addMessage('system', `Agent execution stopped. ${runningNodes.length} running node${runningNodes.length !== 1 ? 's' : ''} terminated.`)
                  }}
                  className="text-[10px] text-red-400 hover:text-red-300 transition-colors"
                >
                  Stop
                </button>
              </div>
            </div>
            {/* Step progress — shows completed/running/total */}
            <AgentStepProgress nodes={nodes} />
            {agentThinking && (
              <div className="mt-2 text-[12px] text-gray-400 leading-relaxed max-h-[120px] overflow-y-auto whitespace-pre-wrap border-l-2 border-accent-blue/20 pl-3 ml-1">
                {agentThinking}
              </div>
            )}
          </div>
        )}
        {/* Playbook progress in chat */}
        <PlaybookChatProgress sessionId={currentSession.id} />
        {/* Auto-investigate progress banner — uses nodes from parent subscription */}
        <AutoInvestigateBanner nodes={nodes} />
      </div>

      {/* Drag overlay */}
      {dragOver && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-surface-0/80 backdrop-blur-sm pointer-events-none">
          <div className="text-center">
            <div className="text-3xl mb-2 opacity-50">{'\u{1F4C4}'}</div>
            <p className="text-[14px] text-accent-blue">Drop file to attach</p>
          </div>
        </div>
      )}
      {/* Dropped file indicator */}
      {droppedFileContent && (
        <div className="px-4 py-1.5 bg-accent-cyan/[0.07] border-t border-accent-cyan/15 flex items-center gap-2 flex-shrink-0">
          <span className="text-[11px] text-accent-cyan">File attached — will be included in your next message</span>
          <button onClick={() => setDroppedFileContent(null)} className="text-[10px] text-gray-400 hover:text-gray-200 ml-auto">Remove</button>
        </div>
      )}
      {/* Trino auth error retry banner */}
      {trinoAuthFailed && (
        <div className="mx-4 mb-2 bg-orange-900/20 border border-orange-700/30 rounded-xl p-3 animate-[fadeIn_0.2s_ease-out]">
          <div className="flex items-center gap-2 text-[13px] text-orange-300">
            <span className="font-medium">Trino authentication expired</span>
          </div>
          <div className="mt-1.5 flex items-center gap-2">
            <code className="text-[11px] bg-black/30 px-2 py-1 rounded text-orange-200 select-all">
              captain setup trino
            </code>
            <button onClick={handleTrinoRetry} className="text-[11px] text-orange-300 hover:text-orange-200 underline">
              Retry
            </button>
            <button onClick={() => setTrinoAuthFailed(null)} className="text-[11px] text-gray-500 hover:text-gray-300">
              Dismiss
            </button>
          </div>
        </div>
      )}
      {/* Investigation maturity banner */}
      <InvestigationMaturityBanner nodes={nodes} />
      <ChatInput onSend={wrappedHandleSend} disabled={isProcessing || readOnly} />
    </div>
  )
}
