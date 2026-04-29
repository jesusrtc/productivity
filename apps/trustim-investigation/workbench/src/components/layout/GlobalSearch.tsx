import { useState, useMemo, useRef, useEffect } from 'react'
import { useGraphStore } from '../../store/graph'
import { confidenceColor } from '../../types'

interface Props {
  onClose: () => void
}

interface SearchHit {
  nodeId: string
  label: string
  confidence: number
  matchLine: string
  matchIdx: number
}

/** Global search across all node results — Cmd+Shift+F */
export function GlobalSearch({ onClose }: Props) {
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const nodes = useGraphStore((s) => s.nodes)
  const selectNode = useGraphStore((s) => s.selectNode)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  // Debounce search to avoid jank on large result sets
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query), 150)
    return () => clearTimeout(timer)
  }, [query])

  const hits = useMemo(() => {
    if (debouncedQuery.length < 2) return []
    const lq = debouncedQuery.toLowerCase()
    const results: SearchHit[] = []
    for (const [nodeId, node] of Object.entries(nodes)) {
      const searchText = [node.result_raw, node.result_summary, node.label, node.reasoning].filter(Boolean).join('\n')
      const lines = searchText.split('\n')
      for (let i = 0; i < lines.length; i++) {
        const idx = lines[i].toLowerCase().indexOf(lq)
        if (idx >= 0) {
          results.push({
            nodeId,
            label: node.label,
            confidence: node.confidence,
            matchLine: lines[i],
            matchIdx: idx,
          })
          break // one hit per node
        }
      }
    }
    return results.slice(0, 50)
  }, [debouncedQuery, nodes])

  return (
    <div className="fixed inset-0 bg-black/50 flex items-start justify-center pt-[15vh] z-[110]" onClick={onClose}>
      <div className="glass-panel rounded-2xl w-[600px] shadow-2xl overflow-hidden" onClick={e => e.stopPropagation()}>
        <div className="flex items-center gap-3 px-5 py-3 border-b border-white/[0.06]">
          <span className="text-gray-500 text-sm">{'\u{1F50D}'}</span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => { if (e.key === 'Escape') onClose() }}
            placeholder="Search all node results..."
            className="flex-1 bg-transparent text-[15px] text-gray-100 placeholder-gray-500 focus:outline-none"
            autoFocus
          />
          {query && (
            <span className="text-[11px] text-gray-500 tabular-nums">{hits.length} results</span>
          )}
        </div>
        <div className="max-h-[400px] overflow-y-auto py-1">
          {hits.length === 0 && query.length >= 2 && (
            <div className="px-5 py-6 text-center text-[13px] text-gray-500">No matches found</div>
          )}
          {hits.map((hit) => (
            <button
              key={hit.nodeId}
              onClick={() => { selectNode(hit.nodeId); onClose() }}
              className="w-full text-left px-5 py-2.5 hover:bg-white/[0.04] transition-colors"
            >
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-[11px] font-bold tabular-nums" style={{ color: confidenceColor(hit.confidence) }}>
                  {(hit.confidence * 100).toFixed(0)}%
                </span>
                <span className="text-[12px] text-gray-200 truncate">{hit.label}</span>
              </div>
              <HighlightLine line={hit.matchLine} query={query} />
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function HighlightLine({ line, query }: { line: string; query: string }) {
  const lq = query.toLowerCase()
  const idx = line.toLowerCase().indexOf(lq)
  if (idx < 0) return <span className="text-[11px] text-gray-500 truncate block">{line.slice(0, 120)}</span>

  // Show context around match
  const start = Math.max(0, idx - 40)
  const end = Math.min(line.length, idx + query.length + 60)
  const before = line.slice(start, idx)
  const match = line.slice(idx, idx + query.length)
  const after = line.slice(idx + query.length, end)

  return (
    <span className="text-[11px] text-gray-500 truncate block font-mono">
      {start > 0 && '\u2026'}
      {before}
      <span className="bg-yellow-500/30 text-yellow-200 rounded-sm px-0.5">{match}</span>
      {after}
      {end < line.length && '\u2026'}
    </span>
  )
}
