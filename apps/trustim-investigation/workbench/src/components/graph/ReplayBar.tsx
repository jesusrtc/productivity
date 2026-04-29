import { useState, useMemo } from 'react'
import { useGraphStore } from '../../store/graph'
import { confidenceColor } from '../../types'

/** Replay mode bar — step through investigation nodes chronologically */
export function ReplayBar() {
  const nodes = useGraphStore((s) => s.nodes)
  const selectNode = useGraphStore((s) => s.selectNode)
  const [replayActive, setReplayActive] = useState(false)
  const [replayIdx, setReplayIdx] = useState(0)

  const sorted = useMemo(() => {
    return Object.values(nodes)
      .filter(n => n.status === 'completed')
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
  }, [nodes])

  if (sorted.length < 2) return null

  if (!replayActive) {
    return (
      <button
        onClick={() => { setReplayActive(true); setReplayIdx(0); selectNode(sorted[0].node_id) }}
        className="text-gray-500 hover:text-gray-300 transition-colors"
        title="Replay investigation step-by-step"
      >
        Replay
      </button>
    )
  }

  const current = sorted[replayIdx]
  const hasPrev = replayIdx > 0
  const hasNext = replayIdx < sorted.length - 1

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => { setReplayActive(false); selectNode(null) }}
        className="text-[10px] text-gray-500 hover:text-gray-300"
      >
        Exit
      </button>
      <button
        onClick={() => { if (hasPrev) { setReplayIdx(i => i - 1); selectNode(sorted[replayIdx - 1].node_id) } }}
        disabled={!hasPrev}
        className="text-gray-400 hover:text-gray-200 disabled:text-gray-600 text-sm"
      >
        {'\u25C0'}
      </button>
      <span className="text-[10px] text-gray-400 tabular-nums min-w-[60px] text-center">
        {replayIdx + 1}/{sorted.length}
      </span>
      <button
        onClick={() => { if (hasNext) { setReplayIdx(i => i + 1); selectNode(sorted[replayIdx + 1].node_id) } }}
        disabled={!hasNext}
        className="text-gray-400 hover:text-gray-200 disabled:text-gray-600 text-sm"
      >
        {'\u25B6'}
      </button>
      {current && (
        <span className="text-[10px] truncate max-w-[120px]" style={{ color: confidenceColor(current.confidence) }}>
          {current.label}
        </span>
      )}
    </div>
  )
}
