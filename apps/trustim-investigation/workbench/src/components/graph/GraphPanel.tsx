import { useMemo, useCallback, useEffect, useRef, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  BackgroundVariant,
  type NodeTypes,
  useReactFlow,
  ReactFlowProvider,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useGraphStore } from '../../store/graph'
import { useSessionStore } from '../../store/session'
import { InvestigationNodeComponent } from './InvestigationNode'
import { NodeContextMenu } from './NodeContextMenu'
import { BranchDiffView } from './BranchDiffView'
import { layoutGraph, setManualPosition, resetLayoutCache, setLayoutPreset, getLayoutPreset, type LayoutPreset } from '../../utils/layout'
import { GraphSearch } from './GraphSearch'
import { ReplayBar } from './ReplayBar'
import { confidenceColor } from '../../types'
import type { InvestigationNode } from '../../types'

const nodeTypes: NodeTypes = {
  investigation: InvestigationNodeComponent as unknown as NodeTypes['investigation'],
}

function GraphPanelInner() {
  const graphNodes = useGraphStore((s) => s.nodes)
  const graphEdges = useGraphStore((s) => s.edges)
  const selectNode = useGraphStore((s) => s.selectNode)
  const selectedNodeId = useGraphStore((s) => s.selectedNodeId)
  const autoInvestigateNodeId = useGraphStore((s) => s.autoInvestigateNodeId)
  const stopAutoInvestigate = useGraphStore((s) => s.stopAutoInvestigate)
  const focusBranchNodeId = useGraphStore((s) => s.focusBranchNodeId)
  const setFocusBranch = useGraphStore((s) => s.setFocusBranch)
  const layoutDirection = useGraphStore((s) => s.layoutDirection)
  const viewMode = useGraphStore((s) => s.viewMode)
  const { fitView } = useReactFlow()
  const prevNodeCount = useRef(0)
  const [contextMenu, setContextMenu] = useState<{ nodeId: string; x: number; y: number } | null>(null)
  const [diffNodes, setDiffNodes] = useState<{ a: string; b: string } | null>(null)
  const [typeFilter, setTypeFilter] = useState<string>('all')

  // Compute focus branch set (ancestors + descendants of focused node)
  const focusedNodeIds = useMemo(() => {
    if (!focusBranchNodeId) return null
    const graph = useGraphStore.getState()
    const ancestors = graph.getAncestors(focusBranchNodeId)
    const descendants = graph.getSubtree(focusBranchNodeId)
    return new Set([...ancestors, ...descendants])
  }, [focusBranchNodeId])

  // Convert our nodes/edges to React Flow format with layout
  // Use a ref to avoid creating new objects for unchanged nodes (perf optimization)
  const prevRfNodesRef = useRef<Map<string, Node>>(new Map())

  const { rfNodes, rfEdges } = useMemo(() => {
    const nodeEntries = Object.values(graphNodes)
    if (nodeEntries.length === 0) {
      prevRfNodesRef.current.clear()
      return { rfNodes: [], rfEdges: [] }
    }

    const { positions } = layoutGraph(graphNodes, graphEdges, 260, 80, layoutDirection)

    const rfNodes = nodeEntries
      .filter((n) => positions[n.node_id])
      .map((n) => ({
        id: n.node_id,
        type: 'investigation' as const,
        position: positions[n.node_id],
        data: n as unknown as Record<string, unknown>,
        selected: n.node_id === selectedNodeId,
        // Dim nodes based on focus branch or type filter
        style: {
          opacity: (focusedNodeIds && !focusedNodeIds.has(n.node_id)) ? 0.15
            : (typeFilter === 'pinned' && !n.pinned) ? 0.15
            : (typeFilter !== 'all' && typeFilter !== 'pinned' && n.action_type !== typeFilter) ? 0.2
            : 1,
          transition: 'opacity 0.3s ease',
        },
      })) satisfies Node[]

    const EDGE_LABEL_MAP: Record<string, string> = {
      led_to: '',
      branched_from: 'branch',
      supports: 'supports',
    }

    const rfEdges: Edge[] = graphEdges
      .filter((e) => positions[e.source] && positions[e.target])
      .map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        animated: graphNodes[e.source]?.status === 'running' || graphNodes[e.target]?.status === 'running',
        label: EDGE_LABEL_MAP[e.relation] || undefined,
        labelStyle: { fill: '#6b7280', fontSize: 10 },
        labelBgStyle: { fill: '#0a0a0f', fillOpacity: 0.8 },
        labelBgPadding: [4, 2] as [number, number],
        style: {
          stroke: e.relation === 'branched_from' ? '#8b5cf6'
            : e.relation === 'supports' ? '#06b6d4'
            : viewMode === 'heatmap'
              ? confidenceColor(graphNodes[e.target]?.confidence ?? 0)
              : (graphNodes[e.target]?.confidence ?? 0) > 0.6
                ? confidenceColor(graphNodes[e.target]?.confidence ?? 0) + '80'
                : '#4a4a5a',
          strokeWidth: viewMode === 'heatmap' ? 3
            : (graphNodes[e.target]?.confidence ?? 0) > 0.6 ? 3
            : 2,
          strokeDasharray: e.relation === 'supports' ? '5 3' : undefined,
          opacity: focusedNodeIds && (!focusedNodeIds.has(e.source) || !focusedNodeIds.has(e.target)) ? 0.1 : 1,
          transition: 'opacity 0.3s ease, stroke 0.3s ease',
        },
      }))

    return { rfNodes, rfEdges }
  }, [graphNodes, graphEdges, selectedNodeId, viewMode, focusedNodeIds, layoutDirection, typeFilter])

  const [nodes, setNodes, onNodesChange] = useNodesState(rfNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(rfEdges)

  // Sync when graph store changes
  useEffect(() => {
    setNodes(rfNodes)
    setEdges(rfEdges)
  }, [rfNodes, rfEdges, setNodes, setEdges])

  // Listen for compare events from BatchActionBar
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail
      if (detail?.a && detail?.b) setDiffNodes({ a: detail.a, b: detail.b })
    }
    window.addEventListener('compareNodes', handler)
    return () => window.removeEventListener('compareNodes', handler)
  }, [])

  // Cmd+0 fit-to-view handler
  useEffect(() => {
    const handler = () => fitView({ padding: 0.2, duration: 300 })
    window.addEventListener('fitGraphToView', handler)
    return () => window.removeEventListener('fitGraphToView', handler)
  }, [fitView])

  // Auto-scroll to new nodes — fit for small graphs, scroll for large
  useEffect(() => {
    const nodeCount = Object.keys(graphNodes).length
    if (nodeCount > prevNodeCount.current) {
      if (nodeCount <= 8) {
        // Small graph — fit all nodes in view
        setTimeout(() => fitView({ padding: 0.2, duration: 300 }), 100)
      } else {
        // Large graph — find the newest node and scroll to it
        const sorted = Object.values(graphNodes).sort((a, b) =>
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
        )
        const newest = sorted[0]
        if (newest) {
          // Fit to just the newest node to avoid zooming out too far
          setTimeout(() => fitView({
            padding: 0.5,
            duration: 300,
            nodes: [{ id: newest.node_id }] as { id: string }[],
          }), 100)
        }
      }
    }
    prevNodeCount.current = nodeCount
  }, [graphNodes, fitView])

  const onNodeClick = useCallback((event: React.MouseEvent, node: Node) => {
    if (event.shiftKey) {
      // Shift+click = multi-select for batch operations
      useGraphStore.getState().toggleMultiSelect(node.id)
    } else {
      selectNode(node.id)
      useGraphStore.getState().clearMultiSelect()
    }
    setContextMenu(null)
  }, [selectNode])

  // Double-click a node = immediately set chat context for branching
  const onNodeDoubleClick = useCallback((_: React.MouseEvent, node: Node) => {
    const n = graphNodes[node.id]
    if (n && n.status === 'completed') {
      const { setChatContext } = useSessionStore.getState()
      setChatContext({
        nodeId: n.node_id,
        label: n.label || n.action_type,
        query: n.query,
        result_summary: n.result_summary,
        result_raw: n.result_raw,
      })
      selectNode(null) // Close drawer to show chat
    }
  }, [graphNodes, selectNode])

  const onPaneClick = useCallback(() => {
    selectNode(null)
    setContextMenu(null)
  }, [selectNode])

  // R64: Persist manual node positions when dragged
  const onNodeDragStop = useCallback((_: React.MouseEvent, node: Node) => {
    setManualPosition(node.id, node.position.x, node.position.y)
  }, [])

  const onNodeContextMenu = useCallback((event: React.MouseEvent, node: Node) => {
    event.preventDefault()
    setContextMenu({ nodeId: node.id, x: event.clientX, y: event.clientY })
  }, [])

  const isEmpty = Object.keys(graphNodes).length === 0

  return (
    <div className="h-full w-full relative" role="tree" aria-label="Investigation decision graph">
      {isEmpty ? (
        <div className="h-full flex items-center justify-center">
          <div className="text-center max-w-[300px]">
            {/* Stylized empty tree illustration */}
            <div className="mb-6 opacity-20">
              <div className="w-12 h-12 rounded-xl border-2 border-gray-500 mx-auto mb-2 animate-pulse" />
              <div className="w-px h-6 bg-gray-500 mx-auto" />
              <div className="flex justify-center gap-8">
                <div>
                  <div className="w-px h-4 bg-gray-500 mx-auto" />
                  <div className="w-8 h-8 rounded-lg border border-gray-600 mx-auto" />
                </div>
                <div>
                  <div className="w-px h-4 bg-gray-500 mx-auto" />
                  <div className="w-8 h-8 rounded-lg border border-gray-600 mx-auto" />
                </div>
              </div>
            </div>
            <p className="text-[15px] text-gray-400 font-medium mb-1">Investigation Tree</p>
            <p className="text-[13px] text-gray-500 leading-relaxed">
              Send a message to start. Each agent action becomes a node, forming a branching investigation tree.
            </p>
          </div>
        </div>
      ) : (
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onNodeDoubleClick={onNodeDoubleClick}
          onPaneClick={onPaneClick}
          onNodeDragStop={onNodeDragStop}
          onNodeContextMenu={onNodeContextMenu}
          nodeTypes={nodeTypes}
          fitView
          minZoom={0.1}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} color="#1a1a25" gap={20} />
          <Controls />
          <MiniMap
            nodeColor={(node) => {
              const data = node.data as unknown as InvestigationNode | undefined
              if (!data) return '#6b7280'
              // During active investigation, show status colors for better orientation
              if (data.status === 'running') return '#3b82f6' // blue
              if (data.status === 'failed') return '#ef4444' // red
              if (data.is_dead_end) return '#374151' // dim gray
              // Completed nodes use confidence color
              return confidenceColor(data.confidence)
            }}
            maskColor="rgba(10, 10, 15, 0.8)"
            pannable
            zoomable
          />
        </ReactFlow>
      )}

      {/* Confidence heat strip */}
      {!isEmpty && Object.keys(graphNodes).length > 2 && (
        <div className="absolute top-0 left-0 right-0 h-1 z-10 flex" title="Confidence distribution across nodes">
          {Object.values(graphNodes)
            .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
            .map(n => (
              <div
                key={n.node_id}
                className="flex-1 cursor-pointer hover:h-2 transition-all"
                style={{ backgroundColor: confidenceColor(n.confidence) }}
                onClick={() => selectNode(n.node_id)}
                title={`${n.label}: ${(n.confidence * 100).toFixed(0)}%`}
              />
            ))}
        </div>
      )}

      {/* Graph summary card for large investigations */}
      {Object.keys(graphNodes).length >= 8 && !autoInvestigateNodeId && (
        <GraphSummaryCard nodes={graphNodes} />
      )}

      {/* Graph legend */}
      {!isEmpty && <GraphLegend />}

      {/* Node search for large graphs */}
      {!isEmpty && <GraphSearch />}

      {/* Auto-investigate progress indicator */}
      {autoInvestigateNodeId && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 bg-accent-cyan/20 border border-accent-cyan/30 rounded-xl px-4 py-2.5 backdrop-blur-sm min-w-[320px]">
          <div className="flex items-center gap-3 mb-1.5">
            <div className="w-2 h-2 bg-accent-cyan rounded-full animate-pulse" />
            <span className="text-xs text-accent-cyan font-medium">Auto-investigating</span>
            <span className="text-[10px] text-gray-400 tabular-nums ml-auto">{Object.keys(graphNodes).length} nodes</span>
            <button
              onClick={stopAutoInvestigate}
              className="text-[10px] bg-accent-cyan/20 hover:bg-accent-cyan/30 text-accent-cyan px-2 py-0.5 rounded transition-colors"
            >
              Stop
          </button>
          </div>
          {/* Checklist progress — shows which dimensions are covered */}
          {(() => {
            const texts = Object.values(graphNodes).map(n => [n.label, n.query, ...(n.tags || [])].join(' ').toLowerCase())
            const dims = [
              { key: ['email','split_part'], label: 'Email' },
              { key: ['ip','requestheader'], label: 'IP' },
              { key: ['canvashash','webgl'], label: 'Device' },
              { key: ['challenge','securitychallenge'], label: 'Challenge' },
              { key: ['restriction','dim_member'], label: 'Restrict' },
              { key: ['wow','t7d'], label: 'WoW' },
              { key: ['dihe','fact_experience'], label: 'DIHE' },
              { key: ['sev','sev-'], label: 'SEV' },
            ]
            return (
              <div className="flex items-center gap-1 mt-0.5">
                {dims.map(d => {
                  const covered = texts.some(t => d.key.some(k => t.includes(k)))
                  return (
                    <span key={d.label} className={`text-[9px] px-1.5 py-0.5 rounded ${covered ? 'bg-accent-cyan/30 text-accent-cyan' : 'bg-surface-4/50 text-gray-600'}`}>
                      {d.label}
                    </span>
                  )
                })}
              </div>
            )
          })()}
        </div>
      )}

      {/* Batch action bar — when multiple nodes are shift-selected */}
      <BatchActionBar />

      {/* Investigation progress bar */}
      {/* Graph toolbar — always visible when graph has nodes */}
      {!isEmpty && (
        <div className="absolute bottom-3 left-3 z-[50] bg-surface-1/95 border border-surface-3 rounded-lg px-3 py-1.5 flex items-center gap-2 text-[11px] text-gray-400 group/toolbar shadow-lg">
          {/* Essential status — always visible */}
          <span className="tabular-nums">{Object.keys(graphNodes).length} nodes</span>
          {(() => {
            const nodeList = Object.values(graphNodes)
            const running = nodeList.filter(n => n.status === 'running').length
            const completed = nodeList.filter(n => n.status === 'completed').length
            const total = nodeList.length
            return (
              <>
                {running > 0 && (
                  <span className="text-accent-blue flex items-center gap-1">
                    <span className="w-1.5 h-1.5 bg-accent-blue rounded-full animate-pulse" />
                    {running}
                  </span>
                )}
                {total > 0 && completed < total && completed > 0 && (
                  <span className="tabular-nums text-accent-blue">{Math.round(completed / total * 100)}%</span>
                )}
              </>
            )
          })()}
          <TokenCounter />
          {/* Coverage dots — only when investigation has substance */}
          {Object.keys(graphNodes).length >= 3 && (() => {
            const texts = Object.values(graphNodes).map(n => [n.label, n.query, ...(n.tags || [])].join(' ').toLowerCase())
            const dims = [['email','split_part'],['ip','requestheader'],['canvashash','webgl'],['challenge','securitychallenge'],['restriction','dim_member'],['wow','t7d'],['dihe','fact_experience'],['sev','sev-']]
            const covered = dims.filter(kws => texts.some(t => kws.some(k => t.includes(k)))).length
            if (covered === 0) return null
            return (
              <div className="flex items-center gap-0.5" title={`${covered}/8 investigation dimensions covered`}>
                {dims.map((_, i) => (
                  <div key={i} className={`w-1.5 h-1.5 rounded-full ${i < covered ? 'bg-accent-blue' : 'bg-surface-4'}`} />
                ))}
              </div>
            )
          })()}

          {/* Context actions — visible on node select */}
          {selectedNodeId && (
            <>
              <span className="text-gray-600">|</span>
              <button
                onClick={() => setFocusBranch(focusBranchNodeId === selectedNodeId ? null : selectedNodeId)}
                className={`transition-colors ${focusBranchNodeId ? 'text-accent-purple font-medium' : 'text-gray-500 hover:text-gray-300'}`}
              >
                {focusBranchNodeId ? 'Unfocus' : 'Focus'}
              </button>
            </>
          )}

          {/* Advanced tools — revealed on hover for clean default */}
          {/* Graph actions — always visible when graph has nodes */}
          {Object.keys(graphNodes).length >= 1 && (
            <>
              <span className="text-gray-600">|</span>
              <button
                onClick={() => {
                  // Expand all collapsed subtrees
                  const graph = useGraphStore.getState()
                  for (const node of Object.values(graph.nodes)) {
                    if (node.subtree_collapsed) graph.toggleSubtreeCollapse(node.node_id)
                  }
                }}
                className="text-gray-500 hover:text-gray-300 transition-colors"
                title="Expand all nodes"
              >
                Expand
              </button>
              <button
                onClick={() => useGraphStore.getState().collapseAllBenign(0.3)}
                className="text-gray-500 hover:text-gray-300 transition-colors"
                title="Collapse low-score branches"
              >
                Collapse
              </button>
              <button
                onClick={() => {
                  resetLayoutCache()
                  const graph = useGraphStore.getState()
                  // Always reset to top-to-bottom
                  if (graph.layoutDirection !== 'TB') {
                    graph.toggleLayoutDirection()
                  }
                  // Force re-layout by toggling twice (clears manual positions, stays TB)
                  graph.toggleLayoutDirection()
                  setTimeout(() => {
                    graph.toggleLayoutDirection()
                    setTimeout(() => fitView({ padding: 0.2, duration: 300 }), 50)
                  }, 50)
                }}
                className="text-gray-500 hover:text-gray-300 transition-colors"
                title="Auto-sort graph (top to bottom)"
              >
                Sort
              </button>
              <button onClick={() => fitView({ padding: 0.2, duration: 300 })} className="text-gray-500 hover:text-gray-300 transition-colors" title="Fit graph to view (Cmd+0)">Fit</button>
              <button onClick={() => { resetLayoutCache(); useGraphStore.getState().toggleLayoutDirection() }} className="text-gray-500 hover:text-gray-300 transition-colors" title="Toggle direction">{layoutDirection === 'TB' ? '\u2195' : '\u2194'}</button>
            </>
          )}

          {/* Advanced tools — revealed on hover */}
          <div className="hidden group-hover/toolbar:flex items-center gap-2">
            <span className="text-gray-600">|</span>
            <FilterDropdown nodes={graphNodes} value={typeFilter} onChange={setTypeFilter} />
            {Object.keys(graphNodes).length > 3 && !selectedNodeId && (
              <>
                <button onClick={() => useGraphStore.getState().expandHighScorePath()} className="text-gray-500 hover:text-gray-300 transition-colors" title="Show highest-score path">Hot path</button>
                <button
                  onClick={() => { const presets: LayoutPreset[] = ['default','compact','expanded']; const next = presets[(presets.indexOf(getLayoutPreset()) + 1) % presets.length]; setLayoutPreset(next) }}
                  className="text-gray-500 hover:text-gray-300 transition-colors"
                  title={`Layout: ${getLayoutPreset()}`}
                >{getLayoutPreset() === 'compact' ? '\u25A0' : getLayoutPreset() === 'expanded' ? '\u25A1' : '\u25A3'}</button>
              </>
            )}
            <ReplayBar />
            <button onClick={() => { import('../../utils/export').then(({ exportGraphTree }) => { import('../../store/session').then(({ useSessionStore: ss }) => { const d = ss.getState().getSessionData(); if (d) { navigator.clipboard.writeText(exportGraphTree(d)); import('../../store/toast').then(({ useToastStore }) => useToastStore.getState().addToast('Graph tree copied', 'success', 2000)) } }) }) }} className="text-gray-500 hover:text-gray-300 transition-colors" title="Copy investigation tree">Tree</button>
            <button onClick={() => { const q = Object.values(useGraphStore.getState().nodes).filter(n => n.query && n.status === 'completed').sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()).map(n => `-- ${n.label}\n${n.query}`).join('\n\n'); if (q) { navigator.clipboard.writeText(q); import('../../store/toast').then(({ useToastStore }) => useToastStore.getState().addToast('All queries copied', 'success', 2000)) } }} className="text-gray-500 hover:text-gray-300 transition-colors" title="Copy all SQL queries">SQL</button>
          </div>

          {/* Help shortcut — always visible */}
          <span className="text-gray-600">|</span>
          <button onClick={() => window.dispatchEvent(new Event('showKeyboardHelp'))} className="text-gray-500 hover:text-gray-300 transition-colors font-mono" title="Keyboard shortcuts">?</button>
        </div>
      )}

      {/* Selected node quick-actions */}
      {selectedNodeId && graphNodes[selectedNodeId]?.status === 'completed' && !contextMenu && (
        <NodeQuickActions
          nodeId={selectedNodeId}
          node={graphNodes[selectedNodeId]}
          onSelectNode={selectNode}
        />
      )}

      {/* Context menu overlay */}
      {contextMenu && (
        <NodeContextMenu
          nodeId={contextMenu.nodeId}
          x={contextMenu.x}
          y={contextMenu.y}
          onClose={() => setContextMenu(null)}
          onCompare={selectedNodeId && selectedNodeId !== contextMenu.nodeId
            ? () => {
                setDiffNodes({ a: selectedNodeId!, b: contextMenu.nodeId })
                setContextMenu(null)
              }
            : undefined
          }
        />
      )}

      {/* Branch diff view */}
      {diffNodes && (
        <BranchDiffView
          nodeIdA={diffNodes.a}
          nodeIdB={diffNodes.b}
          onClose={() => setDiffNodes(null)}
        />
      )}
    </div>
  )
}

export function GraphPanel() {
  return (
    <ReactFlowProvider>
      <GraphPanelInner />
    </ReactFlowProvider>
  )
}

/** Batch action bar for multi-selected nodes */
function BatchActionBar() {
  const selectedIds = useGraphStore((s) => s.selectedNodeIds)
  const count = selectedIds.size
  if (count < 2) return null

  return (
    <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 glass-panel rounded-xl px-4 py-2 flex items-center gap-3 shadow-2xl animate-[fadeIn_0.2s_ease-out]">
      <span className="text-[12px] text-gray-300 font-medium">{count} nodes selected</span>
      <div className="flex gap-1.5">
        <button
          onClick={() => useGraphStore.getState().batchMarkDeadEnd()}
          className="text-[11px] bg-red-900/20 hover:bg-red-900/30 text-red-300 px-2 py-1 rounded-md transition-colors"
        >
          Dead end all
        </button>
        <button
          onClick={() => useGraphStore.getState().batchAddTag('IOC')}
          className="text-[11px] bg-accent-purple/20 hover:bg-accent-purple/30 text-accent-purple px-2 py-1 rounded-md transition-colors"
        >
          Tag: IOC
        </button>
        <button
          onClick={() => {
            const graph = useGraphStore.getState()
            const selected = [...graph.selectedNodeIds]
            const nodes = selected.map(id => graph.nodes[id]).filter(Boolean)
            const text = nodes.map(n => {
              const score = (n.confidence * 100).toFixed(0)
              return `${n.label} (${score}%)${n.result_summary ? ': ' + n.result_summary.slice(0, 80) : ''}`
            }).join('\n')
            navigator.clipboard.writeText(text)
            import('../../store/toast').then(({ useToastStore }) =>
              useToastStore.getState().addToast(`${nodes.length} findings copied`, 'success', 2000)
            )
          }}
          className="text-[11px] bg-surface-3 hover:bg-surface-4 text-gray-300 px-2 py-1 rounded-md transition-colors"
        >
          Copy findings
        </button>
        <button
          onClick={() => useGraphStore.getState().batchAddTag('escalate')}
          className="text-[11px] bg-accent-cyan/20 hover:bg-accent-cyan/30 text-accent-cyan px-2 py-1 rounded-md transition-colors"
        >
          Tag: escalate
        </button>
        {/* Batch confidence override */}
        <div className="flex items-center gap-0.5 border-l border-white/[0.06] pl-1.5 ml-0.5">
          {[0, 0.2, 0.5, 0.8, 1.0].map((c) => (
            <button
              key={c}
              onClick={() => {
                const graph = useGraphStore.getState()
                for (const id of selectedIds) {
                  graph.overrideConfidence(id, c)
                }
              }}
              className="px-1 py-0.5 text-[9px] rounded transition-opacity hover:opacity-80"
              style={{ backgroundColor: confidenceColor(c) + '30', color: confidenceColor(c) }}
              title={`Set all to ${(c * 100).toFixed(0)}%`}
            >
              {(c * 100).toFixed(0)}%
            </button>
          ))}
        </div>
        {/* Compare when exactly 2 selected */}
        {count === 2 && (
          <button
            onClick={() => {
              const ids = [...selectedIds]
              // Dispatch compare event — GraphPanelInner listens
              window.dispatchEvent(new CustomEvent('compareNodes', { detail: { a: ids[0], b: ids[1] } }))
            }}
            className="text-[11px] bg-accent-blue/20 hover:bg-accent-blue/30 text-accent-blue px-2 py-1 rounded-md transition-colors font-medium"
          >
            Compare
          </button>
        )}
        <button
          onClick={() => useGraphStore.getState().clearMultiSelect()}
          className="text-[11px] text-gray-400 hover:text-gray-200 px-2 py-1 rounded-md transition-colors"
        >
          Clear
        </button>
      </div>
    </div>
  )
}

/** Action type filter dropdown with per-type counts */
function FilterDropdown({ nodes, value, onChange }: { nodes: Record<string, InvestigationNode>; value: string; onChange: (v: string) => void }) {
  const counts = useMemo(() => {
    const c: Record<string, number> = { pinned: 0 }
    for (const n of Object.values(nodes)) {
      c[n.action_type] = (c[n.action_type] || 0) + 1
      if (n.pinned) c.pinned++
    }
    return c
  }, [nodes])

  const options: [string, string][] = [
    ['all', 'All types'],
    ['pinned', `Pinned (${counts.pinned || 0})`],
    ['query_execution', `Queries (${counts.query_execution || 0})`],
    ['mcp_tool_call', `Tool calls (${counts.mcp_tool_call || 0})`],
    ['skill_invocation', `Skills (${counts.skill_invocation || 0})`],
    ['enrichment', `Enrichment (${counts.enrichment || 0})`],
    ['annotation', `Annotations (${counts.annotation || 0})`],
    ['recommendation', `Recommendations (${counts.recommendation || 0})`],
  ]

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-transparent text-[11px] text-gray-400 focus:outline-none cursor-pointer"
    >
      {options.map(([val, label]) => (
        <option key={val} value={val}>{label}</option>
      ))}
    </select>
  )
}

/** Graph legend explaining visual language */
function GraphLegend() {
  const [show, setShow] = useState(false)
  if (!show) {
    return (
      <button
        onClick={() => setShow(true)}
        className="absolute bottom-3 right-3 z-10 glass-panel rounded-lg px-2 py-1 text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
      >
        Legend
      </button>
    )
  }
  return (
    <div className="absolute bottom-3 right-3 z-10 glass-panel rounded-xl px-3 py-2.5 w-[180px] text-[10px] animate-[fadeIn_0.15s_ease-out]">
      <div className="flex justify-between items-center mb-1.5">
        <span className="text-gray-400 uppercase font-medium">Legend</span>
        <button onClick={() => setShow(false)} className="text-gray-500 hover:text-gray-300">{'\u2715'}</button>
      </div>
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <div className="w-3 h-1 rounded" style={{ backgroundColor: confidenceColor(0.1) }} />
          <span className="text-gray-500">Low confidence (green)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-1 rounded" style={{ backgroundColor: confidenceColor(0.5) }} />
          <span className="text-gray-500">Medium (yellow)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-1 rounded" style={{ backgroundColor: confidenceColor(0.9) }} />
          <span className="text-gray-500">High confidence (red)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-accent-blue rounded-full animate-pulse" />
          <span className="text-gray-500">Running</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-red-400 text-[8px] font-bold bg-red-900/30 px-1 rounded">SEV-1</span>
          <span className="text-gray-500">Severity badge</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-0.5 bg-purple-500" />
          <span className="text-gray-500">Branch edge</span>
        </div>
      </div>
    </div>
  )
}

/** Graph summary card for large investigations */
function GraphSummaryCard({ nodes }: { nodes: Record<string, InvestigationNode> }) {
  const [collapsed, setCollapsed] = useState(true)
  const nodeList = Object.values(nodes)
  const completed = nodeList.filter(n => n.status === 'completed').length
  const maxConf = Math.max(0, ...nodeList.map(n => n.confidence))
  const highCount = nodeList.filter(n => n.confidence > 0.5).length
  const sevNode = nodeList.find(n => (n.tags || []).some(t => t.startsWith('SEV-')))
  const sevTag = (sevNode?.tags || []).find(t => t.startsWith('SEV-'))

  if (collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        className="absolute top-12 right-3 z-10 glass-panel rounded-lg px-3 py-1.5 text-[11px] text-gray-400 hover:text-gray-200 flex items-center gap-2 transition-colors"
      >
        <span className="tabular-nums font-medium" style={{ color: confidenceColor(maxConf) }}>{(maxConf * 100).toFixed(0)}%</span>
        {sevTag && <span className="text-red-400 font-bold">{sevTag}</span>}
        <span>{completed}/{nodeList.length}</span>
      </button>
    )
  }

  return (
    <div className="absolute top-12 right-3 z-10 glass-panel rounded-xl px-4 py-3 w-[200px] text-[11px] animate-[fadeIn_0.15s_ease-out]">
      <div className="flex items-center justify-between mb-2">
        <span className="text-gray-400 font-medium uppercase text-[10px]">Summary</span>
        <button onClick={() => setCollapsed(true)} className="text-gray-500 hover:text-gray-300">{'\u25B2'}</button>
      </div>
      <div className="space-y-1.5">
        <div className="flex justify-between">
          <span className="text-gray-500">Nodes</span>
          <span className="text-gray-300 tabular-nums">{completed}/{nodeList.length}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Max score</span>
          <span className="font-bold tabular-nums" style={{ color: confidenceColor(maxConf) }}>{(maxConf * 100).toFixed(0)}%</span>
        </div>
        {highCount > 0 && (
          <div className="flex justify-between">
            <span className="text-gray-500">High findings</span>
            <span className="text-orange-400 tabular-nums">{highCount}</span>
          </div>
        )}
        {sevTag && (
          <div className="flex justify-between">
            <span className="text-gray-500">Severity</span>
            <span className="text-red-400 font-bold">{sevTag}</span>
          </div>
        )}
      </div>
    </div>
  )
}

/** Displays token consumption from the session store */
function TokenCounter() {
  const tokenUsage = useSessionStore((s) => s.tokenUsage)
  if (tokenUsage.total === 0) return null
  const fmt = (n: number) => n > 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
  return (
    <>
      <span className="text-gray-600">|</span>
      <span className="tabular-nums text-gray-500" title={`Input: ${tokenUsage.input} | Output: ${tokenUsage.output}`}>
        {fmt(tokenUsage.total)} tokens
      </span>
    </>
  )
}

/** Quick-action bar for selected completed nodes — Branch, Expand (with skill picker), Fan out, Dead end */
function NodeQuickActions({ nodeId, node, onSelectNode }: { nodeId: string; node: InvestigationNode; onSelectNode: (id: string | null) => void }) {
  const [showSkills, setShowSkills] = useState(false)

  // Investigation angles the user can expand into
  const EXPAND_ANGLES = [
    { label: 'Dig deeper', prompt: `Continue investigating from "${node.label}". Run follow-up queries to dig deeper into these findings.` },
    { label: 'Email domains', prompt: `From "${node.label}", analyze email domain distribution. Check for disposable TLDs (.xyz, .icu, .top). Use split_part(email, '@', 2) on tracking.registrationevent.`, skill: 'suspicious-registrations' },
    { label: 'IP analysis', prompt: `From "${node.label}", analyze IP clustering. Check for datacenter IPs, hosting providers, IP reuse patterns.`, skill: 'suspicious-registrations' },
    { label: 'Device fingerprints', prompt: `From "${node.label}", check device fingerprints. Query TRACKING.AntiAbuseJavaScriptDeviceFeaturesEvent for SwiftShader, canvas hash clustering.`, skill: 'suspicious-registrations' },
    { label: 'Challenge rates', prompt: `From "${node.label}", check challenge solve rates from securitychallengeevent. Look for captcha bypass patterns.`, skill: 'challenge-research' },
    { label: 'Restrictions', prompt: `From "${node.label}", check restriction status. Query dim_member_trust_restrictions for the identified cohort.` },
    { label: 'WoW / SEV', prompt: `From "${node.label}", compute T7D WoW for relevant metrics and check against SEV thresholds.`, skill: 'sev-assessment' },
    { label: 'Impact (DIHE)', prompt: `From "${node.label}", assess downstream harmful impact. Check u_tds.fact_experience_base for harmful experiences.` },
  ]

  return (
    <div className="absolute bottom-3 right-3 z-10 animate-[fadeIn_0.15s_ease-out]">
      {/* Skill picker dropdown */}
      {showSkills && (
        <div className="glass-panel rounded-lg mb-1.5 py-1 w-[200px] max-h-[240px] overflow-y-auto">
          {EXPAND_ANGLES.map(angle => (
            <button
              key={angle.label}
              onClick={() => {
                window.dispatchEvent(new CustomEvent('executeFromNode', {
                  detail: { query: angle.prompt, parentNodeId: nodeId, label: `${angle.label}: ${node.label.slice(0, 30)}` }
                }))
                setShowSkills(false)
                onSelectNode(null)
              }}
              className="w-full text-left px-3 py-1.5 text-[11px] text-gray-300 hover:bg-accent-cyan/10 hover:text-accent-cyan transition-colors"
            >
              {angle.label}
              {angle.skill && <span className="text-[9px] text-gray-600 ml-1">({angle.skill})</span>}
            </button>
          ))}
        </div>
      )}
      {/* Action buttons */}
      <div className="glass-panel rounded-lg px-2 py-1.5 flex items-center gap-1.5">
        {/* Re-run: execute the same query as a new child (ipynb auto-execute) */}
        {node.query && node.tool_name && (
          <button
            onClick={() => {
              const isSQL = node.tool_name === 'execute_trino_query' || node.query.toLowerCase().includes('select')
              const queryText = isSQL
                ? `Run this SQL query using execute_trino_query:\n\`\`\`sql\n${node.query}\n\`\`\``
                : node.query
              window.dispatchEvent(new CustomEvent('executeFromNode', {
                detail: { query: queryText, parentNodeId: nodeId, label: `Re-run: ${node.label.slice(0, 30)}` }
              }))
              onSelectNode(null)
            }}
            className="text-[10px] bg-green-900/20 text-green-400 hover:bg-green-900/30 px-2 py-1 rounded transition-colors"
            title="Re-run this query (creates new child node)"
          >
            Re-run
          </button>
        )}
        <button
          onClick={() => {
            useSessionStore.getState().setChatContext({
              nodeId, label: node.label || '', query: node.query,
              result_summary: node.result_summary, result_raw: node.result_raw,
            })
          }}
          className="text-[10px] bg-accent-blue/20 text-accent-blue hover:bg-accent-blue/30 px-2 py-1 rounded transition-colors"
          title="Type a follow-up prompt"
        >
          Branch
        </button>
        <button
          onClick={() => setShowSkills(!showSkills)}
          className={`text-[10px] px-2 py-1 rounded transition-colors ${showSkills ? 'bg-accent-cyan/30 text-accent-cyan' : 'bg-accent-cyan/20 text-accent-cyan hover:bg-accent-cyan/30'}`}
          title="Expand with a specific investigation angle"
        >
          Expand {showSkills ? '\u25B2' : '\u25BC'}
        </button>
        <button
          onClick={() => { useGraphStore.getState().startAutoInvestigate(nodeId); onSelectNode(null) }}
          className="text-[10px] bg-accent-purple/20 text-accent-purple hover:bg-accent-purple/30 px-2 py-1 rounded transition-colors"
          title="Auto-investigate: fan out through all unchecked dimensions"
        >
          Fan out
        </button>
        <button
          onClick={() => useGraphStore.getState().markDeadEnd(nodeId)}
          className="text-[10px] bg-surface-3 text-gray-400 hover:text-gray-200 px-2 py-1 rounded transition-colors"
          title="Mark as dead end"
        >
          Dead end
        </button>
      </div>
    </div>
  )
}
