import { create } from 'zustand'
import type { InvestigationNode, InvestigationEdge, NodeStatus, ViewMode } from '../types'
import { createNode } from '../types'
import { v4 as uuid } from 'uuid'
import { useHistoryStore } from './history'

// Bug #10: Module-level timer for debounced confidence propagation
let _propagateTimer: ReturnType<typeof setTimeout> | null = null

interface GraphState {
  nodes: Record<string, InvestigationNode>
  edges: InvestigationEdge[]
  selectedNodeId: string | null
  /** Multi-select for batch operations (Shift+click) */
  selectedNodeIds: Set<string>
  viewMode: ViewMode
  /** When set, only this node's branch (ancestors + descendants) is highlighted */
  focusBranchNodeId: string | null
  /** Graph layout direction: TB (top-bottom) or LR (left-right) */
  layoutDirection: 'TB' | 'LR'

  // Actions
  addNode: (overrides: Partial<InvestigationNode> & { node_id?: string }) => string
  updateNode: (nodeId: string, updates: Partial<InvestigationNode>) => void
  removeNode: (nodeId: string) => void
  addEdge: (source: string, target: string, relation: InvestigationEdge['relation']) => void
  selectNode: (nodeId: string | null) => void
  toggleMultiSelect: (nodeId: string) => void
  clearMultiSelect: () => void
  batchMarkDeadEnd: () => void
  batchAddTag: (tag: string) => void
  setViewMode: (mode: ViewMode) => void
  setFocusBranch: (nodeId: string | null) => void
  toggleLayoutDirection: () => void
  toggleSubtreeCollapse: (nodeId: string) => void
  collapseAllBenign: (threshold?: number) => void
  expandHighScorePath: () => void
  markDeadEnd: (nodeId: string) => void
  overrideConfidence: (nodeId: string, confidence: number) => void
  addTag: (nodeId: string, tag: string) => void
  removeTag: (nodeId: string, tag: string) => void
  togglePin: (nodeId: string) => void
  updateNodeStatus: (nodeId: string, status: NodeStatus, durationMs?: number) => void
  propagateConfidence: (nodeId: string) => void
  addInvestigatorNote: (nodeId: string, note: string) => void
  setInvestigatorNotes: (nodeId: string, notes: string) => void

  // Queries
  getChildren: (nodeId: string) => string[]
  getAncestors: (nodeId: string) => string[]
  getSubtree: (nodeId: string) => string[]
  getRootNodes: () => string[]

  // Auto-investigate (R24) with configurable limits (PRD Section 8)
  autoInvestigateNodeId: string | null
  /** The node currently being explored by auto-investigate (frontier indicator) */
  autoInvestigateCurrentId: string | null
  maxConcurrentBranches: number
  maxAutoDepth: number
  startAutoInvestigate: (nodeId: string) => void
  stopAutoInvestigate: () => void
  setAutoInvestigateCurrent: (nodeId: string | null) => void
  setMaxConcurrentBranches: (n: number) => void
  setMaxAutoDepth: (n: number) => void

  // Bulk operations
  loadGraph: (nodes: Record<string, InvestigationNode>, edges: InvestigationEdge[]) => void
  clearGraph: () => void
}

export const useGraphStore = create<GraphState>((set, get) => ({
  nodes: {},
  edges: [],
  selectedNodeId: null,
  selectedNodeIds: new Set<string>(),
  viewMode: 'graph',
  focusBranchNodeId: null,
  layoutDirection: 'TB',
  autoInvestigateNodeId: null,
  autoInvestigateCurrentId: null,
  maxConcurrentBranches: 3,
  maxAutoDepth: 5,

  addNode: (overrides) => {
    const nodeId = overrides.node_id || uuid()
    const node = createNode({ ...overrides, node_id: nodeId })
    set((state) => ({
      nodes: { ...state.nodes, [nodeId]: node },
    }))
    return nodeId
  },

  updateNode: (nodeId, updates) => {
    set((state) => {
      const existing = state.nodes[nodeId]
      if (!existing) return state
      return {
        nodes: {
          ...state.nodes,
          [nodeId]: { ...existing, ...updates },
        },
      }
    })
  },

  removeNode: (nodeId) => {
    set((state) => {
      const { [nodeId]: _, ...remainingNodes } = state.nodes
      return {
        nodes: remainingNodes,
        edges: state.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
        selectedNodeId: state.selectedNodeId === nodeId ? null : state.selectedNodeId,
      }
    })
  },

  addEdge: (source, target, relation) => {
    const edge: InvestigationEdge = {
      id: `${source}-${target}`,
      source,
      target,
      relation,
    }
    set((state) => ({
      edges: [...state.edges, edge],
    }))
  },

  selectNode: (nodeId) => set({ selectedNodeId: nodeId }),

  toggleMultiSelect: (nodeId) => {
    set((state) => {
      const next = new Set(state.selectedNodeIds)
      if (next.has(nodeId)) next.delete(nodeId)
      else next.add(nodeId)
      return { selectedNodeIds: next }
    })
  },

  clearMultiSelect: () => set({ selectedNodeIds: new Set() }),

  batchMarkDeadEnd: () => {
    set((state) => {
      const updated = { ...state.nodes }
      for (const id of state.selectedNodeIds) {
        if (updated[id]) updated[id] = { ...updated[id], is_dead_end: true }
      }
      return { nodes: updated, selectedNodeIds: new Set() }
    })
  },

  batchAddTag: (tag) => {
    set((state) => {
      const updated = { ...state.nodes }
      for (const id of state.selectedNodeIds) {
        if (updated[id] && !(updated[id].tags || []).includes(tag)) {
          updated[id] = { ...updated[id], tags: [...(updated[id].tags || []), tag] }
        }
      }
      return { nodes: updated }
    })
  },

  setViewMode: (mode) => set({ viewMode: mode }),

  setFocusBranch: (nodeId) => set({ focusBranchNodeId: nodeId }),
  toggleLayoutDirection: () => set((s) => ({ layoutDirection: s.layoutDirection === 'TB' ? 'LR' : 'TB' })),

  toggleSubtreeCollapse: (nodeId) => {
    set((state) => {
      const node = state.nodes[nodeId]
      if (!node) return state
      return {
        nodes: {
          ...state.nodes,
          [nodeId]: { ...node, subtree_collapsed: !node.subtree_collapsed },
        },
      }
    })
  },

  /** Collapse all branches where the max child score is below threshold */
  collapseAllBenign: (threshold = 0.2) => {
    set((state) => {
      const updated = { ...state.nodes }
      for (const node of Object.values(updated)) {
        const children = state.edges.filter(e => e.source === node.node_id).map(e => e.target)
        if (children.length === 0) continue
        const maxChildScore = Math.max(...children.map(cid => updated[cid]?.confidence ?? 0))
        if (maxChildScore <= threshold && !node.subtree_collapsed) {
          updated[node.node_id] = { ...node, subtree_collapsed: true }
        }
      }
      return { nodes: updated }
    })
  },

  /** Expand only the path with the highest cumulative score from root to leaf */
  expandHighScorePath: () => {
    set((state) => {
      const updated: Record<string, typeof state.nodes[string]> = {}
      // First collapse everything
      for (const [id, node] of Object.entries(state.nodes)) {
        const children = state.edges.filter(e => e.source === id).map(e => e.target)
        updated[id] = { ...node, subtree_collapsed: children.length > 0 }
      }
      // Then expand the highest-score path from root to leaf
      const roots = Object.values(updated).filter(n => n.parent_ids.length === 0)
      for (const root of roots) {
        let current = root.node_id
        while (current) {
          updated[current] = { ...updated[current], subtree_collapsed: false }
          const children = state.edges.filter(e => e.source === current).map(e => e.target)
          if (children.length === 0) break
          // Follow the highest-score child
          current = children.reduce((best, cid) =>
            (updated[cid]?.confidence ?? 0) > (updated[best]?.confidence ?? 0) ? cid : best
          , children[0])
        }
      }
      return { nodes: updated }
    })
  },

  markDeadEnd: (nodeId) => {
    const before = get().nodes[nodeId]?.is_dead_end ?? false
    useHistoryStore.getState().push({
      type: 'toggle_dead_end', nodeId, before, after: !before, timestamp: new Date().toISOString(),
    })
    set((state) => {
      const node = state.nodes[nodeId]
      if (!node) return state
      return {
        nodes: {
          ...state.nodes,
          [nodeId]: { ...node, is_dead_end: !node.is_dead_end },
        },
      }
    })
  },

  overrideConfidence: (nodeId, confidence) => {
    const node = get().nodes[nodeId]
    const before = node?.confidence ?? 0
    const beforeOverride = node?.confidence_override ?? false
    useHistoryStore.getState().push({
      type: 'override_confidence', nodeId, before, beforeOverride, after: confidence, timestamp: new Date().toISOString(),
    })
    set((state) => {
      const node = state.nodes[nodeId]
      if (!node) return state
      return {
        nodes: {
          ...state.nodes,
          [nodeId]: { ...node, confidence, confidence_override: true },
        },
      }
    })
    // Bug #10: Debounce propagation to avoid recursive storms on rapid overrides
    if (_propagateTimer) clearTimeout(_propagateTimer)
    _propagateTimer = setTimeout(() => {
      get().propagateConfidence(nodeId)
      _propagateTimer = null
    }, 100)
  },

  addTag: (nodeId, tag) => {
    set((state) => {
      const node = state.nodes[nodeId]
      if (!node || (node.tags || []).includes(tag)) return state
      return { nodes: { ...state.nodes, [nodeId]: { ...node, tags: [...(node.tags || []), tag] } } }
    })
  },

  removeTag: (nodeId, tag) => {
    set((state) => {
      const node = state.nodes[nodeId]
      if (!node) return state
      return { nodes: { ...state.nodes, [nodeId]: { ...node, tags: (node.tags || []).filter(t => t !== tag) } } }
    })
  },

  togglePin: (nodeId) => {
    set((state) => {
      const node = state.nodes[nodeId]
      if (!node) return state
      return { nodes: { ...state.nodes, [nodeId]: { ...node, pinned: !node.pinned } } }
    })
  },

  updateNodeStatus: (nodeId, status, durationMs) => {
    const updates: Partial<InvestigationNode> = { status }
    if (durationMs !== undefined) updates.duration_ms = durationMs
    get().updateNode(nodeId, updates)
  },

  /**
   * Threat score propagation (PRD Section 3.2):
   * "A parent threat_score is at least the average of its children scores,
   * or its own score, whichever is higher."
   */
  propagateConfidence: (nodeId) => {
    const state = get()
    const node = state.nodes[nodeId]
    if (!node) return

    for (const parentId of node.parent_ids) {
      const parent = state.nodes[parentId]
      if (!parent || parent.confidence_override) continue

      const children = state.getChildren(parentId)
      const childScores = children
        .map((cid) => state.nodes[cid]?.confidence ?? 0)

      if (childScores.length === 0) continue

      // PRD: "at least the average of children, or own score, whichever higher"
      const avg = childScores.reduce((sum, s) => sum + s, 0) / childScores.length
      const propagated = Math.max(avg, parent.confidence)

      if (Math.abs(propagated - parent.confidence) > 0.001) {
        state.updateNode(parentId, { confidence: propagated })
        state.propagateConfidence(parentId)
      }
    }
  },

  addInvestigatorNote: (nodeId, note) => {
    set((state) => {
      const node = state.nodes[nodeId]
      if (!node) return state
      const existing = node.investigator_notes
      const updated = existing ? `${existing}\n\n${note}` : note
      return {
        nodes: {
          ...state.nodes,
          [nodeId]: { ...node, investigator_notes: updated },
        },
      }
    })
  },

  /** R20: Set notes (for edit/delete) */
  setInvestigatorNotes: (nodeId: string, notes: string) => {
    set((state) => {
      const node = state.nodes[nodeId]
      if (!node) return state
      return {
        nodes: {
          ...state.nodes,
          [nodeId]: { ...node, investigator_notes: notes },
        },
      }
    })
  },

  getChildren: (nodeId) => {
    return get().edges.filter((e) => e.source === nodeId).map((e) => e.target)
  },

  getAncestors: (nodeId) => {
    const state = get()
    const node = state.nodes[nodeId]
    if (!node) return []
    const ancestors: string[] = []
    const queue = [...node.parent_ids]
    const visited = new Set<string>()
    while (queue.length > 0) {
      const id = queue.shift()!
      if (visited.has(id)) continue
      visited.add(id)
      ancestors.push(id)
      const parent = state.nodes[id]
      if (parent) queue.push(...parent.parent_ids)
    }
    return ancestors
  },

  getSubtree: (nodeId) => {
    const state = get()
    const subtree: string[] = [nodeId]
    const queue = state.getChildren(nodeId)
    const visited = new Set<string>([nodeId])
    while (queue.length > 0) {
      const id = queue.shift()!
      if (visited.has(id)) continue
      visited.add(id)
      subtree.push(id)
      queue.push(...state.getChildren(id))
    }
    return subtree
  },

  getRootNodes: () => {
    const state = get()
    return Object.values(state.nodes)
      .filter((n) => n.parent_ids.length === 0)
      .map((n) => n.node_id)
  },

  startAutoInvestigate: (nodeId) => set({ autoInvestigateNodeId: nodeId, autoInvestigateCurrentId: nodeId }),
  stopAutoInvestigate: () => set({ autoInvestigateNodeId: null, autoInvestigateCurrentId: null }),
  setAutoInvestigateCurrent: (nodeId) => set({ autoInvestigateCurrentId: nodeId }),
  setMaxConcurrentBranches: (n) => set({ maxConcurrentBranches: Math.max(1, Math.min(10, n)) }),
  setMaxAutoDepth: (n) => set({ maxAutoDepth: Math.max(1, Math.min(20, n)) }),

  loadGraph: (nodes, edges) => {
    // Normalize nodes to ensure required fields are never undefined (handles corrupt/old session files)
    const normalized: Record<string, InvestigationNode> = {}
    for (const [id, node] of Object.entries(nodes)) {
      normalized[id] = {
        ...createNode({ node_id: id }),
        ...node,
        parent_ids: node.parent_ids ?? [],
        tags: node.tags ?? [],
        parameters: node.parameters ?? {},
        result_raw: node.result_raw ?? '',
        result_summary: node.result_summary ?? '',
      }
    }
    set({ nodes: normalized, edges })
  },

  clearGraph: () => set({ nodes: {}, edges: [], selectedNodeId: null, selectedNodeIds: new Set(), autoInvestigateNodeId: null, autoInvestigateCurrentId: null, focusBranchNodeId: null }),
}))

