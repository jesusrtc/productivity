import { useState, useEffect, memo } from 'react'
import {
  ReactFlow, ReactFlowProvider, Background, Controls, BackgroundVariant,
  Handle, Position, type Node, type Edge, type NodeTypes, type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { playbooksApi } from '../../api'
import type { PlaybookExecution } from '../../types/playbook'
import type { Playbook } from '../../types/playbook'

interface Props {
  sessionId: string
}

// Status → color mapping
const STATUS_COLORS: Record<string, { bg: string; border: string; text: string; dot: string }> = {
  completed: { bg: 'bg-green-900/20', border: 'border-green-500', text: 'text-green-400', dot: 'bg-green-400' },
  running:   { bg: 'bg-yellow-900/20', border: 'border-yellow-500', text: 'text-yellow-400', dot: 'bg-yellow-400 animate-pulse' },
  failed:    { bg: 'bg-red-900/20', border: 'border-red-500', text: 'text-red-400', dot: 'bg-red-400' },
  skipped:   { bg: 'bg-gray-900/20', border: 'border-gray-600', text: 'text-gray-500', dot: 'bg-gray-500' },
  pending:   { bg: 'bg-surface-2', border: 'border-surface-4', text: 'text-gray-500', dot: 'bg-gray-700' },
}

// Custom node for the DAG view
const PlaybookDAGNode = memo(({ data }: NodeProps) => {
  const d = data as { label: string; status: string; refType: string; body?: string }
  const colors = STATUS_COLORS[d.status] || STATUS_COLORS.pending
  return (
    <div className={`px-3 py-2 rounded-lg border-2 min-w-[160px] max-w-[220px] ${colors.bg} ${colors.border}`}>
      <Handle type="target" position={Position.Top} className="!w-2.5 !h-2.5 !bg-green-500 !border-2 !border-surface-1" />
      <div className="flex items-center gap-1.5">
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${colors.dot}`} />
        <span className={`text-[11px] font-medium truncate ${colors.text}`}>{d.label}</span>
      </div>
      <div className="flex items-center gap-1.5 mt-0.5">
        <span className="text-[9px] text-gray-600">{d.refType}</span>
        <span className="text-[9px] text-gray-600 ml-auto">{d.status}</span>
      </div>
      {d.body && <div className="text-[8px] text-gray-600 mt-0.5 line-clamp-1 italic">{d.body}</div>}
      <Handle type="source" position={Position.Bottom} className="!w-2.5 !h-2.5 !bg-green-500 !border-2 !border-surface-1" />
    </div>
  )
})
PlaybookDAGNode.displayName = 'PlaybookDAGNode'

const dagNodeTypes: NodeTypes = { pb_dag: PlaybookDAGNode as any }

export function PlaybookProgress({ sessionId }: Props) {
  const [executions, setExecutions] = useState<PlaybookExecution[]>([])
  const [expanded, setExpanded] = useState(true)
  const [dagOpen, setDagOpen] = useState(false)
  const [playbook, setPlaybook] = useState<Playbook | null>(null)

  useEffect(() => {
    const poll = () => {
      playbooksApi.listExecutions()
        .then((execs: PlaybookExecution[]) => {
          const matching = execs.filter(e => e.session_id === sessionId)
          setExecutions(matching)
          // Fetch playbook definition for DAG view
          if (matching.length > 0 && !playbook) {
            playbooksApi.get(matching[0].playbook_id)
              .then(pb => { if (pb?.nodes) setPlaybook(pb) })
              .catch(() => {})
          }
        })
        .catch(() => {})
    }
    poll()
    const timer = setInterval(poll, 2000)
    return () => clearInterval(timer)
  }, [sessionId, playbook])

  if (executions.length === 0) return null

  return (
    <div className="border-b border-surface-3 flex-shrink-0">
      {executions.map(exec => {
        const entries = Object.entries(exec.node_states)
        const total = entries.length
        const completed = entries.filter(([, s]) => s.status === 'completed').length
        const failed = entries.filter(([, s]) => s.status === 'failed').length
        const skipped = entries.filter(([, s]) => s.status === 'skipped').length
        const done = completed + failed + skipped
        const runningStep = entries.find(([, s]) => s.status === 'running')

        return (
          <div key={exec.id}>
            {/* Header bar */}
            <div className="flex items-center gap-2 px-4 py-2">
              <span className="text-[10px] bg-green-600 text-white px-1.5 py-0.5 rounded font-medium">PB</span>
              <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                exec.status === 'running' ? 'bg-yellow-400 animate-pulse'
                : exec.status === 'completed' ? 'bg-green-400'
                : exec.status === 'failed' ? 'bg-red-400'
                : 'bg-gray-500'
              }`} />
              <div className="flex-1 h-1.5 bg-surface-3 rounded-full overflow-hidden">
                <div className="h-full rounded-full transition-all flex">
                  <div className="h-full bg-green-500" style={{ width: `${total > 0 ? (completed / total) * 100 : 0}%` }} />
                  {failed > 0 && <div className="h-full bg-red-500/60" style={{ width: `${(failed / total) * 100}%` }} />}
                </div>
              </div>
              <span className="text-[10px] text-gray-500 tabular-nums">{done}/{total}</span>
              {runningStep && <span className="text-[10px] text-yellow-400 truncate max-w-[100px]">{runningStep[0]}</span>}
              <button
                onClick={() => setDagOpen(!dagOpen)}
                className={`text-[10px] px-2 py-0.5 rounded transition-colors ${dagOpen ? 'bg-green-600/20 text-green-400' : 'text-gray-500 hover:text-green-400 hover:bg-surface-3'}`}
              >
                {dagOpen ? 'Hide DAG' : 'View DAG'}
              </button>
              <button
                onClick={() => setExpanded(!expanded)}
                className="text-[10px] text-gray-500 hover:text-gray-300"
              >
                {expanded ? 'Steps \u25B2' : 'Steps \u25BC'}
              </button>
              {exec.status === 'running' && (
                <button
                  onClick={() => playbooksApi.cancelExecution(exec.id)}
                  className="text-[10px] text-red-400 hover:text-red-300"
                >Cancel</button>
              )}
            </div>

            {/* Expanded step list */}
            {expanded && !dagOpen && (
              <div className="px-4 pb-2 space-y-0.5">
                {entries.map(([nodeId, state]) => (
                  <div key={nodeId} className="flex items-center gap-2 text-[10px]">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${(STATUS_COLORS[state.status] || STATUS_COLORS.pending).dot}`} />
                    <span className={`truncate ${(STATUS_COLORS[state.status] || STATUS_COLORS.pending).text}`}>{nodeId}</span>
                    <span className="text-gray-600 ml-auto flex-shrink-0">{state.status}</span>
                  </div>
                ))}
              </div>
            )}

            {/* DAG visualization */}
            {dagOpen && playbook && (
              <PlaybookDAGPanel playbook={playbook} execution={exec} onClose={() => setDagOpen(false)} />
            )}
          </div>
        )
      })}
    </div>
  )
}

/** Floating ReactFlow panel showing the full playbook DAG with live status */
function PlaybookDAGPanel({ playbook, execution, onClose }: { playbook: Playbook; execution: PlaybookExecution; onClose: () => void }) {
  const rfNodes: Node[] = playbook.nodes.map(n => {
    const status = execution.node_states[n.id]?.status || 'pending'
    return {
      id: n.id,
      type: 'pb_dag',
      position: n.position || { x: 0, y: 0 },
      data: { label: n.label, status, refType: n.ref_type, body: n.body },
    }
  })

  const rfEdges: Edge[] = playbook.edges.map(e => {
    const sourceStatus = execution.node_states[e.source]?.status || 'pending'
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.label || undefined,
      animated: sourceStatus === 'running',
      style: {
        stroke: sourceStatus === 'completed' ? '#22c55e' : sourceStatus === 'running' ? '#eab308' : '#4a4a5a',
        strokeWidth: 2,
      },
      labelStyle: { fill: '#8b5cf6', fontSize: 9 },
      labelBgStyle: { fill: '#12121a', fillOpacity: 0.9 },
      labelBgPadding: [3, 2] as [number, number],
    }
  })

  return (
    <div className="mx-4 mb-3 rounded-lg border border-surface-3 overflow-hidden" style={{ height: 280 }}>
      <div className="flex items-center justify-between px-3 py-1.5 bg-surface-2/60 border-b border-surface-3">
        <div className="flex items-center gap-2">
          <span className="text-[10px] bg-green-600 text-white px-1.5 py-0.5 rounded font-medium">DAG</span>
          <span className="text-[11px] text-gray-300">{playbook.name}</span>
          <span className="text-[9px] text-gray-600">{playbook.nodes.length} steps</span>
        </div>
        <button onClick={onClose} className="text-[10px] text-gray-500 hover:text-gray-300">{'\u2715'}</button>
      </div>
      <ReactFlowProvider>
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          nodeTypes={dagNodeTypes}
          fitView
          minZoom={0.3}
          maxZoom={1.5}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={12} size={1} color="rgba(255,255,255,0.03)" />
          <Controls showInteractive={false} />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  )
}
