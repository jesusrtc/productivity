import { useEffect, useRef } from 'react'
import { sessionsApi, investigationsApi, setupApi } from '../api'
import { useSessionStore } from '../store/session'
import { useGraphStore } from '../store/graph'
import { useToastStore } from '../store/toast'
import { getAdapter, setAdapter, WebSocketAdapter } from '../utils/claude-adapter'

/**
 * Bridge adapter setup: check bridge availability, create WebSocketAdapter,
 * and poll until the WS is connected to attach it.
 */
export function useAdapterSetup(wsRef: React.RefObject<WebSocket | null>) {
  const isConnected = useSessionStore((s) => s.isConnected)

  const adapterConfigured = useRef(false)
  useEffect(() => {
    if (adapterConfigured.current) return
    adapterConfigured.current = true

    let attempts = 0
    const checkBridge = () => {
      setupApi.bridgeStatus()
        .then((status) => {
          if (status.available) {
            const wsAdapter = new WebSocketAdapter()
            setAdapter(wsAdapter)
            const attach = () => {
              if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                wsAdapter.setWebSocket(wsRef.current)
                useToastStore.getState().addToast('Claude Code connected', 'success', 3000)
              } else {
                setTimeout(attach, 300)
              }
            }
            attach()
          } else {
            useToastStore.getState().addToast('Claude Code CLI not found — using simulated mode', 'warning', 6000)
          }
        })
        .catch(() => {
          attempts++
          if (attempts < 5) {
            setTimeout(checkBridge, 2000)
          }
        })
    }
    checkBridge()
  }, [])

  // Re-attach WS to adapter on reconnect
  useEffect(() => {
    if (!isConnected || !wsRef.current) return
    const adapter = getAdapter()
    if (adapter instanceof WebSocketAdapter) {
      adapter.setWebSocket(wsRef.current)
    }
  }, [isConnected])
}

/**
 * Poll for background investigation / playbook updates for the current session.
 */
export function useSessionPolling() {
  const currentSession = useSessionStore((s) => s.currentSession)

  useEffect(() => {
    if (!currentSession?.id) return
    const targetSessionId = currentSession.id
    let active = true
    const poll = async () => {
      const currentId = useSessionStore.getState().currentSession?.id
      if (currentId !== targetSessionId) { active = false; return }

      // Skip polling while a foreground agent is active — its in-memory nodes
      // haven't been saved to disk yet, so the server has stale data
      const processing = useSessionStore.getState().processingInfo
      if (processing?.active) return

      try {
        const [invData, data] = await Promise.all([
          investigationsApi.get(targetSessionId).catch(() => null),
          sessionsApi.get(targetSessionId) as Promise<any>,
        ])
        const isRunning = invData ? (invData as any).status === 'running' : false
        if (!data?.id || data.id !== targetSessionId) return

        if (useSessionStore.getState().currentSession?.id !== targetSessionId) return

        // Re-check after async: foreground agent may have started during the fetch
        if (useSessionStore.getState().processingInfo?.active) return

        const currentNodes = useGraphStore.getState().nodes
        const currentNodeCount = Object.keys(currentNodes).length
        const newNodeCount = Object.keys(data.nodes || {}).length
        const currentMsgs = useSessionStore.getState().currentSession?.messages?.length || 0
        const newMsgs = (data.messages || []).length

        const nodesChanged = newNodeCount !== currentNodeCount || Object.values(data.nodes || {}).some((n: any) => {
          const existing = currentNodes[n.node_id]
          return !existing || existing.status !== n.status
        })

        // Only overwrite graph if server has more or updated data — never fewer nodes
        if (nodesChanged && newNodeCount > 0 && newNodeCount >= currentNodeCount) {
          const edges = (data.edges || []).map((e: any) => ({
            id: e.id || `edge-${e.source}-${e.target}`,
            source: e.source,
            target: e.target,
            relation: e.relation || 'led_to',
          }))
          useGraphStore.getState().loadGraph(data.nodes, edges)
        }
        if (newMsgs > currentMsgs) {
          const sess = useSessionStore.getState().currentSession
          if (sess && sess.id === targetSessionId) {
            const serverIds = new Set((data.messages as any[]).map((m: any) => m.id))
            const localOnly = (sess.messages || []).filter(m => !serverIds.has(m.id))
            useSessionStore.setState({ currentSession: { ...sess, messages: [...data.messages, ...localOnly] } })
          }
        }
        if (!isRunning && !nodesChanged && newMsgs <= currentMsgs) {
          // Nothing new and no agent running — slow down polling
        }
      } catch {}
    }
    poll()
    const timers: ReturnType<typeof setInterval>[] = []
    timers.push(setInterval(() => { if (active) poll() }, 1000))
    setTimeout(() => {
      if (!active) return
      clearInterval(timers[0])
      timers[1] = setInterval(() => { if (active) poll() }, 3000)
    }, 30000)
    return () => { active = false; timers.forEach(t => clearInterval(t)) }
  }, [currentSession?.id])
}
