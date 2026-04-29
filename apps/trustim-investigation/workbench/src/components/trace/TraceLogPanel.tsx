import { useMemo, useState } from 'react'
import { useGraphStore } from '../../store/graph'
import { confidenceColor, ACTION_TYPE_ICONS } from '../../types'
import type { TraceEvent } from '../../types'

/** Chronological log view (R39-R40) with reasoning chains (R38) */
export function TraceLogPanel() {
  const nodes = useGraphStore((s) => s.nodes)
  const selectNode = useGraphStore((s) => s.selectNode)
  const setViewMode = useGraphStore((s) => s.setViewMode)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [filterConfidence, setFilterConfidence] = useState<string>('all')

  // Build trace events from nodes
  const events = useMemo(() => {
    const traceEvents: TraceEvent[] = []
    for (const node of Object.values(nodes)) {
      traceEvents.push({
        id: node.node_id,
        timestamp: node.timestamp,
        type: node.action_type === 'skill_invocation' ? 'skill_invocation'
          : node.action_type === 'query_execution' ? 'query'
          : node.action_type === 'enrichment' ? 'enrichment'
          : node.action_type === 'annotation' ? 'reasoning'
          : 'tool_call',
        node_id: node.node_id,
        summary: node.label || node.action_type,
        detail: node.result_summary || node.query,
        duration_ms: node.duration_ms,
        success: node.status !== 'failed',
      })
    }
    return traceEvents.sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    )
  }, [nodes])

  const filtered = filterConfidence === 'all'
    ? events
    : events.filter((e) => {
        const c = e.node_id ? nodes[e.node_id]?.confidence ?? 0 : 0
        if (filterConfidence === 'high') return c > 0.6
        if (filterConfidence === 'medium') return c > 0.2 && c <= 0.6
        return c <= 0.2
      })

  return (
    <div className="h-full flex flex-col bg-surface-0" role="log" aria-label="Investigation execution trace">
      {/* Header */}
      <div className="px-4 py-2 border-b border-surface-3 flex items-center justify-between flex-shrink-0">
        <h2 className="text-sm font-medium text-gray-300">Execution Trace</h2>
        <div className="flex items-center gap-2">
          {/* Confidence filter */}
          <select
            value={filterConfidence}
            onChange={(e) => setFilterConfidence(e.target.value)}
            className="bg-surface-2 border border-surface-4 rounded px-1.5 py-0.5 text-[10px] text-gray-300 focus:outline-none"
          >
            <option value="all">All ({events.length})</option>
            <option value="high">High (&gt;60%)</option>
            <option value="medium">Medium (21-60%)</option>
            <option value="low">Low (0-20%)</option>
          </select>
          <button
            onClick={() => setViewMode('graph')}
            className="text-xs text-accent-blue hover:text-blue-400"
          >
            Switch to Graph
          </button>
        </div>
      </div>

      {/* Event list */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="text-center text-gray-500 mt-12">
            <p>No trace events{filterConfidence !== 'all' ? ` with confidence "${filterConfidence}"` : ''}</p>
          </div>
        ) : (
          <div className="divide-y divide-surface-3">
            {filtered.map((event) => {
              const node = event.node_id ? nodes[event.node_id] : null
              const confidence = node?.confidence ?? 0
              const isExpanded = expandedId === event.id

              return (
                <div key={event.id}>
                  <button
                    onClick={() => setExpandedId(isExpanded ? null : event.id)}
                    className="w-full text-left px-4 py-2.5 hover:bg-surface-1 transition-colors"
                  >
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-[10px] text-gray-500 font-mono w-[70px] flex-shrink-0">
                        {new Date(event.timestamp).toLocaleTimeString()}
                      </span>
                      <span className="text-sm flex-shrink-0">
                        {node ? ACTION_TYPE_ICONS[node.action_type] : '\u2022'}
                      </span>
                      <span className="text-xs font-medium text-gray-200 truncate flex-1">
                        {event.summary}
                      </span>
                      {event.duration_ms > 0 && (
                        <span className="text-[10px] text-gray-500 flex-shrink-0">
                          {(event.duration_ms / 1000).toFixed(1)}s
                        </span>
                      )}
                      <span
                        className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{ backgroundColor: confidenceColor(confidence) }}
                      />
                      {!event.success && (
                        <span className="text-[10px] text-red-400 flex-shrink-0">FAIL</span>
                      )}
                      <span className="text-[10px] text-gray-600">{isExpanded ? '\u25BC' : '\u25B6'}</span>
                    </div>
                    {!isExpanded && event.detail && (
                      <p className="text-[11px] text-gray-500 truncate ml-[82px]">
                        {event.detail}
                      </p>
                    )}
                  </button>

                  {/* Expanded detail — R38 reasoning chain */}
                  {isExpanded && node && (
                    <div className="px-4 pb-3 ml-[82px] space-y-2">
                      {/* Reasoning (R38) */}
                      {node.reasoning && (
                        <div>
                          <span className="text-[10px] text-gray-500 uppercase">Reasoning</span>
                          <p className="text-xs text-gray-300 mt-0.5 leading-relaxed">{node.reasoning}</p>
                        </div>
                      )}
                      {/* Query */}
                      {node.query && (
                        <div>
                          <span className="text-[10px] text-gray-500 uppercase">Query</span>
                          <pre className="text-[10px] text-gray-400 bg-surface-2 rounded p-1.5 mt-0.5 overflow-auto max-h-[80px] font-mono">
                            {node.query}
                          </pre>
                        </div>
                      )}
                      {/* Result summary */}
                      {node.result_summary && (
                        <div>
                          <span className="text-[10px] text-gray-500 uppercase">Result</span>
                          <p className="text-xs text-gray-300 mt-0.5">{node.result_summary}</p>
                        </div>
                      )}
                      {/* Confidence */}
                      <div className="flex items-center gap-2">
                        <span
                          className="text-[10px] font-medium uppercase px-1.5 py-0.5 rounded"
                          style={{
                            color: confidenceColor(confidence),
                            backgroundColor: confidenceColor(confidence) + '20',
                          }}
                        >
                          {(node.confidence * 100).toFixed(0)}%
                        </span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            selectNode(node.node_id)
                            setViewMode('graph')
                          }}
                          className="text-[10px] text-accent-blue hover:text-blue-400"
                        >
                          View in graph
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
