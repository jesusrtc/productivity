import { useMemo, useState, Fragment } from 'react'
import { useGraphStore } from '../../store/graph'
import { confidenceColor, ACTION_TYPE_ICONS } from '../../types'

interface Props {
  nodeIdA: string
  nodeIdB: string
  onClose: () => void
}

/**
 * PRD Phase 14: Diff view between two branches.
 * Shows two branch paths side by side from their common ancestor to their tips.
 */
export function BranchDiffView({ nodeIdA, nodeIdB, onClose }: Props) {
  const nodes = useGraphStore((s) => s.nodes)
  const [showResults, setShowResults] = useState(false)

  const { pathA, pathB, commonAncestor } = useMemo(() => {
    const ancestorsA = getPathToRoot(nodeIdA, nodes)
    const ancestorsB = getPathToRoot(nodeIdB, nodes)

    // Find common ancestor
    const setB = new Set(ancestorsB)
    let common = ''
    for (const id of ancestorsA) {
      if (setB.has(id)) { common = id; break }
    }

    // Get paths from common ancestor to each tip
    const idxA = ancestorsA.indexOf(common)
    const idxB = ancestorsB.indexOf(common)
    const pathA = idxA >= 0 ? ancestorsA.slice(0, idxA + 1).reverse() : ancestorsA.reverse()
    const pathB = idxB >= 0 ? ancestorsB.slice(0, idxB + 1).reverse() : ancestorsB.reverse()

    return { pathA, pathB, commonAncestor: common }
  }, [nodeIdA, nodeIdB, nodes])

  const maxLen = Math.max(pathA.length, pathB.length)

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[100]" onClick={onClose}>
      <div className="glass-panel rounded-2xl p-6 w-[900px] max-h-[80vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-medium text-gray-200">Branch Comparison</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-200">{'\u2715'}</button>
        </div>

        {commonAncestor && (
          <p className="text-[12px] text-gray-500 mb-3">
            Divergence point: <span className="text-gray-300">{nodes[commonAncestor]?.label?.slice(0, 50) || commonAncestor.slice(0, 8)}</span>
          </p>
        )}

        {/* Side by side columns */}
        <div className="flex-1 overflow-y-auto">
          <div className="grid grid-cols-2 gap-4">
            {/* Column headers */}
            <div className="text-[11px] font-medium text-accent-blue uppercase tracking-wider pb-2 border-b border-surface-3">
              Branch A ({pathA.length} steps)
            </div>
            <div className="text-[11px] font-medium text-accent-purple uppercase tracking-wider pb-2 border-b border-surface-3">
              Branch B ({pathB.length} steps)
            </div>

            {/* Rows */}
            {Array.from({ length: maxLen }).map((_, i) => (
              <Fragment key={i}>
                <DiffNodeCell nodeId={pathA[i]} nodes={nodes} isCommon={pathA[i] === commonAncestor} />
                <DiffNodeCell nodeId={pathB[i]} nodes={nodes} isCommon={pathB[i] === commonAncestor} />
              </Fragment>
            ))}
          </div>
        </div>

        {/* Result diff toggle */}
        <div className="mt-3 pt-3 border-t border-surface-3">
          <button
            onClick={() => setShowResults(!showResults)}
            className="text-[11px] text-accent-blue hover:text-blue-400 transition-colors"
          >
            {showResults ? 'Hide result diff' : 'Show result diff'}
          </button>
          {showResults && (
            <div className="grid grid-cols-2 gap-4 mt-3">
              <div className="bg-surface-2/40 rounded-lg p-3 max-h-[200px] overflow-y-auto">
                <pre className="text-[10px] text-gray-400 font-mono whitespace-pre-wrap break-all">
                  {nodes[nodeIdA]?.result_raw?.slice(0, 2000) || 'No result data'}
                </pre>
              </div>
              <div className="bg-surface-2/40 rounded-lg p-3 max-h-[200px] overflow-y-auto">
                <pre className="text-[10px] text-gray-400 font-mono whitespace-pre-wrap break-all">
                  {nodes[nodeIdB]?.result_raw?.slice(0, 2000) || 'No result data'}
                </pre>
              </div>
            </div>
          )}
        </div>

        {/* Summary */}
        <div className="mt-4 pt-4 border-t border-surface-3 flex gap-6 text-xs text-gray-500 flex-wrap">
          <div>
            Branch A score: <span className="font-medium" style={{ color: confidenceColor(Math.max(...pathA.map(id => nodes[id]?.confidence ?? 0))) }}>
              {(Math.max(...pathA.map(id => nodes[id]?.confidence ?? 0)) * 100).toFixed(0)}%
            </span>
          </div>
          <div>
            Branch B score: <span className="font-medium" style={{ color: confidenceColor(Math.max(...pathB.map(id => nodes[id]?.confidence ?? 0))) }}>
              {(Math.max(...pathB.map(id => nodes[id]?.confidence ?? 0)) * 100).toFixed(0)}%
            </span>
          </div>
          <div>
            Branch A time: <span className="font-medium text-gray-300 tabular-nums">
              {(pathA.reduce((sum, id) => sum + (nodes[id]?.duration_ms ?? 0), 0) / 1000).toFixed(1)}s
            </span>
          </div>
          <div>
            Branch B time: <span className="font-medium text-gray-300 tabular-nums">
              {(pathB.reduce((sum, id) => sum + (nodes[id]?.duration_ms ?? 0), 0) / 1000).toFixed(1)}s
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

function DiffNodeCell({ nodeId, nodes, isCommon }: { nodeId?: string; nodes: Record<string, { label: string; confidence: number; action_type: string; result_summary: string; duration_ms: number; status: string }>; isCommon: boolean }) {
  if (!nodeId || !nodes[nodeId]) {
    return <div className="py-2" /> // Empty cell for mismatched lengths
  }
  const node = nodes[nodeId]
  const color = confidenceColor(node.confidence)
  const icon = ACTION_TYPE_ICONS[node.action_type as keyof typeof ACTION_TYPE_ICONS] || '\u2022'

  return (
    <div className={`py-2 px-3 rounded-lg border transition-colors ${isCommon ? 'border-gray-600 bg-surface-2/30' : 'border-white/[0.04] bg-surface-2/50'}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-sm">{icon}</span>
        <span className="text-[12px] text-gray-200 truncate flex-1">{node.label}</span>
        <span className="text-[10px] font-bold tabular-nums" style={{ color }}>
          {(node.confidence * 100).toFixed(0)}%
        </span>
      </div>
      {node.result_summary && (
        <p className="text-[11px] text-gray-400 line-clamp-2 leading-relaxed">{node.result_summary}</p>
      )}
      <div className="flex items-center gap-2 mt-1 text-[10px] text-gray-500">
        {node.duration_ms > 0 && <span className="tabular-nums">{(node.duration_ms / 1000).toFixed(1)}s</span>}
        {isCommon && <span className="text-gray-600">(common ancestor)</span>}
      </div>
    </div>
  )
}

/** Walk from a node to root, returning the path */
function getPathToRoot(nodeId: string, nodes: Record<string, { parent_ids: string[] }>): string[] {
  const path: string[] = []
  const visited = new Set<string>()
  let current = nodeId
  while (current && !visited.has(current)) {
    visited.add(current)
    path.push(current)
    const node = nodes[current]
    if (!node || (node.parent_ids || []).length === 0) break
    current = (node.parent_ids || [])[0]
  }
  return path
}
