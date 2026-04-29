import { useState, useMemo } from 'react'
import { useGraphStore } from '../../store/graph'
import { confidenceColor, ACTION_TYPE_ICONS } from '../../types'

/** Node search/filter for large graphs */
export function GraphSearch() {
  const nodes = useGraphStore((s) => s.nodes)
  const selectNode = useGraphStore((s) => s.selectNode)
  const [query, setQuery] = useState('')
  const [isOpen, setIsOpen] = useState(false)

  const results = useMemo(() => {
    if (!query.trim()) return []
    const lower = query.toLowerCase()

    // Special filters: "score>70", "status:failed", "tag:SEV"
    const scoreMatch = lower.match(/^score\s*([><=]+)\s*(\d+)$/)
    const statusMatch = lower.match(/^status:\s*(\w+)$/)

    return Object.values(nodes)
      .filter((n) => {
        if (scoreMatch) {
          const threshold = parseInt(scoreMatch[2]) / 100
          const op = scoreMatch[1]
          if (op === '>') return n.confidence > threshold
          if (op === '>=') return n.confidence >= threshold
          if (op === '<') return n.confidence < threshold
          return n.confidence === threshold
        }
        if (statusMatch) {
          return n.status === statusMatch[1]
        }
        return (
          n.label.toLowerCase().includes(lower) ||
          n.query.toLowerCase().includes(lower) ||
          n.result_summary.toLowerCase().includes(lower) ||
          n.investigator_notes.toLowerCase().includes(lower) ||
          n.skill_name?.toLowerCase().includes(lower) ||
          n.tool_name?.toLowerCase().includes(lower) ||
          (n.tags || []).some(t => t.toLowerCase().includes(lower)) ||
          n.node_id.toLowerCase().startsWith(lower)
        )
      })
      .slice(0, 10)
  }, [nodes, query])

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="absolute top-3 right-3 z-10 bg-surface-2/80 backdrop-blur-sm border border-surface-4 rounded-lg px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 hover:border-accent-blue transition-colors"
      >
        {'\u{1F50D}'} Search nodes
      </button>
    )
  }

  return (
    <div className="absolute top-3 right-3 z-10 bg-surface-1 border border-surface-3 rounded-lg shadow-2xl w-[320px]">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-surface-3">
        <span className="text-gray-400 text-sm">{'\u{1F50D}'}</span>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search... (score>70, status:failed, tag name)"
          className="flex-1 bg-transparent text-xs text-gray-200 placeholder-gray-500 focus:outline-none"
          autoFocus
        />
        {query.trim() && <span className="text-[9px] text-gray-500 tabular-nums">{results.length}</span>}
        <button onClick={() => { setIsOpen(false); setQuery('') }} className="text-gray-400 hover:text-gray-200 text-sm">
          {'\u2715'}
        </button>
      </div>
      {query.trim() && (
        <div className="max-h-[240px] overflow-y-auto">
          {results.length === 0 ? (
            <p className="px-3 py-2 text-xs text-gray-500">No nodes found</p>
          ) : (
            results.map((node) => (
              <div key={node.node_id} className="flex items-center border-b border-surface-3 last:border-b-0">
                <button
                  onClick={() => { selectNode(node.node_id); setIsOpen(false); setQuery('') }}
                  className="flex-1 text-left px-3 py-2 hover:bg-surface-2 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm flex-shrink-0">{ACTION_TYPE_ICONS[node.action_type]}</span>
                    <span className="text-xs text-gray-200 truncate flex-1">{node.label || node.action_type}</span>
                    <span
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ backgroundColor: confidenceColor(node.confidence) }}
                    />
                  </div>
                {node.result_summary && (
                  <p className="text-[10px] text-gray-500 truncate ml-6 mt-0.5">{node.result_summary}</p>
                )}
                {(node.tags || []).length > 0 && (
                  <div className="flex gap-1 ml-6 mt-0.5">
                    {(node.tags || []).slice(0, 3).map(t => (
                      <span key={t} className="text-[8px] bg-accent-purple/10 text-accent-purple px-1 py-0.5 rounded">{t}</span>
                    ))}
                  </div>
                )}
                </button>
                {node.status === 'completed' && (
                  <button
                    onClick={() => {
                      import('../../store/session').then(({ useSessionStore }) => {
                        useSessionStore.getState().setChatContext({
                          nodeId: node.node_id,
                          label: node.label || '',
                          query: node.query,
                          result_summary: node.result_summary,
                          result_raw: node.result_raw,
                        })
                      })
                      setIsOpen(false); setQuery('')
                    }}
                    className="px-2 text-[9px] text-accent-blue hover:text-blue-400 transition-colors flex-shrink-0"
                    title="Branch from this node"
                  >
                    Branch
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
