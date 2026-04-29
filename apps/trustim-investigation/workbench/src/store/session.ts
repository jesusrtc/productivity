import { create } from 'zustand'
import { sessionsApi } from '../api'
import type { Session, SessionSummary, ChatMessage } from '../types'
import { createSession } from '../types'
import { v4 as uuid } from 'uuid'
import { useGraphStore } from './graph'
import { resetLayoutCache } from '../utils/layout'

/** Normalize edges: validate references + ensure id/relation fields */
function normalizeEdges(edges: any[], nodeIds: Set<string>): any[] {
  return (edges || [])
    .filter((e: { source: string; target: string }) => nodeIds.has(e.source) && nodeIds.has(e.target))
    .map((e: any) => ({
      id: e.id || `edge-${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      relation: e.relation || 'led_to',
    }))
}

/** Context node for graph-aware chat (R9, R10) */
export interface ChatContext {
  nodeId: string
  label: string
  query: string
  result_summary: string
  result_raw?: string
}

/** Cached session + graph state for tab switching */
interface TabSnapshot {
  session: Session
  readOnly: boolean
}

interface SessionState {
  currentSession: Session | null
  sessionList: SessionSummary[]
  isConnected: boolean
  /** Per-tab session snapshots for fast switching */
  tabSnapshots: Record<string, TabSnapshot>
  /** Active chat context from a selected graph node (R9) */
  chatContext: ChatContext | null
  /** Processing indicator state (R4) */
  processingInfo: { active: boolean; operation: string } | null
  /** Whether the session is read-only (imported for review, R56) */
  readOnly: boolean
  /** Token consumption tracking (PRD Section 7.4) */
  tokenUsage: { input: number; output: number; total: number }
  addTokenUsage: (input: number, output: number) => void

  // Session lifecycle
  newSession: (name: string, startingInput: string) => Session
  loadSession: (session: Session, readOnly?: boolean) => void
  closeSession: () => void
  renameSession: (name: string) => void

  // Chat context
  setChatContext: (ctx: ChatContext | null) => void
  setProcessingInfo: (info: { active: boolean; operation: string } | null) => void

  // Chat
  addMessage: (role: ChatMessage['role'], content: string, extras?: Partial<ChatMessage>) => string
  updateMessage: (messageId: string, updates: Partial<ChatMessage>) => void

  // Track tools/skills
  recordSkillUsed: (skillName: string) => void
  recordToolUsed: (toolName: string) => void

  // Session linking
  linkSession: (sessionId: string) => void
  unlinkSession: (sessionId: string) => void

  // Tab snapshots
  /** Snapshot current session. Pass expectedId to guard against snapshotting the wrong session. */
  snapshotCurrentTab: (expectedId?: string) => void
  restoreTab: (sessionId: string) => boolean
  clearTabSnapshot: (sessionId: string) => void

  // Connection
  setConnected: (connected: boolean) => void

  // Persistence
  getSessionData: () => Session | null
  setSessionList: (list: SessionSummary[]) => void
  /** Flush current session to server immediately (no debounce). Call before session transitions. Pass force=true to save even empty sessions. */
  flushSave: (force?: boolean) => Promise<void>
}

export const useSessionStore = create<SessionState>((set, get) => ({
  currentSession: null,
  sessionList: [],
  isConnected: false,
  chatContext: null,
  processingInfo: null,
  readOnly: false,
  tokenUsage: { input: 0, output: 0, total: 0 },
  tabSnapshots: {},

  addTokenUsage: (input, output) => {
    set((state) => ({
      tokenUsage: {
        input: state.tokenUsage.input + input,
        output: state.tokenUsage.output + output,
        total: state.tokenUsage.total + input + output,
      },
    }))
  },

  newSession: (name, startingInput) => {
    const session = createSession(uuid(), name, startingInput)
    const graph = useGraphStore.getState()
    resetLayoutCache()
    graph.clearGraph()

    // No root node created here — the first chat message becomes the root node.
    // This gives the user a blank canvas to type their investigation prompt.

    set({ currentSession: session, chatContext: null, readOnly: false })
    return session
  },

  loadSession: (session, readOnly = false) => {
    // Flush save the current session before switching — prevents message/node loss
    get().flushSave()
    if (!session?.id || !session?.nodes) {
      console.error('loadSession: invalid session — missing id or nodes')
      return
    }
    resetLayoutCache() // Clear stale positions from previous session
    useGraphStore.getState().clearGraph() // Clear old session's nodes before loading new ones
    const nodeIds = new Set(Object.keys(session.nodes || {}))
    const validEdges = normalizeEdges(session.edges, nodeIds)
    useGraphStore.getState().loadGraph(session.nodes || {}, validEdges)
    set({ currentSession: { ...session, edges: validEdges }, chatContext: null, readOnly })
    // Auto-select the most recent completed node so the investigator sees where they left off
    const nodeList = Object.values(session.nodes)
    if (nodeList.length > 0) {
      const mostRecent = nodeList
        .filter(n => n.status === 'completed')
        .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())[0]
      if (mostRecent) {
        setTimeout(() => useGraphStore.getState().selectNode(mostRecent.node_id), 300)
      }
    }
  },

  closeSession: () => {
    // Flush save before clearing — prevents message/node loss on session switch
    get().flushSave()
    resetLayoutCache()
    useGraphStore.getState().clearGraph()
    set({ currentSession: null, chatContext: null, readOnly: false })
  },

  renameSession: (name) => {
    set((state) => {
      if (!state.currentSession) return state
      return {
        currentSession: { ...state.currentSession, name, updated_at: new Date().toISOString() },
      }
    })
  },

  setChatContext: (ctx) => set({ chatContext: ctx }),

  setProcessingInfo: (info) => set({ processingInfo: info }),

  addMessage: (role, content, extras) => {
    const id = uuid()
    const message: ChatMessage = {
      id,
      role,
      content,
      timestamp: new Date().toISOString(),
      node_ids: [],
      ...extras,
    }
    set((state) => {
      if (!state.currentSession) return state
      return {
        currentSession: {
          ...state.currentSession,
          messages: [...state.currentSession.messages, message],
          updated_at: new Date().toISOString(),
        },
      }
    })
    return id
  },

  updateMessage: (messageId, updates) => {
    set((state) => {
      if (!state.currentSession) return state
      return {
        currentSession: {
          ...state.currentSession,
          messages: state.currentSession.messages.map((m) =>
            m.id === messageId ? { ...m, ...updates } : m
          ),
        },
      }
    })
  },

  recordSkillUsed: (skillName) => {
    set((state) => {
      if (!state.currentSession) return state
      const skills = state.currentSession.skills_used
      if (skills.includes(skillName)) return state
      return {
        currentSession: {
          ...state.currentSession,
          skills_used: [...skills, skillName],
        },
      }
    })
  },

  recordToolUsed: (toolName) => {
    set((state) => {
      if (!state.currentSession) return state
      const tools = state.currentSession.tools_used
      if (tools.includes(toolName)) return state
      return {
        currentSession: {
          ...state.currentSession,
          tools_used: [...tools, toolName],
        },
      }
    })
  },

  linkSession: (sessionId) => {
    set((state) => {
      if (!state.currentSession) return state
      const linked = state.currentSession.linked_sessions || []
      if (linked.includes(sessionId)) return state
      return {
        currentSession: { ...state.currentSession, linked_sessions: [...linked, sessionId] },
      }
    })
  },

  unlinkSession: (sessionId) => {
    set((state) => {
      if (!state.currentSession) return state
      const linked = (state.currentSession.linked_sessions || []).filter(id => id !== sessionId)
      return {
        currentSession: { ...state.currentSession, linked_sessions: linked },
      }
    })
  },

  snapshotCurrentTab: (expectedId?: string) => {
    const state = get()
    if (!state.currentSession?.id) return
    // Guard: if caller specifies an expected ID, only snapshot if it matches
    if (expectedId && state.currentSession.id !== expectedId) {
      console.warn(`snapshotCurrentTab: expected ${expectedId} but currentSession is ${state.currentSession.id} — skipping`)
      return
    }
    const graphState = useGraphStore.getState()
    const session: Session = {
      ...state.currentSession,
      nodes: graphState.nodes,
      edges: graphState.edges,
    }
    set((s) => ({
      tabSnapshots: {
        ...s.tabSnapshots,
        [session.id]: { session, readOnly: s.readOnly },
      },
    }))
  },

  restoreTab: (sessionId) => {
    const snapshot = get().tabSnapshots[sessionId]
    if (!snapshot?.session?.id) return false
    resetLayoutCache()
    const nodeIds = new Set(Object.keys(snapshot.session.nodes || {}))
    const edges = normalizeEdges(snapshot.session.edges, nodeIds)
    // Only clear + load after validation passes
    useGraphStore.getState().clearGraph()
    useGraphStore.getState().loadGraph(snapshot.session.nodes || {}, edges)
    set({
      currentSession: snapshot.session,
      chatContext: null,
      readOnly: snapshot.readOnly,
    })
    return true
  },

  clearTabSnapshot: (sessionId) => {
    set((s) => {
      const { [sessionId]: _, ...rest } = s.tabSnapshots
      return { tabSnapshots: rest }
    })
  },

  setConnected: (connected) => set({ isConnected: connected }),

  getSessionData: () => {
    const state = get()
    if (!state.currentSession) return null
    const graphState = useGraphStore.getState()
    return {
      ...state.currentSession,
      nodes: graphState.nodes,
      edges: graphState.edges,
    }
  },

  setSessionList: (list) => set({ sessionList: list }),

  flushSave: async (force?: boolean) => {
    const data = get().getSessionData()
    if (!data) return
    if (!force) {
      const hasContent = Object.keys(data.nodes || {}).length > 0
        || (data.messages && data.messages.length > 0)
      if (!hasContent) return
    }
    const json = JSON.stringify(data)
    // Save to server and wait for completion
    try {
      await sessionsApi.save(data.id, data)
    } catch {}
    // Backup to localStorage
    try { localStorage.setItem(`investigation-backup-${data.id}`, json) } catch {}
  },
}))
