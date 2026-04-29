import { useMemo, useRef, useEffect } from 'react'
import { useGraphStore } from '../../store/graph'
import { confidenceColor, ACTION_TYPE_ICONS } from '../../types'

/** Horizontal chronological timeline of all investigation nodes */
export function TimelineView() {
  const nodes = useGraphStore((s) => s.nodes)
  const selectedNodeId = useGraphStore((s) => s.selectedNodeId)
  const selectNode = useGraphStore((s) => s.selectNode)
  const scrollRef = useRef<HTMLDivElement>(null)

  const sorted = useMemo(() => {
    return Object.values(nodes)
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
  }, [nodes])

  // Auto-scroll to selected node
  useEffect(() => {
    if (!selectedNodeId || !scrollRef.current) return
    const el = scrollRef.current.querySelector(`[data-node-id="${selectedNodeId}"]`) as HTMLElement
    if (el) el.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
  }, [selectedNodeId])

  if (sorted.length === 0) {
    return <div className="h-full flex items-center justify-center text-gray-500 text-sm">No nodes yet</div>
  }

  const startTime = new Date(sorted[0].timestamp).getTime()
  const endTime = new Date(sorted[sorted.length - 1].timestamp).getTime()
  const range = Math.max(endTime - startTime, 1000) // min 1s range

  return (
    <div className="h-full flex flex-col bg-surface-0">
      <div className="px-4 py-2 border-b border-surface-3 flex items-center justify-between flex-shrink-0">
        <h2 className="text-sm font-medium text-gray-300">Investigation Timeline</h2>
        <span className="text-[11px] text-gray-500 tabular-nums">{sorted.length} nodes</span>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-x-auto overflow-y-hidden px-4 py-6">
        <div className="relative" style={{ minWidth: `${Math.max(sorted.length * 120, 600)}px`, height: '100%' }}>
          {/* Timeline line */}
          <div className="absolute top-1/2 left-0 right-0 h-px bg-surface-3" />

          {/* Time markers */}
          {sorted.map((node, i) => {
            const t = new Date(node.timestamp).getTime()
            const pct = ((t - startTime) / range) * 100
            const color = confidenceColor(node.confidence)
            const icon = ACTION_TYPE_ICONS[node.action_type as keyof typeof ACTION_TYPE_ICONS] || '\u2022'
            const isSelected = node.node_id === selectedNodeId
            const above = i % 2 === 0 // alternate above/below timeline

            return (
              <div
                key={node.node_id}
                data-node-id={node.node_id}
                className="absolute flex flex-col items-center"
                style={{
                  left: `${Math.min(pct, 98)}%`,
                  top: above ? '10%' : '50%',
                  transform: 'translateX(-50%)',
                }}
              >
                {/* Connector line to timeline */}
                <div
                  className="w-px bg-surface-3"
                  style={{ height: above ? 'calc(40% - 4px)' : 'calc(40% - 4px)', order: above ? 1 : -1 }}
                />

                {/* Node card */}
                <button
                  onClick={() => selectNode(node.node_id)}
                  className={`group relative rounded-lg px-2.5 py-2 transition-all max-w-[140px] ${
                    isSelected
                      ? 'bg-accent-blue/20 border border-accent-blue/40 scale-105'
                      : 'bg-surface-2/60 border border-white/[0.04] hover:border-white/[0.08] hover:scale-[1.02]'
                  }`}
                  style={{ order: above ? 0 : 0 }}
                >
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span className="text-xs">{icon}</span>
                    <span className="text-[10px] font-bold tabular-nums" style={{ color }}>
                      {(node.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="text-[11px] text-gray-200 truncate">{node.label}</div>
                  <div className="text-[9px] text-gray-500 tabular-nums mt-0.5">
                    {new Date(node.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </div>
                  {node.status === 'failed' && (
                    <div className="absolute -top-1 -right-1 w-3 h-3 bg-red-500 rounded-full" />
                  )}
                </button>

                {/* Dot on timeline */}
                <div
                  className="w-2.5 h-2.5 rounded-full border-2 border-surface-0 flex-shrink-0"
                  style={{ backgroundColor: color, order: above ? 2 : -2 }}
                />
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
