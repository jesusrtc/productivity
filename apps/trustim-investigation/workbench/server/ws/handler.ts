import { WebSocketServer, WebSocket } from 'ws'
import http from 'http'
import fs from 'fs'
import { ClaudeBridge } from '../bridge/claude-bridge.js'
import { handleAgentMessage } from '../bridge/event-translator.js'
import { sanitizeId, safePath } from '../middleware/sanitize.js'

export interface WsHandlerConfig {
  SESSIONS_DIR: string
  REPO_ROOT: string
}

export interface WsHandler {
  broadcast: (message: object, excludeWs?: WebSocket) => void
  getSocketBridges: () => Map<WebSocket, ClaudeBridge>
  getBridgeMaxTurns: () => number
  setBridgeMaxTurns: (n: number) => void
}

export function createWsHandler(server: http.Server, config: WsHandlerConfig): WsHandler {
  const { SESSIONS_DIR, REPO_ROOT } = config

  const clients = new Set<WebSocket>()
  const socketBridges = new Map<WebSocket, ClaudeBridge>()
  let bridgeMaxTurns = 25

  function getBridgeForSocket(ws: WebSocket): ClaudeBridge {
    let bridge = socketBridges.get(ws)
    if (!bridge) {
      bridge = new ClaudeBridge(REPO_ROOT)
      bridge.maxTurns = bridgeMaxTurns
      socketBridges.set(ws, bridge)
    }
    return bridge
  }

  function broadcast(message: object, excludeWs?: WebSocket) {
    const data = JSON.stringify(message)
    for (const client of clients) {
      if (client !== excludeWs && client.readyState === WebSocket.OPEN) {
        client.send(data)
      }
    }
  }

  function handleWsMessage(ws: WebSocket, msg: { type: string; payload?: unknown }) {
    switch (msg.type) {
      case 'node_created':
      case 'node_updated':
      case 'edge_created':
      case 'chat_message':
        // Broadcast to other clients (multi-window support per R33)
        broadcast(msg, ws)
        break
      case 'save_session': {
        const session = msg.payload as { id: string }
        if (session?.id) {
          const filePath = safePath(SESSIONS_DIR, `${sanitizeId(session.id)}.json`)
          if (!filePath) break
          try {
            fs.writeFileSync(filePath, JSON.stringify(session, null, 2))
            ws.send(JSON.stringify({ type: 'session_saved', id: session.id }))
          } catch (e) {
            console.error('Failed to save session:', e)
            ws.send(JSON.stringify({ type: 'error', message: 'Failed to save session' }))
          }
        }
        break
      }
      case 'agent_message': {
        // Real Claude Code integration: forward message through the bridge
        const payload = msg.payload as { message: string; systemPrompt?: string }
        if (!payload?.message) break

        handleAgentMessage(ws, payload.message, payload.systemPrompt, getBridgeForSocket(ws))
        break
      }
      case 'agent_abort': {
        socketBridges.get(ws)?.abort()
        ws.send(JSON.stringify({ type: 'agent_aborted' }))
        break
      }
      case 'ping':
        ws.send(JSON.stringify({ type: 'pong' }))
        break
    }
  }

  const wss = new WebSocketServer({ server, path: '/ws' })

  wss.on('connection', (ws) => {
    clients.add(ws)
    ws.send(JSON.stringify({ type: 'connected', timestamp: new Date().toISOString() }))

    ws.on('close', () => {
      clients.delete(ws)
      const socketBridge = socketBridges.get(ws)
      socketBridge?.abort()
      socketBridges.delete(ws)
    })

    ws.on('message', (raw) => {
      try {
        const msg = JSON.parse(raw.toString())
        handleWsMessage(ws, msg)
      } catch {
        ws.send(JSON.stringify({ type: 'error', message: 'Invalid JSON' }))
      }
    })
  })

  return {
    broadcast,
    getSocketBridges: () => socketBridges,
    getBridgeMaxTurns: () => bridgeMaxTurns,
    setBridgeMaxTurns: (n: number) => { bridgeMaxTurns = n },
  }
}
