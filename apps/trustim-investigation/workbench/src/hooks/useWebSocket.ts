import { useEffect, useRef, useCallback } from 'react'
import { useSessionStore } from '../store/session'
import { useGraphStore } from '../store/graph'
import { useToastStore } from '../store/toast'
import { sessionsApi } from '../api'

const pendingMessages: string[] = []
let sharedWebSocket: WebSocket | null = null
const sharedSocketWaiters = new Set<(ws: WebSocket | null) => void>()

function resolveSharedSocketWaiters(ws: WebSocket | null) {
  for (const resolve of sharedSocketWaiters) {
    resolve(ws)
  }
  sharedSocketWaiters.clear()
}

function setSharedWebSocket(ws: WebSocket | null) {
  sharedWebSocket = ws
  if (ws && ws.readyState === WebSocket.OPEN) {
    resolveSharedSocketWaiters(ws)
  }
}

export function getSharedWebSocket(): WebSocket | null {
  return sharedWebSocket && sharedWebSocket.readyState === WebSocket.OPEN ? sharedWebSocket : null
}

export function waitForSharedWebSocket(timeout = 2000): Promise<WebSocket | null> {
  const ws = getSharedWebSocket()
  if (ws) return Promise.resolve(ws)

  return new Promise((resolve) => {
    const waiter = (socket: WebSocket | null) => {
      clearTimeout(timer)
      sharedSocketWaiters.delete(waiter)
      resolve(socket)
    }

    const timer = setTimeout(() => {
      sharedSocketWaiters.delete(waiter)
      resolve(getSharedWebSocket())
    }, timeout)

    sharedSocketWaiters.add(waiter)
  })
}

export function queueWsMessage(ws: WebSocket | null, message: object) {
  const serialized = JSON.stringify(message)
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(serialized)
  } else {
    pendingMessages.push(serialized)
  }
}

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const retryRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout>>()
  const pingIntervalRef = useRef<ReturnType<typeof setInterval>>()
  const intentionalCloseRef = useRef(false)
  const setConnected = useSessionStore((s) => s.setConnected)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN || wsRef.current?.readyState === WebSocket.CONNECTING) return
    intentionalCloseRef.current = false

    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current)
      pingIntervalRef.current = undefined
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.hostname
    const backendPort = 3100
    const ws = new WebSocket(`${protocol}//${host}:${backendPort}/ws`)
    wsRef.current = ws
    setSharedWebSocket(ws)

    ws.onopen = () => {
      const wasReconnect = retryRef.current > 0
      setConnected(true)
      retryRef.current = 0
      setSharedWebSocket(ws)
      if (wasReconnect) {
        useToastStore.getState().addToast('Reconnected to server', 'success', 2000)
      }
      while (pendingMessages.length > 0) {
        const msg = pendingMessages.shift()!
        ws.send(msg)
      }
    }

    ws.onclose = () => {
      setConnected(false)
      if (wsRef.current === ws) {
        wsRef.current = null
      }
      if (sharedWebSocket === ws) {
        setSharedWebSocket(null)
      }
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current)
        pingIntervalRef.current = undefined
      }
      if (intentionalCloseRef.current) {
        return
      }
      const delay = Math.min(1000 * Math.pow(2, retryRef.current), 30000)
      retryRef.current++
      retryTimerRef.current = setTimeout(connect, delay)
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        switch (msg.type) {
          case 'node_created':
          case 'node_updated':
            if (msg.payload?.node_id) {
              useGraphStore.getState().updateNode(msg.payload.node_id, msg.payload)
            }
            break
          case 'edge_created':
            if (msg.payload) {
              useGraphStore.getState().addEdge(
                msg.payload.source,
                msg.payload.target,
                msg.payload.relation || 'led_to'
              )
            }
            break
          case 'skills_changed':
            useToastStore.getState().addToast(
              `Skill updated: ${msg.payload?.file || 'unknown'}`,
              'info',
              3000
            )
            break
          case 'session_saved':
            break
          case 'bg_node_start': {
            const p = msg.payload
            if (!p?.node || !p?.sessionId) break
            const currentId = useSessionStore.getState().currentSession?.id
            if (p.sessionId !== currentId) break
            const node = p.node
            if (node.node_id) {
              useGraphStore.getState().addNode(node)
              if (node.parent_ids?.[0]) {
                useGraphStore.getState().addEdge(node.parent_ids[0], node.node_id, 'led_to')
              }
            }
            break
          }
          case 'bg_node_complete': {
            const p = msg.payload
            if (!p?.nodeId || !p?.sessionId) break
            if (p.sessionId !== useSessionStore.getState().currentSession?.id) break
            if (p.node) {
              useGraphStore.getState().updateNode(p.nodeId, {
                status: p.node.status,
                result_raw: p.node.result_raw,
                result_summary: p.node.result_summary,
                confidence: p.node.confidence,
                duration_ms: p.node.duration_ms,
              })
            }
            break
          }
          case 'bg_investigation_done': {
            const p = msg.payload
            if (!p?.sessionId) break
            if (p.sessionId !== useSessionStore.getState().currentSession?.id) break
            sessionsApi.get(p.sessionId)
              .then((data: any) => {
                if (data?.id && data.id === useSessionStore.getState().currentSession?.id) {
                  if (data.nodes) {
                    const edges = (data.edges || []).map((e: any) => ({
                      id: e.id || `edge-${e.source}-${e.target}`,
                      source: e.source,
                      target: e.target,
                      relation: e.relation || 'led_to',
                    }))
                    useGraphStore.getState().loadGraph(data.nodes, edges)
                  }
                  if (data.messages) {
                    const sess = useSessionStore.getState().currentSession
                    if (sess) {
                      // Merge server messages with local to preserve unsaved user input
                      const serverIds = new Set((data.messages as any[]).map((m: any) => m.id))
                      const localOnly = (sess.messages || []).filter(m => !serverIds.has(m.id))
                      useSessionStore.setState({ currentSession: { ...sess, messages: [...data.messages, ...localOnly] } })
                    }
                  }
                }
              })
              .catch(() => {})
            useToastStore.getState().addToast(
              `Investigation ${p.status === 'completed' ? 'completed' : p.status === 'failed' ? 'failed' : 'stopped'}`,
              p.status === 'completed' ? 'success' : 'warning',
              5000
            )
            break
          }
          case 'bg_doc_created': {
            const p = msg.payload
            if (!p?.sessionId || !p?.docUrl) break
            if (p.sessionId !== useSessionStore.getState().currentSession?.id) break
            sessionsApi.get(p.sessionId)
              .then((data: any) => {
                if (data?.messages) {
                  const sess = useSessionStore.getState().currentSession
                  if (sess && sess.id === p.sessionId) {
                    // Merge server messages with local to preserve unsaved user input
                    const serverIds = new Set((data.messages as any[]).map((m: any) => m.id))
                    const localOnly = (sess.messages || []).filter(m => !serverIds.has(m.id))
                    useSessionStore.setState({ currentSession: { ...sess, messages: [...data.messages, ...localOnly] } })
                  }
                }
              })
              .catch(() => {})
            useToastStore.getState().addToast('Investigation report published to Google Docs', 'success', 5000)
            break
          }
          case 'bg_auth_required': {
            const p = msg.payload
            if (!p?.sessionId) break
            if (p.sessionId !== useSessionStore.getState().currentSession?.id) break
            useToastStore.getState().addToast(
              'Background investigation paused — Trino auth expired. Run "captain setup trino" then resume.',
              'warning',
              0 // persistent until dismissed
            )
            break
          }
          case 'bg_agent_thinking':
            break
        }
      } catch {
        // Ignore parse errors
      }
    }

    pingIntervalRef.current = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)
  }, [setConnected])

  useEffect(() => {
    connect()
    return () => {
      intentionalCloseRef.current = true
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current)
      if (pingIntervalRef.current) clearInterval(pingIntervalRef.current)
      if (sharedWebSocket === wsRef.current) {
        setSharedWebSocket(null)
      }
      wsRef.current?.close()
    }
  }, [connect])

  return wsRef
}
