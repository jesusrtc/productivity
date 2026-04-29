import { useSessionStore } from '../../store/session'
import { getUncoveredDimensions } from '../../utils/investigation-checklist'

interface InvestigationMiniStatsProps {
  nodes: Record<string, { confidence: number; status: string; tags: string[]; label: string; query: string }>
}

/** Compact investigation stats shown in chat header */
export function InvestigationMiniStats({ nodes }: InvestigationMiniStatsProps) {
  const nodeList = Object.values(nodes)
  const completed = nodeList.filter(n => n.status === 'completed').length
  const failed = nodeList.filter(n => n.status === 'failed').length
  const running = nodeList.filter(n => n.status === 'running').length
  const done = completed + failed
  const maxConf = Math.max(0, ...nodeList.map(n => n.confidence))
  const hasSev = nodeList.some(n => (n.tags || []).some(t => t.startsWith('SEV-')))
  const sevTag = hasSev ? nodeList.flatMap(n => (n.tags || [])).find(t => t.startsWith('SEV-')) : null

  // Maturity score: checklist coverage + depth + confidence diversity
  const uncovered = getUncoveredDimensions(nodes)
  const checklistPct = ((8 - uncovered.length) / 8) * 100
  const maturityLabel = checklistPct >= 75 ? 'Ready' : checklistPct >= 50 ? 'Good' : checklistPct >= 25 ? 'Early' : ''

  return (
    <div className="flex items-center gap-2 text-[10px] text-gray-500">
      <span className="tabular-nums">{done}/{nodeList.length}{failed > 0 ? ` (${failed} failed)` : ''}</span>
      {running > 0 && <span className="text-accent-blue">{running} active</span>}
      {maxConf > 0 && (
        <span className="tabular-nums" style={{ color: `hsl(${120 * (1 - maxConf)}, 75%, 45%)` }}>
          {(maxConf * 100).toFixed(0)}%
        </span>
      )}
      {sevTag && <span className="text-red-400 font-bold">{sevTag}</span>}
      {maturityLabel && completed >= 3 && (
        <span className={`${checklistPct >= 75 ? 'text-green-500' : 'text-gray-500'}`}>{maturityLabel}</span>
      )}
      {(() => {
        const tokens = useSessionStore.getState().tokenUsage
        if (tokens.total > 0) {
          const fmt = tokens.total > 1000 ? `${(tokens.total / 1000).toFixed(1)}k` : String(tokens.total)
          return <span className="text-gray-600 tabular-nums">{fmt}t</span>
        }
        return null
      })()}
    </div>
  )
}
