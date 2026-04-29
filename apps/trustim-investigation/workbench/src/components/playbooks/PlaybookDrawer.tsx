/**
 * Resizable playbook DAG drawer — shows the full playbook graph with live execution status.
 * Opens from the bottom of the investigation view. Each node is clickable to jump to
 * the corresponding investigation node in the main graph.
 */
import { useState, useEffect, useRef, useCallback, memo } from 'react'
import {
  ReactFlow, ReactFlowProvider, Background, Controls, BackgroundVariant,
  Handle, Position, type Node, type Edge, type NodeTypes, type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { playbooksApi } from '../../api'
import { useGraphStore } from '../../store/graph'
import type { PlaybookExecution, Playbook } from '../../types/playbook'

interface Props {
  sessionId: string
}

const STATUS_STYLES: Record<string, { bg: string; border: string; text: string; dot: string }> = {
  completed: { bg: 'bg-green-900/20', border: '#22c55e', text: 'text-green-400', dot: 'bg-green-400' },
  running:   { bg: 'bg-yellow-900/20', border: '#eab308', text: 'text-yellow-400', dot: 'bg-yellow-400 animate-pulse' },
  failed:    { bg: 'bg-red-900/20', border: '#ef4444', text: 'text-red-400', dot: 'bg-red-400' },
  skipped:   { bg: 'bg-gray-900/20', border: '#6b7280', text: 'text-gray-500', dot: 'bg-gray-500' },
  pending:   { bg: 'bg-surface-2', border: '#2a2a3a', text: 'text-gray-500', dot: 'bg-gray-700' },
}

// Custom node — clickable to navigate to investigation node
const PlaybookDAGNode = memo(({ data }: NodeProps) => {
  const d = data as { label: string; status: string; refType: string; body?: string; invNodeId?: string; onNavigate?: (id: string) => void }
  const style = STATUS_STYLES[d.status] || STATUS_STYLES.pending
  return (
    <div
      className={`px-3 py-2.5 rounded-lg min-w-[180px] max-w-[250px] cursor-pointer transition-all hover:brightness-125 ${style.bg}`}
      style={{ border: `2px solid ${style.border}` }}
      onClick={() => { if (d.invNodeId && d.onNavigate) d.onNavigate(d.invNodeId) }}
    >
      <Handle type="target" position={Position.Top} className="!w-3 !h-3 !bg-green-500 !border-2 !border-surface-1" />
      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${style.dot}`} />
        <span className={`text-[12px] font-medium truncate ${style.text}`}>{d.label}</span>
      </div>
      <div className="flex items-center gap-2 mt-1">
        <span className={`text-[9px] px-1.5 py-0.5 rounded ${
          d.refType === 'automation' ? 'bg-blue-900/30 text-blue-400'
          : d.refType === 'condition' ? 'bg-yellow-900/30 text-yellow-400'
          : d.refType === 'prompt' ? 'bg-cyan-900/30 text-cyan-400'
          : 'bg-green-900/30 text-green-400'
        }`}>{d.refType}</span>
        <span className="text-[9px] text-gray-600">{d.status}</span>
        {d.invNodeId && <span className="text-[8px] text-accent-blue ml-auto">click to view</span>}
      </div>
      {d.body && <div className="text-[9px] text-gray-500 mt-1 line-clamp-2 italic">{d.body}</div>}
      <Handle type="source" position={Position.Bottom} className="!w-3 !h-3 !bg-green-500 !border-2 !border-surface-1" />
    </div>
  )
})
PlaybookDAGNode.displayName = 'PlaybookDAGNode'

const nodeTypes: NodeTypes = { pb_node: PlaybookDAGNode as any }

export function PlaybookDrawer({ sessionId }: Props) {
  const [executions, setExecutions] = useState<PlaybookExecution[]>([])
  const [playbooks, setPlaybooks] = useState<Record<string, Playbook>>({})
  const [open, setOpen] = useState(false)
  const [height, setHeight] = useState(320)
  const [selectedExecIdx, setSelectedExecIdx] = useState(0)
  const resizing = useRef(false)

  // Poll executions
  useEffect(() => {
    const poll = () => {
      playbooksApi.listExecutions()
        .then((execs: PlaybookExecution[]) => {
          const matching = execs.filter(e => e.session_id === sessionId)
          setExecutions(matching)
          // Auto-open when a playbook starts
          if (matching.some(e => e.status === 'running') && !open) setOpen(true)
          // Fetch playbook definitions
          for (const exec of matching) {
            if (!playbooks[exec.playbook_id]) {
              playbooksApi.get(exec.playbook_id)
                .then(pb => { if (pb?.nodes) setPlaybooks(prev => ({ ...prev, [pb.id]: pb })) })
                .catch(() => {})
            }
          }
        })
        .catch(() => {})
    }
    poll()
    const timer = setInterval(poll, 2000)
    return () => clearInterval(timer)
  }, [sessionId, open, playbooks])

  // Resize drag
  const onResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    resizing.current = true
    const startY = e.clientY
    const startH = height
    const onMove = (ev: MouseEvent) => {
      if (!resizing.current) return
      setHeight(Math.max(150, Math.min(600, startH + (startY - ev.clientY))))
    }
    const onUp = () => { resizing.current = false; window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [height])

  // Navigate to investigation node when clicking a playbook step
  const navigateToNode = useCallback((invNodeId: string) => {
    useGraphStore.getState().selectNode(invNodeId)
  }, [])

  const [forceShow, setForceShow] = useState(false)

  // Listen for external toggle event (from SessionBar button)
  useEffect(() => {
    const handler = () => {
      if (executions.length > 0) {
        setOpen(prev => !prev)
      } else {
        setForceShow(prev => !prev)
      }
    }
    window.addEventListener('togglePlaybookDrawer', handler)
    return () => window.removeEventListener('togglePlaybookDrawer', handler)
  }, [executions.length])

  if (executions.length === 0 && !forceShow) return null
  if (executions.length === 0 && forceShow) {
    return (
      <div className="border-t border-surface-3 flex-shrink-0">
        <div className="flex items-center gap-2 px-4 py-2 bg-surface-1">
          <span className="text-[10px] bg-green-600 text-white px-1.5 py-0.5 rounded font-medium">Playbook</span>
          <span className="text-[11px] text-gray-500">No playbook executions for this investigation</span>
          <button onClick={() => setForceShow(false)} className="text-[10px] text-gray-600 hover:text-gray-400 ml-auto">{'\u2715'}</button>
        </div>
      </div>
    )
  }

  const clampedIdx = Math.min(selectedExecIdx, executions.length - 1)
  const exec = executions[clampedIdx] || executions[0]
  const pb = exec ? playbooks[exec.playbook_id] : null
  const entries = exec ? Object.entries(exec.node_states) : []
  const total = entries.length
  const completed = entries.filter(([, s]) => s.status === 'completed').length
  const failed = entries.filter(([, s]) => s.status === 'failed').length
  const skipped = entries.filter(([, s]) => s.status === 'skipped').length
  const done = completed + failed + skipped

  // Map playbook node IDs to investigation node IDs (pb-{nodeId}-{timestamp})
  const invNodeMap: Record<string, string> = {}
  const graphNodes = useGraphStore.getState().nodes
  for (const [gid, gnode] of Object.entries(graphNodes)) {
    if (gnode.source_tool === 'playbook') {
      // Extract playbook node ID from investigation node ID: pb-{pbNodeId}-{timestamp}
      const match = gid.match(/^pb-(.+?)-\d+$/)
      if (match) invNodeMap[match[1]] = gid
    }
  }

  return (
    <div className="flex flex-col border-t border-surface-3" style={open ? { height } : {}}>
      {/* Toggle bar — always visible */}
      <div
        className="flex items-center gap-2 px-3 py-1.5 bg-surface-1 cursor-pointer hover:bg-surface-2/50 flex-shrink-0"
        onClick={() => setOpen(!open)}
      >
        <span className="text-[10px] bg-green-600 text-white px-1.5 py-0.5 rounded font-medium">Playbook</span>
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
          exec?.status === 'running' ? 'bg-yellow-400 animate-pulse'
          : exec?.status === 'completed' ? 'bg-green-400'
          : exec?.status === 'failed' ? 'bg-red-400'
          : 'bg-gray-500'
        }`} />
        <div className="flex-1 h-1.5 bg-surface-3 rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all flex">
            <div className="h-full bg-green-500" style={{ width: `${total > 0 ? (completed / total) * 100 : 0}%` }} />
            {failed > 0 && <div className="h-full bg-red-500/60" style={{ width: `${(failed / total) * 100}%` }} />}
          </div>
        </div>
        <span className="text-[10px] text-gray-500 tabular-nums">{done}/{total}</span>
        {pb && <span className="text-[10px] text-gray-400 truncate max-w-[150px]">{pb.name}</span>}
        {exec?.status === 'running' && (
          <button
            onClick={(e) => { e.stopPropagation(); playbooksApi.cancelExecution(exec.id) }}
            className="text-[10px] text-red-400 hover:text-red-300"
          >Cancel</button>
        )}
        <span className="text-[10px] text-gray-600">{open ? '\u25BC' : '\u25B2'}</span>
      </div>

      {/* Resize handle */}
      {open && (
        <div
          className="h-1 cursor-ns-resize bg-surface-3 hover:bg-accent-blue/50 transition-colors flex-shrink-0"
          onMouseDown={onResizeStart}
        />
      )}

      {/* DAG panel */}
      {open && (
        <div className="flex-1 flex overflow-hidden">
          {/* Execution tabs (if multiple playbooks ran) */}
          {executions.length > 1 && (
            <div className="w-[140px] border-r border-surface-3 overflow-y-auto p-2 flex-shrink-0">
              {executions.map((ex, i) => (
                <button
                  key={ex.id}
                  onClick={() => setSelectedExecIdx(i)}
                  className={`w-full text-left px-2 py-1.5 rounded text-[10px] mb-0.5 truncate ${
                    i === selectedExecIdx ? 'bg-accent-blue/15 text-accent-blue' : 'text-gray-500 hover:text-gray-300 hover:bg-surface-3'
                  }`}
                >
                  {playbooks[ex.playbook_id]?.name || ex.playbook_id}
                </button>
              ))}
            </div>
          )}

          {/* ReactFlow DAG */}
          {pb ? (
            <PlaybookDAGView
              playbook={pb}
              execution={exec}
              invNodeMap={invNodeMap}
              onNavigate={navigateToNode}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-600 text-[12px]">Loading playbook...</div>
          )}

          {/* Step list sidebar */}
          <div className="w-[180px] border-l border-surface-3 overflow-y-auto p-2 flex-shrink-0">
            <h4 className="text-[9px] text-gray-600 uppercase tracking-wider mb-1">Steps</h4>
            {entries.map(([nodeId, state]) => {
              const style = STATUS_STYLES[state.status] || STATUS_STYLES.pending
              const invId = invNodeMap[nodeId]
              return (
                <div
                  key={nodeId}
                  className={`flex items-center gap-1.5 px-2 py-1 rounded text-[10px] mb-0.5 cursor-pointer hover:bg-white/[0.04] ${invId ? '' : 'opacity-60'}`}
                  onClick={() => { if (invId) navigateToNode(invId) }}
                >
                  <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${style.dot}`} />
                  <span className={`truncate ${style.text}`}>{pb?.nodes.find(n => n.id === nodeId)?.label || nodeId}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

/** ReactFlow view of the playbook DAG with live status coloring */
function PlaybookDAGView({ playbook, execution, invNodeMap, onNavigate }: {
  playbook: Playbook
  execution: PlaybookExecution
  invNodeMap: Record<string, string>
  onNavigate: (invNodeId: string) => void
}) {
  const rfNodes: Node[] = playbook.nodes.map(n => {
    const status = execution.node_states[n.id]?.status || 'pending'
    return {
      id: n.id,
      type: 'pb_node',
      position: n.position || { x: 0, y: 0 },
      data: { label: n.label, status, refType: n.ref_type, body: n.body, invNodeId: invNodeMap[n.id], onNavigate },
    }
  })

  const rfEdges: Edge[] = playbook.edges.map(e => {
    const sourceStatus = execution.node_states[e.source]?.status || 'pending'
    const s = STATUS_STYLES[sourceStatus] || STATUS_STYLES.pending
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.label || undefined,
      animated: sourceStatus === 'running',
      style: { stroke: s.border, strokeWidth: 2 },
      labelStyle: { fill: '#8b5cf6', fontSize: 9 },
      labelBgStyle: { fill: '#12121a', fillOpacity: 0.9 },
      labelBgPadding: [3, 2] as [number, number],
    }
  })

  return (
    <div className="flex-1">
      <ReactFlowProvider>
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          nodeTypes={nodeTypes}
          fitView
          minZoom={0.2}
          maxZoom={2}
          nodesDraggable={false}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="rgba(255,255,255,0.03)" />
          <Controls showInteractive={false} />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  )
}
