import dagre from 'dagre'
import type { InvestigationNode, InvestigationEdge } from '../types'

interface LayoutResult {
  positions: Record<string, { x: number; y: number }>
}

/**
 * Stable auto-layout for the investigation DAG (R61-R64).
 *
 * R62: Existing nodes must not reposition when new nodes are added.
 * This is achieved by caching positions and only computing layout for
 * nodes that don't have a cached or manual position.
 *
 * R64: Manual positions override auto-layout and are preserved.
 */

// Cache of auto-layout positions to stabilize the graph
const positionCache: Record<string, { x: number; y: number }> = {}
// Manual position overrides set by the user dragging nodes
const manualPositions: Record<string, { x: number; y: number }> = {}

export type LayoutPreset = 'default' | 'compact' | 'expanded'

const PRESET_CONFIG: Record<LayoutPreset, { nodesep: number; ranksep: number; nodeWidth: number; nodeHeight: number }> = {
  default: { nodesep: 60, ranksep: 100, nodeWidth: 260, nodeHeight: 80 },
  compact: { nodesep: 30, ranksep: 60, nodeWidth: 220, nodeHeight: 60 },
  expanded: { nodesep: 100, ranksep: 160, nodeWidth: 280, nodeHeight: 90 },
}

let currentPreset: LayoutPreset = 'default'
export function setLayoutPreset(preset: LayoutPreset) { currentPreset = preset; resetLayoutCache() }
export function getLayoutPreset(): LayoutPreset { return currentPreset }

export function layoutGraph(
  nodes: Record<string, InvestigationNode>,
  edges: InvestigationEdge[],
  nodeWidth?: number,
  nodeHeight?: number,
  rankdir: 'TB' | 'LR' = 'TB',
): LayoutResult {
  const preset = PRESET_CONFIG[currentPreset]
  if (!nodeWidth) nodeWidth = preset.nodeWidth
  if (!nodeHeight) nodeHeight = preset.nodeHeight
  // Get visible nodes (skip children of collapsed subtrees)
  const collapsedParents = new Set<string>()
  for (const node of Object.values(nodes)) {
    if (node.subtree_collapsed) {
      collapsedParents.add(node.node_id)
    }
  }
  const visibleNodes = getVisibleNodes(nodes, edges, collapsedParents)

  // Check if we need a full re-layout or just incremental
  const newNodes = [...visibleNodes].filter(
    (id) => !positionCache[id] && !manualPositions[id]
  )

  // If no new nodes, return cached + manual positions
  if (newNodes.length === 0) {
    const positions: Record<string, { x: number; y: number }> = {}
    for (const nodeId of visibleNodes) {
      positions[nodeId] = manualPositions[nodeId] || positionCache[nodeId]
    }
    return { positions }
  }

  // Run dagre layout — increase spacing for parallel branches
  const hasParallelBranches = edges.some(e1 =>
    edges.some(e2 => e1.source === e2.source && e1.target !== e2.target && visibleNodes.has(e1.target) && visibleNodes.has(e2.target))
  )
  const g = new dagre.graphlib.Graph()
  g.setGraph({
    rankdir,
    nodesep: hasParallelBranches ? preset.nodesep + 20 : preset.nodesep,
    ranksep: hasParallelBranches ? preset.ranksep + 20 : preset.ranksep,
    marginx: 40,
    marginy: 40,
  })
  g.setDefaultEdgeLabel(() => ({}))

  for (const nodeId of visibleNodes) {
    g.setNode(nodeId, { width: nodeWidth, height: nodeHeight })
  }

  for (const edge of edges) {
    if (visibleNodes.has(edge.source) && visibleNodes.has(edge.target)) {
      g.setEdge(edge.source, edge.target)
    }
  }

  dagre.layout(g)

  // Build result: manual positions take priority, then cache, then new dagre positions
  const positions: Record<string, { x: number; y: number }> = {}
  for (const nodeId of visibleNodes) {
    if (manualPositions[nodeId]) {
      // R64: Manual positions always preserved
      positions[nodeId] = manualPositions[nodeId]
    } else if (positionCache[nodeId]) {
      // R62: Existing nodes keep their position
      positions[nodeId] = positionCache[nodeId]
    } else {
      // New node — use dagre position
      const pos = g.node(nodeId)
      if (pos) {
        const computed = { x: pos.x - nodeWidth / 2, y: pos.y - nodeHeight / 2 }
        positions[nodeId] = computed
        positionCache[nodeId] = computed
      }
    }
  }

  return { positions }
}

/** Record a manual position override from user dragging (R64) */
export function setManualPosition(nodeId: string, x: number, y: number) {
  manualPositions[nodeId] = { x, y }
}

/** Clear manual position (revert to auto-layout) */
export function clearManualPosition(nodeId: string) {
  delete manualPositions[nodeId]
}

/** Clear all cached positions (for full re-layout after import) */
export function resetLayoutCache() {
  for (const key of Object.keys(positionCache)) delete positionCache[key]
  for (const key of Object.keys(manualPositions)) delete manualPositions[key]
}

/** Get visible nodes, excluding children of collapsed subtrees */
function getVisibleNodes(
  nodes: Record<string, InvestigationNode>,
  edges: InvestigationEdge[],
  collapsedParents: Set<string>,
): Set<string> {
  const hidden = new Set<string>()

  // BFS from collapsed parents to hide their descendants (unless pinned)
  for (const parentId of collapsedParents) {
    const queue = edges.filter((e) => e.source === parentId).map((e) => e.target)
    while (queue.length > 0) {
      const id = queue.shift()!
      if (hidden.has(id)) continue
      // Pinned nodes stay visible even when parent is collapsed
      if (nodes[id]?.pinned) continue
      hidden.add(id)
      queue.push(...edges.filter((e) => e.source === id).map((e) => e.target))
    }
  }

  const visible = new Set<string>()
  for (const nodeId of Object.keys(nodes)) {
    if (!hidden.has(nodeId)) {
      visible.add(nodeId)
    }
  }
  return visible
}
