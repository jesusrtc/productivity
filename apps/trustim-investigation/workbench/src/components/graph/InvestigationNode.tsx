import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { InvestigationNode as INode } from '../../types'
import { confidenceColor, ACTION_TYPE_ICONS } from '../../types'
import { useGraphStore } from '../../store/graph'

/** Map skill names to consistent colors for visual grouping */
function skillColor(name: string): string {
  const colors = ['#8b5cf6', '#06b6d4', '#f59e0b', '#10b981', '#ef4444', '#ec4899', '#6366f1', '#14b8a6']
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0
  return colors[Math.abs(hash) % colors.length]
}

/** Custom React Flow node for the investigation graph (Section 7.1) */
export const InvestigationNodeComponent = memo(function InvestigationNodeComponent({
  data,
  selected,
}: NodeProps & { data: INode }) {
  const node = data
  const viewMode = useGraphStore((s) => s.viewMode)
  const isFrontier = useGraphStore((s) => s.autoInvestigateCurrentId === node.node_id)
  const borderColor = confidenceColor(node.confidence)
  const icon = ACTION_TYPE_ICONS[node.action_type]
  const isRunning = node.status === 'running'
  const isFailed = node.status === 'failed'
  const isDeadEnd = node.is_dead_end
  const isHeatmap = viewMode === 'heatmap'
  const ageMs = Date.now() - new Date(node.timestamp).getTime()
  const isNew = ageMs < 5000 // 5s — tight window for "new" badge
  const justCompleted = node.status === 'completed' && ageMs < 3000 // Flash for recent completions

  const statusIcon =
    node.status === 'completed' ? '\u2713' :
    node.status === 'running' ? '' :
    node.status === 'failed' ? '\u2717' :
    '\u0021'

  // R51: Heatmap mode — emphasize severity, suppress details
  if (isHeatmap) {
    return (
      <>
        <Handle type="target" position={Position.Top} className="!bg-transparent !border-transparent !w-2 !h-2" />
        <div
          className={`rounded-lg px-3 py-2 min-w-[120px] max-w-[160px] cursor-pointer transition-all ${
            selected ? 'ring-2 ring-white ring-offset-1 ring-offset-surface-0' : ''
          }`}
          style={{
            backgroundColor: confidenceColor(node.confidence) + '30',
            borderWidth: 3,
            borderColor: confidenceColor(node.confidence),
          }}
        >
          <div className="text-center">
            <span className="text-lg">{icon}</span>
            <div
              className="text-xs font-bold uppercase mt-0.5"
              style={{ color: confidenceColor(node.confidence) }}
            >
              {(node.confidence * 100).toFixed(0)}%
            </div>
            {node.confidence_override && (
              <div className="text-[9px] text-gray-400">override</div>
            )}
          </div>
        </div>
        <Handle type="source" position={Position.Bottom} className="!bg-transparent !border-transparent !w-2 !h-2" />
      </>
    )
  }

  return (
    <div role="treeitem" aria-label={`${node.action_type}: ${node.label}. Score ${(node.confidence * 100).toFixed(0)}%. Status: ${node.status}`}>
      <Handle type="target" position={Position.Top} className="!bg-transparent !border-transparent !w-3 !h-3" />
      <div
        className={`
          relative rounded-xl border px-3.5 py-2.5 min-w-[250px] max-w-[290px]
          bg-surface-2/90 backdrop-blur-sm
          transition-all duration-200 cursor-pointer group/node
          ${isRunning ? 'node-running' : ''}
          ${justCompleted && node.confidence > 0.5 ? 'node-just-completed' : ''}
          ${isFrontier ? 'ring-2 ring-accent-cyan/50 ring-offset-1 ring-offset-surface-0' : ''}
          ${isDeadEnd ? 'opacity-35' : ''}
          ${selected ? 'ring-2 ring-accent-blue/70 ring-offset-2 ring-offset-surface-0 scale-[1.02]' : 'hover:shadow-xl hover:shadow-black/30'}
        `}
        style={{
          borderColor: borderColor + '80',
          boxShadow: node.confidence > 0.7
            ? `0 0 12px ${borderColor}40, 0 4px 20px rgba(0,0,0,0.2)`
            : (node.tags || []).some(t => t.startsWith('SEV-'))
              ? `0 0 10px rgba(239,68,68,0.25), 0 4px 20px rgba(0,0,0,0.2)`
              : '0 4px 20px rgba(0,0,0,0.2)',
        }}
        title={`${node.label}\n${node.result_summary ? `Result: ${node.result_summary.slice(0, 120)}` : ''}\nScore: ${(node.confidence * 100).toFixed(0)}% | ${node.status}`}
      >
        {/* Hover tooltip — richer than title attr */}
        {/* Hover tooltip with result summary + timeline */}
        <div className="absolute bottom-full left-0 right-0 mb-2 opacity-0 group-hover/node:opacity-100 pointer-events-none transition-opacity duration-200 z-50">
          <div className="glass-panel rounded-lg px-3 py-2 text-[11px] leading-relaxed shadow-xl max-w-[360px]">
            {node.result_summary && (
              <p className="text-gray-300 mb-1">{node.result_summary.slice(0, 150)}{node.result_summary.length > 150 && '...'}</p>
            )}
            {node.query && (
              <p className="text-accent-cyan/60 font-mono text-[10px] mb-1 truncate">{node.query.slice(0, 80)}{node.query.length > 80 && '...'}</p>
            )}
            {node.result_raw && !node.result_summary && (
              <p className="text-gray-400 font-mono text-[10px] mb-1 line-clamp-3 whitespace-pre-wrap">{node.result_raw.slice(0, 200)}</p>
            )}
            <div className="flex items-center gap-2 text-[10px] text-gray-500">
              <span className="tabular-nums">{new Date(node.timestamp).toLocaleTimeString()}</span>
              {node.duration_ms > 0 && <span className="tabular-nums">{(node.duration_ms / 1000).toFixed(1)}s</span>}
              {node.tool_name && <span className="text-accent-cyan/70">{node.tool_name}</span>}
            </div>
          </div>
        </div>
        {/* New node indicator */}
        {isNew && node.status === 'completed' && (
          <div className="absolute -top-1 left-4 text-[7px] text-accent-blue font-bold uppercase tracking-wider animate-pulse">new</div>
        )}
        {/* Confidence indicator bar */}
        <div
          className="absolute top-0 left-4 right-4 h-[2px] rounded-b"
          style={{ backgroundColor: borderColor }}
        />
        {/* Playbook step indicator — green left bar + badge */}
        {node.source_tool === 'playbook' ? (
          <>
            <div className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r bg-green-500" title="Playbook step" />
            <div className="absolute -top-1.5 -left-1.5 px-1.5 py-0.5 rounded-full bg-green-600 text-[7px] text-white font-bold">
              PB
            </div>
          </>
        ) : node.skill_name ? (
          <div
            className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r"
            style={{ backgroundColor: skillColor(node.skill_name) }}
            title={`Skill: ${node.skill_name}`}
          />
        ) : null}

        {/* Pin indicator */}
        {node.pinned && (
          <div className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-accent-cyan/80 flex items-center justify-center text-[8px] text-white" title="Pinned">
            {'\u{1F4CC}'}
          </div>
        )}

        {/* SEV badge — shows when node has been tagged with a SEV level */}
        {!node.pinned && (node.tags || []).some(t => t.startsWith('SEV-')) && (
          <div className="absolute -top-1.5 -right-1.5 px-1.5 py-0.5 rounded-full bg-red-500 text-[7px] text-white font-bold">
            {(node.tags || []).find(t => t.startsWith('SEV-'))}
          </div>
        )}

        {/* Notes indicator — shows when node has investigator annotations */}
        {node.investigator_notes && !node.pinned && (
          <div className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-yellow-500/80 flex items-center justify-center text-[8px]" title="Has notes">
            {'\u{1F4DD}'}
          </div>
        )}

        {/* Sequence number badge — shows investigation order */}
        <NodeSequenceBadge nodeId={node.node_id} />

        {/* Top row: icon + label + status */}
        <div className="flex items-center gap-2 mb-1.5 mt-0.5">
          <span className="text-[15px] flex-shrink-0 opacity-70" title={node.action_type}>{icon}</span>
          <span className="text-[13px] font-medium text-gray-100 truncate flex-1 leading-tight">
            {node.label || node.action_type.replace(/_/g, ' ')}
          </span>
          <span className={`text-xs flex-shrink-0 ${
            isFailed ? 'text-red-400' :
            node.status === 'paused_for_input' ? 'text-yellow-400' :
            node.status === 'needs_review' ? 'text-yellow-400' :
            node.status === 'completed' ? 'text-green-400/70' :
            'text-blue-400'
          }`}>
            {isRunning ? (
              <span className="inline-block w-3.5 h-3.5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
            ) : node.status === 'paused_for_input' ? '\u275A\u275A' : statusIcon}
          </span>
        </div>

        {/* Live execution indicator for running nodes */}
        {isRunning && (
          <div className="mb-1">
            {node.tool_name && (
              <p className="text-[10px] text-accent-blue/80 truncate leading-tight mb-0.5">
                {node.tool_name}
              </p>
            )}
            {node.query && (
              <p className="text-[9px] text-gray-500 font-mono truncate leading-tight">
                {node.query.slice(0, 60)}
              </p>
            )}
            <div className="mt-1 h-[2px] bg-surface-4 rounded-full overflow-hidden">
              <div className="h-full bg-accent-blue/60 rounded-full animate-[shimmer_1.5s_ease-in-out_infinite]"
                style={{ width: '60%' }} />
            </div>
          </div>
        )}
        {/* Result summary subtitle */}
        {node.result_summary && node.status === 'completed' && (
          <p className="text-[10px] text-gray-400/80 truncate mb-1 leading-tight">
            {node.result_summary.slice(0, 60)}
          </p>
        )}
        {/* Error hint for failed nodes */}
        {isFailed && node.result_raw && (
          <p className="text-[10px] text-red-400/70 truncate mb-1 leading-tight">
            {node.result_raw.slice(0, 50)}
          </p>
        )}

        {/* Bottom row: metadata — Apple HIG: secondary info is subdued */}
        <div className="flex items-center gap-2 text-[11px] text-gray-500">
          {node.skill_name && (
            <span className="text-accent-purple/70 truncate max-w-[80px]">{node.skill_name}</span>
          )}
          {!node.skill_name && node.tool_name && (
            <span className="text-accent-cyan/50 truncate max-w-[80px]">{node.tool_name}</span>
          )}
          {node.duration_ms > 0 && (
            <span className="tabular-nums opacity-60">{(node.duration_ms / 1000).toFixed(1)}s</span>
          )}
          <span
            className="ml-auto px-1.5 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-wide cursor-pointer hover:ring-1 hover:ring-white/20 transition-all"
            style={{
              backgroundColor: confidenceColor(node.confidence) + '15',
              color: confidenceColor(node.confidence),
            }}
            title="Double-click to cycle confidence"
            onDoubleClick={(e) => {
              e.stopPropagation()
              // Cycle through: current → 0.8 → 0.5 → 0.2 → 0
              const levels = [0, 0.2, 0.5, 0.8, 1.0]
              const current = Math.round(node.confidence * 10) / 10
              const idx = levels.findIndex(l => l >= current)
              const next = levels[(idx + 1) % levels.length]
              useGraphStore.getState().overrideConfidence(node.node_id, next)
            }}
          >
            {(node.confidence * 100).toFixed(0)}%
            {node.confidence_override && ' *'}
          </span>
        </div>

        {/* Tags */}
        {node.tags && node.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {(node.tags || []).map(tag => (
              <span key={tag} className="text-[9px] bg-accent-purple/20 text-accent-purple px-1.5 py-0.5 rounded-md">
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* Entity count badge — shows when results contain extractable IOCs */}
        {node.status === 'completed' && node.result_raw && (() => {
          const ipCount = (node.result_raw.match(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g) || []).length
          const midCount = (node.result_raw.match(/\b\d{7,12}\b/g) || []).filter((m: string) => !m.startsWith('202')).length
          const total = ipCount + midCount
          if (total < 3) return null
          return (
            <div className="flex items-center gap-1.5 mt-1 text-[9px] text-accent-cyan/70">
              {ipCount > 0 && <span>{ipCount} IPs</span>}
              {midCount > 0 && <span>{midCount > 20 ? '20+' : midCount} MIDs</span>}
            </div>
          )
        })()}

        {/* Collapsed subtree indicator */}
        {node.subtree_collapsed && (
          <CollapsedBadge nodeId={node.node_id} />
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-transparent !border-transparent !w-3 !h-3" />
    </div>
  )
})

/** Shows the depth in the tree (distance from root). O(n) via ancestor walk. */
function NodeSequenceBadge({ nodeId }: { nodeId: string }) {
  const seq = useGraphStore((s) => {
    let depth = 0
    let current = s.nodes[nodeId]
    const visited = new Set<string>()
    while (current && current.parent_ids.length > 0 && !visited.has(current.node_id)) {
      visited.add(current.node_id)
      depth++
      current = s.nodes[(current.parent_ids || [])[0]]
    }
    return depth
  })
  if (seq <= 0) return null
  return (
    <div className="absolute -top-2.5 -left-2.5 w-5 h-5 rounded-full bg-surface-3 border border-white/[0.08] flex items-center justify-center text-[9px] text-gray-400 font-medium tabular-nums">
      {seq}
    </div>
  )
}

/** Shows count of hidden nodes in a collapsed subtree */
function CollapsedBadge({ nodeId }: { nodeId: string }) {
  const subtreeSize = useGraphStore((s) => s.getSubtree(nodeId).length - 1)
  return (
    <div className="absolute -bottom-3 left-1/2 -translate-x-1/2 text-[10px] text-gray-500 bg-surface-1 px-1.5 rounded border border-surface-3">
      {subtreeSize > 0 ? `+${subtreeSize} hidden` : 'collapsed'}
    </div>
  )
}
